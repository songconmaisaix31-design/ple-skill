#!/usr/bin/env python3
"""Check the PLE artifact guard against original, labeled delivery scenarios.

Run against one checkout with --entry, or compare an unchanged checkout with
--baseline and --entry. This uses no model, Docker, or PLE benchmark data.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


COMMISSIONING = """Package the invented air-system commissioning record. Use
`inputs/sensor-map.md` as a reference only. Save the package as
`export/commissioning.zip`. The following three members are required, each at
the exact path given below. Optional supplementary evidence may go under
`notes/`, such as `notes/calibration-context.md`.

### 1. `tables/pressure.csv`
Columns, exactly these names:

```text
station,pressure_pa,status
```

Keep this exact order and do not add other columns.

### 2. `records/instruments.json`
Write a valid JSON object. The maximum error must be a finite JSON number.

### 3. `report.docx`
Write a concise handoff note. One paragraph is enough.
"""

PUMP_INSPECTION = """Assemble the pump inspection handover. Read the source log
`inputs/site-log.csv` and the historical references `inputs/old-register.json`.
Save the deliverables under `output/`. Required files: `output/logs/readings.csv`
and `output/inspection.json`. The readings CSV must have these columns in this
exact order: location,flow_lps,verified. Optional photographs and comments may
be placed in `output/evidence/`.
"""

VIBRATION_RECORD = """Record an invented shaker test. Save `measurements.csv`
and `calibration.json` directly in the working directory. Both are required.
The CSV must contain the columns sensor,frequency_hz,amplitude_mm in any order.
The calibration file must be valid JSON with a finite reference amplitude.
"""

EQUIPMENT_MEMO = """Save the safety-walk handoff as `handoff/observations.docx`.
Describe the verified clearance in a single paragraph. Do not reproduce the
background note from `inputs/walkthrough.md`.
"""

SENSOR_REGISTER = """Export the updated sensor register to `results/sensors.csv`.
The required CSV header columns are sensor,channel,units, in any order.
An additional notes column is permitted.
"""


@dataclass(frozen=True)
class Case:
    scenario: str
    name: str
    instruction: str
    files: dict[str, bytes]
    valid: bool


def zip_bytes(files):
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


def docx_bytes(*paragraphs):
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    body = "".join(f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>" for paragraph in paragraphs)
    document = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>{body}<w:sectPr/></w:body>
</w:document>"""
    return zip_bytes({"[Content_Types].xml": content_types.encode(),
                      "_rels/.rels": relationships.encode(),
                      "word/document.xml": document.encode()})


def omit(files, name):
    return {path: data for path, data in files.items() if path != name}


def move(files, source, destination):
    return {**omit(files, source), destination: files[source]}


def cases():
    short_report = docx_bytes("Supply air was stable. The isolation switch was labeled and inspected.")
    report = docx_bytes("Supply air was stable at station P1.", "Static pressure measured 42 Pa.",
                        "The installed instrument was verified before use.",
                        "Maximum recorded instrument error was 0.6 Pa.",
                        "Leave the isolation switch labeled and the service panel closed.")
    archive_members = {
        "tables/pressure.csv": b"station,pressure_pa,status\nP1,42,normal\n",
        "records/instruments.json": b'{"sensor":"P1","max_error_pa":0.6}\n',
        "report.docx": report,
    }
    archive_cases = (
        ("required members only", archive_members, True),
        ("concise report in package", {**archive_members, "report.docx": short_report}, True),
        ("optional evidence included", {**archive_members, "notes/calibration-context.md":
                                        b"# Calibration\nReference adjusted at 08:00.\n"}, True),
        ("missing required CSV", omit(archive_members, "tables/pressure.csv"), False),
        ("missing required JSON", omit(archive_members, "records/instruments.json"), False),
        ("malformed required JSON", {**archive_members, "records/instruments.json": b'{"sensor":'}, False),
        ("nonfinite required JSON", {**archive_members, "records/instruments.json":
                                     b'{"sensor":"P1","max_error_pa":NaN}\n'}, False),
        ("missing required DOCX", omit(archive_members, "report.docx"), False),
        ("incorrect CSV labels", {**archive_members, "tables/pressure.csv":
                                   b"station,pressure_psi,status\nP1,42,normal\n"}, False),
        ("incorrect exact CSV order", {**archive_members, "tables/pressure.csv":
                                       b"pressure_pa,station,status\n42,P1,normal\n"}, False),
        ("extra forbidden CSV column", {**archive_members, "tables/pressure.csv":
                                        b"station,pressure_pa,status,note\nP1,42,normal,none\n"}, False),
        ("suffix collision in ZIP", move(archive_members, "tables/pressure.csv", "backup/tables/pressure.csv"),
         False),
    )
    for name, members, valid in archive_cases:
        yield Case("commissioning ZIP", name, COMMISSIONING,
                   {"export/commissioning.zip": zip_bytes(members),
                    "inputs/sensor-map.md": b"# Location map\nP1: supply duct.\n"}, valid)
    yield Case("commissioning ZIP", "damaged outer package", COMMISSIONING,
               {"export/commissioning.zip": b"PK\x03\x04"}, False)

    pump_files = {
        "inputs/site-log.csv": b"location,flow_lps,verified\nlegacy,0,no\n",
        "inputs/old-register.json": b'{"historical":true}\n',
        "output/logs/readings.csv": b"location,flow_lps,verified\nP3,7.2,yes\n",
        "output/inspection.json": b'{"pump":"P3","observed":"stable"}\n',
    }
    pump_cases = (
        ("required paths only", pump_files, True),
        ("extra valid evidence", {**pump_files, "output/evidence/notes.txt": b"No visible leakage.\n"}, True),
        ("right CSV basename under wrong parent", move(pump_files, "output/logs/readings.csv",
                                                       "output/backup/readings.csv"), False),
        ("wrong exact CSV order in directory", {**pump_files, "output/logs/readings.csv":
                                                 b"flow_lps,location,verified\n7.2,P3,yes\n"}, False),
        ("missing JSON in directory", omit(pump_files, "output/inspection.json"), False),
        ("malformed JSON in directory", {**pump_files, "output/inspection.json": b'{"pump":'}, False),
    )
    for name, files, valid in pump_cases:
        yield Case("pump handover directory", name, PUMP_INSPECTION, files, valid)

    vibration_files = {
        "measurements.csv": b"frequency_hz,amplitude_mm,sensor\n30,1.2,S2\n",
        "calibration.json": b'{"reference_amplitude_mm":1.0}\n',
    }
    yield Case("shaker records", "both root files with unordered columns", VIBRATION_RECORD, vibration_files, True)
    yield Case("shaker records", "one of two root files missing", VIBRATION_RECORD,
               omit(vibration_files, "calibration.json"), False)
    yield Case("shaker records", "missing required unordered column", VIBRATION_RECORD,
               {**vibration_files, "measurements.csv": b"frequency_hz,sensor\n30,S2\n"}, False)

    yield Case("equipment memo", "valid one-paragraph OOXML", EQUIPMENT_MEMO,
               {"handoff/observations.docx": short_report}, True)
    yield Case("equipment memo", "invalid OOXML", EQUIPMENT_MEMO,
               {"handoff/observations.docx": b"This file is not an OOXML package."}, False)

    yield Case("sensor register", "unordered required columns and allowed addition", SENSOR_REGISTER,
               {"results/sensors.csv": b"notes,units,sensor,channel\ncalibrated,Pa,P1,7\n"}, True)
    yield Case("sensor register", "required column missing despite allowed addition", SENSOR_REGISTER,
               {"results/sensors.csv": b"notes,units,sensor\ncalibrated,Pa,P1\n"}, False)


VALIDATOR_RESULT = re.compile(r"^RESULT:\s*(PASS|WARN|FAIL)(?:\s|$)", re.MULTILINE)


def read_spec(entry, instruction):
    script = "import json, runpy, sys; print(json.dumps(runpy.run_path(sys.argv[1])['build'](sys.stdin.read())))"
    result = subprocess.run([sys.executable, "-c", script, str(entry / "skillkit/specgen.py")],
                            input=instruction, capture_output=True, text=True, timeout=10, check=True)
    return json.loads(result.stdout)


def validate(entry, case, spec):
    with TemporaryDirectory(prefix="ple-artifact-regression-") as temporary:
        root = Path(temporary)
        work = root / "work"
        work.mkdir()
        for relative, data in case.files.items():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        check = subprocess.run([sys.executable, str(entry / "skills/_shared/validate.py"),
                                "--base", str(work), "--spec", str(spec_path)],
                               capture_output=True, text=True, timeout=10)
    result = VALIDATOR_RESULT.search(check.stdout)
    if result:
        status = result.group(1)
    elif check.returncode == 1 and check.stdout.startswith("FAIL:"):
        status = "FAIL"
    else:
        status = "ERROR"
    details = [line.strip() for line in check.stdout.splitlines() if line.strip().startswith(("FAIL", "WARN"))]
    if status == "ERROR":
        details.extend(check.stderr.splitlines()[-2:])
    return status, " | ".join(details)


def check_entry(entry, case_list, verbose):
    entry = entry.resolve()
    specs = {}
    counts = Counter()
    print(f"Entry: {entry}")
    for case in case_list:
        if case.instruction not in specs:
            specs[case.instruction] = read_spec(entry, case.instruction)
        spec = specs[case.instruction]
        status, details = validate(entry, case, spec)
        expected = "accept" if case.valid else "reject"
        actual = {"PASS": "accept", "WARN": "accept", "FAIL": "reject", "ERROR": "error"}[status]
        verdict = {("accept", "accept"): "valid accepted", ("reject", "reject"): "invalid rejected",
                   ("accept", "reject"): "false negative", ("reject", "accept"): "false positive"}.get(
                       (expected, actual), "validator error")
        counts[verdict] += 1
        print(f"  {case.scenario} / {case.name}: expected={expected}, actual={actual} ({status}), {verdict}")
        if verbose and details:
            print(f"    {details}")
    summary = (f"total={len(case_list)}; valid accepted={counts['valid accepted']}; "
               f"invalid rejected={counts['invalid rejected']}; false positives={counts['false positive']}; "
               f"false negatives={counts['false negative']}; validator errors={counts['validator error']}")
    print(f"Summary: {summary}")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--baseline", type=Path, help="compare against a separate unchanged checkout first")
    parser.add_argument("--verbose", action="store_true", help="show the validator's failure or warning details")
    args = parser.parse_args()
    case_list = list(cases())
    if args.baseline:
        check_entry(args.baseline, case_list, args.verbose)
    final = check_entry(args.entry, case_list, args.verbose)
    return int(any(final[key] for key in ("false positive", "false negative", "validator error")))


if __name__ == "__main__":
    sys.exit(main())
