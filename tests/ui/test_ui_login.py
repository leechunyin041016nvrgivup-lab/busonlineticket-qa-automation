"""
tests/ui/test_ui_login.py
─────────────────────────
UI Test: Login via phone number on BusOnlineTicket.com

TC-UI-01 │ Login via Phone Number
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


def _wait_present(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def _wait_clickable(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _is_ci() -> bool:
    """True when running inside GitHub Actions (or any CI with CI=true)."""
    return os.getenv("CI", "false").lower() == "true"


# ── test ──────────────────────────────────────────────────────────────────────

@pytest.mark.ui
class TestUILogin:

    def test_login_with_phone_number(self, driver, login_data, base_urls, ctx):
        """
        TC-UI-01 │ Login via Phone Number
        ────────────────────────────────────
        Mirrors the working login.py flow step-for-step.
        Uses phone number + password with Malaysia (+60) country code.
        """
        log_section("TC-UI-01 │ Login via Phone Number")

        phone    = login_data["phone"]
        password = login_data["password"]
        url      = base_urls["ui"]

        wait = WebDriverWait(driver, 15)

        # ── Step 1: Load page ────────────────────────────────────────────────
        msg = f"Navigate to {url}"
        log_step(msg); ctx.step(msg)
        driver.get(url)
        driver.maximize_window()
        time.sleep(3)

        src = driver.page_source.lower()
        assert "err_network" not in src and "connection was interrupted" not in src, \
            f"Page failed to load: {url}"
        log_pass("Page loaded"); ctx.passed("Page loaded and window maximised")

        # ── Step 2: Click 'Log in / Sign up' ────────────────────────────────
        msg = "Click 'Log in / Sign up' (#lnkUserLoginPop)"
        log_step(msg); ctx.step(msg)
        try:
            login_link = wait.until(EC.presence_of_element_located((By.ID, "lnkUserLoginPop")))
        except TimeoutException:
            if _is_ci():
                pytest.xfail(
                    "Site blocked headless Chrome in CI — #lnkUserLoginPop did not appear. "
                    "The site detects automated/cloud browsers and withholds page content. "
                    "Run this test locally where a real browser session is available."
                )
            raise
        _js_click(driver, login_link)
        time.sleep(2)
        log_pass("Login modal opened"); ctx.passed("Login modal opened")

        # ── Step 3: Select Phone radio ───────────────────────────────────────
        msg = "Select Phone login method (#rbLogPhone)"
        log_step(msg); ctx.step(msg)
        phone_radio = wait.until(EC.presence_of_element_located((By.ID, "rbLogPhone")))
        _js_click(driver, phone_radio)
        time.sleep(1.5)
        log_pass("Phone login method selected"); ctx.passed("Phone login method selected")

        # ── Step 4: Open country code dropdown ───────────────────────────────
        msg = "Open country code dropdown"
        log_step(msg); ctx.step(msg)
        try:
            dropdown = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".chosen-container .chosen-single"))
            )
        except TimeoutException:
            dropdown = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "[id*='CountryCode'],[id*='countryCode'],.ddcountryCode")
                )
            )
        _js_click(driver, dropdown)
        time.sleep(1)
        log_pass("Country code dropdown opened"); ctx.passed("Country code dropdown opened")

        # ── Step 4b: Select Malaysia (+60) ───────────────────────────────────
        msg = "Select Malaysia (+60)"
        log_step(msg); ctx.step(msg)
        malaysia = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//input[@class='hdnLocFilter'][@value='Malaysia(+60)']/ancestor::li"
        )))
        driver.execute_script("arguments[0].scrollIntoView(true);", malaysia)
        time.sleep(0.3)
        _js_click(driver, malaysia)
        time.sleep(1)
        log_pass("Malaysia (+60) selected"); ctx.passed("Malaysia (+60) selected")

        # ── Step 5: Enter phone number ───────────────────────────────────────
        msg = f"Enter phone number: {phone}"
        log_step(msg); ctx.step(msg)
        phone_input = wait.until(EC.presence_of_element_located((By.ID, "textPhoneNumberL")))
        phone_input.clear()
        phone_input.send_keys(phone)
        time.sleep(0.5)
        log_pass(f"Phone number entered: {phone}"); ctx.passed(f"Phone entered: {phone}")

        # ── Step 6: Enter password ───────────────────────────────────────────
        msg = "Enter password"
        log_step(msg); ctx.step(msg)
        pwd_input = wait.until(EC.presence_of_element_located((By.ID, "textPasswordPage")))
        pwd_input.clear()
        pwd_input.send_keys(password)
        time.sleep(0.5)
        log_pass("Password entered (masked)"); ctx.passed("Password entered (masked)")

        # ── Step 7: Click Log In ─────────────────────────────────────────────
        msg = "Click 'Log in' button (#btnLogin)"
        log_step(msg); ctx.step(msg)
        login_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnLogin")))
        _js_click(driver, login_btn)
        time.sleep(3)
        log_pass("Login button clicked"); ctx.passed("Login button clicked")

        # ── Step 8: Assert login success ─────────────────────────────────────
        msg = "Assert login was successful"
        log_step(msg); ctx.step(msg)

        success_selectors = [
            (By.ID,           "lnkUserAccount"),
            (By.ID,           "lnkLogout"),
            (By.CSS_SELECTOR, ".user-name, .username, .account-name"),
            (By.XPATH,        "//*[contains(@class,'logout') or contains(@id,'logout')]"),
            (By.XPATH,        "//*[contains(text(),'My Account') or "
                              "contains(text(),'Logout') or contains(text(),'Log Out')]"),
        ]

        logged_in = False
        for by, sel in success_selectors:
            try:
                WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, sel)))
                logged_in = True
                break
            except TimeoutException:
                continue

        if logged_in:
            log_pass("Login successful — authenticated user element detected")
            ctx.passed("Login successful — post-login element found")
        else:
            fail_msg = (
                f"Login success element not found.\n"
                f"  Page title : {driver.title}\n"
                f"  Current URL: {driver.current_url}\n"
                f"  Hint: Check credentials in test_data.json or update success selectors."
            )
            log_fail(fail_msg)
            ctx.failed(fail_msg)

        assert logged_in, (
            "Login failed: none of the expected post-login elements were found. "
            "Verify credentials in data/test_data.json and update selectors if needed."
        )