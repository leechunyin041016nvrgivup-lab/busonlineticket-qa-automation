"""
utils/logger.py
───────────────
Clean, structured terminal logging for QA automation.
Each section has consistent alignment and width so output
is easy to scan at a glance.
"""

import json

# ── ANSI colour codes ─────────────────────────────────────────────────────────
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"
_DIM    = "\033[2m"
_BLUE   = "\033[94m"
_WHITE  = "\033[97m"
_GREY   = "\033[90m"

_WIDTH = 68   # consistent line width across all log calls


# ── internal helpers ──────────────────────────────────────────────────────────

def _line(char="─", colour=_GREY):
    print(f"{colour}{char * _WIDTH}{_RESET}")


def _kv(label: str, value, colour=_WHITE, mask=False):
    """Print a tidy key = value row, optionally masking the value."""
    label_str = f"{_BOLD}{label:<14}{_RESET}"
    val_str   = ("*" * len(str(value))) if mask else str(value)
    print(f"  {label_str}  {colour}{val_str}{_RESET}")


# ── public API ────────────────────────────────────────────────────────────────

def log_section(title: str):
    """Prints a bold section header — use at the top of every test."""
    print()
    _line("═", colour=_BOLD + _CYAN)
    print(f"{_BOLD}{_CYAN}  {title}{_RESET}")
    _line("═", colour=_BOLD + _CYAN)


def log_step(message: str):
    """A numbered-style action step inside a test."""
    print(f"  {_BLUE}▷{_RESET}  {message}")


def log_pass(message: str):
    """Green tick — step or assertion passed."""
    print(f"  {_GREEN}✔{_RESET}  {message}")


def log_fail(message: str):
    """Red cross — step or assertion failed. Supports multi-line messages."""
    lines = message.splitlines()
    print(f"  {_RED}✘{_RESET}  {_BOLD}{lines[0]}{_RESET}")
    for extra in lines[1:]:
        print(f"     {_RED}{extra}{_RESET}")


def log_info(message: str):
    """Neutral info line — for notes that are neither pass nor fail."""
    print(f"  {_YELLOW}ℹ{_RESET}  {message}")


def log_request(method: str, url: str, payload: dict | None = None):
    """
    Prints outgoing HTTP request details in a tidy block.
    Automatically masks any key whose name contains 'pass'.
    """
    print()
    _line()
    print(f"{_BOLD}{_CYAN}  REQUEST{_RESET}")
    _line()
    _kv("Method",  method.upper(), colour=_CYAN)
    _kv("URL",     url,            colour=_WHITE)
    if payload:
        print(f"  {_BOLD}{'Payload':<14}{_RESET}")
        for k, v in payload.items():
            masked = "pass" in k.lower()
            _kv(f"  └ {k}", v, colour=_GREY, mask=masked)
    _line()


def log_response(status_code: int, body):
    """
    Prints incoming HTTP response in a tidy block.
    Status line is green for 2xx, red otherwise.
    """
    is_ok    = str(status_code).startswith("2")
    colour   = _GREEN if is_ok else _RED
    icon     = "✔" if is_ok else "✘"

    _line()
    print(f"{_BOLD}{colour}  RESPONSE  {icon}{_RESET}")
    _line()
    _kv("Status", status_code, colour=colour)

    # Pretty-print body
    if isinstance(body, dict):
        formatted = json.dumps(body, indent=2)
    else:
        try:
            formatted = json.dumps(json.loads(body), indent=2)
        except Exception:
            formatted = str(body)

    print(f"  {_BOLD}{'Body':<14}{_RESET}")
    for line in formatted.splitlines()[:40]:   # cap at 40 lines to avoid noise
        print(f"    {_GREY}{line}{_RESET}")
    if len(formatted.splitlines()) > 40:
        print(f"    {_GREY}... (truncated){_RESET}")
    _line()
    print()