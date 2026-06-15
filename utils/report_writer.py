"""
utils/report_writer.py
──────────────────────
Generates separate, self-contained HTML reports for UI and API tests
after the full pytest session completes.

Each report includes:
  • Search box  — filter cards by test case name in real-time
  • Status tabs — All / Passed / Failed
  UI report  — step log, failure reason, screenshot at failure
  API report — full JSON request body, full JSON response body, failure reason
"""

from __future__ import annotations
import base64
import html
import json
import re
import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
#  CSS
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
.subtitle { font-size: 0.85rem; color: #64748b; margin-bottom: 20px; }

.summary-bar {
    display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
    align-items: center;
}
.badge {
    padding: 8px 18px; border-radius: 8px; font-size: 0.82rem;
    font-weight: 600; letter-spacing: .4px;
}
.badge.pass  { background: #14532d; color: #86efac; }
.badge.fail  { background: #450a0a; color: #fca5a5; }
.badge.total { background: #1e293b; color: #94a3b8; }

/* ── Toolbar ── */
.toolbar {
    display: flex; gap: 12px; margin-bottom: 24px;
    flex-wrap: wrap; align-items: center;
}
.search-box {
    flex: 1; min-width: 200px; max-width: 400px;
    background: #1e293b; border: 1px solid #334155;
    border-radius: 8px; padding: 8px 14px;
    color: #e2e8f0; font-size: 0.85rem; outline: none;
}
.search-box::placeholder { color: #475569; }
.search-box:focus { border-color: #3b82f6; }

.filter-btn {
    padding: 7px 16px; border-radius: 8px; border: 1px solid #334155;
    background: #1e293b; color: #94a3b8; font-size: 0.82rem;
    font-weight: 600; cursor: pointer; transition: all .15s;
}
.filter-btn:hover { border-color: #475569; color: #e2e8f0; }
.filter-btn.active        { background: #1e40af; border-color: #3b82f6; color: #bfdbfe; }
.filter-btn.active.passed { background: #14532d; border-color: #22c55e; color: #86efac; }
.filter-btn.active.failed { background: #450a0a; border-color: #ef4444; color: #fca5a5; }

.no-results {
    text-align: center; padding: 48px; color: #475569;
    font-size: 0.9rem; display: none;
}

/* ── Cards ── */
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

/* ── Code blocks ── */
.step-log {
    background: #0f1117; border-radius: 8px;
    padding: 12px 14px; font-size: 0.78rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    line-height: 1.65; overflow-x: auto;
    white-space: pre-wrap; word-break: break-word;
    border: 1px solid #1e293b;
    max-height: 600px; overflow-y: auto;
}
.http-block {
    background: #0f1117; border-radius: 8px;
    padding: 12px 14px; font-size: 0.78rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    line-height: 1.65; overflow-x: auto;
    white-space: pre; word-break: break-word;
    border: 1px solid #1e293b;
    max-height: 380px; overflow-y: auto;
}

/* ── Per-step screenshot ── */
.step-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 2px; }
.step-text { flex: 1; white-space: pre-wrap; word-break: break-word; }
.ss-btn {
    flex-shrink: 0;
    background: none; border: 1px solid #334155;
    border-radius: 4px; color: #64748b;
    font-size: 0.7rem; padding: 1px 6px;
    cursor: pointer; line-height: 1.6;
    transition: all .15s;
}
.ss-btn:hover { border-color: #3b82f6; color: #93c5fd; }
.ss-btn.active { border-color: #3b82f6; color: #93c5fd; background: #1e3a5f22; }
.step-ss {
    display: none;
    margin: 6px 0 10px 28px;
}
.step-ss img {
    max-width: 100%; border-radius: 6px;
    border: 1px solid #334155; cursor: zoom-in;
    transition: border-color .15s;
}
.step-ss img:hover { border-color: #64748b; }

.step-pass { color: #22c55e; }
.step-fail { color: #ef4444; }
.step-info { color: #38bdf8; }
.step-dim  { color: #475569; }

/* JSON syntax highlighting */
.j-key    { color: #7dd3fc; }
.j-str    { color: #86efac; }
.j-num    { color: #fde68a; }
.j-bool   { color: #f9a8d4; }
.j-null   { color: #94a3b8; }
.j-punct  { color: #64748b; }

.http-method { color: #f59e0b; font-weight: 700; }
.http-url    { color: #38bdf8; }
.http-status-ok  { color: #22c55e; font-weight: 700; }
.http-status-err { color: #ef4444; font-weight: 700; }
.http-masked { color: #f97316; font-style: italic; }

.error-box {
    background: #1c0a0a; border: 1px solid #7f1d1d;
    border-radius: 8px; padding: 12px 14px;
    font-size: 0.8rem; color: #fca5a5;
    white-space: pre-wrap; word-break: break-word;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
}
.screenshot-wrap { text-align: center; margin-top: 8px; }
.screenshot-wrap img {
    max-width: 100%; border-radius: 8px;
    border: 1px solid #334155; cursor: zoom-in;
}
.screenshot-wrap img:hover { border-color: #64748b; }
"""


# ─────────────────────────────────────────────────────────────────────────────
#  JavaScript  (search + filter + expand/collapse)
# ─────────────────────────────────────────────────────────────────────────────

_JS = """
(function () {
  // collapse / expand
  document.querySelectorAll('.card-header').forEach(h => {
    h.addEventListener('click', () => h.closest('.card').classList.toggle('open'));
  });

  // auto-expand failed
  document.querySelectorAll('.card[data-status="fail"]').forEach(c => c.classList.add('open'));

  // search + filter
  var searchEl = document.getElementById('search');
  var filterBtns = document.querySelectorAll('.filter-btn');
  var noResults  = document.getElementById('no-results');

  function applyFilters() {
    var query  = searchEl ? searchEl.value.trim().toLowerCase() : '';
    var active = document.querySelector('.filter-btn.active');
    var status = active ? active.dataset.filter : 'all';

    var cards = document.querySelectorAll('.card');
    var visible = 0;

    cards.forEach(function(card) {
      var name      = (card.dataset.name || '').toLowerCase();
      var tcid      = (card.dataset.tcid || '').toLowerCase();
      var cardSt    = card.dataset.status;

      var matchSearch = !query || name.includes(query) || tcid.includes(query);
      var matchStatus = status === 'all' || cardSt === status;

      if (matchSearch && matchStatus) {
        card.style.display = '';
        visible++;
      } else {
        card.style.display = 'none';
      }
    });

    if (noResults) noResults.style.display = (visible === 0) ? 'block' : 'none';
  }

  if (searchEl) searchEl.addEventListener('input', applyFilters);

  filterBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      filterBtns.forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
      applyFilters();
    });
  });
})();

// Per-step screenshot toggle
function toggleStepSS(btn) {
  var ssDiv = btn.parentElement.nextElementSibling;
  if (!ssDiv || !ssDiv.classList.contains('step-ss')) return;
  var isOpen = ssDiv.style.display === 'block';
  ssDiv.style.display = isOpen ? 'none' : 'block';
  btn.classList.toggle('active', !isOpen);
  btn.textContent = isOpen ? '📷' : '✕';
}
"""


# ─────────────────────────────────────────────────────────────────────────────
#  HTML shell
# ─────────────────────────────────────────────────────────────────────────────

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
<div class="toolbar">
  <input id="search" class="search-box" type="text" placeholder="Search by test case name or ID…" />
  <button class="filter-btn active" data-filter="all">All</button>
  <button class="filter-btn passed" data-filter="pass">Passed</button>
  <button class="filter-btn failed" data-filter="fail">Failed</button>
</div>
{body}
<p class="no-results" id="no-results">No test cases match your search / filter.</p>
<script>{_JS}</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  JSON syntax highlighting
# ─────────────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r'("(?:[^"\\]|\\.)*")\s*:'           # key
    r'|("(?:[^"\\]|\\.)*")'              # string value
    r'|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'  # number
    r'|(true|false)'                     # boolean
    r'|(null)'                           # null
    r'|([{}\[\],:])'                     # punctuation
)

_MASK_KEYS = {"password", "pass", "passwd", "confirmpassword", "secret", "token"}


def _highlight_json(obj, mask_keys: set[str] | None = None) -> str:
    """Return syntax-highlighted HTML for a JSON object (or raw string)."""
    if isinstance(obj, (dict, list)):
        raw = json.dumps(obj, indent=2, ensure_ascii=False)
    else:
        try:
            raw = json.dumps(json.loads(str(obj)), indent=2, ensure_ascii=False)
        except Exception:
            return html.escape(str(obj))

    if mask_keys is None:
        mask_keys = _MASK_KEYS

    out: list[str] = []
    last = 0
    lines = raw.split("\n")
    result_lines: list[str] = []

    for line in lines:
        highlighted = _highlight_line(line, mask_keys)
        result_lines.append(highlighted)

    return "\n".join(result_lines)


def _highlight_line(line: str, mask_keys: set[str]) -> str:
    out: list[str] = []
    pos = 0
    # Check if this line defines a password key → mask the value on next key match
    # We track whether the previous key was a sensitive one
    _is_after_sensitive_key = [False]

    for m in _TOKEN_RE.finditer(line):
        # literal text before this token
        if m.start() > pos:
            out.append(html.escape(line[pos:m.start()]))
        pos = m.end()

        key_match, str_match, num_match, bool_match, null_match, punct_match = m.groups()

        if key_match:
            inner = key_match[1:-1].lower()
            _is_after_sensitive_key[0] = any(k in inner for k in mask_keys)
            out.append(f'<span class="j-key">{html.escape(key_match)}</span>')
        elif str_match:
            if _is_after_sensitive_key[0]:
                out.append('<span class="http-masked">"••••••••"</span>')
                _is_after_sensitive_key[0] = False
            else:
                out.append(f'<span class="j-str">{html.escape(str_match)}</span>')
        elif num_match:
            out.append(f'<span class="j-num">{html.escape(num_match)}</span>')
        elif bool_match:
            out.append(f'<span class="j-bool">{html.escape(bool_match)}</span>')
        elif null_match:
            out.append(f'<span class="j-null">null</span>')
        elif punct_match:
            out.append(f'<span class="j-punct">{html.escape(punct_match)}</span>')

    if pos < len(line):
        out.append(html.escape(line[pos:]))

    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
#  Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _status_class(passed: bool) -> str:
    return "pass" if passed else "fail"


def _encode_screenshot(path: str | None) -> str | None:
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Card builders
# ─────────────────────────────────────────────────────────────────────────────

def build_ui_card(
    tc_id: str,
    name: str,
    passed: bool,
    duration: float,
    steps: list[dict],
    error_message: str | None,
    screenshot_path: str | None,
) -> str:
    sc  = _status_class(passed)
    dur = f"{duration:.2f}s"
    icon = "✔" if passed else "✘"

    step_parts = []
    for s in steps:
        st  = s.get("status", "step")
        tx  = html.escape(s.get("text", ""))
        b64 = s.get("screenshot")

        if st == "pass":
            label = f'<span class="step-pass">  ✔  {tx}</span>'
        elif st == "fail":
            label = f'<span class="step-fail">  ✘  {tx}</span>'
        elif st == "info":
            label = f'<span class="step-info">  ▷  {tx}</span>'
        else:
            label = f'<span class="step-dim">     {tx}</span>'

        if b64:
            row = (
                f'<div class="step-row">'
                f'<span class="step-text">{label}</span>'
                f'<button class="ss-btn" onclick="toggleStepSS(this)" title="Toggle screenshot">📷</button>'
                f'</div>'
                f'<div class="step-ss"><img src="data:image/png;base64,{b64}" alt="step screenshot"/></div>'
            )
        else:
            row = f'<div class="step-row"><span class="step-text">{label}</span></div>'

        step_parts.append(row)

    step_html = "\n".join(step_parts) or '<span class="step-dim">(no steps recorded)</span>'

    error_html = ""
    if not passed and error_message:
        error_html = f"""
<p class="section-label">Failure Reason</p>
<div class="error-box">{html.escape(error_message)}</div>"""

    ss_html = ""
    b64 = _encode_screenshot(screenshot_path)
    if b64:
        ss_html = f"""
<p class="section-label">Screenshot at Failure</p>
<div class="screenshot-wrap">
  <img src="data:image/png;base64,{b64}" alt="screenshot" />
</div>"""

    return f"""
<div class="card" data-status="{sc}" data-name="{html.escape(name.lower())}" data-tcid="{html.escape(tc_id.lower())}">
  <div class="card-header">
    <span class="status-dot {sc}"></span>
    <div>
      <div class="tc-id">{html.escape(tc_id)}</div>
      <div class="tc-name">{icon} {html.escape(name)}</div>
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
    sc   = _status_class(passed)
    dur  = f"{duration:.2f}s"
    icon = "✔" if passed else "✘"

    # ── Request block ─────────────────────────────────────────────────────────
    method_html = f'<span class="http-method">{html.escape(method.upper())}</span>'
    url_html    = f'<span class="http-url">{html.escape(url)}</span>'

    if request_body:
        body_highlighted = _highlight_json(request_body)
        req_content = f"{method_html}  {url_html}\n\n{body_highlighted}"
    else:
        req_content = f"{method_html}  {url_html}\n\n<span class=\"step-dim\">(no request body)</span>"

    # ── Response block ────────────────────────────────────────────────────────
    if status_code:
        ok = str(status_code).startswith("2")
        sc_cls  = "http-status-ok" if ok else "http-status-err"
        sc_html = f'<span class="{sc_cls}">HTTP {status_code}</span>'

        if response_body is not None:
            resp_highlighted = _highlight_json(response_body)
            resp_content = f"{sc_html}\n\n{resp_highlighted}"
        else:
            resp_content = f"{sc_html}\n\n<span class=\"step-dim\">(empty body)</span>"
    else:
        resp_content = '<span class="step-fail">(no response received)</span>'

    # ── Error box ─────────────────────────────────────────────────────────────
    error_html = ""
    if not passed and error_message:
        error_html = f"""
<p class="section-label">Failure Reason</p>
<div class="error-box">{html.escape(error_message)}</div>"""

    return f"""
<div class="card" data-status="{sc}" data-name="{html.escape(name.lower())}" data-tcid="{html.escape(tc_id.lower())}">
  <div class="card-header">
    <span class="status-dot {sc}"></span>
    <div>
      <div class="tc-id">{html.escape(tc_id)}</div>
      <div class="tc-name">{icon} {html.escape(name)}</div>
    </div>
    <span class="tc-dur">{dur}</span>
    <span class="chevron">▶</span>
  </div>
  <div class="card-body">
    <p class="section-label">Request</p>
    <div class="http-block">{req_content}</div>
    <p class="section-label">Response</p>
    <div class="http-block">{resp_content}</div>
    {error_html}
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Public write functions
# ─────────────────────────────────────────────────────────────────────────────

def write_ui_report(results: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cards   = "".join(build_ui_card(**r) for r in results)
    passed  = sum(1 for r in results if r["passed"])
    failed  = len(results) - passed
    content = _shell("UI Test Report", cards, passed, failed)
    path    = output_dir / "report_ui.html"
    path.write_text(content, encoding="utf-8")
    return path


def write_api_report(results: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cards   = "".join(build_api_card(**r) for r in results)
    passed  = sum(1 for r in results if r["passed"])
    failed  = len(results) - passed
    content = _shell("API Test Report", cards, passed, failed)
    path    = output_dir / "report_api.html"
    path.write_text(content, encoding="utf-8")
    return path
