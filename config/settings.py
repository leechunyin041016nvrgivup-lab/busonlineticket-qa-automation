"""
config/settings.py
──────────────────
Central configuration for the BusOnlineTicket QA framework.

Override any setting via environment variables before running pytest:

  BROWSER=firefox  pytest -m ui
  HEADLESS=true    pytest -m ui
  UI_MODE=fast     pytest -m ui

UI_MODE options
───────────────
  visible  (default) — browser window is shown; useful for debugging
  headless            — no browser window; faster, good for CI pipelines
  fast                — visible but with reduced sleep times (smoke runs)

These can also be combined:
  UI_MODE=headless pytest -m ui     # same as HEADLESS=true
"""

import os
import pathlib

# ── URLs ──────────────────────────────────────────────────────────────────────
BASE_URL     = "https://www2.busonlineticket.com"
API_BASE_URL = "https://www2.busonlineticket.com"

# ── Browser ───────────────────────────────────────────────────────────────────
BROWSER  = os.getenv("BROWSER", "chrome").lower()   # chrome | firefox | edge

# UI_MODE drives both headless flag and timing multiplier
_UI_MODE = os.getenv("UI_MODE", "visible").lower()  # visible | headless | fast

# HEADLESS=true env var is still supported as an alias for UI_MODE=headless
HEADLESS = (
    os.getenv("HEADLESS", "false").lower() == "true"
    or _UI_MODE == "headless"
)

# Timing multiplier: 'fast' mode cuts all sleeps by 60 %
SLEEP_MULTIPLIER: float = 0.4 if _UI_MODE == "fast" else 1.0

# ── Timeouts (seconds) ────────────────────────────────────────────────────────
IMPLICIT_WAIT    = 10
EXPLICIT_WAIT    = 15
PAGE_LOAD_TIMEOUT = 30

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = pathlib.Path(__file__).parent.parent
DATA_FILE   = ROOT_DIR / "data" / "test_data.json"
REPORTS_DIR = ROOT_DIR / "reports"