"""
utils/report_writer.py
──────────────────────
Generates separate, self-contained HTML reports for UI and API tests
after the full pytest session completes.

Each report shows:
  UI report  — test name, status, step log, failure reason, screenshot
  API report — test name, status, request body, response body, failure reason
"""

from __future__ import annotations
import base64
import html
import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
#  Shared HTML shell
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    padding: 32px 24px;
    min-height: 100vh;
}
h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; color: #fff; }
.subtitle { font-size: 0.85rem; color: #64748b; margin-bottom: 28px; }
.summary-bar {
    display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap;
}
.badge {
    padding: 8px 18px; border-radius: 8px; font-size: 0.82rem;
    font-weight: 600; letter-spacing: .4px;
}
.badge.pass { background: #14532d; color: #86efac; }
.badge.fail { background: #450a0a; color: #fca5a5; }
.badge.total { background: #1e293b; color: #94a3b8; }

.card {
    background: #1e293b;
    border-radius: 12px;
    margin-bottom: 18px;
    overflow: hidden;
    border: 1px solid #334155;
    transition: border-color .2s;
}
.card:hover { border-color: #475569; }
.card-header {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 20px; cursor: pointer;
    user-select: none;
}
.card-header:hover { background: #263347; }
.status-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.status-dot.pass { background: #22c55e; box-shadow: 0 0 6px #22c55e88; }
.status-dot.fail { background: #ef4444; box-shadow: 0 0 6px #ef444488; }
.tc-id   { font-size: 0.72rem; color: #64748b; font-weight: 600; letter-spacing: .5px; }
.tc-name { font-size: 0.95rem; font-weight: 600; color: #e2e8f0; }
.tc-dur  { margin-left: auto; font-size: 0.75rem; color: #475569; }
.chevron { font-size: 0.7rem; color: #475569; margin-left: 8px; transition: transform .2s; }
.card.open .chevron { transform: rotate(90deg); }

.card-body { display: none; padding: 0 20px 20px; border-top: 1px solid #334155; }
.card.open .card-body { display: block; }

.section-label {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 1px;
    color: #64748b; text-transform: uppercase;
    margin: 16px 0 6px;
}
.step-log {
    background: #0f1117; border-radius: 8px;
    padding: 12px 14px; font-size: 0.78rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    line-height: 1.65; overflow-x: auto;
    white-space: pre-wrap; word-break: break-word;
    max-height: 320px; overflow-y: auto;
    border: 1px solid #1e293b;
}
.step-pass { color: #22c55e; }
.step-fail { color: #ef4444; }
.step-info { color: #38bdf8; }
.step-dim  { color: #475569; }

.http-block {
    background: #0f1117; border-radius: 8px;
    padding: 12px 14px; font-size: 0.78rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    line-height: 1.6; overflow-x: auto;
    white-space: pre-wrap; word-break: break-word;
    max-height: 280px; overflow-y: auto;
    border: 1px solid #1e293b;
}
.method  { color: #f59e0b; font-weight: 700; }
.url     { color: #38bdf8; }
.key     { color: #a78bfa; }
.val     { color: #e2e8f0; }
.status-ok  { color: #22c55e; font-weight: 700; }
.status-err { color: #ef4444; font-weight: 700; }

.error-box {
    background: #1c0a0a; border: 1px solid #7f1d1d;
    border-radius: 8px; padding: 12px 14px;
    font-size: 0.8rem; color: #fca5a5;
    white-space: pre-wrap; word-break: break-word;
}
.screenshot-wrap { text-align: center; margin-top: 8px; }
.screenshot-wrap img {
    max-width: 100%; border-radius: 8px;
    border: 1px solid #334155;
    cursor: zoom-in;
}
.screenshot-wrap img:hover { border-color: #64748b; }
"""

_JS = """
document.querySelectorAll('.card-header').forEach(h => {
    h.addEventListener('click', () => {
        h.closest('.card').classList.toggle('open');
    });
});
// Auto-expand failed cards
document.querySelectorAll('.card').forEach(c => {
    if (c.dataset.status === 'fail') c.classList.add('open');
});
"""

def _shell(title: str, body: str, passed: int, failed: int) -> str:
    total = passed + failed
    ts    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="subtitle">Generated: {ts}</p>
<div class="summary-bar">
  <span class="badge total">Total: {total}</span>
  <span class="badge pass">Passed: {passed}</span>
  <span class="badge fail">Failed: {failed}</span>
</div>
{body}
<script>{_JS}</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Card builders
# ─────────────────────────────────────────────────────────────────────────────

def _status_class(passed: bool) -> str:
    return "pass" if passed else "fail"


def _icon(passed: bool) -> str:
    return "✔" if passed else "✘"


def _encode_screenshot(path: str | None) -> str | None:
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


def build_ui_card(
    tc_id: str,
    name: str,
    passed: bool,
    duration: float,
    steps: list[dict],          # [{"status": "pass"|"fail"|"info"|"step", "text": str}]
    error_message: str | None,
    screenshot_path: str | None,
) -> str:
    sc  = _status_class(passed)
    dur = f"{duration:.2f}s"

    # ── step log ─────────────────────────────────────────────────────────────
    step_lines = []
    for s in steps:
        st = s.get("status", "step")
        tx = html.escape(s.get("text", ""))
        if st == "pass":
            step_lines.append(f'<span class="step-pass">  ✔  {tx}</span>')
        elif st == "fail":
            step_lines.append(f'<span class="step-fail">  ✘  {tx}</span>')
        elif st == "info":
            step_lines.append(f'<span class="step-info">  ▷  {tx}</span>')
        else:
            step_lines.append(f'<span class="step-dim">     {tx}</span>')
    step_html = "\n".join(step_lines) or '<span class="step-dim">(no steps recorded)</span>'

    # ── error box ─────────────────────────────────────────────────────────────
    error_html = ""
    if not passed and error_message:
        error_html = f"""
<p class="section-label">Failure Reason</p>
<div class="error-box">{html.escape(error_message)}</div>"""

    # ── screenshot ────────────────────────────────────────────────────────────
    ss_html = ""
    b64 = _encode_screenshot(screenshot_path)
    if b64:
        ss_html = f"""
<p class="section-label">Screenshot at Failure</p>
<div class="screenshot-wrap">
  <img src="data:image/png;base64,{b64}" alt="screenshot" />
</div>"""

    return f"""
<div class="card" data-status="{sc}">
  <div class="card-header">
    <span class="status-dot {sc}"></span>
    <div>
      <div class="tc-id">{html.escape(tc_id)}</div>
      <div class="tc-name">{_icon(passed)} {html.escape(name)}</div>
    </div>
    <span class="tc-dur">{dur}</span>
    <span class="chevron">▶</span>
  </div>
  <div class="card-body">
    <p class="section-label">Step Log</p>
    <div class="step-log">{step_html}</div>
    {error_html}
    {ss_html}
  </div>
</div>"""


def build_api_card(
    tc_id: str,
    name: str,
    passed: bool,
    duration: float,
    method: str,
    url: str,
    request_body: dict | None,
    status_code: int | None,
    response_body,
    error_message: str | None,
) -> str:
    sc  = _status_class(passed)
    dur = f"{duration:.2f}s"
    import json

    # ── request block ─────────────────────────────────────────────────────────
    req_lines = [
        f'<span class="method">{html.escape(method.upper())}</span>  '
        f'<span class="url">{html.escape(url)}</span>',
        "",
    ]
    if request_body:
        for k, v in request_body.items():
            masked = "pass" in k.lower()
            v_str  = "••••••••" if masked else str(v)
            req_lines.append(
                f'<span class="key">{html.escape(str(k))}</span>'
                f'<span class="step-dim"> : </span>'
                f'<span class="val">{html.escape(v_str)}</span>'
            )
    req_html = "\n".join(req_lines)

    # ── response block ────────────────────────────────────────────────────────
    sc_class = "status-ok" if status_code and str(status_code).startswith("2") else "status-err"
    if isinstance(response_body, dict):
        body_str = json.dumps(response_body, indent=2)
    else:
        try:
            body_str = json.dumps(json.loads(str(response_body)), indent=2)
        except Exception:
            body_str = str(response_body)
    # truncate at 60 lines
    lines = body_str.splitlines()
    if len(lines) > 60:
        lines = lines[:60] + ["... (truncated)"]
    body_str = "\n".join(html.escape(l) for l in lines)

    resp_html = (
        f'<span class="{sc_class}">HTTP {status_code}</span>\n\n{body_str}'
        if status_code else
        '<span class="step-fail">(no response)</span>'
    )

    # ── error box ─────────────────────────────────────────────────────────────
    error_html = ""
    if not passed and error_message:
        error_html = f"""
<p class="section-label">Failure Reason</p>
<div class="error-box">{html.escape(error_message)}</div>"""

    return f"""
<div class="card" data-status="{sc}">
  <div class="card-header">
    <span class="status-dot {sc}"></span>
    <div>
      <div class="tc-id">{html.escape(tc_id)}</div>
      <div class="tc-name">{_icon(passed)} {html.escape(name)}</div>
    </div>
    <span class="tc-dur">{dur}</span>
    <span class="chevron">▶</span>
  </div>
  <div class="card-body">
    <p class="section-label">Request</p>
    <div class="http-block">{req_html}</div>
    <p class="section-label">Response</p>
    <div class="http-block">{resp_html}</div>
    {error_html}
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Public write functions
# ─────────────────────────────────────────────────────────────────────────────

def write_ui_report(results: list[dict], output_dir: Path) -> Path:
    """
    results: list of dicts with keys:
      tc_id, name, passed, duration, steps, error_message, screenshot_path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cards   = "".join(build_ui_card(**r) for r in results)
    passed  = sum(1 for r in results if r["passed"])
    failed  = len(results) - passed
    content = _shell("UI Test Report", cards, passed, failed)
    path    = output_dir / "report_ui.html"
    path.write_text(content, encoding="utf-8")
    return path


def write_api_report(results: list[dict], output_dir: Path) -> Path:
    """
    results: list of dicts with keys:
      tc_id, name, passed, duration, method, url,
      request_body, status_code, response_body, error_message
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cards   = "".join(build_api_card(**r) for r in results)
    passed  = sum(1 for r in results if r["passed"])
    failed  = len(results) - passed
    content = _shell("API Test Report", cards, passed, failed)
    path    = output_dir / "report_api.html"
    path.write_text(content, encoding="utf-8")
    return path