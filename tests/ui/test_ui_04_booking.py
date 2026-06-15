"""
tests/ui/test_ui_04_booking.py
───────────────────────────────
UI Test: Search trip and select operator — TC-BK-01 to TC-BK-04

Test cases are driven by the "BookingTestData" sheet in data/test_data.xlsx.
Each active row becomes one parametrized test.

Flow (per test case):
  STEP 1  Navigate to homepage
  STEP 2  Select transport tab (Bus / Train / Ferry)
  STEP 3  Enter origin  (autocomplete dropdown)
  STEP 4  Enter destination (autocomplete dropdown)
  STEP 5  Set depart date  (JS datepicker injection)
  STEP 6  Set return date  (JS datepicker injection, if provided)
  STEP 7  Click "Search Trip"
  STEP 8  Wait for trip results
  STEP 9  Find operator in result list
  STEP 10 Click "Select" on the matching trip

Run:
    pytest tests/ui/test_ui_04_booking.py -v
"""

from __future__ import annotations
import os
import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from utils.data_loader import get_booking_data
from utils.logger import log_section, log_step, log_pass, log_fail


# ── Transport field config ────────────────────────────────────────────────────
# Maps transport type (lowercase) → element IDs for each tab's form fields.

_TRANSPORT = {
    "bus": {
        "tab_href":          "#bus",
        "origin_id":         "txtOrigin",
        "dest_id":           "txtDestination",
        "depart_id":         "txtDepartDate",
        "depart_click_id":   "txtDepartDateMobile",
        "return_id":         "txtReturnDate",
        "return_click_id":   "txtReturnDateMobile",
        "search_btn_id":     "btnBusSearchNew",
        "result_from_id":    "divSearchResultFrom",
        "result_to_id":      "divSearchResultTo",
    },
    "train": {
        "tab_href":          "#train",
        "origin_id":         "txtTrainFrom",
        "dest_id":           "txtTrainTo",
        "depart_id":         "txtTrainDepartDate",
        "depart_click_id":   "txtTrainDepartDateMobile",
        "return_id":         "txtTrainReturnDate",
        "return_click_id":   "txtTrainReturnDateMobile",
        "search_btn_id":     "btnTrainSearchNew",
        "result_from_id":    "divSearchResultFromTrain",
        "result_to_id":      "divSearchResultToTrain",
    },
    "ferry": {
        "tab_href":          "#ferry",
        "origin_id":         "txtFerryFrom",
        "dest_id":           "txtFerryTo",
        "depart_id":         "txtFerryDepartDate",
        "depart_click_id":   "txtFerryDepartDateMobile",
        "return_id":         "txtFerryReturnDate",
        "return_click_id":   "txtFerryReturnDateMobile",
        "search_btn_id":     "btnFerrySearchNew",
        "result_from_id":    "divSearchResultFromFerry",
        "result_to_id":      "divSearchResultToFerry",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _type_autocomplete(driver, field_id: str, result_div_id: str, text: str, ctx):
    """
    Type into an autocomplete field and click the first matching suggestion.
    """
    ctx.step(f"Typing '{text}' into #{field_id}"); log_step(f"Typing '{text}' into #{field_id}")
    field = _wait_visible(driver, By.ID, field_id)
    field.clear()
    for ch in text:
        field.send_keys(ch)
        time.sleep(0.08)
    time.sleep(1.5)  # wait for AJAX suggestions

    # Wait for dropdown to appear
    try:
        result_div = WebDriverWait(driver, 8).until(
            EC.visibility_of_element_located((By.ID, result_div_id))
        )
        first_item = result_div.find_element(By.CSS_SELECTOR, "ul.select2-results li")
        item_text = first_item.text.strip()
        _js_click(driver, first_item)
        time.sleep(0.5)
        ctx.passed(f"Selected '{item_text}' from autocomplete"); log_pass(f"Selected '{item_text}' from autocomplete")
    except (TimeoutException, NoSuchElementException):
        # Dropdown didn't appear — value may have been accepted directly
        ctx.step(f"No autocomplete dropdown — proceeding with typed value"); log_step("No autocomplete dropdown — proceeding with typed value")


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _pick_date(driver, field_id: str, date_str: str, ctx, label: str = "date",
               click_id: str | None = None):
    """
    Select a date via jQuery UI datepicker.

    date_str format: DD/MM/YYYY  (e.g. 30/06/2026)
    """
    if not date_str:
        return

    ctx.step(f"Opening datepicker for {label}: {date_str}"); log_step(f"Opening datepicker for {label}: {date_str}")

    try:
        target_day, target_month, target_year = (int(x) for x in date_str.split("/"))
    except ValueError:
        ctx.step(f"Unrecognised date format '{date_str}' — skipping"); log_step(f"Unrecognised date format '{date_str}' — skipping")
        return

    # Open the datepicker. The site uses jQuery.noConflict() so `$` is not
    # available — must use window.jQuery. We try the mobile wrapper first,
    # then desktop input, then jQuery.datepicker._showDatepicker (internal
    # API), then a native MouseEvent click on the mobile div as last resort.
    driver.execute_script("""
        var fieldId  = arguments[0];
        var mobileId = fieldId + 'Mobile';
        var jq       = window.jQuery;

        if (jq) {
            // Try mobile wrapper's hidden datepicker input
            var $m = jq('#' + mobileId).find('.hasDatepicker');
            if ($m.length) { $m.datepicker('show'); return; }

            // Try desktop input
            var $d = jq('#' + fieldId);
            if ($d.hasClass('hasDatepicker')) { $d.datepicker('show'); return; }

            // Try jQuery.datepicker internal method (bypasses element visibility)
            if (jq.datepicker) {
                var el = document.querySelector('#' + mobileId + ' .hasDatepicker')
                      || document.getElementById(fieldId);
                if (el) { jq.datepicker._showDatepicker(el); return; }
            }
        }

        // Fallback: dispatch native click on the mobile div
        var mDiv = document.getElementById(mobileId);
        if (mDiv) {
            mDiv.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return;
        }
        // Last resort: native click on the (possibly hidden) desktop input
        var inp = document.getElementById(fieldId);
        if (inp) inp.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
    """, field_id)
    time.sleep(0.8)

    # Wait for the datepicker widget to appear
    try:
        WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".ui-datepicker"))
        )
    except TimeoutException:
        ctx.failed(f"Datepicker did not open for #{field_id}"); log_fail(f"Datepicker did not open for #{field_id}")
        raise AssertionError(f"Datepicker calendar did not open when clicking #{field_id}")

    # Navigate month-by-month until we reach the target month/year
    for _ in range(36):   # safety cap — up to 3 years of clicks
        curr_month_str, curr_year = _read_datepicker_month_year(driver)
        curr_month_num = _MONTH_NAMES.index(curr_month_str) + 1

        if curr_year == target_year and curr_month_num == target_month:
            break

        if (curr_year, curr_month_num) < (target_year, target_month):
            btn = driver.find_element(By.CSS_SELECTOR, ".ui-datepicker-next")
        else:
            btn = driver.find_element(By.CSS_SELECTOR, ".ui-datepicker-prev")

        _js_click(driver, btn)
        time.sleep(0.3)
    else:
        ctx.failed(f"Could not navigate datepicker to {_MONTH_NAMES[target_month-1]} {target_year}")
        raise AssertionError(f"Datepicker navigation timed out for {date_str}")

    # Click the target day
    day_cells = driver.find_elements(
        By.CSS_SELECTOR,
        ".ui-datepicker-calendar td:not(.ui-datepicker-unselectable):not(.ui-state-disabled) a"
    )
    for cell in day_cells:
        if cell.text.strip() == str(target_day):
            _js_click(driver, cell)
            time.sleep(0.5)
            ctx.passed(f"{label} selected: {date_str}"); log_pass(f"{label} selected: {date_str}")
            return

    ctx.failed(f"Day {target_day} not found in datepicker for #{field_id}")
    raise AssertionError(f"Day {target_day} not clickable in datepicker calendar for #{field_id}")


def _read_datepicker_month_year(driver) -> tuple[str, int]:
    """
    Read the currently displayed month and year from the open datepicker.
    Handles both <span> and <select> elements (jQuery UI supports both).
    """
    from selenium.webdriver.support.ui import Select as SeleniumSelect

    month_el = driver.find_element(By.CSS_SELECTOR, ".ui-datepicker-month")
    year_el  = driver.find_element(By.CSS_SELECTOR, ".ui-datepicker-year")

    if month_el.tag_name.lower() == "select":
        month_str = SeleniumSelect(month_el).first_selected_option.text.strip()
    else:
        month_str = month_el.text.strip()

    if year_el.tag_name.lower() == "select":
        year_str = SeleniumSelect(year_el).first_selected_option.text.strip()
    else:
        year_str = year_el.text.strip()

    return month_str, int(year_str)


def _find_and_click_select(driver, operator_name: str, ctx):
    """
    Scan the trip result list for a card whose operator name matches,
    then click its Select button.
    Returns True on success, False if not found.
    """
    ctx.step(f"Searching trip list for operator: {operator_name}"); log_step(f"Searching trip list for operator: {operator_name}")

    # Wait for at least one trip card to appear
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".trip-item"))
        )
    except TimeoutException:
        ctx.failed("No trip results loaded — .trip-item not found"); log_fail("No trip results loaded")
        return False

    time.sleep(1)  # let all cards render

    trip_items = driver.find_elements(By.CSS_SELECTOR, ".trip-item")
    operator_lower = operator_name.lower()

    for item in trip_items:
        # Check img alt (operator logo alt text) and all spans
        matched = False

        try:
            img_alt = item.find_element(By.TAG_NAME, "img").get_attribute("alt") or ""
            if operator_lower in img_alt.lower():
                matched = True
        except NoSuchElementException:
            pass

        if not matched:
            for span in item.find_elements(By.TAG_NAME, "span"):
                if operator_lower in span.text.strip().lower():
                    matched = True
                    break

        if matched:
            try:
                select_btn = item.find_element(By.CSS_SELECTOR, ".selectseatbutton")
                _js_click(driver, select_btn)
                ctx.passed(f"Found '{operator_name}' — clicked Select"); log_pass(f"Found '{operator_name}' — clicked Select")
                return True
            except NoSuchElementException:
                continue

    ctx.failed(f"Operator '{operator_name}' not found in results"); log_fail(f"Operator '{operator_name}' not found in results")
    return False


# ── Load booking cases from Excel at collection time ─────────────────────────

def _load_cases() -> list[dict]:
    try:
        return get_booking_data()
    except Exception:
        return []


_CASES = _load_cases()
_IDS   = [c.get("TC ID", f"case-{i}") for i, c in enumerate(_CASES)]


# ── Test class ────────────────────────────────────────────────────────────────

@pytest.mark.ui
@pytest.mark.booking
class TestUIBooking:

    @pytest.mark.parametrize("booking", _CASES, ids=_IDS)
    def test_search_and_select_operator(self, driver, ctx, base_urls, booking):
        """
        TC-BK-XX │ Search trip and select operator from results
        ─────────────────────────────────────────────────────────
        Reads route & operator from BookingTestData sheet in test_data.xlsx.
        Steps: homepage → transport tab → origin → destination → dates →
               Search Trip → find operator in list → click Select.
        """
        tc_id     = booking.get("TC ID", "TC-BK-??")
        transport = booking.get("Transport", "bus").strip().lower()
        operator  = booking.get("Operator", "").strip()
        origin    = booking.get("Origin", "").strip()
        dest      = booking.get("Destination", "").strip()
        depart    = booking.get("Depart Date", "").strip()
        ret       = booking.get("Return Date", "").strip()
        url       = base_urls["ui"]

        log_section(f"{tc_id} │ {operator} | {origin} → {dest} ({transport.title()})")
        ctx.driver = driver

        cfg = _TRANSPORT.get(transport)
        assert cfg, f"Unknown transport type '{transport}'. Expected: bus / train / ferry"

        # ── Step 1: Navigate to homepage ──────────────────────────────────────
        ctx.step(f"Navigating to {url}"); log_step(f"Navigating to {url}")
        driver.get(url)
        driver.maximize_window()
        time.sleep(3)

        src = driver.page_source.lower()
        assert "err_network" not in src and "connection was interrupted" not in src, \
            f"Page failed to load: {url}"
        ctx.passed("Homepage loaded"); log_pass("Homepage loaded")

        # ── Step 2: Select transport tab ──────────────────────────────────────
        ctx.step(f"Selecting '{transport.title()}' tab ({cfg['tab_href']})"); log_step(f"Selecting '{transport.title()}' tab")
        try:
            tab_link = _wait_clickable(
                driver, By.CSS_SELECTOR,
                f"a[href='{cfg['tab_href']}']"
            )
            _js_click(driver, tab_link)
            time.sleep(1)
            ctx.passed(f"'{transport.title()}' tab active"); log_pass(f"'{transport.title()}' tab active")
        except TimeoutException:
            if _is_ci():
                pytest.xfail("Site blocked headless Chrome in CI — transport tab not found")
            raise

        # ── Step 3: Enter origin ──────────────────────────────────────────────
        _type_autocomplete(driver, cfg["origin_id"], cfg["result_from_id"], origin, ctx)

        # ── Step 4: Enter destination ─────────────────────────────────────────
        _type_autocomplete(driver, cfg["dest_id"], cfg["result_to_id"], dest, ctx)

        # ── Step 5: Pick depart date from calendar ────────────────────────────
        _pick_date(driver, cfg["depart_id"], depart, ctx, label="Depart Date")

        # ── Step 6: Pick return date from calendar (optional) ─────────────────
        if ret:
            _pick_date(driver, cfg["return_id"], ret, ctx, label="Return Date")
        else:
            ctx.step("No return date — one-way trip"); log_step("No return date — one-way trip")

        # ── Step 7: Click Search Trip ─────────────────────────────────────────
        ctx.step(f"Clicking Search Trip (#{cfg['search_btn_id']})"); log_step(f"Clicking Search Trip (#{cfg['search_btn_id']})")
        search_btn = _wait_clickable(driver, By.ID, cfg["search_btn_id"])
        _js_click(driver, search_btn)
        time.sleep(3)
        ctx.passed("Search Trip clicked — waiting for results"); log_pass("Search Trip clicked — waiting for results")

        # ── Step 8: Wait for results page ─────────────────────────────────────
        ctx.step("Waiting for trip results to load"); log_step("Waiting for trip results to load")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".trip-item"))
            )
            ctx.passed("Trip results loaded"); log_pass("Trip results loaded")
        except TimeoutException:
            ctx.failed("Trip results did not load within 20s")
            log_fail("Trip results did not load within 20s")
            pytest.fail(
                f"No trip results appeared for {origin} → {dest} on {depart}.\n"
                "Check that the route exists and the date is valid."
            )

        # ── Step 9 + 10: Find operator and click Select ───────────────────────
        found = _find_and_click_select(driver, operator, ctx)

        assert found, (
            f"Operator '{operator}' was not found in the trip results for "
            f"{origin} → {dest} on {depart}.\n"
            f"Check that the operator name in BookingTestData sheet matches "
            f"the name displayed on the site exactly (partial match is used)."
        )

        time.sleep(2)
        ctx.passed(f"{tc_id} PASSED — operator found and Select clicked")
        log_pass(f"{tc_id} PASSED — '{operator}' selected successfully")
