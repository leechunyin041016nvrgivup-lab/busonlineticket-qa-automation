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
  STEP 5  Set depart date  (datepicker)
  STEP 6  Set return date  (datepicker, if provided)
  STEP 7  Click "Search Trip"
  STEP 8  Wait for trip results
  STEP 9  Find operator in result list (filter via "Operators" modal if absent)
  STEP 10 Click "Select" / "View Trips" on the matching trip
  STEP 10b Seat/ticket selection — Bus/Train: pick `pax_count` seats then
           Proceed; Ferry: choose a time slot then seats or ticket count
  STEP 11 Wait for the passenger-details (manifest) page
  STEP 12 Detect which manifest input fields are VISIBLE (is_displayed)
  STEP 13 Compare visible fields against "expected_fields" in the JSON (if set)
  STEP 14 Auto-fill the manifest from the per-case JSON (lead + N passengers)
  STEP 15 Click "Next" (#btnNext) and verify the booking advances
  STEP 16 Payment page — VERIFY amounts/method only; NEVER submit a payment

Per-case data comes from the "Test Data (JSON)" cell of the BookingTestData
sheet (see utils.data_loader.parse_booking_json). Number of passengers in the
JSON drives the seat/ticket count. The per-field visibility result is recorded
to the HTML report and the "ManifestResults" sheet of data/test_data.xlsx.

NOT YET WIRED (need page HTML): per-passenger meal selection, and precise
payment-page verification (currently a best-effort page-text check).

Run:
    pytest tests/ui/test_ui_04_booking.py -v
"""

from __future__ import annotations
import os
import re
import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select as SeleniumSelect
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
)

from utils.data_loader import (
    get_booking_data, get_manifest_data, parse_booking_json, BOOKING_JSON_COL,
)
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
    """
    Click via JS. A click that triggers navigation can make Chrome's renderer
    go busy and raise "timeout: Timed out receiving message from renderer" even
    though the click DID fire. We swallow that here — every call site follows up
    with an explicit wait that is the real check on whether the action took.
    """
    try:
        driver.execute_script("arguments[0].click();", element)
    except TimeoutException:
        pass


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


def _op_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if t}


def _operator_matches(data_name: str, site_text: str) -> bool:
    """
    Conservative, order-free operator match.

    True when one name's word-set is a subset of the other's (so "Transtar
    Travel Express" matches "Transtar Express", but NOT "Transtar Express Xtras"
    — neither token-set contains the other), OR one name is a substring of the
    other AND the shorter side is at least 5 chars (so a 2-3 letter name like
    "KL" can't substring-match an unrelated price/time/operator string).

    NOTE: deliberately does NOT strip generic words like "Express"/"Travel".
    Doing so collapses "Transtar Travel Express" to just {transtar}, which would
    then ALSO match the sibling brand "Transtar Express Xtras" — the token-set
    subset rule on the FULL words is what keeps siblings distinct.
    """
    a, b = (data_name or "").lower().strip(), (site_text or "").lower().strip()
    if not a or not b:
        return False
    if min(len(a), len(b)) >= 5 and (a in b or b in a):
        return True
    ta, tb = _op_tokens(a), _op_tokens(b)
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


# Spans that are prices, currencies, times or durations — never operator names.
_PRICE_TIME_RE = re.compile(r"(rm|s\$|sgd|myr|usd)\b|\d+\.\d{2}|\d{1,2}:\d{2}", re.I)


def _trip_operator_texts(item) -> list[str]:
    """
    Collect only the operator-name-bearing strings from a trip card: logo img
    `alt` text, plus spans that look like names (skipping price/time/duration
    spans). Prevents a short operator name from matching a price/time span.
    """
    texts: list[str] = []
    try:
        for img in item.find_elements(By.TAG_NAME, "img"):
            alt = (img.get_attribute("alt") or "").strip()
            if alt:
                texts.append(alt)
        for span in item.find_elements(By.TAG_NAME, "span"):
            t = (span.text or "").strip()
            if len(t) < 3 or t.isdigit() or _PRICE_TIME_RE.search(t):
                continue
            texts.append(t)
    except StaleElementReferenceException:
        pass
    return texts


# The Select / View Trips button on every trip card — the ONLY reliable anchor.
# The live www. site renders trip cards as inline-styled <div>s with NO stable
# class (no ".trip-item"), so we locate cards via this button and climb to the
# enclosing card. Waiting on ".trip-item" times out even though cards are shown.
_SELECT_BTN_CSS = ".selectseatbutton"


def _find_trip_cards(driver) -> list:
    """
    Return [(card_element, select_button)] for every trip on the results page.

    Anchors on the Select/View-Trips button (present on every card) and climbs
    up to the nearest ancestor that still contains exactly ONE such button —
    that ancestor is the individual trip card (so its img/span text is just this
    operator's, not the whole list's).
    """
    cards = []
    for btn in driver.find_elements(By.CSS_SELECTOR, _SELECT_BTN_CSS):
        try:
            card = btn
            for _ in range(8):
                parent = card.find_element(By.XPATH, "..")
                # Climbing one level too far would swallow sibling cards; stop
                # as soon as the parent holds more than this one select button.
                if len(parent.find_elements(By.CSS_SELECTOR, _SELECT_BTN_CSS)) > 1:
                    break
                card = parent
            cards.append((card, btn))
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return cards


def _click_trip_select(driver, operator_name: str) -> bool:
    """One pass over the trip list: click Select/View Trips on the first card
    whose logo alt or name text matches the operator. Returns True if clicked."""
    for card, btn in _find_trip_cards(driver):
        try:
            texts = _trip_operator_texts(card)
            if any(_operator_matches(operator_name, t) for t in texts):
                # Scroll the button into view first — some click handlers ignore
                # taps on off-screen elements (matters for "View Trips" on ferry).
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.3)
                except Exception:
                    pass
                _js_click(driver, btn)
                return True
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return False


def _filter_operator(driver, operator_name: str, ctx) -> bool:
    """
    Open the 'Operators' filter modal, tick the checkbox matching the operator,
    then close the modal (ESC) so the trip list re-filters. Returns True if a
    matching operator checkbox was found and ticked.
    """
    ctx.step(f"Operator not in list — opening operator filter for '{operator_name}'")
    log_step("Opening operator filter")

    btn = None
    for b in driver.find_elements(By.CSS_SELECTOR,
                                  "button[data-target*='OperatorFilter'], button[data-toggle='modal']"):
        target = (b.get_attribute("data-target") or "").lower()
        if "operatorfilter" in target or (b.text or "").strip().lower() == "operators":
            btn = b
            break
    if btn is None:
        ctx.step("No operator-filter button found"); log_step("No operator-filter button found")
        return False
    _js_click(driver, btn)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".filter-input-group input[type='checkbox']"))
        )
    except TimeoutException:
        ctx.step("Operator filter modal did not open"); log_step("Operator filter modal did not open")
        return False
    time.sleep(1)

    matched = False
    for grp in driver.find_elements(By.CSS_SELECTOR, ".filter-input-group"):
        try:
            label = grp.find_element(By.TAG_NAME, "label").text.strip()
        except NoSuchElementException:
            continue
        name = re.sub(r"\(\s*\d+\s*\)\s*$", "", label).strip()  # drop trailing "(17)"
        if _operator_matches(operator_name, name):
            try:
                cb = grp.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                if not cb.is_selected():
                    _js_click(driver, cb)
                matched = True
                ctx.passed(f"Filtered to operator: {name}"); log_pass(f"Filtered to operator: {name}")
                break
            except NoSuchElementException:
                continue

    # Close the modal so the (now filtered) list is interactable again.
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.5)
    for c in driver.find_elements(By.CSS_SELECTOR, ".modal .close[data-dismiss='modal']"):
        if c.is_displayed():
            try:
                _js_click(driver, c)
            except Exception:
                pass
            break
    time.sleep(2)  # let the list re-filter
    return matched


def _find_and_click_select(driver, operator_name: str, ctx):
    """
    Find the trip card matching `operator_name` and click its Select / View Trips
    button. If not found, open the operator filter, tick the operator, and retry
    once. Returns True on success.
    """
    ctx.step(f"Searching trip list for operator: {operator_name}"); log_step(f"Searching trip list for operator: {operator_name}")

    try:
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, _SELECT_BTN_CSS))
        )
    except TimeoutException:
        ctx.failed("No trip results loaded — no Select/View-Trips button found")
        log_fail("No trip results loaded")
        return False
    time.sleep(1.5)  # let all cards render

    if _click_trip_select(driver, operator_name):
        ctx.passed(f"Found '{operator_name}' — clicked Select/View Trips")
        log_pass(f"Found '{operator_name}' — clicked Select/View Trips")
        return True

    # Not directly visible — try filtering to it, then retry once.
    if _filter_operator(driver, operator_name, ctx) and _click_trip_select(driver, operator_name):
        ctx.passed(f"Found '{operator_name}' after filtering — clicked Select/View Trips")
        log_pass(f"Found '{operator_name}' after filtering — clicked")
        return True

    ctx.failed(f"Operator '{operator_name}' not found in results"); log_fail(f"Operator '{operator_name}' not found in results")
    return False


# ── Seat / ticket selection (between operator-select and the manifest) ────────

def _manifest_present(driver) -> bool:
    """True if the passenger-details (manifest) page is already showing."""
    els = driver.find_elements(By.CSS_SELECTOR, ".payment_textName")
    return bool(els) and els[0].is_displayed()


def _seat_img_state(seat) -> str:
    """Return 'available' (white), 'selected' (blue), 'taken' (grey) or '' (spacer/none)."""
    try:
        src = (seat.find_element(By.TAG_NAME, "img").get_attribute("src") or "").lower()
    except (NoSuchElementException, StaleElementReferenceException):
        return ""
    if "white.png" in src:
        return "available"
    if "blue.png" in src:
        return "selected"
    if "grey.png" in src:
        return "taken"
    return ""


def _seat_available(seat) -> bool:
    """A .seat is available iff its <img> is white.png (not blue/grey, not a spacer)."""
    return _seat_img_state(seat) == "available"


def _seat_is_selected(driver, num: str, timeout: float = 6) -> bool:
    """Poll until the seat numbered `num` shows the selected (blue.png) image."""
    def _check(d):
        for s in d.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']"):
            try:
                if s.text.strip() == num:
                    return _seat_img_state(s) == "selected"
            except StaleElementReferenceException:
                continue
        return False
    try:
        return WebDriverWait(driver, timeout).until(_check)
    except TimeoutException:
        return False


def _select_available_seats(driver, pax_count: int, ctx) -> int:
    """
    Select exactly `pax_count` seats. Counts a seat ONLY after confirming its
    image flipped to selected (blue.png) — so a click that didn't register, or a
    re-click that would toggle a seat back off, never inflates the count. Tracks
    chosen seats by their number so the same seat is never clicked twice.
    Returns the number of confirmed-selected seats.
    """
    chosen: set[str] = set()
    guard = 0
    while len(chosen) < pax_count and guard < pax_count * 8 + 4:
        guard += 1
        time.sleep(0.3)   # let seat map settle between iterations
        all_seats = driver.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")
        target = None
        for s in all_seats:
            try:
                num = s.text.strip()
                if num and num not in chosen and _seat_available(s):
                    target = (s, num)
                    break
            except StaleElementReferenceException:
                continue
        if target is None:
            avail = sum(1 for s in all_seats if _seat_available(s))
            if guard <= 3:
                # Seat map may still be rendering — give it a moment and retry
                ctx.step(f"Seat scan {guard}: {len(all_seats)} total, {avail} available — retrying")
                continue
            ctx.step(f"No selectable seat found after {guard} tries "
                     f"(total={len(all_seats)}, avail={avail}, chosen={len(chosen)})")
            log_step(f"No available seat — total={len(all_seats)} avail={avail}")
            break
        seat, num = target
        try:
            _js_click(driver, seat)
        except Exception:
            continue
        time.sleep(0.5)   # wait for click to register before polling state
        if _seat_is_selected(driver, num):
            chosen.add(num)
            ctx.passed(f"Seat {num} selected ({len(chosen)}/{pax_count})"); log_pass(f"Seat {num} selected")
        else:
            ctx.step(f"Seat {num} click did not confirm — retrying")
            log_step(f"Seat {num} not confirmed selected")
    return len(chosen)


def _click_seat_proceed(driver, ctx) -> None:
    """Click the seat-map / ticket-panel Proceed button (waits until enabled)."""
    proceed = None
    # Try the known class selector first, then fall back to button text
    try:
        proceed = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".seatProceed"))
        )
    except TimeoutException:
        pass
    if proceed is None:
        # Fallback: any visible, enabled button whose text contains "Proceed"
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            if "proceed" in (btn.text or "").lower() and btn.is_displayed() and btn.is_enabled():
                proceed = btn
                break
    if proceed is None:
        raise TimeoutException(
            "Seat proceed button not found — tried .seatProceed and text-based fallback"
        )
    _js_click(driver, proceed)
    time.sleep(3)
    ctx.passed("Clicked Proceed"); log_pass("Clicked Proceed")


# Matches a time anywhere in a label: 12-hour (9:00 AM / 10:30 PM) or
# 24-hour (09:00 / 10:30). `search` (not `match`) so "Depart 09:00" still hits.
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*([AP]M)?\b", re.I)

# Elements that could be a clickable time slot. Ferries render these in varying
# ways (button, anchor, or a div/li styled as a button), so we cast a wide net.
_TIME_SLOT_SELECTOR = (
    "button, a, [role='button'], .trip-time-item, .time-slot, "
    ".timing, .timing-item, li.trip-time, .ferry-time, .schedule-time"
)


def _visible_time_slots(driver) -> list:
    """All on-screen elements whose text looks like a clickable time slot."""
    out = []
    for el in driver.find_elements(By.CSS_SELECTOR, _TIME_SLOT_SELECTOR):
        try:
            t = (el.text or "").strip()
            if t and _TIME_RE.search(t) and len(t) <= 40 and el.is_displayed():
                out.append(el)
        except StaleElementReferenceException:
            continue
    return out


def _dump_ferry_state(driver, ctx) -> None:
    """Log a snapshot of the ferry page so a failure is diagnosable from the report."""
    try:
        btns = [(b.text or "").strip() for b in driver.find_elements(By.TAG_NAME, "button")
                if b.is_displayed() and (b.text or "").strip()]
        has_ticket = bool(driver.find_elements(By.CSS_SELECTOR, ".ticket-no-input"))
        has_seatmap = bool(driver.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']"))
        ctx.step(f"Ferry page state — URL: {driver.current_url}")
        ctx.step(f"Visible buttons: {btns[:25]}")
        ctx.step(f"ticket-no-input present: {has_ticket} | seat map present: {has_seatmap}")
        log_step(f"Ferry buttons: {btns[:25]} | ticket={has_ticket} seatmap={has_seatmap}")
    except Exception:
        pass


def _ferry_select_time(driver, ctx) -> bool:
    """
    Ferry: click the first visible time-slot element.

    Time slots may be <button>, <a>, or styled <div>/<li> elements, and the
    section header wording varies per operator — so we wait for either a
    recognisable time-slot element OR a time-ish header, then click the first
    slot found. If a ticket counter / seat map already showed (slot pre-picked),
    we skip and let the caller handle it.
    """
    try:
        WebDriverWait(driver, 20).until(
            lambda d: _visible_time_slots(d)
            or d.find_elements(By.CSS_SELECTOR, ".ticket-no-input")
            or d.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")
            or d.find_elements(
                By.XPATH,
                "//*[contains(text(),'Trip Time') or contains(text(),'Select Time') "
                "or contains(text(),'Timings') or contains(text(),'Departure Time') "
                "or contains(text(),'Select Your Trip')]")
        )
    except TimeoutException:
        ctx.step("No trip-time panel appeared"); log_step("No trip-time panel")
        _dump_ferry_state(driver, ctx)
        return False
    time.sleep(0.5)

    # A ticket counter / seat map already present means no separate time step.
    if (driver.find_elements(By.CSS_SELECTOR, ".ticket-no-input")
            or driver.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")):
        ctx.step("Ticket/seat panel already shown — no separate time-slot step")
        log_step("No separate time-slot step")
        return True

    slots = _visible_time_slots(driver)
    if not slots:
        ctx.failed("Trip-time section appeared but no clickable time slot was found")
        log_fail("No clickable time-slot element found")
        _dump_ferry_state(driver, ctx)
        return False

    slot = slots[0]
    label = (slot.text or "").strip()
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", slot)
        time.sleep(0.2)
    except Exception:
        pass
    _js_click(driver, slot)
    time.sleep(2)
    ctx.passed(f"Selected trip time: {label}"); log_pass(f"Selected trip time: {label}")
    return True


def _read_ticket_count(driver) -> int:
    """Current value of the ferry .ticket-no-input, or -1 if unreadable."""
    try:
        v = driver.find_element(By.CSS_SELECTOR, ".ticket-no-input").get_attribute("value")
        return int(v) if v not in (None, "") else -1
    except (NoSuchElementException, StaleElementReferenceException, ValueError):
        return -1


def _find_plus_button(driver):
    """
    The ticket "+" button. DOM order is [minus, input, plus]; at count 1 the
    minus is disabled, so the enabled button is the plus. Once count > 1 both are
    enabled, and the plus is the last in DOM order — so 'last enabled' is the plus
    in both states.
    """
    btns = [b for b in driver.find_elements(By.CSS_SELECTOR, ".ticket-no-button") if b.is_displayed()]
    enabled = [b for b in btns if b.is_enabled()]
    if enabled:
        return enabled[-1]
    return btns[-1] if btns else None


def _set_ticket_count_and_proceed(driver, pax_count: int, ctx) -> bool:
    """
    Raise the ferry ticket counter to exactly `pax_count`, verifying by reading
    the input back after each click (so a capped/disabled "+" can't pass
    silently), then click Proceed. Returns True only if the count truly reached
    `pax_count`.
    """
    ctx.step(f"Seat map unavailable — setting ticket count to {pax_count}")
    log_step(f"Setting ticket count to {pax_count}")

    guard = 0
    while _read_ticket_count(driver) < pax_count and guard < pax_count * 3 + 5:
        guard += 1
        before = _read_ticket_count(driver)
        plus = _find_plus_button(driver)
        if plus is None:
            break
        _js_click(driver, plus)
        time.sleep(0.5)
        if _read_ticket_count(driver) <= before:
            break  # click didn't register (capped / disabled) — stop, don't loop forever

    final = _read_ticket_count(driver)
    if final != pax_count:
        ctx.failed(f"Ticket count reached {final}, expected {pax_count}")
        log_fail(f"Ticket count {final} != expected {pax_count}")
        return False
    ctx.passed(f"Ticket count set to {pax_count}"); log_pass(f"Ticket count set to {pax_count}")
    _click_seat_proceed(driver, ctx)
    return True


def _ferry_seat_or_ticket(driver, pax_count: int, ctx) -> bool:
    """
    Ferry: after a time slot is chosen, either pick `pax_count` seats from a seat
    map, or (when seat selection is unavailable) set the ticket count to
    `pax_count`. Then click Proceed. Returns True on success.
    """
    # The seat map / ticket panel renders via AJAX after the time-slot click —
    # wait for it instead of a fixed sleep (mirrors the bus/train branch).
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")
            or d.find_elements(By.CSS_SELECTOR, ".ticket-no-input")
            or _manifest_present(d)
        )
    except TimeoutException:
        ctx.failed("Ferry seat map / ticket panel did not load"); log_fail("Ferry panel did not load")
        return False

    if _manifest_present(driver):
        ctx.step("Manifest shown directly — no seat/ticket step"); log_step("Manifest shown directly")
        return True

    avail = [s for s in driver.find_elements(
                By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")
             if _seat_available(s)]
    if avail:
        sel = _select_available_seats(driver, pax_count, ctx)
        if sel < pax_count:
            ctx.failed(f"Only {sel}/{pax_count} ferry seats selectable"); log_fail("Not enough ferry seats")
            return False
        _click_seat_proceed(driver, ctx)
        return True

    if driver.find_elements(By.CSS_SELECTOR, ".ticket-no-input"):
        return _set_ticket_count_and_proceed(driver, pax_count, ctx)

    ctx.failed("Neither a seat map nor a ticket counter appeared for this ferry trip")
    log_fail("No ferry seat map / ticket counter")
    return False


def _select_seats(driver, transport: str, pax_count: int, ctx) -> bool:
    """
    Handle the seat/ticket step between operator-select and the manifest.
    Bus/Train: pick seats from the map. Ferry: time slot → seats or ticket count.
    Returns True when the booking has proceeded toward the manifest.
    """
    if transport in ("bus", "train"):
        ctx.step(f"Selecting {pax_count} seat(s) from the seat map"); log_step(f"Selecting {pax_count} seat(s)")
        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")
                or _manifest_present(d)
            )
        except TimeoutException:
            ctx.failed("Seat map did not appear after Select"); log_fail("Seat map did not appear")
            return False
        if _manifest_present(driver):
            ctx.step("No seat-selection step — manifest shown directly"); log_step("Manifest shown directly")
            return True
        time.sleep(1.5)
        sel = _select_available_seats(driver, pax_count, ctx)
        if sel < pax_count:
            ctx.failed(f"Only {sel}/{pax_count} seats selectable"); log_fail("Not enough seats available")
            return False
        _click_seat_proceed(driver, ctx)
        return True

    # ── Ferry ───────────────────────────────────────────────────────────────
    if _manifest_present(driver):
        ctx.step("No seat-selection step — manifest shown directly"); log_step("Manifest shown directly")
        return True

    # After "View Trips" click, wait for the time-selection page/panel to load.
    # This gives more time than the 2 s sleep in the main test code.
    ctx.step("Waiting for ferry time-selection content to load"); log_step("Waiting for ferry time content")
    try:
        WebDriverWait(driver, 15).until(
            lambda d: (
                _visible_time_slots(d)
                or d.find_elements(By.CSS_SELECTOR, ".ticket-no-input")
                or d.find_elements(By.CSS_SELECTOR, ".query-seat-lg div.seat[role='button']")
                or _manifest_present(d)
            )
        )
    except TimeoutException:
        ctx.step("Ferry content not loaded yet — proceeding anyway"); log_step("Ferry content wait timed out")

    if _manifest_present(driver):
        ctx.step("Manifest shown after View Trips — no seat/ticket step"); log_step("Manifest shown directly")
        return True

    _ferry_select_time(driver, ctx)        # optional for some ferries
    return _ferry_seat_or_ticket(driver, pax_count, ctx)


# ── Manifest (passenger-details / payment page) field catalog ────────────────
# Every input the manifest page MIGHT show. Whether it actually shows depends on
# the route/criteria — the site keeps the element in the DOM but hides its
# wrapper with display:none, so we judge "shown" via Selenium is_displayed().
#
# Locator convention mirrors the site:
#   • Lead passenger fields have NO id  → matched by CLASS  (.payment_xxx)
#   • Add-on checkboxes & "other passenger" fields HAVE ids → matched by #id
#
# `kind` drives how the field is auto-filled.

_MANIFEST_FIELDS = [
    # ── Lead passenger (class-based, no id) ──────────────────────────────────
    {"key": "lead_name",   "label": "Lead — Full Name",     "css": ".payment_textName",      "kind": "text"},
    {"key": "lead_phone",  "label": "Lead — Phone Number",  "css": ".payment_txtPhoneLogin", "kind": "text"},
    {"key": "lead_email",  "label": "Lead — Email",         "css": ".payment_txtEmail",      "kind": "text"},
    {"key": "child_qty",   "label": "No. of Child Tickets", "css": ".payment_ddChild1",      "kind": "select"},
    {"key": "meal_depart", "label": "Meal for Depart Trip", "css": ".payment_ddMeal1",       "kind": "select"},
    {"key": "meal_return", "label": "Meal for Return Trip", "css": ".payment_ddMeal2",       "kind": "select"},
    # ── Add-ons (id-based checkboxes; left unchecked, detection only) ─────────
    {"key": "addon_qr",        "label": "Add-on — Boarding Pass / QR",  "css": "#payment_chkQRCode",       "kind": "checkbox"},
    {"key": "addon_insurance", "label": "Add-on — Travel Insurance",    "css": "#payment_chkInsurance",    "kind": "checkbox"},
    {"key": "addon_refund",    "label": "Add-on — Protect My Booking",  "css": "#payment_chkRefundProtect","kind": "checkbox"},
    {"key": "addon_pop",       "label": "Add-on — Featured Promo",      "css": "#payment_chkPoP",          "kind": "checkbox"},
    # ── Other passenger #1 (id-based) ────────────────────────────────────────
    {"key": "other_name",            "label": "Other Pax 1 — Full Name",       "css": "#payment_textNameOther1",           "kind": "text"},
    {"key": "other_gender",          "label": "Other Pax 1 — Gender",          "css": "#payment_ddPassengerSex1",          "kind": "select"},
    {"key": "other_dob",             "label": "Other Pax 1 — Date of Birth",   "css": "#payment_textDobOther1",            "kind": "date"},
    {"key": "other_nationality",     "label": "Other Pax 1 — Nationality",     "css": "#payment_textNationalityOther1",    "kind": "country"},
    {"key": "other_passport_no",     "label": "Other Pax 1 — Passport No",     "css": "#payment_textPassportNoOther1",     "kind": "text"},
    {"key": "other_passport_expiry", "label": "Other Pax 1 — Passport Expiry", "css": "#payment_textPassportExpiryOther1", "kind": "date"},
]

_FIELD_BY_KEY = {f["key"]: f for f in _MANIFEST_FIELDS}

# Lead-passenger Full Name / Phone / Email are present on EVERY manifest page,
# no matter the trip or operator. They're always filled with these fixed dummy
# values (overrides whatever the JSON or a logged-in account would supply).
_LEAD_FULL_NAME = "LEE CHUN YIN"
_LEAD_PHONE     = "0163553613"
_LEAD_EMAIL     = "leechunyin@gmail.com"


def _is_shown(driver, css: str) -> bool:
    """True only if the element is present AND actually visible (no display:none ancestor)."""
    try:
        return driver.find_element(By.CSS_SELECTOR, css).is_displayed()
    except (NoSuchElementException, Exception):
        return False


def _detect_manifest_fields(driver) -> list[dict]:
    """Return [{key, label, shown}] for every catalog field on the manifest page."""
    return [
        {"key": f["key"], "label": f["label"], "shown": _is_shown(driver, f["css"])}
        for f in _MANIFEST_FIELDS
    ]


def _select_first_or_text(driver, el, value: str):
    """
    Pick a <select> option matching `value`, else the first real option.

    Matching is EXACT (case-insensitive) first — a substring match would let
    'Male' select 'Female' ('male' is inside 'feMALE'). Only if no exact option
    exists do we fall back to a substring match.
    """
    sel = SeleniumSelect(el)
    real = [o for o in sel.options if (o.get_attribute("value") or "").strip()]
    want = value.strip().lower()
    if want:
        # 1) exact (case-insensitive) match among real options
        for o in real:
            if o.text.strip().lower() == want:
                sel.select_by_visible_text(o.text)
                return
        # 2) fall back to substring match among real options
        for o in real:
            if want in o.text.strip().lower():
                sel.select_by_visible_text(o.text)
                return
    if real:
        sel.select_by_value(real[0].get_attribute("value"))


def _set_manifest_date(driver, el, value: str):
    """Set a jQuery-UI datepicker input (readonly) via setDate so the widget's state updates too."""
    driver.execute_script("""
        var el = arguments[0], v = arguments[1];
        var p = v.split('/');               // dd/mm/yyyy
        var jq = window.jQuery;
        if (jq && jq(el).hasClass('hasDatepicker')) {
            var d = new Date(parseInt(p[2],10), parseInt(p[1],10)-1, parseInt(p[0],10));
            jq(el).datepicker('setDate', d);
            jq(el).trigger('change');
        } else {
            el.removeAttribute('readonly');
            el.value = v;
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }
    """, el, value)


def _fill_country(driver, el, value: str):
    """Type a nationality and click the first suggestion in the .divSearchCountryN dropdown."""
    try:
        el.clear()
    except Exception:
        pass
    for ch in value:
        el.send_keys(ch)
        time.sleep(0.05)
    time.sleep(1.0)
    for box in driver.find_elements(By.CSS_SELECTOR, ".divSearchCountryN"):
        if not box.is_displayed():
            continue
        for item in box.find_elements(By.CSS_SELECTOR, "div, li, a, span"):
            if item.text.strip():
                _js_click(driver, item)
                return
    # No dropdown — leave the typed value as-is.


def _fill_one(driver, css: str, kind: str, value: str, label: str,
              ctx, fill_failures: list[str]) -> None:
    """
    Fill a single manifest field located by CSS selector.

    Silently skips fields that are absent or hidden (display:none) for this
    route. A failure while filling a VISIBLE field is logged as a red step and
    appended to fill_failures, so a "Shown" field that never got a value can't
    pass silently.
    """
    try:
        el = driver.find_element(By.CSS_SELECTOR, css)
    except NoSuchElementException:
        return
    if not el.is_displayed():
        return
    try:
        if kind == "text":
            try:
                el.clear()
            except Exception:
                pass
            el.send_keys(value)
        elif kind == "select":
            if el.tag_name.lower() != "select":
                raise AssertionError(f"expected a <select> but found <{el.tag_name}>")
            _select_first_or_text(driver, el, value)
        elif kind == "date":
            _set_manifest_date(driver, el, value)
        elif kind == "country":
            _fill_country(driver, el, value)
        ctx.passed(f"Filled: {label}"); log_pass(f"Filled: {label}")
    except Exception as e:
        fill_failures.append(label)
        ctx.failed(f"Could not fill VISIBLE field '{label}': {e}")
        log_fail(f"Could not fill VISIBLE field '{label}': {e}")


def _select_child_ticket(driver, count: str, ctx) -> None:
    """Set the 'No. of Tickets for Child' select on the lead block (if shown)."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, ".payment_ddChild1")
    except NoSuchElementException:
        return
    if not el.is_displayed():
        ctx.step(f"Child-ticket field hidden — not setting ({count})"); return
    try:
        _select_first_or_text(driver, el, str(count))
        ctx.passed(f"Set No. of child tickets: {count}"); log_pass(f"Child tickets: {count}")
    except Exception as e:
        ctx.step(f"Could not set child tickets ({count}): {e}")


# Score a meal-dropdown option against requested veg / non-veg counts. The site
# renders combined options like "2 vegetarian" or "1 non-vegetarian 1 vegetarian";
# we parse the number before each diet word and compare to what the JSON asked.
def _meal_counts_in_text(text: str) -> tuple[int, int]:
    t = text.lower()
    veg = nonveg = 0
    m = re.search(r"(\d+)\s*non[- ]?vegetarian", t)
    if m:
        nonveg = int(m.group(1))
    # vegetarian count: a "\d vegetarian" NOT preceded by "non-"
    for mm in re.finditer(r"(\d+)\s*(non[- ]?)?vegetarian", t):
        if not mm.group(2):
            veg = int(mm.group(1))
    return veg, nonveg


def _select_meal(driver, css: str, meal: dict, label: str, ctx) -> None:
    """
    Best-effort meal pick. `meal` = {"vegetarian": n, "non_vegetarian": m}. Picks
    the option whose parsed veg/non-veg counts match; falls back to a token match.
    Soft — logs a step (never a hard fail), since meal text varies by operator.
    """
    if not meal:
        return
    try:
        el = driver.find_element(By.CSS_SELECTOR, css)
    except NoSuchElementException:
        return
    if not el.is_displayed():
        ctx.step(f"{label} meal field hidden — skipping"); return

    try:
        veg = int(meal.get("vegetarian", 0) or 0)
        nonveg = int(meal.get("non_vegetarian", 0) or 0)
    except (TypeError, ValueError):
        veg = nonveg = 0

    try:
        sel = SeleniumSelect(el)
        real = [o for o in sel.options if (o.get_attribute("value") or "").strip()]
        # 1) exact veg/non-veg count match
        for o in real:
            if _meal_counts_in_text(o.text) == (veg, nonveg):
                sel.select_by_visible_text(o.text)
                ctx.passed(f"{label} meal: {o.text.strip()}"); log_pass(f"{label} meal: {o.text.strip()}")
                return
        # 2) fall back: an option mentioning the veg count if veg-only requested
        if veg and not nonveg:
            for o in real:
                if "vegetarian" in o.text.lower() and "non" not in o.text.lower():
                    sel.select_by_visible_text(o.text)
                    ctx.step(f"{label} meal (approx): {o.text.strip()}"); return
        ctx.step(f"{label} meal: no option matched {veg} veg / {nonveg} non-veg "
                 f"(options: {[o.text.strip() for o in real][:6]})")
        log_step(f"{label} meal: no matching option")
    except Exception as e:
        ctx.step(f"{label} meal selection skipped: {e}")


# Add-on canonical key → manifest checkbox selector (from _MANIFEST_FIELDS).
_ADDON_CSS = {
    "insurance": "#payment_chkInsurance",
    "refund":    "#payment_chkRefundProtect",
    "promo":     "#payment_chkPoP",
    "qr":        "#payment_chkQRCode",
}


def _tick_addons(driver, addons: list[str], ctx) -> None:
    """Tick each add-on checkbox named in the JSON (insurance/refund/promo/qr)."""
    for key in addons:
        css = _ADDON_CSS.get(key)
        if not css:
            continue
        try:
            cb = driver.find_element(By.CSS_SELECTOR, css)
        except NoSuchElementException:
            ctx.step(f"Add-on '{key}' checkbox not present on this manifest"); continue
        if not cb.is_displayed():
            ctx.step(f"Add-on '{key}' checkbox hidden — not ticking"); continue
        try:
            if not cb.is_selected():
                _js_click(driver, cb)
            ctx.passed(f"Add-on ticked: {key}"); log_pass(f"Add-on ticked: {key}")
        except Exception as e:
            ctx.step(f"Could not tick add-on '{key}': {e}")


def _fill_manifest(driver, bdata: dict, defaults: dict, ctx) -> list[str]:
    """
    Auto-fill the manifest from the parsed booking JSON.

    Passenger → DOM mapping:
      • Lead block (.payment_textName / phone / email) — ALWAYS the fixed dummy
        values _LEAD_FULL_NAME / _LEAD_PHONE / _LEAD_EMAIL. The lead block only
        has Name/Phone/Email (no gender/dob/passport), and per requirement these
        are the same on every trip, so the JSON is NOT consulted here. The lead
        also occupies passengers[0]'s seat, so JSON passengers START at index 1.
      • Other block k (#payment_…Other{k}) = passengers[k]   (k = 1..N-1), each
        with full Name/Gender/DoB/Nationality/Passport.

    With no passengers in the JSON it falls back to `defaults` (the TestData
    "manifest" section) for a single "other" block — harmless on a 1-seat trip
    where no "other" block is shown (the fill silently skips absent fields).
    Returns labels of any VISIBLE fields that failed to fill.
    """
    fails: list[str] = []
    passengers = bdata.get("passengers") or []

    # ── Lead passenger block (class-based, no id) ───────────────────────────
    # These three fields always appear on the manifest regardless of the trip /
    # operator, so they're always filled with the fixed dummy values above.
    _fill_one(driver, ".payment_textName",      "text", _LEAD_FULL_NAME, "Lead — Full Name", ctx, fails)
    _fill_one(driver, ".payment_txtPhoneLogin", "text", _LEAD_PHONE,     "Lead — Phone Number", ctx, fails)
    _fill_one(driver, ".payment_txtEmail",      "text", _LEAD_EMAIL,     "Lead — Email", ctx, fails)

    # ── Other passenger blocks (id-based, suffix = 1-based block number) ────
    if passengers:
        others = passengers[1:]
    else:
        others = [{
            "full_name":   defaults.get("full_name", ""),   "gender":          defaults.get("gender", ""),
            "dob":         defaults.get("dob", ""),          "nationality":     defaults.get("nationality", ""),
            "passport_no": defaults.get("passport_no", ""),  "passport_expiry": defaults.get("passport_expiry", ""),
        }]
    for k, p in enumerate(others, start=1):
        tag = f"Other Pax {k}"
        _fill_one(driver, f"#payment_textNameOther{k}",           "text",    p.get("full_name", ""),       f"{tag} — Full Name",       ctx, fails)
        _fill_one(driver, f"#payment_ddPassengerSex{k}",          "select",  p.get("gender", ""),          f"{tag} — Gender",          ctx, fails)
        _fill_one(driver, f"#payment_textDobOther{k}",            "date",    p.get("dob", ""),             f"{tag} — Date of Birth",   ctx, fails)
        _fill_one(driver, f"#payment_textNationalityOther{k}",    "country", p.get("nationality", ""),     f"{tag} — Nationality",     ctx, fails)
        _fill_one(driver, f"#payment_textPassportNoOther{k}",     "text",    p.get("passport_no", ""),     f"{tag} — Passport No",     ctx, fails)
        _fill_one(driver, f"#payment_textPassportExpiryOther{k}", "date",    p.get("passport_expiry", ""), f"{tag} — Passport Expiry", ctx, fails)

    # ── No. of child tickets (lead block select) ───────────────────────────
    child = str(bdata.get("child", "")).strip()
    if child:
        _select_child_ticket(driver, child, ctx)

    # ── Meals (best-effort; the option text varies by passenger count) ──────
    _select_meal(driver, ".payment_ddMeal1", bdata.get("depart_meal") or {}, "Depart", ctx)
    _select_meal(driver, ".payment_ddMeal2", bdata.get("return_meal") or {}, "Return", ctx)

    # ── Add-ons: tick the checkboxes named in the JSON ──────────────────────
    _tick_addons(driver, bdata.get("addons") or [], ctx)

    return fails


def _build_manifest_rows(detected: list[dict], expected_keys
                         ) -> tuple[list[dict], set[str], set[str]]:
    """
    Attach Expected / Verdict to each detected field.

    expected_keys: iterable of catalog field keys that SHOULD be visible
    (from the JSON "expected_fields"). Empty → record-only (verdict '—');
    otherwise strict per-field PASS/FAIL.

    Returns (rows, expected_keys, unknown_keys). `unknown_keys` are entries that
    don't match any catalog key (typo / stale) — surfaced so a misspelling can't
    silently disable a check.
    """
    expected_keys = {str(k).strip() for k in (expected_keys or []) if str(k).strip()}
    unknown_keys = expected_keys - set(_FIELD_BY_KEY)

    rows = []
    for d in detected:
        if expected_keys:
            should  = d["key"] in expected_keys
            verdict = "PASS" if d["shown"] == should else "FAIL"
            exp     = "Yes" if should else "No"
        else:
            verdict, exp = "—", "—"
        rows.append({**d, "expected": exp, "verdict": verdict})
    return rows, expected_keys, unknown_keys


# ── Load booking cases from Excel at collection time ─────────────────────────

# Captures any exception raised while reading BookingTestData (e.g. the workbook
# is open in Excel → PermissionError on Windows). Surfaced by the guard test
# below so a load failure can't masquerade as "0 tests, all green".
_LOAD_ERROR: Exception | None = None


def _load_cases() -> list[dict]:
    global _LOAD_ERROR
    try:
        return get_booking_data()
    except Exception as e:
        _LOAD_ERROR = e
        import sys
        print(
            f"\n[test_ui_04_booking] Could not load BookingTestData from Excel: {e!r}",
            file=sys.stderr,
        )
        return []


_CASES = _load_cases()
_IDS   = [c.get("TC ID", f"case-{i}") for i, c in enumerate(_CASES)]


# ── Test class ────────────────────────────────────────────────────────────────

@pytest.mark.ui
@pytest.mark.booking
class TestUIBooking:

    def test_booking_data_available(self):
        """
        TC-BK-00 │ Booking test data loads
        ─────────────────────────────────────
        Guard so an Excel read failure (e.g. the workbook is open in Excel)
        surfaces as a clear FAIL instead of silently collecting zero cases.
        """
        if _LOAD_ERROR is not None:
            pytest.fail(
                "Could not load the BookingTestData sheet from data/test_data.xlsx:\n"
                f"    {_LOAD_ERROR!r}\n"
                "If the file is open in Excel, close it and re-run."
            )
        if not _CASES:
            pytest.skip("No active rows found in the BookingTestData sheet.")

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

        # Full per-case booking payload from the "Test Data (JSON)" cell.
        bdata     = parse_booking_json(booking.get(BOOKING_JSON_COL, ""))
        pax_count = len(bdata["passengers"]) or 1   # seats/tickets to select

        log_section(f"{tc_id} │ {operator} | {origin} → {dest} ({transport.title()})")
        ctx.driver = driver

        # A malformed JSON cell is a test-data error — fail clearly, don't guess.
        if bdata["error"]:
            ctx.failed(f"Bad 'Test Data (JSON)' for {tc_id}: {bdata['error']}")
            log_fail(f"Bad Test Data JSON: {bdata['error']}")
            pytest.fail(
                f"{tc_id}: the 'Test Data (JSON)' cell is not valid JSON:\n"
                f"    {bdata['error']}"
            )

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
        # Cards on the live site have no ".trip-item" class — the reliable marker
        # that results rendered is the per-card Select/View-Trips button.
        ctx.step("Waiting for trip results to load"); log_step("Waiting for trip results to load")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _SELECT_BTN_CSS))
            )
            ctx.passed("Trip results loaded"); log_pass("Trip results loaded")
        except TimeoutException:
            ctx.failed("Trip results did not load within 30s")
            log_fail("Trip results did not load within 30s")
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
        ctx.passed(f"Operator '{operator}' found and Select clicked"); log_pass(f"Operator '{operator}' selected")

        # ── Step 10b: Seat / ticket selection (count = pax_count) ─────────────
        # Bus/Train → pick seats from the seat map; Ferry → time slot then seats
        # or ticket count. Skips itself if the manifest is shown directly.
        ctx.step(f"Selecting {pax_count} seat(s)/ticket(s) for {transport.title()}")
        log_step(f"Seat/ticket selection ({pax_count})")
        if not _select_seats(driver, transport, pax_count, ctx):
            pytest.fail(
                f"{tc_id}: could not complete seat/ticket selection for "
                f"{pax_count} passenger(s) on this {transport} trip. "
                f"Current URL: {driver.current_url}"
            )

        # ── Step 11: Wait for the passenger-details (manifest) page ───────────
        ctx.step("Waiting for passenger-details (manifest) page"); log_step("Waiting for manifest page")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".payment_textName"))
            )
            time.sleep(2)  # let conditional fields settle
            ctx.passed("Manifest page loaded"); log_pass("Manifest page loaded")
        except TimeoutException:
            ctx.failed("Manifest page not reached"); log_fail("Manifest page not reached")
            pytest.fail(
                f"Did not reach the passenger-details page for {tc_id} after seat "
                f"selection. The operator's flow may differ.\n"
                f"Current URL: {driver.current_url}"
            )

        # ── Step 12: Detect which manifest fields are visible ─────────────────
        ctx.step("Detecting visible manifest fields"); log_step("Detecting visible manifest fields")
        detected   = _detect_manifest_fields(driver)
        shown      = [d["label"] for d in detected if d["shown"]]
        hidden     = [d["label"] for d in detected if not d["shown"]]
        ctx.passed(f"Visible fields ({len(shown)}): " + ", ".join(shown)); log_pass(f"Visible: {', '.join(shown)}")
        ctx.step(f"Hidden / not shown ({len(hidden)}): " + ", ".join(hidden)); log_step(f"Hidden: {', '.join(hidden)}")

        # ── Step 13: Compare against expected_fields from the JSON (if provided) ─
        # The visibility verdict is decided here, BEFORE filling or clicking Next,
        # so a wrong-manifest route fails without us submitting a live booking.
        manifest_rows, expected_keys, unknown_keys = _build_manifest_rows(
            detected, bdata["expected_fields"]
        )
        ctx.manifest_fields = manifest_rows  # picked up by conftest → Excel + report

        # M1: a typo'd / stale key in expected_fields would silently disable a
        # check — surface it as a hard failure instead.
        if unknown_keys:
            ctx.failed(f"expected_fields contains unknown key(s): {', '.join(sorted(unknown_keys))}")
            log_fail(f"Unknown expected_fields key(s): {', '.join(sorted(unknown_keys))}")
            pytest.fail(
                f"{tc_id}: the JSON 'expected_fields' contains key(s) that are not "
                f"valid manifest fields: {', '.join(sorted(unknown_keys))}\n"
                f"    Valid keys: {', '.join(f['key'] for f in _MANIFEST_FIELDS)}"
            )

        if expected_keys:
            mismatches = [r for r in manifest_rows if r["verdict"] == "FAIL"]
            if mismatches:
                ctx.failed(f"{len(mismatches)} manifest field(s) did not match expected_fields")
                log_fail("Manifest field mismatch")
                # Fail NOW — do not fill or submit a booking for a route whose
                # manifest already failed its field-visibility contract.
                pytest.fail(
                    f"{tc_id}: manifest showed the wrong fields for this route.\n"
                    + "\n".join(
                        f"    • {r['label']} ({r['key']}): expected to be "
                        f"{'shown' if r['expected'] == 'Yes' else 'hidden'}, "
                        f"but was {'shown' if r['shown'] else 'hidden'}"
                        for r in mismatches
                    )
                )
            ctx.passed("All manifest fields match expected_fields"); log_pass("Manifest fields match expectations")
        else:
            ctx.step("No expected_fields set — recording visible fields only (no pass/fail check)")
            log_step("expected_fields blank — record-only")

        # ── Step 14: Auto-fill the visible fields from the booking JSON ───────
        ctx.step(f"Auto-filling manifest from JSON ({pax_count} passenger(s))")
        log_step(f"Auto-filling manifest ({pax_count} passenger(s))")
        manifest_data = get_manifest_data()  # fallback defaults when JSON omits a field
        fill_failures = _fill_manifest(driver, bdata, manifest_data, ctx)
        if fill_failures:
            ctx.failed(f"{len(fill_failures)} visible field(s) could not be filled: " + ", ".join(fill_failures))
            log_fail("Some visible fields could not be filled: " + ", ".join(fill_failures))

        # ── Step 15: Click Next and verify the booking advances ───────────────
        pre_url = driver.current_url
        ctx.step("Clicking 'Next' (#btnNext)"); log_step("Clicking 'Next' (#btnNext)")
        try:
            next_btn = _wait_clickable(driver, By.ID, "btnNext")
            _js_click(driver, next_btn)
            time.sleep(4)
        except TimeoutException:
            ctx.failed("'Next' button (#btnNext) not found"); log_fail("'Next' button not found")
            pytest.fail("Could not find the #btnNext button on the manifest page.")

        # (a) A JS alert blocking the page is a failure.
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.dismiss()
            ctx.failed(f"Booking blocked by alert: {alert_text}"); log_fail(f"Alert after Next: {alert_text}")
            pytest.fail(f"Clicking Next raised a browser alert:\n    {alert_text}")
        except Exception:
            pass

        # (b) A visible, non-empty validation message means we were blocked.
        error_text = ""
        for sel in (".paymentErrorTab", ".field-validation-error", "span.text-danger"):
            for e in driver.find_elements(By.CSS_SELECTOR, sel):
                if e.is_displayed() and e.text.strip():
                    error_text = e.text.strip()
                    break
            if error_text:
                break

        if error_text:
            ctx.failed(f"Booking did not advance — validation error: {error_text}")
            log_fail(f"Validation error after Next: {error_text}")
            pytest.fail(
                f"Clicking Next on the manifest page raised a validation error:\n"
                f"    {error_text}\n"
                "A required field may not have been filled correctly."
            )

        # (c) Positively confirm the page actually moved on — absence of an error
        # is NOT proof of advancement (the click could have been a no-op).
        def _advanced(drv):
            if drv.current_url != pre_url and "payment_secure" not in drv.current_url.lower():
                return True
            # Or the lead passenger field is gone / hidden (page replaced). A
            # stale element here means the DOM was swapped out → also advanced.
            try:
                els = drv.find_elements(By.CSS_SELECTOR, ".payment_textName")
                return not els or not els[0].is_displayed()
            except Exception:
                return True

        try:
            WebDriverWait(driver, 12).until(_advanced)
            ctx.passed("Booking advanced past the manifest page"); log_pass("Booking advanced past manifest page")
        except TimeoutException:
            ctx.failed("Booking did not advance — still on the manifest page after Next")
            log_fail("No advancement after Next")
            pytest.fail(
                f"{tc_id}: clicking Next showed no validation error but the page did "
                f"not advance (still at {driver.current_url}). The Next click may have "
                "been a no-op, the button disabled, or validation surfaced in an "
                "unrecognised way."
            )

        # ── Step 16: Payment page — VERIFY ONLY, never submit ─────────────────
        # We deliberately STOP before paying. Touch N Go (or any method) would be
        # a real charge on the live site. Until the payment-page HTML is provided
        # this is a best-effort text check that the expected amounts/method show;
        # NO pay button is ever clicked.
        if bdata.get("total") or bdata.get("discount") or bdata.get("payment_method"):
            ctx.step("Payment page — verifying amounts (NO payment will be submitted)")
            log_step("Payment page — verify only, no payment submitted")
            time.sleep(2)
            page_text = driver.page_source.lower()
            for label, val in (("Discount",       bdata.get("discount", "")),
                               ("Total",          bdata.get("total", "")),
                               ("Payment method", bdata.get("payment_method", ""))):
                if not val:
                    continue
                if val.lower() in page_text:
                    ctx.passed(f"{label} '{val}' is shown on the payment page")
                    log_pass(f"{label} '{val}' shown on payment page")
                else:
                    ctx.step(f"{label} '{val}' not found in page text — payment-page "
                             "locators not wired yet (send the payment HTML)")
                    log_step(f"{label} '{val}' not found — needs payment-page HTML")
            ctx.passed("Stopped before submitting payment — no real transaction made")
            log_pass("Stopped before payment submit — no transaction made")

        ctx.passed(f"{tc_id} PASSED — manifest validated; stopped at payment (no payment made)")
        log_pass(f"{tc_id} PASSED — manifest validated; stopped at payment (no payment made)")
