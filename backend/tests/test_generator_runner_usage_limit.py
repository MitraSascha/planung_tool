from app.services.generator_runner import detect_usage_limit


# False positives: must NOT match
def test_no_match_csv_value():
    csv_line = (
        "Fläche ;15,46 m²;Außenwand;Wand massive Konstruktion;"
        "1,5;0,1;2,85;3,75;8,39;20;-12;1;32;0429 W;;;;"
    )
    assert detect_usage_limit(csv_line, "") is None


def test_no_match_html_line_number():
    html = "./output/foo.html:429:      <td>Kein Ist-Stand.</td>"
    assert detect_usage_limit(html, "") is None


def test_no_match_unrelated_reset_word():
    text = "Schritt 5: Reset des Pumpenstellwerts auf 0,5 — Doku erstellt"
    assert detect_usage_limit(text, "") is None


# True positives: must match
def test_match_claude_limit():
    msg = "You've hit your limit · resets 10:50pm (UTC)"
    assert detect_usage_limit(msg, "") == msg


def test_match_codex_rate_limit_snake_case():
    msg = "Error: rate_limit_exceeded: too many requests"
    assert detect_usage_limit(msg, "") == msg


def test_match_http_429_with_context():
    msg = "HTTP 429 Too Many Requests"
    assert detect_usage_limit(msg, "") == msg


def test_match_quota_exceeded():
    msg = "Provider returned: quota exceeded"
    assert detect_usage_limit(msg, "") == msg


def test_match_in_stderr_stream():
    stdout = "Files generated successfully"
    stderr = "WARN: usage limit approaching"
    assert detect_usage_limit(stdout, stderr) == "WARN: usage limit approaching"
