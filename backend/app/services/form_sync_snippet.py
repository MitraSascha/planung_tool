"""HTML snippet that wires fillable elements in a generated document to
the form-responses API. Injected just before ``</body>`` by the file
serving endpoint so the on-disk artefact stays static.

Element conventions emitted by the generator:
  - ``data-field-id="<role>.<doc>.<section>.<field>"`` on every fillable
    element. Stable across re-runs so existing answers re-hydrate.
  - ``<input type="checkbox" data-field-id="...">``        → bool
  - ``<input type="text|number|date" data-field-id="...">`` → text/number/date
  - ``<td contenteditable data-field-id="...">``           → text
  - ``<textarea data-field-id="...">``                     → text
"""
from __future__ import annotations

# Vanilla JS — no framework. Inlined as a Python string so the file
# endpoint can serve it without an extra static-files mount.
#
# Auth: the page itself is already served via /api/.../outputs/file/...
# (header- or ?token-authenticated). The script reuses the same token
# from the URL query so its own fetch() calls authenticate without a
# round-trip to localStorage / the SPA.
FORM_SYNC_SNIPPET = """
<style>
  body { padding-top: 56px; }
  .form-sync-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    min-height: 48px;
    padding: 8px 16px;
    font: 700 14px/1.3 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #e8f5ed;
    color: #146835;
    border-bottom: 1px solid rgba(20, 130, 60, .25);
    box-shadow: 0 4px 12px rgba(0, 0, 0, .06);
    transition: background .2s ease, color .2s ease;
  }
  .form-sync-bar.saving {
    background: #eef5fb;
    color: #114c70;
    border-bottom-color: rgba(17, 76, 112, .25);
  }
  .form-sync-bar.error {
    background: #fdecec;
    color: #8a2424;
    border-bottom-color: rgba(138, 36, 36, .35);
  }
  .form-sync-bar .form-sync-retry {
    appearance: none;
    border: 1px solid currentColor;
    background: transparent;
    color: inherit;
    font: inherit;
    font-weight: 800;
    padding: 6px 14px;
    border-radius: 999px;
    cursor: pointer;
  }
  .form-sync-bar .form-sync-retry:hover { background: rgba(0, 0, 0, .06); }
  [data-field-id] { transition: background .25s ease-out, box-shadow .25s ease-out; }
  [data-field-id].form-sync-saving {
    background: rgba(17, 76, 112, .10);
    box-shadow: 0 0 0 2px rgba(17, 76, 112, .25);
  }
  [data-field-id].form-sync-saved {
    background: rgba(20, 130, 60, .12);
    animation: form-sync-pulse .9s ease-out;
  }
  [data-field-id].form-sync-error {
    background: rgba(180, 50, 50, .15);
    box-shadow: 0 0 0 2px rgba(180, 50, 50, .35);
  }
  @keyframes form-sync-pulse {
    0% { box-shadow: 0 0 0 0 rgba(20, 130, 60, .45); }
    100% { box-shadow: 0 0 0 8px rgba(20, 130, 60, 0); }
  }
  @media print {
    body { padding-top: 0; }
    .form-sync-bar { display: none !important; }
  }
</style>
<script>
(function () {
  // ---- URL / context --------------------------------------------------
  // The page lives at /api/projects/<slug>/outputs/file/<doc>?token=<jwt>.
  // Extract slug, document path, and auth token from that URL — same-origin
  // so this works for both header-auth (token absent) and query-auth.
  var path = window.location.pathname;
  var fileMarker = "/outputs/file/";
  var fileIdx = path.indexOf(fileMarker);
  if (fileIdx < 0) {
    return; // Not served from the file endpoint — nothing to do.
  }
  var slugMatch = path.slice(0, fileIdx).match(/\\/projects\\/([^/]+)$/);
  if (!slugMatch) {
    return;
  }
  var slug = slugMatch[1];
  var docPath = path.slice(fileIdx + fileMarker.length);
  var qs = new URLSearchParams(window.location.search);
  var token = qs.get("token");

  // ---- Fetch helpers --------------------------------------------------
  function authedHeaders(extra) {
    var h = Object.assign({}, extra || {});
    if (token) {
      h["Authorization"] = "Bearer " + token;
    }
    return h;
  }

  function fieldUrl() {
    var base = "/api/projects/" + encodeURIComponent(slug)
      + "/form-responses/" + docPath.split("/").map(encodeURIComponent).join("/");
    // Append the same token so any redirect / new tab continues to
    // authenticate without help from the SPA interceptor.
    return token ? base + "?token=" + encodeURIComponent(token) : base;
  }

  // ---- Sticky Status-Bar ----------------------------------------------
  var bar = document.createElement("div");
  bar.className = "form-sync-bar";
  var barText = document.createElement("span");
  bar.appendChild(barText);
  var retryBtn = document.createElement("button");
  retryBtn.type = "button";
  retryBtn.className = "form-sync-retry";
  retryBtn.textContent = "Erneut versuchen";
  retryBtn.style.display = "none";
  bar.appendChild(retryBtn);
  document.body.appendChild(bar);

  var pendingCount = 0;
  var lastSavedAt = null;
  var lastError = null;

  function pad2(n) { return n < 10 ? "0" + n : String(n); }
  function formatTime(d) { return pad2(d.getHours()) + ":" + pad2(d.getMinutes()); }

  function renderBar() {
    if (lastError) {
      bar.className = "form-sync-bar error";
      barText.textContent = "⚠ Konnte nicht speichern";
      retryBtn.style.display = "";
      return;
    }
    if (pendingCount > 0) {
      bar.className = "form-sync-bar saving";
      barText.textContent = "⏳ Wird gespeichert …";
      retryBtn.style.display = "none";
      return;
    }
    bar.className = "form-sync-bar";
    if (lastSavedAt) {
      barText.textContent = "✓ Alle Eingaben gesichert um " + formatTime(lastSavedAt);
    } else {
      barText.textContent = "✓ Bereit — Eingaben werden automatisch gesichert";
    }
    retryBtn.style.display = "none";
  }

  retryBtn.addEventListener("click", function () {
    if (lastError && lastError.el) {
      save(lastError.el, true);
    }
  });

  renderBar();

  // ---- Element <-> value-type bridge ----------------------------------
  function inferValueType(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === "input") {
      var type = (el.type || "text").toLowerCase();
      if (type === "checkbox") return "bool";
      if (type === "number") return "number";
      if (type === "date") return "date";
      return "text";
    }
    if (tag === "textarea") return "text";
    // contenteditable td/div/span — always text.
    return "text";
  }

  function readValue(el, valueType) {
    if (valueType === "bool") return { value_bool: !!el.checked };
    if (valueType === "number") {
      var raw = el.value;
      if (raw === "" || raw === null || raw === undefined) return { value_number: null };
      var n = parseFloat(String(raw).replace(",", "."));
      return { value_number: isFinite(n) ? n : null };
    }
    if (valueType === "date") {
      return { value_date: el.value || null };
    }
    if (el.tagName.toLowerCase() === "input" || el.tagName.toLowerCase() === "textarea") {
      return { value_text: el.value };
    }
    return { value_text: el.innerText };
  }

  function writeValue(el, valueType, row) {
    if (valueType === "bool") {
      el.checked = !!row.value_bool;
      return;
    }
    if (valueType === "number") {
      el.value = row.value_number === null || row.value_number === undefined
        ? "" : String(row.value_number);
      return;
    }
    if (valueType === "date") {
      el.value = row.value_date || "";
      return;
    }
    if (el.tagName.toLowerCase() === "input" || el.tagName.toLowerCase() === "textarea") {
      el.value = row.value_text || "";
    } else {
      el.innerText = row.value_text || "";
    }
  }

  // ---- Saving ---------------------------------------------------------
  var saveTimers = {};
  function flagSaving(el) {
    el.classList.remove("form-sync-saved");
    el.classList.remove("form-sync-error");
    el.classList.add("form-sync-saving");
  }
  function flagSaved(el) {
    el.classList.remove("form-sync-saving");
    el.classList.remove("form-sync-error");
    el.classList.remove("form-sync-saved");
    // re-add on next frame so the CSS animation re-fires.
    requestAnimationFrame(function () { el.classList.add("form-sync-saved"); });
  }
  function flagError(el) {
    el.classList.remove("form-sync-saving");
    el.classList.remove("form-sync-saved");
    el.classList.add("form-sync-error");
  }
  function save(el, immediate) {
    var fieldId = el.getAttribute("data-field-id");
    if (!fieldId) return;
    var valueType = inferValueType(el);
    var values = readValue(el, valueType);
    var payload = Object.assign({ field_id: fieldId, value_type: valueType }, values);

    if (saveTimers[fieldId]) clearTimeout(saveTimers[fieldId]);
    saveTimers[fieldId] = setTimeout(function () {
      flagSaving(el);
      pendingCount += 1;
      renderBar();
      fetch(fieldUrl(), {
        method: "PUT",
        headers: authedHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
        credentials: "same-origin",
      }).then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        pendingCount = Math.max(0, pendingCount - 1);
        lastSavedAt = new Date();
        // Wenn alle anstehenden Speichervorgänge durch sind, Fehlermarker
        // löschen — der User hat es offensichtlich behoben.
        if (pendingCount === 0) {
          lastError = null;
        }
        flagSaved(el);
        renderBar();
      }).catch(function (err) {
        pendingCount = Math.max(0, pendingCount - 1);
        lastError = { el: el, fieldId: fieldId, message: String(err) };
        flagError(el);
        renderBar();
        console.warn("[form-sync] save failed for", fieldId, err);
      });
    }, immediate ? 0 : 350);
  }

  // ---- Bootstrap ------------------------------------------------------
  function attachListeners() {
    var nodes = document.querySelectorAll("[data-field-id]");
    nodes.forEach(function (el) {
      var valueType = inferValueType(el);
      if (valueType === "bool" || el.tagName.toLowerCase() === "select" ||
          (el.tagName.toLowerCase() === "input" &&
           (el.type === "date" || el.type === "checkbox"))) {
        el.addEventListener("change", function () { save(el, true); });
      } else {
        el.addEventListener("input", function () { save(el, false); });
        el.addEventListener("blur", function () { save(el, true); });
      }
    });
  }

  function hydrate() {
    fetch(fieldUrl(), {
      method: "GET",
      headers: authedHeaders(),
      credentials: "same-origin",
    }).then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    }).then(function (data) {
      var rows = (data && data.responses) || [];
      var byField = {};
      rows.forEach(function (r) { byField[r.field_id] = r; });
      document.querySelectorAll("[data-field-id]").forEach(function (el) {
        var fieldId = el.getAttribute("data-field-id");
        var row = byField[fieldId];
        if (!row) return;
        writeValue(el, inferValueType(el), row);
        flagSaved(el);
      });
    }).catch(function (err) {
      console.warn("[form-sync] hydrate failed", err);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { hydrate(); attachListeners(); });
  } else {
    hydrate();
    attachListeners();
  }
})();
</script>
""".strip()


def inject_form_sync_snippet(html: str) -> str:
    """Insert the snippet just before ``</body>``; fall back to appending
    if no body close tag is present (defensive against minified or
    fragment-style HTML)."""
    snippet = FORM_SYNC_SNIPPET
    lowered = html.lower()
    close_idx = lowered.rfind("</body>")
    if close_idx < 0:
        return html + "\n" + snippet
    return html[:close_idx] + snippet + "\n" + html[close_idx:]
