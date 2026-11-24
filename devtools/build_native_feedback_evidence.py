"""Build deterministic N/O evidence from the six immutable Actions artifacts."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


ARMS = ("native-patch", "native-feedback")
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
    if case not in ("n", "o") or repeat not in (1, 2, 3) or not path:
        raise argparse.ArgumentTypeError("job must name N/O and repeat 1, 2 or 3")
    return case, repeat, Path(path)


def build(protocol_bytes, jobs):
    protocol = json.loads(protocol_bytes)
    require(protocol.get("id") == "native-feedback-v1", "wrong protocol")
    expected = {(case, repeat) for case in ("n", "o") for repeat in (1, 2, 3)}
    require(set(jobs) == expected and len(jobs) == 6, "provide one artifact for every N/O repeat")
    members, sources = {}, []
    for (case, repeat), path in sorted(jobs.items()):
        raw = path.read_bytes()
        sources.append({"case": case, "repeat": repeat, "file": path.name, "sha256": digest(raw)})
        with ZipFile(path) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), f"{path}: duplicate ZIP member")
            allowed = {f"{arm}/{name}" for arm in ARMS for name in (*MEMBERS, *RAW_LOGS)}
            require(set(names) <= allowed, f"{path}: unexpected artifact member")
            expected_first = protocol["design"]["first_arm"][case][str(repeat)]
            for arm in ARMS:
                prefix = f"{arm}/"
                require(prefix + "metadata.json" in archive.NameToInfo, f"{path}: missing {arm} metadata")
                require(prefix + "model-io.jsonl" in archive.NameToInfo, f"{path}: missing {arm} transcript")
                metadata = json.loads(archive.read(prefix + "metadata.json"))
                expected_order = 1 if arm == expected_first else 2
                require(all(metadata.get(key) == value for key, value in {
                    "variant": case, "repeat": repeat, "mode": arm,
                    "order": expected_order, "first_mode": expected_first,
                }.items()), f"{case}/{repeat}/{arm}: assignment differs from protocol")
                for member in MEMBERS:
                    source = prefix + member
                    if source in archive.NameToInfo:
                        members[f"{case}/{repeat}/{arm}/{member}"] = archive.read(source)
    return members, {"protocol_sha256": digest(protocol_bytes), "sources": sources, "corrections": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--job", required=True, action="append", type=parse_job)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()
    try:
        jobs = {}
        for case, repeat, path in args.job:
            require((case, repeat) not in jobs, "duplicate pair")
            jobs[case, repeat] = path
        members, audit = build(args.protocol.read_bytes(), jobs)
        require(not args.output.exists() and not args.audit.exists(), "outputs must be new")
        with ZipFile(args.output, "x") as archive:
            for path, data in sorted(members.items()):
                info = ZipInfo(path, date_time=STAMP)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        args.audit.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        print(f"{digest(args.output.read_bytes())}  {args.output}")
    except (BadZipFile, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
