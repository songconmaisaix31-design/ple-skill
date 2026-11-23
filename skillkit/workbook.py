"""Bounded, read-only Excel preview through the task container's Python."""
import json

from .transport import quote_path


PREVIEW_SOURCE = r'''
import json
from pathlib import Path
import re
from stat import S_ISREG
import sys
from zipfile import ZipFile

try:
    from openpyxl import load_workbook
    from openpyxl.utils.cell import get_column_letter, range_boundaries
except ImportError:
    sys.exit("Workbook preview unavailable: openpyxl is not installed in the task environment.")


def compact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 160 else text[:160] + " [value truncated]"


def preview(path, sheet, cell_range):
    cell_range = cell_range.upper()
    if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}(?::[A-Z]{1,3}[1-9][0-9]{0,6})?", cell_range):
        raise ValueError("cell_range must be an A1 reference or range such as D7:E12")
    first_col, first_row, last_col, last_row = range_boundaries(cell_range)
    rows = last_row - first_row + 1
    cols = last_col - first_col + 1
    if not (1 <= last_row <= 1048576 and 1 <= last_col <= 16384 and rows > 0 and cols > 0 and rows * cols <= 96):
        raise ValueError("cell_range must be within Excel limits and contain at most 96 cells")

    if not S_ISREG(Path(path).stat().st_mode):
        raise ValueError("path is not a regular workbook file")
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 2048 or sum(entry.file_size for entry in entries) > 64 * 1024**2:
            raise ValueError("workbook exceeds the preview's ZIP size limits; inspect a specific section with run_python")

    formulas = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        worksheets = formulas.worksheets
        if not worksheets:
            raise ValueError("workbook has no worksheets")
        if sheet is None:
            selected = next((item for item in worksheets if item.sheet_state == "visible"), worksheets[0])
        else:
            selected = next((item for item in worksheets if item.title == sheet), None)
        names = ", ".join(f"{compact(item.title)} ({item.sheet_state})" for item in worksheets[:30])
        if len(worksheets) > 30:
            names += f", … ({len(worksheets) - 30} more)"
        print(f"Worksheets: {names}")
        if selected is None:
            raise ValueError("requested worksheet was not found; use an exact name from the worksheet list")

        print(f"Worksheet {compact(selected.title)}, sampled range {cell_range}. Blank cells omitted.")
        try:
            extent = selected.calculate_dimension()
        except ValueError:
            print("Workbook-reported used range unavailable.")
        else:
            print(f"Workbook-reported used range {extent} (advisory; may be inaccurate).")
        print("Formula cache values are saved workbook state and may be stale. null means no cached value; 0 is cached zero.")
        bounds = {"min_row": first_row, "max_row": last_row, "min_col": first_col, "max_col": last_col}
        cached = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            raw_rows = selected.iter_rows(**bounds)
            cached_rows = cached[selected.title].iter_rows(**bounds)
            output_size = 0
            for row, (raw_row, cached_row) in enumerate(zip(raw_rows, cached_rows), first_row):
                for col, (cell, stored) in enumerate(zip(raw_row, cached_row), first_col):
                    if cell.value is None:
                        continue
                    address = f"{get_column_letter(col)}{row}"
                    if cell.data_type == "f":
                        formula = cell.value if isinstance(cell.value, str) else getattr(cell.value, "text", None)
                        line = f"{address}: formula={compact(formula or type(cell.value).__name__)} cached={compact(stored.value)}"
                    else:
                        line = f"{address}: value={compact(cell.value)}"
                    output_size += len(line) + 1
                    if output_size > 5500:
                        print("[Cell preview truncated; request a smaller range.]")
                        return
                    print(line)
            if not output_size:
                print("[No nonblank cells in the sampled range. Request a different cell_range to inspect more.]")
        finally:
            cached.close()
    finally:
        formulas.close()


try:
    preview(*json.loads(sys.argv[1]))
except Exception as exc:
    sys.exit(f"Workbook preview unavailable: {type(exc).__name__}: {str(exc)[:220]}")
'''


async def workbook_preview(transport, path, sheet=None, cell_range="A1:H12"):
    if any(value is not None and (not isinstance(value, str) or "\x00" in value)
           for value in (path, sheet, cell_range)) or cell_range is None:
        return "[read_file] workbook path, sheet and cell_range must be strings without NUL bytes"
    arguments = json.dumps([path, sheet, cell_range])
    command = f"{quote_path(transport.python_cmd)} -c {quote_path(PREVIEW_SOURCE)} {quote_path(arguments)}"
    result = await transport.exec(command, timeout_sec=15)
    output = result.get("output") or ""
    if result.get("timed_out"):
        return "[read_file] workbook preview timed out; use run_python for a targeted inspection"
    return output.rstrip() if output else "[read_file] workbook preview unavailable"
