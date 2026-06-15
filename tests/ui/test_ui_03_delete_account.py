"""
tests/ui/test_ui_03_delete_account.py
──────────────────────────────────────
UI Test: Delete the account that was created by TC-UI-01 (signup test).

TC-UI-03 │ Delete Test Account

This test runs AFTER TC-UI-01 (signup) and TC-UI-02 (login) to clean up
the test account so no leftover data remains on the site.

Flow:
  STEP 1  Open homepage
  STEP 2  Click 'Log in / Sign up' (#lnkUserLoginPop)
  STEP 3  Select phone login (#rbLogPhone)
  STEP 4  Enter country code + phone (signup credentials)
  STEP 5  Enter password (signup credentials)
  STEP 6  Click login (#btnLogin) — logs into the signup test account
  STEP 7  Assert logged in
  STEP 8  Click 'My Account' (#liLogin a)
  STEP 9  Click 'Edit' (#btnEditProfile)
  STEP 10 Click 'Delete Account' (#btnDeleteAcc)
  STEP 11 Click 'Yes, delete it' (#btn-dialog-deleteAcc)
  STEP 12 Assert account deleted (login link reappears)

Run:
    pytest tests/ui/ -v
"""

import os
import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utils.logger import log_section, log_step, log_pass, log_fail


# ── helpers ───────────────────────────────────────────────────────────────────

def _js_click(driver, element):
    driver.execute_script("arguments[0].click();", element)


def _wait_clickable(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _wait_visible(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, value))
    )


def _is_ci() -> bool:
    return os.getenv("CI", "false").lower() == "true"


# ── test ──────────────────────────────────────────────────────────────────────

@pytest.mark.ui
@pytest.mark.delete
class TestUIDeleteAccount:

    def test_delete_signup_account(self, driver, signup_data, base_urls, ctx):
        """
        TC-UI-03 │ Delete Test Account (post-signup cleanup)
        ──────────────────────────────────────────────────────
        Logs in using the credentials from signup_data, navigates to My Account,
        and permanently deletes the account created by TC-UI-01.
        PASS: Site redirects to homepage and the login link reappears.
        """
        log_section("TC-UI-03 │ Delete Test Account")

        ctx.driver   = driver
        url          = base_urls["ui"]
        country_code = "+" + signup_data["country_code"].lstrip("+")
        phone        = signup_data["phone"]
        password     = signup_data["password"]

        # ── Step 1: Open homepage ──────────────────────────────────────────────
        ctx.step(f"Navigating to {url}"); log_step(f"Navigating to {url}")
        driver.get(url)
        driver.maximize_window()
        time.sleep(3)

        src = driver.page_source.lower()
        assert "err_network" not in src and "connection was interrupted" not in src, \
            f"Page failed to load: {url}"
        ctx.passed("Homepage loaded"); log_pass("Homepage loaded")

        # ── Step 2: Click 'Log in / Sign up' ──────────────────────────────────
        ctx.step("Clicking 'Log in / Sign up' (#lnkUserLoginPop)"); log_step("Clicking 'Log in / Sign up' (#lnkUserLoginPop)")
        try:
            login_link = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "lnkUserLoginPop"))
            )
        except TimeoutException:
            if _is_ci():
                pytest.xfail(
                    "Site blocked headless Chrome in CI — #lnkUserLoginPop did not appear."
                )
            raise
        _js_click(driver, login_link)
        time.sleep(2)
        ctx.passed("Login modal opened"); log_pass("Login modal opened")

        # ── Step 3: Select phone login method (#rbLogPhone) ───────────────────
        ctx.step("Selecting phone login method (#rbLogPhone)"); log_step("Selecting phone login method (#rbLogPhone)")
        try:
            phone_radio = _wait_clickable(driver, By.ID, "rbLogPhone")
            _js_click(driver, phone_radio)
            time.sleep(1)
            ctx.passed("Phone login method selected"); log_pass("Phone login method selected")
        except TimeoutException:
            ctx.step("Phone radio not found — assuming phone login is already default")
            log_step("Phone radio not found — assuming phone login is already default")

        # ── Step 4: Enter country code + phone ────────────────────────────────
        ctx.step(f"Entering country code {country_code} and phone {phone}"); log_step(f"Entering country code {country_code} and phone {phone}")
        try:
            cc_input = _wait_visible(driver, By.ID, "textCountryCodeL")
            cc_input.clear()
            cc_input.send_keys(country_code)
            time.sleep(0.5)
        except TimeoutException:
            ctx.step("Country code input #textCountryCodeL not found — skipping")
            log_step("Country code input #textCountryCodeL not found — skipping")

        phone_input = _wait_visible(driver, By.ID, "textPhoneNumberL")
        phone_input.clear()
        phone_input.send_keys(phone)
        time.sleep(0.3)
        ctx.passed(f"Phone entered: {country_code}{phone}"); log_pass(f"Phone entered: {country_code}{phone}")

        # ── Step 5: Enter password ─────────────────────────────────────────────
        ctx.step("Entering password"); log_step("Entering password")
        pwd_input = _wait_visible(driver, By.ID, "textPasswordPage")
        pwd_input.clear()
        pwd_input.send_keys(password)
        time.sleep(0.3)
        ctx.passed("Password entered"); log_pass("Password entered")

        # ── Step 6: Click login ────────────────────────────────────────────────
        ctx.step("Clicking login button (#btnLogin)"); log_step("Clicking login button (#btnLogin)")
        login_btn = _wait_clickable(driver, By.ID, "btnLogin")
        _js_click(driver, login_btn)
        time.sleep(4)
        ctx.passed("Login button clicked"); log_pass("Login button clicked")

        # ── Step 7: Assert logged in ───────────────────────────────────────────
        ctx.step("Asserting login was successful"); log_step("Asserting login was successful")
        logged_in = False
        for by, sel in [
            (By.CSS_SELECTOR, "#liLogin a"),
            (By.XPATH, "//*[contains(text(),'My Account')]"),
            (By.ID, "lnkLogout"),
        ]:
            try:
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((by, sel)))
                logged_in = True
                break
            except TimeoutException:
                continue

        assert logged_in, (
            f"Login failed with signup credentials (phone: {country_code}{phone}). "
            "Verify signup was completed in TC-UI-01 before running this test."
        )
        ctx.passed("Logged in with signup account credentials"); log_pass("Logged in with signup account credentials")

        # ── Step 8: Click 'My Account' (#liLogin a) ───────────────────────────
        ctx.step("Clicking 'My Account' (#liLogin a)"); log_step("Clicking 'My Account' (#liLogin a)")
        my_account_link = _wait_clickable(driver, By.CSS_SELECTOR, "#liLogin a")
        _js_click(driver, my_account_link)
        time.sleep(3)
        ctx.passed("'My Account' page loaded"); log_pass("'My Account' page loaded")

        # ── Step 9: Click 'Edit' (#btnEditProfile) ────────────────────────────
        ctx.step("Clicking 'Edit' profile button (#btnEditProfile)"); log_step("Clicking 'Edit' profile button (#btnEditProfile)")
        edit_btn = _wait_clickable(driver, By.ID, "btnEditProfile")
        _js_click(driver, edit_btn)
        time.sleep(2)
        ctx.passed("'Edit' button clicked — profile edit mode active"); log_pass("'Edit' button clicked — profile edit mode active")

        # ── Step 10: Click 'Delete Account' (#btnDeleteAcc) ───────────────────
        ctx.step("Clicking 'Delete Account' (#btnDeleteAcc)"); log_step("Clicking 'Delete Account' (#btnDeleteAcc)")
        delete_btn = _wait_clickable(driver, By.ID, "btnDeleteAcc")
        _js_click(driver, delete_btn)
        time.sleep(2)
        ctx.passed("'Delete Account' clicked — confirmation dialog should appear"); log_pass("'Delete Account' button clicked — confirmation dialog should appear")

        # ── Step 11: Confirm deletion (#btn-dialog-deleteAcc) ─────────────────
        ctx.step("Confirming deletion (#btn-dialog-deleteAcc)"); log_step("Confirming deletion ('Yes, delete it') (#btn-dialog-deleteAcc)")
        confirm_btn = _wait_clickable(driver, By.ID, "btn-dialog-deleteAcc")
        _js_click(driver, confirm_btn)
        time.sleep(4)
        ctx.passed("'Yes, delete it' clicked — deletion in progress"); log_pass("'Yes, delete it' clicked — deletion in progress")

        # ── Step 12: Assert account deleted ───────────────────────────────────
        ctx.step("Asserting account has been deleted"); log_step("Asserting account has been deleted")

        deleted = False
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "lnkUserLoginPop"))
            )
            deleted = True
        except TimeoutException:
            pass

        if deleted:
            ctx.passed("TC-UI-03 PASSED — Account deleted, site returned to homepage")
            log_pass(
                "TC-UI-03 PASSED — Test account deleted. "
                "Site returned to logged-out homepage. No leftover data on site."
            )
        else:
            ctx.failed("Login link did not reappear — deletion may have failed")
            log_fail(
                "Login link did not reappear after deletion.\n"
                f"    Current URL: {driver.current_url}\n"
                "    Account may not have been deleted — please verify manually."
            )

        assert deleted, (
            "Account deletion could not be confirmed. "
            "Please check the site manually to ensure the account is gone."
        )
