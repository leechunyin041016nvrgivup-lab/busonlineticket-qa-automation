"""
utils/data_loader.py
────────────────────
Loads external test data from data/test_data.json.
All tests retrieve credentials and URLs from here —
never hardcode values inside test files.
"""

import json
from config.settings import DATA_FILE


def load_test_data() -> dict:
    """Load and return the full test_data.json as a dictionary."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_login_data() -> dict:
    return load_test_data()["login"]


def get_signup_data() -> dict:
    return load_test_data()["signup"]


def get_base_urls() -> dict:
    return load_test_data()["base_url"]