#!/usr/bin/env python3
"""Exercise XLSX input previews against an invented pump workbook."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skillkit.harness import Harness
from skillkit.transport import LocalTransport


SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def make_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Flow checks"
    sheet["D7"], sheet["E7"] = "flow_lps", 12
    sheet["E8"], sheet["E9"], sheet["E10"] = "=E7*2", "=E7-E7", "=E7*3"
    hidden = workbook.create_sheet("Calibration")
    hidden.sheet_state = "hidden"
    hidden["K20"] = "reference point"
    hidden["K21"] = "long note " * 30
    draft = path.with_name("draft.xlsx")
    workbook.save(draft)
    workbook.close()

    # Write only test-fixture cache values. One is deliberately stale (20
    # instead of 24), one is zero, and E10 keeps its empty cache.
    with ZipFile(draft) as source, ZipFile(path, "w", ZIP_DEFLATED) as destination:
        for name in source.namelist():
            contents = source.read(name)
            if name == "xl/worksheets/sheet1.xml":
                tree = ET.fromstring(contents)
                for address, value in (("E8", "20"), ("E9", "0")):
                    cell = tree.find(f".//{SPREADSHEET_NS}c[@r='{address}']")
                    cell.find(f"{SPREADSHEET_NS}v").text = value
                contents = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
            destination.writestr(name, contents)


class TrackingTransport(LocalTransport):
    def __init__(self, root):
        super().__init__(root)
        self.read_paths = []

    async def read_file(self, path):
        self.read_paths.append(path)
        return await super().read_file(path)


async def exercise(root):
    path = root / "pump check's.xlsx"
    make_workbook(path)
    before = hashlib.sha256(path.read_bytes()).digest()
    (root / "broken.xlsx").write_bytes(b"Not an XLSX file.")
    (root / "directory.xlsx").mkdir()
    (root / "note.txt").write_text("normal text path", encoding="utf-8")

    transport = TrackingTransport(root)
    harness = Harness(transport, None, "Inspect the invented workbook for pump-flow source values.")

    async def read(name=path.name, **selection):
        return await harness._do({"name": "read_file", "arguments": {"path": name, **selection}})

    default = await read()
    for expected in ('"Flow checks" (visible)', '"Calibration" (hidden)', "sampled range A1:H12",
                     'D7: value="flow_lps"', 'E8: formula="=E7*2" cached=20',
                     'E9: formula="=E7-E7" cached=0', 'E10: formula="=E7*3" cached=null'):
        assert expected in default, default
    alternate = await read(sheet="Calibration", cell_range="K20:K21")
    assert "sampled range K20:K21" in alternate and 'K20: value="reference point"' in alternate, alternate
    assert "E8:" not in alternate and "K21: value=" in alternate and "[value truncated]" in alternate, alternate
    sparse = await read(sheet="Calibration")
    assert "No nonblank cells" in sparse and "sampled range A1:H12" in sparse, sparse
    assert "used range K20:K21 (advisory" in sparse and "K20: value" not in sparse, sparse
    assert "at most 96 cells" in await read(cell_range="A1:H13")
    assert "A1 reference" in await read(cell_range="A:H")
    assert "requested worksheet was not found" in await read(sheet="absent")
    assert "BadZipFile" in await read("broken.xlsx")
    assert "FileNotFoundError" in await read("absent.xlsx")
    assert "not a regular workbook file" in await read("directory.xlsx")
    if hasattr(os, "mkfifo"):
        os.mkfifo(root / "pipe.xlsx")
        assert "not a regular workbook file" in await read("pipe.xlsx")
    assert not transport.read_paths, transport.read_paths
    assert before == hashlib.sha256(path.read_bytes()).digest()
    assert "normal text path" == await read("note.txt")
    assert transport.read_paths == ["note.txt"]


def main():
    if Workbook is None:
        print("XLSX REGRESSION: SKIP (openpyxl unavailable in the test interpreter)")
        return 77
    with TemporaryDirectory(prefix="ple-workbook-regression-") as directory:
        asyncio.run(exercise(Path(directory)))
    print("XLSX REGRESSION: PASS (stored cache states, sheet and range, limits, no workbook writes, text compatibility)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
