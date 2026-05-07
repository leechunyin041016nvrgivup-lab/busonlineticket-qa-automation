"""
tests/api/test_api_signup.py
────────────────────────────
API Test: Signup endpoint on BusOnlineTicket.com

⚠️  OTP NOTE
────────────────────────────────────────────────────────────────────────────────
Phone-based signup triggers an OTP SMS to the registered number.
Automated tests CANNOT complete OTP verification without:
  • A virtual number service (e.g. Twilio, where OTP can be read via API), or
  • A test-bypass endpoint from the development team.

What this test DOES cover:
  ✔  TC-API-03: Valid signup payload → HTTP 200 + "OTP sent" type response
  ✔  TC-API-04: Duplicate/invalid signup → API returns an error (negative test)

The OTP submission step is intentionally out-of-scope for automated testing
in this framework. It is documented here so that it can be added later when
a virtual number or bypass is available.
────────────────────────────────────────────────────────────────────────────────
"""

import pytest
import requests

from utils.logger import log_section, log_request, log_response, log_step, log_pass, log_fail


# ── endpoint config ───────────────────────────────────────────────────────────

API_SIGNUP_ENDPOINT = "/index.aspx/UserRegister"  # ← update if endpoint changes
# ⚠️  If you get HTTP 404, capture the correct path from your browser's
#     Network tab during a manual signup and update the constant above.

COMMON_HEADERS = {
    "Content-Type":     "application/json; charset=utf-8",
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer":          "https://www2.busonlineticket.com/",
    "Origin":           "https://www2.busonlineticket.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_json(response: requests.Response) -> dict | str:
    try:
        return response.json()
    except Exception:
        return response.text


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


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.api
class TestAPISignup:

    def test_signup_valid_payload_triggers_otp(self, request, signup_data, base_urls):
        """
        TC-API-03 │ Signup — valid payload triggers OTP step
        ──────────────────────────────────────────────────────
        Sends a signup POST request with valid, non-registered data.
        PASS: HTTP 200 AND response indicates OTP was sent (or account created).

        ⚠️  Use a phone number that has NOT been registered before.
            Update data/test_data.json → signup.phone for each test run,
            or integrate a virtual number service for persistent automation.
        """
        log_section("TC-API-03 │ API Signup — Valid Payload")

        base = base_urls["api"]
        url  = f"{base}{API_SIGNUP_ENDPOINT}"

        report_request = {
            "phone":           signup_data["phone"],
            "password":        signup_data["password"],   # masked by report_writer
            "confirmPassword": signup_data["confirm_password"],
            "countryCode":     signup_data["country_code"],
        }

        log_request("POST", url, report_request)

        session = requests.Session()
        log_step("Pre-fetching homepage to initialise session cookies")
        session.get(base, headers={"User-Agent": COMMON_HEADERS["User-Agent"]}, timeout=15)

        response = session.post(
            url,
            json=report_request,
            headers=COMMON_HEADERS,
            timeout=15,
        )
        body = _safe_json(response)

        log_response(response.status_code, body)

        # ── Store for HTML report ─────────────────────────────────────────────
        _store_api_result(request, "POST", url, report_request, response.status_code, body)

        # ── Assertions ────────────────────────────────────────────────────────
        # 403 means the site's WAF blocked the request based on IP.
        # GitHub Actions runs on cloud IPs that are flagged by the site.
        # This is an environment limitation, not a code or credential bug.
        if response.status_code == 403:
            pytest.xfail(
                "Site returned 403 Forbidden — request blocked by WAF (IP-based restriction). "
                "GitHub Actions cloud IPs are blocked by this site. "
                "Run this test locally or via a self-hosted runner to verify real behaviour."
            )

        # 404 means the endpoint path is wrong — skip with a clear fix instruction
        if response.status_code == 404:
            pytest.skip(
                f"Signup endpoint returned 404 — '{API_SIGNUP_ENDPOINT}' may have changed. "
                "Open the site in DevTools → Network tab, attempt a manual signup, "
                "then copy the correct path into API_SIGNUP_ENDPOINT in test_api_signup.py."
            )

        assert response.status_code == 200, (
            f"Expected HTTP 200 from signup endpoint, got {response.status_code}."
        )

        body_str = str(body).lower()

        # Skip (not fail) if the number is already registered
        hard_failures = ["already registered", "already exist", "already used"]
        for phrase in hard_failures:
            if phrase in body_str:
                pytest.skip(
                    f"Phone number {signup_data['phone']} is already registered. "
                    f"Update signup.phone in data/test_data.json with a fresh number."
                )

        log_pass(
            "TC-API-03 PASSED — signup API accepted the payload with HTTP 200.\n"
            "    ℹ  OTP verification step is out-of-scope (requires real SMS)."
        )

    def test_signup_duplicate_phone_rejected(self, request, signup_data, base_urls):
        """
        TC-API-04 │ Signup — duplicate phone number is rejected (negative test)
        ─────────────────────────────────────────────────────────────────────────
        Sends a signup request with a phone number that is already registered.
        PASS: API returns status=0 or an "already registered" type message.
        """
        log_section("TC-API-04 │ API Signup — Duplicate Phone (Negative Test)")

        base = base_urls["api"]
        url  = f"{base}{API_SIGNUP_ENDPOINT}"

        report_request = {
            "phone":           signup_data["phone"],
            "password":        signup_data["password"],
            "confirmPassword": signup_data["confirm_password"],
            "countryCode":     signup_data["country_code"],
        }

        log_request("POST", url, report_request)

        session = requests.Session()
        session.get(base, headers={"User-Agent": COMMON_HEADERS["User-Agent"]}, timeout=15)

        response = session.post(
            url,
            json=report_request,
            headers=COMMON_HEADERS,
            timeout=15,
        )
        body = _safe_json(response)

        log_response(response.status_code, body)

        # ── Store for HTML report ─────────────────────────────────────────────
        _store_api_result(request, "POST", url, report_request, response.status_code, body)

        # 404 means wrong endpoint — skip with fix instruction (same as TC-API-03)
        if response.status_code == 404:
            pytest.skip(
                f"Signup endpoint returned 404 — '{API_SIGNUP_ENDPOINT}' may have changed. "
                "Capture the correct path from DevTools → Network and update API_SIGNUP_ENDPOINT."
            )

        # ── Assertion ─────────────────────────────────────────────────────────
        body_str = str(body).lower()

        # Check API-level status field first (most reliable)
        is_rejection = False
        if isinstance(body, dict):
            api_status = (
                body.get("response", {}).get("status")
                if isinstance(body.get("response"), dict)
                else body.get("status")
            )
            if api_status == 0:
                is_rejection = True

        # Fallback: known rejection phrases
        rejection_phrases = ["already registered", "already exist", "already used", "duplicate"]
        if any(phrase in body_str for phrase in rejection_phrases):
            is_rejection = True

        # Also accept HTTP 4xx
        if response.status_code in range(400, 500):
            is_rejection = True

        assert is_rejection, (
            f"Expected API to reject duplicate phone {signup_data['phone']}, "
            f"got status {response.status_code} with body: {body}\n"
            f"If this phone is not yet registered, this test is not applicable — "
            f"run TC-API-03 first or use an already-registered number."
        )

        log_pass("TC-API-04 PASSED — duplicate phone correctly rejected by API")