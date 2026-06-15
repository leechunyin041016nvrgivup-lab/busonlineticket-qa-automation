"""
utils/data_loader.py
────────────────────
Loads test data from data/test_data.xlsx (primary source).

Sheet layout — "TestData":
  Row 1 : headers  →  Section | Key | Value
  Row 2+: data rows (one setting per row)

If the Excel file does not exist yet it is auto-created from
data/test_data.json so existing projects migrate seamlessly.
"""

from __future__ import annotations
import json
from pathlib import Path
from config.settings import DATA_FILE, EXCEL_FILE


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_from_json() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _create_excel_from_json(data: dict) -> None:
    """Bootstrap the Excel file from the JSON seed data."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()

    # ── TestData sheet ────────────────────────────────────────────────────────
    ws_data = wb.active
    ws_data.title = "TestData"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E3A5F")

    for col, heading in enumerate(["Section", "Key", "Value"], start=1):
        cell = ws_data.cell(row=1, column=col, value=heading)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    ws_data.column_dimensions["A"].width = 18
    ws_data.column_dimensions["B"].width = 22
    ws_data.column_dimensions["C"].width = 45

    row = 2
    for section, fields in data.items():
        if isinstance(fields, dict):
            for key, value in fields.items():
                ws_data.cell(row=row, column=1, value=section)
                ws_data.cell(row=row, column=2, value=key)
                ws_data.cell(row=row, column=3, value=str(value) if value is not None else "")
                row += 1
        else:
            ws_data.cell(row=row, column=1, value=section)
            ws_data.cell(row=row, column=2, value="value")
            ws_data.cell(row=row, column=3, value=str(fields))
            row += 1

    # ── TestResults sheet ─────────────────────────────────────────────────────
    ws_results = wb.create_sheet("TestResults")

    result_headers = ["Run Date", "TC ID", "Test Name", "Type", "Status", "Duration (s)", "Error Message"]
    for col, heading in enumerate(result_headers, start=1):
        cell = ws_results.cell(row=1, column=col, value=heading)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    ws_results.column_dimensions["A"].width = 20
    ws_results.column_dimensions["B"].width = 14
    ws_results.column_dimensions["C"].width = 40
    ws_results.column_dimensions["D"].width = 8
    ws_results.column_dimensions["E"].width = 10
    ws_results.column_dimensions["F"].width = 14
    ws_results.column_dimensions["G"].width = 60

    EXCEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    wb.save(EXCEL_FILE)


def _load_from_excel() -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(EXCEL_FILE, data_only=True)
    ws = wb["TestData"]

    data: dict = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        section, key, value = row[0], row[1], row[2]
        if section and key:
            data.setdefault(str(section), {})[str(key)] = value if value is not None else ""
    return data


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def load_test_data() -> dict:
    """Return the full test data dict, sourcing from Excel (creates it if missing)."""
    if not EXCEL_FILE.exists():
        seed = _load_from_json() if DATA_FILE.exists() else {}
        _create_excel_from_json(seed)

    return _load_from_excel()


def get_login_data() -> dict:
    return load_test_data()["login"]


def get_signup_data() -> dict:
    return load_test_data()["signup"]


def get_base_urls() -> dict:
    return load_test_data()["base_url"]
