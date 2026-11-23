"""Build canonical H/I evidence from six raw Actions job artifacts.

The experiment recorder accidentally shadowed ``first_mode`` with the unique
scripted first-response record.  This builder repairs only that redundant
field, and only when the raw value exactly matches the corresponding record in
the immutable model-I/O transcript.  Raw job artifacts remain separate.
"""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


ARMS = ("text", "text-source")
MEMBERS = (
    "metadata.json", "report.json", "model-io.jsonl",
    "case/task.md", "case/input/site.json", "case/input/periods.csv",
    "case/output/schedule.csv", "case/output/summary.json",
)
RAW_LOGS = ("startup.log", "probe.log", "server.log", "experiment.log")
STAMP = (2026, 11, 24, 0, 0, 0)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_job(value):
    try:
        case, repeat, path = value.split(":", 2)
        repeat = int(repeat)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError("job must be CASE:REPEAT:ARTIFACT.zip") from error
    if case not in ("h", "i") or repeat not in (1, 2, 3) or not path:
        raise argparse.ArgumentTypeError("job must name H/I and repeat 1, 2 or 3")
    return case, repeat, Path(path)


def transcript_records(data):
    records = [json.loads(line) for line in data.splitlines()]
    require(records and records[-1].get("event") == "end", "model transcript lacks end record")
    return records[:-1]


def normalize_metadata(data, transcript, protocol, case, repeat, arm):
    metadata = json.loads(data)
    require(isinstance(metadata, dict), "metadata is not an object")
    expected_first = protocol["design"]["first_arm"][case][str(repeat)]
    expected_order = 1 if arm == expected_first else 2
    expected = {"variant": case, "repeat": repeat, "mode": arm, "order": expected_order}
    require(all(metadata.get(key) == value for key, value in expected.items()),
            f"{case}/{repeat}/{arm}: assignment metadata differs from protocol")
    original = metadata.get("first_mode")
    correction = None
    if original != expected_first:
        scripted = [record for record in transcript_records(transcript)
                    if record.get("event") == "response" and record.get("call") == 1
                    and record.get("scripted") is True]
        require(len(scripted) == 1 and original == scripted,
                f"{case}/{repeat}/{arm}: first_mode is neither valid nor the exact shadowed record")
        before = digest(data)
        metadata["first_mode"] = expected_first
        data = (json.dumps(metadata, indent=2) + "\n").encode()
        correction = {
            "path": f"{case}/{repeat}/{arm}/metadata.json",
            "field": "first_mode",
            "reason": "recorder local-variable shadowing",
            "reconstructed_from": "protocol design.first_arm after exact model-io scripted-response match",
            "before_sha256": before,
            "after_sha256": digest(data),
        }
    return data, correction


def build(protocol_bytes, jobs):
    protocol = json.loads(protocol_bytes)
    require(protocol.get("id") == "controlled-repair-replay-v1", "wrong protocol")
    expected_pairs = {(case, repeat) for case in ("h", "i") for repeat in (1, 2, 3)}
    require(set(jobs) == expected_pairs and len(jobs) == len(expected_pairs),
            "provide exactly one raw job artifact for every H/I repeat")
    members = {}
    corrections = []
    sources = []
    for (case, repeat), path in sorted(jobs.items()):
        raw = path.read_bytes()
        sources.append({"case": case, "repeat": repeat, "file": path.name,
                        "sha256": digest(raw)})
        with ZipFile(path) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), f"{path}: duplicate ZIP member")
            allowed = {f"{arm}/{name}" for arm in ARMS for name in (*MEMBERS, *RAW_LOGS)}
            require(set(names) <= allowed, f"{path}: unexpected artifact member")
            for arm in ARMS:
                transcript_name = f"{arm}/model-io.jsonl"
                metadata_name = f"{arm}/metadata.json"
                require(transcript_name in archive.NameToInfo and metadata_name in archive.NameToInfo,
                        f"{path}: missing {arm} transcript or metadata")
                transcript = archive.read(transcript_name)
                metadata, correction = normalize_metadata(
                    archive.read(metadata_name), transcript, protocol, case, repeat, arm)
                if correction:
                    corrections.append(correction)
                for member in MEMBERS:
                    source = f"{arm}/{member}"
                    if source not in archive.NameToInfo:
                        continue
                    target = f"{case}/{repeat}/{arm}/{member}"
                    members[target] = metadata if member == "metadata.json" else archive.read(source)
    require(len(corrections) == 12,
            "expected the preregistered recorder-shadow correction in all twelve arms")
    return members, {"protocol_sha256": digest(protocol_bytes), "sources": sources,
                     "corrections": corrections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--job", required=True, action="append", type=parse_job)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--corrections", required=True, type=Path)
    args = parser.parse_args()
    try:
        jobs = {}
        for case, repeat, path in args.job:
            require((case, repeat) not in jobs, "duplicate pair argument")
            jobs[case, repeat] = path
        members, audit = build(args.protocol.read_bytes(), jobs)
        require(not args.output.exists() and not args.corrections.exists(), "outputs must be new files")
        with ZipFile(args.output, "x") as archive:
            for path, data in sorted(members.items()):
                info = ZipInfo(path, date_time=STAMP)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        args.corrections.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        print(f"{digest(args.output.read_bytes())}  {args.output}")
    except (BadZipFile, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
