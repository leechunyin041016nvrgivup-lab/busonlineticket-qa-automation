"""
conftest.py  (root-level)
─────────────────────────
Shared pytest fixtures and hooks:

  • Browser driver (UI tests)
  • Test-data fixtures (login / signup / base_urls)
  • Step & HTTP capture for HTML reports
  • Screenshot on UI failure
  • Post-session HTML report generation (reports/report_ui.html + report_api.html)
  • Custom terminal summary: "UI: 2/2 passed  |  API: 4/4 passed"
"""

from __future__ import annotations

import time
import pytest
from pathlib import Path

from utils.driver_factory import get_driver
from utils.data_loader    import get_login_data, get_signup_data, get_base_urls
from config.settings      import REPORTS_DIR


# ─────────────────────────────────────────────────────────────────────────────
#  In-session result stores  (populated by fixtures + hooks)
# ─────────────────────────────────────────────────────────────────────────────

_ui_results:  list[dict] = []
_api_results: list[dict] = []


# ─────────────────────────────────────────────────────────────────────────────
#  Step / HTTP capture context  (per-test)
# ─────────────────────────────────────────────────────────────────────────────

class _TestContext:
    """Accumulates steps and HTTP details for one test."""

    def __init__(self):
        self.steps:         list[dict]    = []   # UI
        self.method:        str           = "POST"
        self.url:           str           = ""
        self.request_body:  dict | None   = None
        self.status_code:   int | None    = None
        self.response_body                = None
        self.screenshot_path: str | None  = None
        # Set ctx.driver = driver at the start of each UI test to enable
        # automatic per-step screenshots in the HTML report.
        self.driver                       = None

    def _snap(self) -> str | None:
        """Capture current browser state as a base64 PNG, silently skip if unavailable."""
        if not self.driver:
            return None
        try:
            return self.driver.get_screenshot_as_base64()
        except Exception:
            return None

    # ── UI helpers ─────────────────────────────────────────────────────────────
    def step(self, text: str):
        self.steps.append({"status": "info", "text": text, "screenshot": self._snap()})

    def passed(self, text: str):
        self.steps.append({"status": "pass", "text": text, "screenshot": self._snap()})

    def failed(self, text: str):
        self.steps.append({"status": "fail", "text": text, "screenshot": self._snap()})

    # ── API helpers ────────────────────────────────────────────────────────────
    def record_request(self, method: str, url: str, body: dict | None):
        self.method       = method
        self.url          = url
        self.request_body = body

    def record_response(self, status_code: int, body):
        self.status_code   = status_code
        self.response_body = body


# One context object per running test, keyed by nodeid
_contexts: dict[str, _TestContext] = {}


@pytest.fixture
def ctx(request) -> _TestContext:
    """Per-test context object for step/HTTP capture."""
    c = _TestContext()
    _contexts[request.node.nodeid] = c
    return c


# ─────────────────────────────────────────────────────────────────────────────
#  Browser driver fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def driver():
    """Spin up a browser, yield it, then quit cleanly."""
    d = get_driver()
    yield d
    d.quit()


# ─────────────────────────────────────────────────────────────────────────────
#  Test-data fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def login_data():
    return get_login_data()


@pytest.fixture(scope="session")
def signup_data():
    return get_signup_data()


@pytest.fixture(scope="session")
def base_urls():
    return get_base_urls()


# ─────────────────────────────────────────────────────────────────────────────
#  Screenshot + result capture hook
# ─────────────────────────────────────────────────────────────────────────────

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report  = outcome.get_result()

    if report.when != "call":
        return

    nodeid   = item.nodeid
    markers  = {m.name for m in item.iter_markers()}
    passed   = report.passed
    duration = report.duration or 0.0
    ctx      = _contexts.get(nodeid)

    # ── Error message ─────────────────────────────────────────────────────────
    error_msg: str | None = None
    if not passed and report.longrepr:
        error_msg = str(report.longrepr)

    # ── UI tests ──────────────────────────────────────────────────────────────
    if "ui" in markers:
        # Screenshot on failure
        ss_path: str | None = None
        if not passed:
            driver_fixture = item.funcargs.get("driver")
            if driver_fixture:
                REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                ts      = time.strftime("%Y%m%d_%H%M%S")
                ss_file = str(REPORTS_DIR / f"screenshot_{item.name}_{ts}.png")
                try:
                    driver_fixture.save_screenshot(ss_file)
                    ss_path = ss_file
                except Exception:
                    pass

        if ctx:
            ctx.screenshot_path = ss_path

        _ui_results.append({
            "tc_id":           _tc_id(item),
            "name":            item.name,
            "passed":          passed,
            "duration":        duration,
            "steps":           ctx.steps if ctx else [],
            "error_message":   error_msg,
            "screenshot_path": ss_path,
        })

    # ── API tests ─────────────────────────────────────────────────────────────
    elif "api" in markers:
        # Tests call _store_api_result() which stores directly on item (request.node).
        # Fall back to ctx fixture values if the node attrs aren't set.
        _api_results.append({
            "tc_id":         _tc_id(item),
            "name":          item.name,
            "passed":        passed,
            "duration":      duration,
            "method":        getattr(item, "_api_method",        ctx.method        if ctx else "POST"),
            "url":           getattr(item, "_api_url",           ctx.url           if ctx else ""),
            "request_body":  getattr(item, "_api_request_body",  ctx.request_body  if ctx else None),
            "status_code":   getattr(item, "_api_status_code",   ctx.status_code   if ctx else None),
            "response_body": getattr(item, "_api_response_body", ctx.response_body if ctx else None),
            "error_message": error_msg,
        })


def _tc_id(item) -> str:
    """Extract TC-ID from the docstring first line, e.g. 'TC-UI-01 │ …'."""
    doc = (item.function.__doc__ or "").strip()
    if doc:
        first = doc.splitlines()[0].strip()
        if first.startswith("TC-"):
            return first.split("│")[0].strip() if "│" in first else first[:20]
    return item.name


# ─────────────────────────────────────────────────────────────────────────────
#  Post-session: write HTML reports + terminal summary
# ─────────────────────────────────────────────────────────────────────────────

def pytest_sessionfinish(session, exitstatus):
    from utils.report_writer import write_ui_report, write_api_report
    from utils.excel_writer  import append_results

    out = Path(REPORTS_DIR)

    if _ui_results:
        p = write_ui_report(_ui_results, out)
        print(f"\n  📄 UI  report → {p}")

    if _api_results:
        p = write_api_report(_api_results, out)
        print(f"  📄 API report → {p}")

    if _ui_results or _api_results:
        try:
            append_results(_ui_results, _api_results)
            print(f"  📊 Results appended → data/test_data.xlsx")
        except Exception as e:
            print(f"  ⚠  Excel write skipped: {e}")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    GREEN = "\033[92m"
    RED   = "\033[91m"
    BOLD  = "\033[1m"
    RESET = "\033[0m"

    terminalreporter.write_sep("=", "QA AUTOMATION SUMMARY", bold=True)

    def _summary_line(label, results):
        total  = len(results)
        passed = sum(1 for r in results if r["passed"])
        colour = GREEN if passed == total and total > 0 else RED
        icon   = "✔" if passed == total and total > 0 else "✘"
        terminalreporter.write_line(
            f"  {colour}{icon}{RESET}  {BOLD}{label:<6}{RESET}  "
            f"{colour}{passed}/{total} passed{RESET}"
        )

    if _ui_results:
        _summary_line("UI:", _ui_results)
    if _api_results:
        _summary_line("API:", _api_results)

    terminalreporter.write_sep("=", "")


# ─────────────────────────────────────────────────────────────────────────────
#  Marker + plugin registration
# ─────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "ui:     mark test as a UI (Selenium) test")
    config.addinivalue_line("markers", "api:    mark test as an API (requests) test")
    config.addinivalue_line("markers", "signup:  mark test as requiring OTP (excluded from CI)")
    config.addinivalue_line("markers", "delete:  mark test as account-deletion cleanup (excluded from CI)")
    config.addinivalue_line("markers", "booking: mark test as a booking flow test (excluded from CI)")