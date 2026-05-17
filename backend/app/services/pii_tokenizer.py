import re
import unicodedata
from importlib.util import find_spec
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.orm_models import AnonymizationRun, AnonymizationToken


@dataclass(frozen=True)
class EntitySpan:
    start: int
    end: int
    entity_type: str
    score: float
    source: str


ENTITY_PRIORITY = {
    "IBAN": 100,
    "EMAIL": 95,
    "PHONE": 90,
    "ADDRESS": 85,
    "PERSON": 80,
    "ORGANIZATION": 70,
    "LOCATION": 60,
}

FALLBACK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+49|0049|0)[\d\s()/.-]{7,}\d")),
    (
        "ADDRESS",
        re.compile(
            r"\b[A-ZÄÖÜ][a-zäöüß.-]+(?:[\s-]+[A-ZÄÖÜ][a-zäöüß.-]+){0,2}\s+"
            r"(?i:strasse|straße|str\.|weg|allee|platz|damm|ring|ufer|gasse)\s+\d+[a-zA-Z]?\b",
        ),
    ),
)

PERSON_PATTERN = re.compile(
    r"\b(?:Herr|Frau)?\s*([A-ZÄÖÜ][a-zäöüß-]{2,}\s+[A-ZÄÖÜ][a-zäöüß-]{2,})\b"
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized.strip()).casefold()


def _type_key(entity_type: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", entity_type.upper()).strip("_") or "PII"


def _placeholder(run_id: str, entity_type: str, number: int) -> str:
    return f"[[PII:{run_id[:8]}:{_type_key(entity_type)}:{number:04d}]]"


class PiiTokenizer:
    def __init__(self) -> None:
        self._presidio_analyzer = None
        self._presidio_loaded = False
        self._gliner_model = None
        self._gliner_loaded = False

    @property
    def presidio_available(self) -> bool:
        return find_spec("presidio_analyzer") is not None

    @property
    def gliner_available(self) -> bool:
        return find_spec("gliner") is not None

    def tokenize(
        self,
        db: Session,
        text: str,
        scope: str | None = None,
        mode: str = "internal",
    ) -> tuple[AnonymizationRun, str]:
        run_id = uuid4().hex
        spans = self._detect(text)
        spans = self._merge_boundary_candidates(text, spans)
        spans = [self._trim_span(text, span) for span in spans]
        spans = self._dedupe_overlaps(spans)

        counters: dict[str, int] = {}
        known_values: dict[tuple[str, str], str] = {}
        replacements: list[tuple[EntitySpan, str, str]] = []

        for span in spans:
            original = text[span.start : span.end]
            key = (_type_key(span.entity_type), _normalize(original))
            placeholder = known_values.get(key)

            if placeholder is None:
                counters[key[0]] = counters.get(key[0], 0) + 1
                placeholder = _placeholder(run_id, key[0], counters[key[0]])
                known_values[key] = placeholder

            replacements.append((span, placeholder, original))

        anonymized_text = self._replace_from_end(text, replacements)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.privacy_mapping_ttl_hours)

        run = AnonymizationRun(
            run_id=run_id,
            scope=scope,
            mode=mode,
            expires_at=expires_at,
        )
        db.add(run)
        db.flush()

        saved_placeholders: set[str] = set()
        for span, placeholder, original in replacements:
            if placeholder in saved_placeholders:
                continue
            saved_placeholders.add(placeholder)
            db.add(
                AnonymizationToken(
                    run_id=run.id,
                    placeholder=placeholder,
                    entity_type=_type_key(span.entity_type),
                    original_text=original,
                    normalized_text=_normalize(original),
                    source=span.source,
                    start=span.start,
                    end=span.end,
                    confidence=span.score,
                )
            )

        db.commit()
        db.refresh(run)
        return run, anonymized_text

    def reidentify(self, db: Session, run_id: str, text: str, mode: str) -> tuple[str, int]:
        run = db.query(AnonymizationRun).filter(AnonymizationRun.run_id == run_id).one_or_none()
        if run is None:
            raise ValueError("Anonymization run not found")

        if mode == "external":
            return text, 0

        tokens = sorted(run.tokens, key=lambda token: len(token.placeholder), reverse=True)
        replaced_count = 0
        result = text

        for token in tokens:
            pattern = re.escape(token.placeholder)
            result, count = re.subn(pattern, token.original_text, result)
            replaced_count += count

        return result, replaced_count

    def reidentify_text_partial(
        self,
        db: Session,
        text: str,
        allowed_original_values: list[str] | set[str] | tuple[str, ...],
    ) -> tuple[str, int]:
        """Reveal only those placeholders whose original maps to a value in
        the whitelist. Used to selectively un-mask a small set of names
        (project staff: responsible, construction manager, foreman) for
        roles that may legitimately know the names but not the rest of the
        customer PII.
        """
        placeholders = set(re.findall(r"\[\[PII:[^\]]+\]\]", text))
        if not placeholders:
            return text, 0

        normalized_whitelist = {
            _normalize(v) for v in allowed_original_values if v and str(v).strip()
        }
        if not normalized_whitelist:
            return text, 0

        rows = (
            db.query(AnonymizationToken)
            .filter(
                AnonymizationToken.placeholder.in_(placeholders),
                AnonymizationToken.normalized_text.in_(normalized_whitelist),
            )
            .all()
        )
        if not rows:
            return text, 0

        rows.sort(key=lambda token: len(token.placeholder), reverse=True)
        replaced_count = 0
        result = text
        for token in rows:
            pattern = re.escape(token.placeholder)
            result, count = re.subn(pattern, token.original_text, result)
            replaced_count += count
        return result, replaced_count

    def reidentify_text(self, db: Session, text: str) -> tuple[str, int]:
        """Re-identify every ``[[PII:...]]`` placeholder found in ``text``.

        Unlike :meth:`reidentify`, this doesn't need an explicit run_id —
        every distinct placeholder string in the input is looked up in
        ``anonymization_tokens`` (the column is indexed) and replaced with
        the original value. Placeholders that have no matching token row
        (e.g. because the run expired and was garbage-collected) are left
        untouched so the output never silently loses information.

        Used by the role-aware output-file endpoint to render internal
        documents in clear text for staff roles while keeping the
        artefacts on disk anonymised.
        """
        placeholders = set(re.findall(r"\[\[PII:[^\]]+\]\]", text))
        if not placeholders:
            return text, 0

        rows = (
            db.query(AnonymizationToken)
            .filter(AnonymizationToken.placeholder.in_(placeholders))
            .all()
        )
        if not rows:
            return text, 0

        # Longest placeholder first so substring overlaps can't matter
        # (placeholders all share the same shape, but the sort is cheap).
        rows.sort(key=lambda token: len(token.placeholder), reverse=True)

        replaced_count = 0
        result = text
        for token in rows:
            pattern = re.escape(token.placeholder)
            result, count = re.subn(pattern, token.original_text, result)
            replaced_count += count
        return result, replaced_count

    def _detect(self, text: str) -> list[EntitySpan]:
        spans: list[EntitySpan] = []
        spans.extend(self._fallback_detect(text))
        spans.extend(self._presidio_detect(text))
        spans.extend(self._gliner_detect(text))
        return spans

    def _fallback_detect(self, text: str) -> list[EntitySpan]:
        spans: list[EntitySpan] = []

        for entity_type, pattern in FALLBACK_PATTERNS:
            for match in pattern.finditer(text):
                spans.append(EntitySpan(match.start(), match.end(), entity_type, 0.72, "fallback"))

        for match in PERSON_PATTERN.finditer(text):
            start, end = match.span(1)
            candidate = text[start:end]
            lowered = candidate.casefold()
            if any(word in lowered for word in ("berlin", "neukölln", "neukoelln", "projekt", "heizung")):
                continue
            spans.append(EntitySpan(start, end, "PERSON", 0.56, "fallback"))

        return spans

    def _presidio_detect(self, text: str) -> list[EntitySpan]:
        self._load_presidio()
        if self._presidio_analyzer is None:
            return []

        try:
            results = self._presidio_analyzer.analyze(text=text, language="de")
        except Exception:
            return []

        return [
            EntitySpan(result.start, result.end, self._map_entity_type(result.entity_type), result.score, "presidio")
            for result in results
        ]

    def _gliner_detect(self, text: str) -> list[EntitySpan]:
        self._load_gliner()
        if self._gliner_model is None:
            return []

        labels = ["person", "address", "phone number", "email", "organization", "location", "iban"]
        try:
            entities = self._gliner_model.predict_entities(text, labels, threshold=0.35)
        except Exception:
            return []

        spans: list[EntitySpan] = []
        for entity in entities:
            entity_type = self._map_entity_type(str(entity.get("label", "")))
            start = int(entity["start"])
            end = int(entity["end"])
            score = float(entity.get("score", 0.5))
            spans.append(EntitySpan(start, end, entity_type, score, "gliner"))
        return spans

    def _load_presidio(self) -> None:
        if self._presidio_loaded:
            return
        self._presidio_loaded = True
        try:
            from presidio_analyzer import AnalyzerEngine

            self._presidio_analyzer = AnalyzerEngine()
        except Exception:
            self._presidio_analyzer = None

    def _load_gliner(self) -> None:
        if self._gliner_loaded:
            return
        self._gliner_loaded = True
        try:
            from gliner import GLiNER

            self._gliner_model = GLiNER.from_pretrained(settings.gliner_model_name)
        except Exception:
            self._gliner_model = None

    def _merge_boundary_candidates(self, text: str, spans: list[EntitySpan]) -> list[EntitySpan]:
        merged = list(spans)
        person_spans = [span for span in spans if _type_key(span.entity_type) == "PERSON"]

        for span in person_spans:
            expanded = self._expand_person_boundary(text, span)
            if expanded != span:
                merged.append(expanded)

        return merged

    def _trim_span(self, text: str, span: EntitySpan) -> EntitySpan:
        start = span.start
        end = span.end

        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1

        if start == span.start and end == span.end:
            return span

        return EntitySpan(start, end, span.entity_type, span.score, span.source)

    def _expand_person_boundary(self, text: str, span: EntitySpan) -> EntitySpan:
        left = span.start
        right = span.end

        while left > 0 and text[left - 1].isspace():
            left -= 1
        while right < len(text) and text[right : right + 1].isspace():
            right += 1

        token_pattern = re.compile(r"[A-ZÄÖÜ][a-zäöüß-]{2,}")
        prefix = text[max(0, left - 40) : left]
        suffix = text[right : min(len(text), right + 40)]

        prefix_matches = list(token_pattern.finditer(prefix))
        if prefix_matches and prefix_matches[-1].end() == len(prefix.rstrip()):
            candidate_start = max(0, left - 40) + prefix_matches[-1].start()
            if left - candidate_start <= 24:
                left = candidate_start

        suffix_match = token_pattern.match(suffix.lstrip())
        if suffix_match:
            whitespace_offset = len(suffix) - len(suffix.lstrip())
            candidate_end = right + whitespace_offset + suffix_match.end()
            if candidate_end - right <= 24:
                right = candidate_end

        if left == span.start and right == span.end:
            return span

        return EntitySpan(left, right, span.entity_type, min(1.0, span.score + 0.08), f"{span.source}+boundary")

    def _dedupe_overlaps(self, spans: list[EntitySpan]) -> list[EntitySpan]:
        candidates = sorted(
            spans,
            key=lambda span: (
                span.start,
                -(span.end - span.start),
                -ENTITY_PRIORITY.get(_type_key(span.entity_type), 0),
                -span.score,
            ),
        )
        selected: list[EntitySpan] = []

        for span in candidates:
            if span.start >= span.end:
                continue
            if any(not (span.end <= existing.start or span.start >= existing.end) for existing in selected):
                continue
            selected.append(span)

        return sorted(selected, key=lambda span: span.start)

    def _replace_from_end(self, text: str, replacements: list[tuple[EntitySpan, str, str]]) -> str:
        result = text
        for span, placeholder, _ in sorted(replacements, key=lambda item: item[0].start, reverse=True):
            result = result[: span.start] + placeholder + result[span.end :]
        return result

    def _map_entity_type(self, entity_type: str) -> str:
        normalized = entity_type.upper().replace(" ", "_")
        mappings = {
            "PERSON": "PERSON",
            "PER": "PERSON",
            "PHONE_NUMBER": "PHONE",
            "PHONE": "PHONE",
            "EMAIL_ADDRESS": "EMAIL",
            "EMAIL": "EMAIL",
            "LOCATION": "LOCATION",
            "LOC": "LOCATION",
            "ADDRESS": "ADDRESS",
            "STREET_ADDRESS": "ADDRESS",
            "ORGANIZATION": "ORGANIZATION",
            "ORG": "ORGANIZATION",
            "IBAN_CODE": "IBAN",
            "IBAN": "IBAN",
        }
        return mappings.get(normalized, normalized)


pii_tokenizer = PiiTokenizer()
