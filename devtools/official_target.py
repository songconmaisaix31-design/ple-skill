"""Attest to the preregistered wind ZIP without publishing paths or member names."""
import json
import re
import sys
import zipfile

from official_export import ENTRY, EVIDENCE, PILOT, TASKS, TEMP, sha256, write
from kit import artifacts


SOURCE_CHECKS = ("target_declared", "trial_matched", "declared_zip_captured",
                 "zip_readable", "declared_zip_exported")
FINAL_CHECK = "replay_input_matches"


def regular(path):
    # The run and submission directories are absolute, host-owned paths.
    # Reject a link at the leaf or anywhere on the way to it before reading.
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError
    return path


def record(path):
    return json.loads(regular(path).read_bytes())


def target_path():
    # These same absolute paths are passed to Harbor by the frozen eval/run.py.
    paths = TASKS[PILOT]["deliverables"]
    if len(paths) != 1 or not paths[0].startswith("/") or not paths[0].lower().endswith(".zip"):
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


def matches_export(folder, relative, expected_hash):
    listed = record(folder / "manifest.json")["tasks"][PILOT]["files"]
    if relative not in listed:
        return False
    path = regular(folder / PILOT / "files" / relative)
    return (path.stat().st_size <= artifacts.MAX_FILE_BYTES
            and artifacts.file_blob_id(path) == listed[relative] and sha256(path) == expected_hash)


def check_capture(report):
    report["target_declared"] = False
    relative = target_path()
    report["target_declared"] = True
    run = TEMP / "run"
    report["trial_matched"] = False
    rows = record(run / "export.json")["rows"]
    results = record(run / "results.json")["tasks"]
    if (len(rows) != 1 or rows[0]["task"] != PILOT or len(results) != 1 or results[0]["id"] != PILOT
            or rows[0]["trial"] != results[0]["trial"] or artifacts.path_problem(rows[0]["trial"])):
        return
    report["trial_matched"] = True
    cap = run / rows[0]["trial"] / "deliverables"
    report["declared_zip_captured"] = False
    capture = record(cap / "capture.json")
    if capture.get("error") or relative not in capture["files"]:
        return
    path = regular(cap / "files" / relative)
    size = capture["files"][relative]["bytes"]
    if type(size) is not int or size != path.stat().st_size or size > artifacts.MAX_FILE_BYTES:
        return
    report["declared_zip_captured"] = True
    report["target_sha256"] = sha256(path)
    report["declared_zip_exported"] = False
    report["declared_zip_exported"] = matches_export(run / "artifacts", relative, report["target_sha256"])
    report["zip_readable"] = False
    report["zip_readable"] = readable_zip(path)


def complete(report, checks):
    return (all(report.get(k) is True for k in checks)
            and re.fullmatch("[0-9a-f]{64}", report.get("target_sha256") or "") is not None)


def verified_target(path):
    try:
        report = record(path)
        if complete(report, (*SOURCE_CHECKS, FINAL_CHECK)):
            return {k: report[k] for k in (*SOURCE_CHECKS, FINAL_CHECK, "target_sha256")}
    except (ValueError, OSError, TypeError, AttributeError):
        pass
    raise SystemExit("The recorded pilot ZIP verification is incomplete.")


def main(task, phase):
    if task != PILOT:
        return
    report = dict.fromkeys((*SOURCE_CHECKS, FINAL_CHECK, "target_sha256"))
    checks = SOURCE_CHECKS
    try:
        if phase == "capture":
            check_capture(report)
        elif phase == "export":
            checks = (*SOURCE_CHECKS, FINAL_CHECK)
            prior = record(EVIDENCE / "target.json")
            # Only known fields written during this host-side run enter evidence.
            if complete(prior, SOURCE_CHECKS):
                report.update({k: prior[k] for k in (*SOURCE_CHECKS, "target_sha256")})
                report[FINAL_CHECK] = False
                report[FINAL_CHECK] = matches_export(ENTRY / "artifacts", target_path(), report["target_sha256"])
        else:
            raise ValueError
        accepted = complete(report, checks)
    except Exception:
        # Malformed archives and filesystem exceptions can include restricted names.
        accepted = False
    write("target.json", report)
    if not accepted:
        raise SystemExit("The declared pilot ZIP did not pass verification.")


if __name__ == "__main__":
    main(*sys.argv[1:])
