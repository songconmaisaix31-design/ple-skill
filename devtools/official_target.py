"""Attest to the declared wind ZIP and data hall source without publishing their contents."""
import json
import re
import sys
import tokenize
import zipfile

from official_export import ENTRY, EVIDENCE, MODEL, PILOT, TASKS, TEMP, sha256, write
from kit import artifacts


TRANSFER = "data-hall-mep-routing"
FILE_CHECKS = {
    PILOT: ("declared_zip_captured", "zip_readable", "declared_zip_exported"),
    TRANSFER: ("declared_source_captured", "source_nonempty_readable", "declared_source_exported"),
}
FINAL_CHECK = "replay_input_matches"
REPLAY_CHECK = "replay_wrote_declared_source"


def requires_target(task):
    return task in FILE_CHECKS


def regular(path):
    # The run and submission directories are absolute, host-owned paths.
    # Reject a link at the leaf or anywhere on the way to it before reading.
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError
    return path


def record(path):
    return json.loads(regular(path).read_bytes())


def target_path(task):
    # These same absolute paths are passed to Harbor by the frozen eval/run.py.
    spec = TASKS[task]
    paths = spec["deliverables"]
    suffix = ".zip" if task == PILOT else ".py"
    if len(paths) != 1 or not paths[0].startswith("/") or not paths[0].lower().endswith(suffix):
        raise ValueError
    if task == TRANSFER and (spec["grading"] != "checks" or spec["final_message"] is not False):
        raise ValueError
    relative = paths[0][1:]
    if artifacts.path_problem("files/" + relative):
        raise ValueError
    return relative


def readable_zip(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        # Match the existing publication inspection budget. Read each member by
        # ZipInfo so duplicate names cannot hide a corrupt earlier member.
        if len(members) > 10000 or sum(m.file_size for m in members) > 512 * 1024 ** 2:
            return False
        for member in members:
            with archive.open(member) as stream:
                while stream.read(1024 * 1024):
                    pass
    return True


def readable_source(path):
    # Honor the Python source encoding. Only decode text here; the official
    # verifier grades the submitted program inside its own container.
    nonblank = False
    with tokenize.open(path) as stream:
        for chunk in iter(lambda: stream.read(65536), ""):
            if "\x00" in chunk:
                return False
            if chunk.strip():
                nonblank = True
    return nonblank


def matches_export(task, folder, relative, expected_hash):
    listed = record(folder / "manifest.json")["tasks"][task]["files"]
    if relative not in listed or (task == TRANSFER and set(listed) != {relative}):
        return False
    path = regular(folder / task / "files" / relative)
    return (path.stat().st_size <= artifacts.MAX_FILE_BYTES
            and artifacts.file_blob_id(path) == listed[relative] and sha256(path) == expected_hash)


def check_capture(task, report):
    report["target_declared"] = False
    relative = target_path(task)
    report["target_declared"] = True
    run = TEMP / "run"
    report["trial_matched"] = False
    rows = record(run / "export.json")["rows"]
    results = record(run / "results.json")["tasks"]
    if (len(rows) != 1 or rows[0]["task"] != task or len(results) != 1 or results[0]["id"] != task
            or rows[0]["trial"] != results[0]["trial"] or artifacts.path_problem(rows[0]["trial"])):
        return
    report["trial_matched"] = True
    cap = run / rows[0]["trial"] / "deliverables"
    captured, readable, exported = FILE_CHECKS[task]
    report[captured] = False
    capture = record(cap / "capture.json")
    if capture.get("error") or relative not in capture["files"]:
        return
    path = regular(cap / "files" / relative)
    size = capture["files"][relative]["bytes"]
    if type(size) is not int or size != path.stat().st_size or size > artifacts.MAX_FILE_BYTES:
        return
    report[captured] = True
    report["target_sha256"] = sha256(path)
    report[exported] = False
    report[exported] = matches_export(task, run / "artifacts", relative, report["target_sha256"])
    report[readable] = False
    report[readable] = readable_zip(path) if task == PILOT else readable_source(path)


def replay_wrote_source(task):
    # kit.replay_agent can finish and receive a score when a destination was
    # blocked. Its host-side log counts the files it actually wrote.
    root = TEMP / "replay"
    summary = record(root / "results.json")
    rows = summary["tasks"]
    if (summary.get("artifacts") is not True or summary.get("submission_dir") != str(ENTRY)
            or summary.get("model") != MODEL or summary.get("submission") != "skillguard-harness"
            or len(rows) != 1):
        return False
    row = rows[0]
    if (row["id"] != task or row["artifact"] != artifacts.OK or row["kind"] != "ok"
            or row["measured"] is not True or artifacts.path_problem(row["trial"])):
        return False
    log = regular(root / row["trial"] / "agent/skillguard-harness.txt")
    with log.open("rb") as stream:
        notes, marker, _ = stream.read(4096).partition(b"\nreplay of the submitted artifacts: no harness, no model\n")
    return bool(marker and b"wrote 1 file(s)" in notes.splitlines())


def complete(report, checks):
    return (all(report.get(k) is True for k in checks)
            and re.fullmatch("[0-9a-f]{64}", report.get("target_sha256") or "") is not None)


def verified_target(path, task=PILOT):
    checks = ("target_declared", "trial_matched", *FILE_CHECKS[task], FINAL_CHECK)
    if task == TRANSFER:
        checks += (REPLAY_CHECK,)
    try:
        report = record(path)
        if complete(report, checks):
            return {k: report[k] for k in (*checks, "target_sha256")}
    except (ValueError, OSError, TypeError, AttributeError):
        pass
    raise SystemExit("The recorded target verification is incomplete.")


def main(task, phase):
    if not requires_target(task) or (phase == "replay" and task != TRANSFER):
        return
    checks = ("target_declared", "trial_matched", *FILE_CHECKS[task])
    report = dict.fromkeys((*checks, FINAL_CHECK, "target_sha256"))
    if task == TRANSFER:
        report[REPLAY_CHECK] = None
    try:
        if phase == "capture":
            check_capture(task, report)
        elif phase in ("export", "replay"):
            if phase == "replay":
                checks += (FINAL_CHECK,)
            prior = record(EVIDENCE / "target.json")
            field = FINAL_CHECK if phase == "export" else REPLAY_CHECK
            if complete(prior, checks):
                report.update({k: prior[k] for k in (*checks, "target_sha256")})
                report[field] = False
                if phase == "export":
                    report[field] = matches_export(task, ENTRY / "artifacts", target_path(task), report["target_sha256"])
                else:
                    report[field] = replay_wrote_source(task)
            checks += (field,)
        else:
            raise ValueError
        accepted = complete(report, checks)
    except Exception:
        # Malformed archives and filesystem exceptions can include restricted names.
        accepted = False
    write("target.json", report)
    if not accepted:
        raise SystemExit("The declared target did not pass verification.")


if __name__ == "__main__":
    main(*sys.argv[1:])
