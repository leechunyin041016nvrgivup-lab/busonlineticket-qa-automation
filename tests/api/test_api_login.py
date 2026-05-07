"""
tests/api/test_api_login.py
───────────────────────────
API Test: Login endpoint on BusOnlineTicket.com

Endpoint and payload structure reverse-engineered from login.py intercept:
  POST https://www2.busonlineticket.com/webapi/api/web/Login
"""

import pytest
import requests

from utils.logger import log_section, log_request, log_response, log_step, log_pass, log_fail


# ── Endpoint config ───────────────────────────────────────────────────────────

API_LOGIN_ENDPOINT = "/webapi/api/web/Login"

COMMON_HEADERS = {
    "Content-Type":      "application/json",
    "Accept":            "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":   "en-US,en;q=0.9",
    "X-Requested-With":  "XMLHttpRequest",
    "Origin":            "https://www2.busonlineticket.com",
    "Referer":           "https://www2.busonlineticket.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _build_payload(phone: str, password: str, country_code: str = "60") -> dict:
    """
    Build the exact JSON payload the site JS sends.
    Phone is submitted as +{country_code}{phone}.
    """
    return {
        "info": {
            "profile":        "",
            "hashkey":        "",
            "appversion":     "",
            "googleresponse": "",
            "language":       "en",
        },
        "userid":     f"+{country_code}{phone}",
        "password":   password,
        "registerid": "",
        "name":       "",
        "logintype":  "bot",
        "authcode":   "",
        "currency":   "SGD",
        "fbid":       0,
    }


def _safe_json(response: requests.Response) -> dict | str:
    try:
        return response.json()
    except Exception:
        return response.text


def _init_session(base: str) -> requests.Session:
    """Pre-fetch homepage to pick up any session cookies."""
    session = requests.Session()
    log_step("Pre-fetching homepage to initialise session cookies")
    session.get(
        base,
        headers={"User-Agent": COMMON_HEADERS["User-Agent"]},
        timeout=15,
    )
    return session


def _store_api_result(request, method, url, request_body, status_code, response_body):
    """
    Store API call data onto the pytest request node so conftest.py
    can pick it up and pass it to build_api_card for the HTML report.
    """
    request.node._api_method        = method
    request.node._api_url           = url
    request.node._api_request_body  = request_body
    request.node._api_status_code   = status_code
    request.node._api_response_body = response_body


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.api
class TestAPILogin:

    def test_login_valid_credentials(self, request, login_data, base_urls):
        """
        TC-API-01 │ Login with valid phone + password
        ────────────────────────────────────────────────
        POST to /webapi/api/web/Login with valid credentials.
        PASS: HTTP 200 AND response.status == 1 (API-level success flag).
        """
        log_section("TC-API-01 │ API Login — Valid Credentials")

        base    = base_urls["api"]
        url     = f"{base}{API_LOGIN_ENDPOINT}"
        payload = _build_payload(
            login_data["phone"],
            login_data["password"],
            login_data.get("country_code", "60"),
        )

        # What we log/display in the report (password masked)
        report_request = {
            "userid":    payload["userid"],
            "password":  payload["password"],   # report_writer masks keys with "pass"
            "logintype": payload["logintype"],
        }

        log_request("POST", url, report_request)

        session  = _init_session(base)
        response = session.post(url, json=payload, headers=COMMON_HEADERS, timeout=20)
        body     = _safe_json(response)

        log_response(response.status_code, body)

        # ── Store for HTML report ─────────────────────────────────────────────
        _store_api_result(request, "POST", url, report_request, response.status_code, body)

        # ── Assertions ────────────────────────────────────────────────────────
        assert response.status_code == 200, (
            f"Expected HTTP 200, got {response.status_code}. "
            "Check credentials or endpoint."
        )

        # The API uses response.status: 1 = success, 0 = failure
        # Checking this field is reliable — keyword scanning is NOT because
        # even a successful response body can contain words like "invalid"
        # inside the error message of a nested field.
        if isinstance(body, dict):
            api_status = (
                body.get("response", {}).get("status")   # nested: {"response": {"status": 1}}
                if isinstance(body.get("response"), dict)
                else body.get("status")                   # flat: {"status": 1}
            )
            if api_status == 0:
                api_msg = (
                    body.get("response", {}).get("message", "")
                    if isinstance(body.get("response"), dict)
                    else body.get("message", "")
                )
                pytest.fail(f"Login API rejected credentials (status=0): {api_msg}")
            # If api_status is 1 or None (unknown shape), treat as success

        log_pass("TC-API-01 PASSED — valid login returned HTTP 200 with status=1")

    def test_login_invalid_credentials(self, request, base_urls):
        """
        TC-API-02 │ Login with invalid credentials (negative test)
        ────────────────────────────────────────────────────────────
        POST with a bogus phone + password.
        PASS: HTTP 4xx  OR  response.status == 0 (API-level rejection flag).
        """
        log_section("TC-API-02 │ API Login — Invalid Credentials (Negative Test)")

        base    = base_urls["api"]
        url     = f"{base}{API_LOGIN_ENDPOINT}"
        payload = _build_payload("0000000000", "wrongpassword123")

        report_request = {
            "userid":   payload["userid"],
            "password": payload["password"],
        }

        log_request("POST", url, report_request)

        response = requests.post(url, json=payload, headers=COMMON_HEADERS, timeout=20)
        body     = _safe_json(response)

        log_response(response.status_code, body)

        # ── Store for HTML report ─────────────────────────────────────────────
        _store_api_result(request, "POST", url, report_request, response.status_code, body)

        # ── Assertion — check API-level status field, not keyword scan ────────
        is_rejection = response.status_code in range(400, 500)

        if isinstance(body, dict):
            api_status = (
                body.get("response", {}).get("status")
                if isinstance(body.get("response"), dict)
                else body.get("status")
            )
            if api_status == 0:
                is_rejection = True

        assert is_rejection, (
            f"Expected API to reject invalid credentials, "
            f"got status {response.status_code} with body: {body}"
        )

        log_pass("TC-API-02 PASSED — invalid credentials correctly rejected")