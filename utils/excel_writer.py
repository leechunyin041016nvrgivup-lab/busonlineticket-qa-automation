"""
utils/excel_writer.py
─────────────────────
Appends test run results to the "TestResults" sheet in data/test_data.xlsx.

Each test run adds rows at the bottom so history is preserved across runs.
Columns: Run Date | TC ID | Test Name | Type | Status | Duration (s) | Error Message
"""

from __future__ import annotations
import datetime
from pathlib import Path

from config.settings import EXCEL_FILE


def append_results(ui_results: list[dict], api_results: list[dict]) -> None:
    """Append UI and API test results to the TestResults sheet."""
    if not EXCEL_FILE.exists():
        return  # data_loader creates the file; skip if somehow missing

    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return

    wb = load_workbook(EXCEL_FILE)

    if "TestResults" not in wb.sheetnames:
        return

    ws = wb["TestResults"]

    run_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    pass_font  = Font(color="166534")
    fail_font  = Font(color="991B1B")
    pass_fill  = PatternFill("solid", fgColor="DCFCE7")
    fail_fill  = PatternFill("solid", fgColor="FEE2E2")

    def _write_row(result: dict, test_type: str):
        row = ws.max_row + 1
        status = "PASS" if result["passed"] else "FAIL"
        error  = (result.get("error_message") or "").replace("\n", " ")[:500]

        ws.cell(row=row, column=1, value=run_date)
        ws.cell(row=row, column=2, value=result.get("tc_id", ""))
        ws.cell(row=row, column=3, value=result.get("name", ""))
        ws.cell(row=row, column=4, value=test_type)
        status_cell = ws.cell(row=row, column=5, value=status)
        ws.cell(row=row, column=6, value=round(result.get("duration", 0), 2))
        ws.cell(row=row, column=7, value=error)

        if result["passed"]:
            status_cell.font = pass_font
            status_cell.fill = pass_fill
        else:
            status_cell.font = fail_font
            status_cell.fill = fail_fill

    for r in ui_results:
        _write_row(r, "UI")
    for r in api_results:
        _write_row(r, "API")

    wb.save(EXCEL_FILE)
