from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.database import get_db
from app.models.privacy import (
    PrivacyHealthResponse,
    PrivacyToken,
    ReidentifyRequest,
    ReidentifyResponse,
    TokenizeRequest,
    TokenizeResponse,
)
from app.services.pii_tokenizer import FALLBACK_PATTERNS, pii_tokenizer

router = APIRouter()


@router.get("/health", response_model=PrivacyHealthResponse)
def privacy_health() -> PrivacyHealthResponse:
    return PrivacyHealthResponse(
        presidio_available=pii_tokenizer.presidio_available,
        gliner_available=pii_tokenizer.gliner_available,
        gliner_model_name=settings.gliner_model_name,
        fallback_recognizers=[entity_type for entity_type, _ in FALLBACK_PATTERNS] + ["PERSON"],
    )


@router.post("/tokenize", response_model=TokenizeResponse)
def tokenize(request: TokenizeRequest, db: Session = Depends(get_db)) -> TokenizeResponse:
    run, anonymized_text = pii_tokenizer.tokenize(
        db=db,
        text=request.text,
        scope=request.scope,
        mode=request.mode,
    )

    tokens = [
        PrivacyToken(
            placeholder=token.placeholder,
            entity_type=token.entity_type,
            original_text=token.original_text if request.include_mapping else None,
            source=token.source,
            start=token.start,
            end=token.end,
            confidence=token.confidence,
        )
        for token in run.tokens
    ]

    return TokenizeResponse(
        run_id=run.run_id,
        mode=run.mode,
        anonymized_text=anonymized_text,
        tokens=tokens,
        expires_at=run.expires_at,
    )


@router.post("/reidentify", response_model=ReidentifyResponse)
def reidentify(request: ReidentifyRequest, db: Session = Depends(get_db)) -> ReidentifyResponse:
    try:
        text, replaced_count = pii_tokenizer.reidentify(
            db=db,
            run_id=request.run_id,
            text=request.text,
            mode=request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ReidentifyResponse(
        run_id=request.run_id,
        mode=request.mode,
        text=text,
        replaced_count=replaced_count,
    )
