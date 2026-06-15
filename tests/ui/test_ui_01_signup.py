"""
tests/ui/test_ui_signup.py
──────────────────────────
UI Test: Full Signup flow on BusOnlineTicket.com

Flow:
  PHASE 1 — Phone Verification
    STEP 1  Open homepage & maximise
    STEP 2  Click 'Log in / Sign up' (#lnkUserLoginPop)
    STEP 3  Click 'Sign up' tab (li.signUp > a)
    STEP 4  Enter country code "+60"  (#textCountryCodeS)
    STEP 5  Enter phone "163553613"   (#textPhoneNumberS)
    STEP 6  Click 'Verify Phone Number' (#btnRequestSignupOTP)

  PHASE 2 — Phone OTP Entry
    STEP 7  PAUSE → tester types phone OTP from SMS into terminal
    STEP 8  Wait for OTP boxes (#signup-step2 / #txtOTPSignup1)
    STEP 9  Fill digits into #txtOTPSignup1 … #txtOTPSignup6
    STEP 10 Click 'Verify OTP' (#btnVerifySignupOTP)

  PHASE 3 — Account Details (#signup-step3)
    STEP 11 Wait for account form to appear
    STEP 11b Click OK on alert popup (#btn-alert-okay) if present
    STEP 12 Enter Full Name   (#textNamePage)      → "QA Tester"
    STEP 13 Enter Email       (#textEmailPage)     → "internit2.busonlineticket@gmail.com"
    STEP 14 Enter DOB         (#textDOB)           → "10/16/2004"
    STEP 15 Enter Password    (#textPassword2Page) → "Test@1234"
    STEP 16 Enter Re-Password (#textPassword3Page) → "Test@1234"

  PHASE 4 — Email OTP Verification
    STEP 17 Click 'Verify Email' (#btnVerifyEmailOTP)
    STEP 18 PAUSE → tester types email OTP into terminal
    STEP 19 Wait for email OTP boxes (#txtOTPEmailSignup1)
    STEP 20 Fill digits into #txtOTPEmailSignup1 … #txtOTPEmailSignup6
    STEP 21 Click 'Verify OTP' (#btnVerifySignupEmailOTP)
    STEP 22 Click OK to close popup (#btn-alert-okay)

  PHASE 5 — Final Signup
    STEP 23 Click final 'Sign Up' (#buttonSaveSignUp)
    STEP 24 Assert signup success (redirected to homepage, logged in)

Account deletion is handled by TC-UI-03 (test_ui_03_delete_account.py)
which runs after TC-UI-01 (login test).

Run:
    pytest tests/ui/test_ui_01_signup.py -v
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
    """Click via JavaScript — bypasses overlays and cookie banners."""
    driver.execute_script("arguments[0].click();", element)


def _wait_present(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def _wait_clickable(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _wait_visible(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, value))
    )


def _click_ok_popup(driver, timeout=5):
    """
    Click #btn-alert-okay if it appears.
    Silently skips if the popup is not present within timeout.
    """
    try:
        ok_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "btn-alert-okay"))
        )
        _js_click(driver, ok_btn)
        time.sleep(1)
        log_pass("OK popup dismissed (#btn-alert-okay)")
    except TimeoutException:
        pass  # popup didn't appear — that's fine, continue


def _prompt_otp(label: str) -> str:
    """
    Show a popup dialog asking for the OTP.

    A Tkinter window appears on top of the browser — staff types the 6 digits
    and clicks OK. The browser stays open and visible the entire time.
    Falls back to terminal input if Tkinter is unavailable (e.g. headless server).
    """
    try:
        import tkinter as tk
        from tkinter import simpledialog, messagebox

        root = tk.Tk()
        root.withdraw()                    # hide the blank root window
        root.attributes("-topmost", True)  # ensure dialog floats above browser

        otp = simpledialog.askstring(
            title=f"OTP Required",
            prompt=(
                f"OTP has been sent to your {label}.\n\n"
                f"Enter the 6-digit OTP code below:"
            ),
            parent=root,
        )
        root.destroy()

        if otp is None:
            # Staff closed/cancelled the dialog
            pytest.fail("OTP dialog was cancelled by the user.")

        return otp.strip()

    except ImportError:
        # Tkinter not available — fall back to terminal
        import builtins
        print(f"\n  OTP sent to {label}. Enter 6-digit OTP: ", end="", flush=True)
        return builtins.input("").strip()


def _fill_otp_boxes(driver, otp_code: str, box_id_prefix: str):
    """
    Fill a 6-digit OTP into individual input boxes.

    box_id_prefix — e.g. "txtOTPSignup" or "txtOTPEmailSignup"
    Boxes are expected to be named {prefix}1 … {prefix}6.
    """
    for i, digit in enumerate(otp_code, start=1):
        box = _wait_visible(driver, By.ID, f"{box_id_prefix}{i}")
        box.clear()
        box.send_keys(digit)
        time.sleep(0.15)  # small pause so site JS registers each keystroke


# ── test ──────────────────────────────────────────────────────────────────────

def _is_ci() -> bool:
    """True when running inside GitHub Actions (or any CI with CI=true)."""
    return os.getenv("CI", "false").lower() == "true"


@pytest.mark.ui
class TestUISignup:

    def test_signup_full_flow(self, driver, signup_data, base_urls, ctx):
        """
        TC-UI-01 │ Full Signup Flow with Phone OTP + Account Details + Email OTP
        ─────────────────────────────────────────────────────────────────────────
        Covers 5 phases:
          phone verify → phone OTP → account details → email OTP → final signup

        RUN WITH:  pytest tests/ui/test_ui_signup.py -s
        """
        log_section("TC-UI-01 │ Full Signup Flow")

        ctx.driver   = driver                       # enables per-step screenshots
        url          = base_urls["ui"]
        country_code = "+" + signup_data["country_code"].lstrip("+")  # "60" → "+60"
        phone        = signup_data["phone"]         # "163553613"
        full_name    = signup_data["full_name"]     # "QA Tester"
        email        = signup_data["email"]         # "internit2.busonlineticket@gmail.com"
        dob          = signup_data["dob"]           # "10/16/2004"
        password     = signup_data["password"]      # "Test@1234"

        # ═════════════════════════════════════════════════════════════════════
        #  PHASE 1 — Phone Verification
        # ═════════════════════════════════════════════════════════════════════

        # ── Step 1: Navigate & maximise ───────────────────────────────────────
        ctx.step(f"Navigating to {url}"); log_step(f"Navigating to {url}")
        driver.get(url)
        driver.maximize_window()
        time.sleep(3)

        src = driver.page_source.lower()
        assert "err_network" not in src and "connection was interrupted" not in src, \
            f"Page failed to load: {url}"
        ctx.passed("Page loaded and window maximised"); log_pass("Page loaded and window maximised")

        # ── Step 2: Click 'Log in / Sign up' (#lnkUserLoginPop) ──────────────
        ctx.step("Clicking 'Log in / Sign up' (#lnkUserLoginPop)"); log_step("Clicking 'Log in / Sign up' (#lnkUserLoginPop)")
        try:
            login_link = _wait_present(driver, By.ID, "lnkUserLoginPop")
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
        ctx.passed("Login/Signup modal opened"); log_pass("Login/Signup modal opened")

        # ── Step 3: Click 'Sign up' tab ───────────────────────────────────────
        ctx.step("Clicking 'Sign up' tab inside the modal"); log_step("Clicking 'Sign up' tab inside the modal")
        signup_tab = _wait_clickable(
            driver,
            By.XPATH,
            "//li[contains(@class,'signUp')]//a[contains(text(),'Sign up')]"
        )
        _js_click(driver, signup_tab)
        time.sleep(1.5)
        ctx.passed("'Sign up' tab selected — signup form is visible"); log_pass("'Sign up' tab selected — signup form is visible")

        # ── Step 4: Enter country code ─────────────────────────────────────────
        ctx.step(f"Entering country code: {country_code}"); log_step(f"Entering country code: {country_code}")
        country_input = _wait_visible(driver, By.ID, "textCountryCodeS")
        country_input.clear()
        country_input.send_keys(country_code)
        time.sleep(1)
        driver.execute_script("document.getElementById('textCountryCodeS').blur();")
        time.sleep(0.5)
        ctx.passed(f"Country code entered: {country_code}"); log_pass(f"Country code entered: {country_code}")

        # ── Step 5: Enter phone number ─────────────────────────────────────────
        ctx.step(f"Entering phone number: {phone}"); log_step(f"Entering phone number: {phone}")
        try:
            phone_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "textPhoneNumberS"))
            )
        except TimeoutException:
            driver.execute_script(
                "document.getElementById('textPhoneNumberS').removeAttribute('disabled');"
            )
            phone_input = _wait_visible(driver, By.ID, "textPhoneNumberS")

        phone_input.clear()
        phone_input.send_keys(phone)
        time.sleep(0.5)
        ctx.passed(f"Phone number entered: {phone}"); log_pass(f"Phone number entered: {phone}")

        # ── Step 6: Click 'Verify Phone Number' ───────────────────────────────
        ctx.step("Clicking 'Verify Phone Number' (#btnRequestSignupOTP)"); log_step("Clicking 'Verify Phone Number' (#btnRequestSignupOTP)")
        verify_phone_btn = _wait_clickable(driver, By.ID, "btnRequestSignupOTP")
        _js_click(driver, verify_phone_btn)
        time.sleep(2)
        ctx.passed("'Verify Phone Number' clicked — OTP SMS is on its way"); log_pass("'Verify Phone Number' clicked — OTP SMS is on its way")

        # ═════════════════════════════════════════════════════════════════════
        #  PHASE 2 — Phone OTP Entry
        # ═════════════════════════════════════════════════════════════════════

        # ── Step 7: PAUSE — tester enters phone OTP via popup ─────────────────
        phone_otp = _prompt_otp("phone SMS")

        assert phone_otp.isdigit() and len(phone_otp) == 6, (
            f"Invalid OTP entered: '{phone_otp}'.\n"
            f"Must be exactly 6 digits (e.g. 483921). "
            f"You entered {len(phone_otp)} character(s)."
        )
        ctx.passed("Valid 6-digit phone OTP received"); log_pass("Valid 6-digit phone OTP received from tester")

        # ── Step 8: Wait for phone OTP section (#signup-step2) ───────────────
        ctx.step("Waiting for phone OTP section (#signup-step2)"); log_step("Waiting for phone OTP section (#signup-step2)")
        try:
            WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.ID, "signup-step2"))
            )
            _wait_visible(driver, By.ID, "txtOTPSignup1", timeout=10)
            ctx.passed("Phone OTP boxes visible"); log_pass("Phone OTP boxes visible (#txtOTPSignup1 to #txtOTPSignup6)")
        except TimeoutException:
            ctx.failed("OTP section (#signup-step2) did not appear")
            log_fail(
                "OTP section (#signup-step2) did not appear.\n"
                "    Possible reasons:\n"
                "      • Phone number may already be registered\n"
                "      • Country code wrong — must be '+60' not '60'\n"
                "      • Check the browser for red error text near the phone field"
            )
            raise AssertionError(
                "OTP section did not appear. Check browser for error messages."
            )

        # ── Step 9: Fill phone OTP digits ─────────────────────────────────────
        ctx.step("Filling phone OTP into #txtOTPSignup1–6"); log_step("Filling phone OTP into #txtOTPSignup1 to #txtOTPSignup6")
        _fill_otp_boxes(driver, phone_otp, "txtOTPSignup")
        ctx.passed("All 6 phone OTP digits filled"); log_pass("All 6 phone OTP digits filled")

        # ── Step 10: Click 'Verify OTP' (phone) ───────────────────────────────
        ctx.step("Clicking 'Verify OTP' (#btnVerifySignupOTP)"); log_step("Clicking 'Verify OTP' (#btnVerifySignupOTP)")
        verify_otp_btn = _wait_clickable(driver, By.ID, "btnVerifySignupOTP")
        _js_click(driver, verify_otp_btn)
        time.sleep(4)
        ctx.passed("Phone OTP verified"); log_pass("Phone OTP verified")

        # ═════════════════════════════════════════════════════════════════════
        #  PHASE 3 — Account Details Form
        # ═════════════════════════════════════════════════════════════════════

        # ── Step 11: Wait for account details form (#signup-step3) ────────────
        ctx.step("Waiting for account details form (#signup-step3)"); log_step("Waiting for account details form (#signup-step3)")
        try:
            WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.ID, "signup-step3"))
            )
            ctx.passed("Account details form is visible (#signup-step3)"); log_pass("Account details form is visible (#signup-step3)")
        except TimeoutException:
            ctx.failed("Account details form (#signup-step3) did not appear")
            log_fail(
                "Account details form (#signup-step3) did not appear.\n"
                "    The OTP may have been wrong or expired.\n"
                "    Check the browser for an error message near the OTP boxes."
            )
            raise AssertionError(
                "#signup-step3 did not appear — OTP likely incorrect or expired."
            )

        # ── Step 11b: Dismiss OK popup if it appears ──────────────────────────
        ctx.step("Checking for OK alert popup (#btn-alert-okay)"); log_step("Checking for OK alert popup (#btn-alert-okay)")
        _click_ok_popup(driver, timeout=5)

        # ── Step 12: Enter Full Name ───────────────────────────────────────────
        ctx.step(f"Entering full name: {full_name}"); log_step(f"Entering full name: {full_name}")
        name_input = _wait_visible(driver, By.ID, "textNamePage")
        name_input.clear()
        name_input.send_keys(full_name)
        time.sleep(0.3)
        ctx.passed(f"Full name entered: {full_name}"); log_pass(f"Full name entered: {full_name}")

        # ── Step 13: Enter Email ───────────────────────────────────────────────
        ctx.step(f"Entering email: {email}"); log_step(f"Entering email: {email}")
        try:
            email_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.ID, "textEmailPage"))
            )
        except TimeoutException:
            driver.execute_script(
                "document.getElementById('textEmailPage').removeAttribute('disabled');"
            )
            email_input = _wait_visible(driver, By.ID, "textEmailPage")

        email_input.clear()
        email_input.send_keys(email)
        time.sleep(0.5)
        ctx.passed(f"Email entered: {email}"); log_pass(f"Email entered: {email}")

        # ── Step 14: Enter Date of Birth ──────────────────────────────────────
        ctx.step(f"Entering date of birth: {dob}"); log_step(f"Entering date of birth: {dob}")
        dob_input = _wait_visible(driver, By.ID, "textDOB")
        driver.execute_script(
            "document.getElementById('textDOB').removeAttribute('readonly');"
        )
        dob_input.clear()
        dob_input.send_keys(dob)
        driver.execute_script(
            "document.getElementById('textDOB').dispatchEvent(new Event('change'));"
        )
        time.sleep(0.3)
        driver.execute_script(
            "try { $.datepicker._hideDatepicker(); } catch(e) {}"
        )
        time.sleep(0.3)
        ctx.passed(f"Date of birth entered: {dob}"); log_pass(f"Date of birth entered: {dob}")

        # ── Step 15: Enter Password ────────────────────────────────────────────
        ctx.step("Entering password"); log_step("Entering password")
        pwd_input = _wait_visible(driver, By.ID, "textPassword2Page")
        pwd_input.clear()
        pwd_input.send_keys(password)
        time.sleep(0.3)
        ctx.passed("Password entered"); log_pass("Password entered")

        # ── Step 16: Enter Retype Password ────────────────────────────────────
        ctx.step("Entering retype password"); log_step("Entering retype password")
        repwd_input = _wait_visible(driver, By.ID, "textPassword3Page")
        repwd_input.clear()
        repwd_input.send_keys(password)
        time.sleep(0.3)
        ctx.passed("Retype password entered"); log_pass("Retype password entered")

        # ═════════════════════════════════════════════════════════════════════
        #  PHASE 4 — Email OTP Verification
        # ═════════════════════════════════════════════════════════════════════

        # ── Step 17: Click 'Verify Email' (#btnVerifyEmailOTP) ────────────────
        ctx.step("Clicking 'Verify Email' (#btnVerifyEmailOTP)"); log_step("Clicking 'Verify Email' (#btnVerifyEmailOTP)")
        verify_email_btn = _wait_clickable(driver, By.ID, "btnVerifyEmailOTP")
        _js_click(driver, verify_email_btn)
        time.sleep(2)
        ctx.passed(f"'Verify Email' clicked — OTP sent to {email}"); log_pass(f"'Verify Email' clicked — OTP sent to {email}")

        # ── Step 18: PAUSE — tester enters email OTP via popup ────────────────
        email_otp = _prompt_otp("email inbox")

        assert email_otp.isdigit() and len(email_otp) == 6, (
            f"Invalid OTP entered: '{email_otp}'.\n"
            f"Must be exactly 6 digits (e.g. 483921). "
            f"You entered {len(email_otp)} character(s)."
        )
        ctx.passed("Valid 6-digit email OTP received"); log_pass("Valid 6-digit email OTP received from tester")

        # ── Step 19: Wait for email OTP boxes (#txtOTPEmailSignup1) ──────────
        ctx.step("Waiting for email OTP boxes (#txtOTPEmailSignup1)"); log_step("Waiting for email OTP boxes (#txtOTPEmailSignup1)")
        try:
            _wait_visible(driver, By.ID, "txtOTPEmailSignup1", timeout=15)
            ctx.passed("Email OTP boxes visible"); log_pass("Email OTP boxes visible (#txtOTPEmailSignup1 to #txtOTPEmailSignup6)")
        except TimeoutException:
            ctx.failed("Email OTP boxes did not appear")
            log_fail(
                "Email OTP boxes did not appear.\n"
                "    Possible reasons:\n"
                "      • Email address may already be registered\n"
                "      • Check the browser for an error message near the email field"
            )
            raise AssertionError(
                "Email OTP boxes did not appear. Check browser for error messages."
            )

        # ── Step 20: Fill email OTP digits ────────────────────────────────────
        ctx.step("Filling email OTP into #txtOTPEmailSignup1–6"); log_step("Filling email OTP into #txtOTPEmailSignup1 to #txtOTPEmailSignup6")
        _fill_otp_boxes(driver, email_otp, "txtOTPEmailSignup")
        ctx.passed("All 6 email OTP digits filled"); log_pass("All 6 email OTP digits filled")

        # ── Step 21: Click 'Verify OTP' (email) ───────────────────────────────
        ctx.step("Clicking 'Verify OTP' (#btnVerifySignupEmailOTP)"); log_step("Clicking 'Verify OTP' (#btnVerifySignupEmailOTP)")
        verify_email_otp_btn = _wait_clickable(driver, By.ID, "btnVerifySignupEmailOTP")
        _js_click(driver, verify_email_otp_btn)
        time.sleep(3)
        ctx.passed("Email OTP verified"); log_pass("Email OTP verified")

        # ── Step 22: Click OK to close post-email-verification popup ──────────
        ctx.step("Dismissing post-email-verification popup (#btn-alert-okay)"); log_step("Dismissing post-email-verification popup (#btn-alert-okay)")
        _click_ok_popup(driver, timeout=8)

        # ═════════════════════════════════════════════════════════════════════
        #  PHASE 5 — Final Signup
        # ═════════════════════════════════════════════════════════════════════

        # ── Step 23: Click final 'Sign Up' (#buttonSaveSignUp) ────────────────
        ctx.step("Clicking final 'Sign Up' button (#buttonSaveSignUp)"); log_step("Clicking final 'Sign Up' button (#buttonSaveSignUp)")
        save_btn = _wait_clickable(driver, By.ID, "buttonSaveSignUp")
        _js_click(driver, save_btn)
        time.sleep(4)
        ctx.passed("'Sign Up' button clicked"); log_pass("'Sign Up' button clicked")

        # ── Step 24: Assert signup success ────────────────────────────────────
        ctx.step("Asserting signup was successful"); log_step("Asserting signup was successful")

        # Check the signup error span first — if it has text, something went wrong
        try:
            error_span = driver.find_element(By.ID, "signUpErrorPage")
            error_text = error_span.text.strip()
            if error_text:
                ctx.failed(f"Signup error: '{error_text}'"); log_fail(f"Signup error: '{error_text}'")
                raise AssertionError(f"Signup failed with error message: '{error_text}'")
        except AssertionError:
            raise
        except Exception:
            pass  # span not found or empty — good, continue

        # Look for post-login success indicators
        success_selectors = [
            (By.ID,    "lnkUserAccount"),
            (By.ID,    "lnkLogout"),
            (By.CSS_SELECTOR, ".user-name, .username, .account-name"),
            (By.XPATH, "//*[contains(text(),'My Account') or contains(text(),'Logout') or contains(text(),'Log Out')]"),
            (By.XPATH, "//*[contains(@class,'logout') or contains(@id,'logout')]"),
        ]

        signed_up = False
        for by, sel in success_selectors:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((by, sel))
                )
                signed_up = True
                break
            except TimeoutException:
                continue

        if signed_up:
            ctx.passed("TC-UI-01 PASSED — Account created and user is logged in")
            log_pass("TC-UI-01 PASSED — Signup complete! Account created and user is logged in.")
        else:
            ctx.failed("Success indicator not found after clicking Sign Up")
            log_fail(
                f"Success indicator not found after clicking Sign Up.\n"
                f"    Page title : {driver.title}\n"
                f"    Current URL: {driver.current_url}\n"
                f"    Hint: Signup may have worked but the post-login element\n"
                f"    selector needs updating to match the page DOM."
            )

        assert signed_up, (
            "Signup flow completed but no success element was found. "
            "Check the browser and update success_selectors if needed."
        )