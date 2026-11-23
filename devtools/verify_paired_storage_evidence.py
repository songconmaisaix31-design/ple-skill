"""Replay a fixed-seed storage experiment from its evidence ZIP, without running model code."""
import argparse
import ast
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from design_regression import grade, prepare


INPUTS = ("task.md", "input/site.json", "input/periods.csv")
OUTPUTS = ("schedule.csv", "summary.json")
MODEL = "gemma-4-26b"
SHA = re.compile(r"[0-9a-f]{40}")
FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)\n```", re.I | re.S)
FIELDS = ("case", "repeat", "arm", "order", "seed", "score", "feasible", "optimal",
          "measured", "submitted_cost_cents", "first_verified_sec", "evidence_status",
          "transcript_complete", "requests_archived", "responses_archived",
          "programs_recovered", "programs_parseable", "git_sha")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(zf, name, size):
    try:
        member = zf.getinfo(name)
    except KeyError:
        return None
    require(member.file_size <= size and not member.is_dir(), f"invalid member {name}")
    return zf.read(member)


def load_json(zf, name):
    data = read(zf, name, 256 * 1024)
    if data is None:
        return None
    record = json.loads(data)
    require(isinstance(record, dict), f"invalid JSON record {name}")
    return record


def program_detail(source, call, interface):
    # Only identify parseable source. Never execute or import any generated program.
    check = source.strip()
    if fenced := FENCE.fullmatch(check):
        check = fenced.group(1)
    try:
        ast.parse(check)
        valid = bool(check)
    except (ValueError, SyntaxError, RecursionError):
        valid = False
    return {"call": call, "interface": interface, "source_sha256": digest(source.encode()),
            "parseable": valid}


REPAIR_FIELDS = ("repair_requested", "source_feedback_observed", "source_line", "completed_files")
SOURCE_TITLE = re.compile(r"\n\nFirst program source near traceback line (\d+):\n")
ERROR_MESSAGE = "The first Python program did not run cleanly. Inspect any outputs and use the normal tools."
DIAGNOSTICS = ERROR_MESSAGE + "\n\nSandbox diagnostics, for debugging only:\n"
TRACEBACK_HEADER = "\nTraceback (most recent call last):\n"
TRACEBACK_FRAME = re.compile(r'^  File "([^"\n]+)", line ([1-9][0-9]{0,6})(?:, in [^\n]+)?$', re.M)


def repair_exposure(requests, responses, complete, arm, event):
    # Inspect what was actually sent in a subsequent request, even when its
    # inference was interrupted. Never infer exposure from the assigned arm.
    unknown = None if not complete else 0
    fields = {"repair_requested": unknown, "source_feedback_observed": unknown, "source_line": None}
    for request_id, request in sorted(requests.items()):
        messages = request["body"].get("messages") or []
        if (request_id < 2 or len(messages) < 3 or
                [m.get("role") for m in messages[:3]] != ["system", "user", "user"]):
            continue
        observation = messages[2].get("content")
        if not isinstance(observation, str) or not observation.startswith(ERROR_MESSAGE):
            continue
        fields["repair_requested"] = 1
        marker = SOURCE_TITLE.search(observation)
        if not marker:
            fields["source_feedback_observed"] = 0
            return fields
        require(arm == "text-source", "baseline received an added source excerpt")
        require(observation.startswith(DIAGNOSTICS), "source feedback lacks sandbox diagnostics")
        if not event and not complete:
            return fields
        require(event.get("mode") == "text" and event.get("classification") == "exec_failed" and type(event.get("exec_exit_status")) is int
                and event["exec_exit_status"] != 0, "source feedback lacks a matching failed execution")
        number = int(marker[1])
        diagnostics = observation[len(DIAGNOSTICS):marker.start()]
        _, found, traceback = ("\n" + diagnostics).rpartition(TRACEBACK_HEADER)
        traceback = traceback.rstrip("\n")
        frames = list(TRACEBACK_FRAME.finditer(traceback))
        require(found and traceback.startswith("  File ") and frames and
                frames[-1].groups() == ("<run_python>", str(number)) and
                "\n  File " not in traceback[frames[-1].end():] and
                re.fullmatch(r"[A-Za-z_][\w.]*(?::.*)?", traceback.rsplit("\n", 1)[-1]),
                "source location disagrees with final traceback")
        response = responses.get(1)
        if not response and not complete:
            return fields
        require(response and response.get("choices"), "source excerpt has no archived first response")
        source = response["choices"][0]["message"].get("content")
        require(isinstance(source, str), "source excerpt has no first text program")
        source = source.strip()
        if fence := FENCE.fullmatch(source):
            source = fence[1]
        source = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        require(1 <= number <= len(source), "excerpt traceback line lies outside first program")
        positions = range(max(1, number - 2), min(len(source), number + 2) + 1)
        width = (800 - len(marker[0]) + 1) // len(positions) - 1
        expected = []
        for i in positions:
            row = f"{i}: {source[i - 1]}"
            expected.append(row if len(row) <= width else row[:width - 1] + "…")
        require(observation[marker.end():] == "\n".join(expected), "excerpt differs from archived first program")
        fields.update(source_feedback_observed=1, source_line=number)
        return fields
    return fields


def transcript(data, summary, arm, recorder_complete, repair_event=None):
    requests, responses, statuses = {}, {}, {}
    programs = []
    end = None
    if data:
        lines = data.splitlines()
        for index, line in enumerate(lines):
            try:
                rec = json.loads(line)
            except (UnicodeError, ValueError):
                if index == len(lines) - 1 and not data.endswith(b"\n"):
                    # An interrupted transfer can end partway through one record.
                    end = None
                    break
                raise
            event = rec["event"]
            require(end is None, "transcript continued after end")
            if event == "end":
                end = rec
                continue
            call = rec["call"]
            require(type(call) is int and call > 0, "invalid model call ID")
            if event == "request":
                require(call not in requests, "duplicate model request")
                requests[call] = rec
            elif event == "response":
                require(call not in responses, "duplicate model response")
                responses[call] = rec
                for choice in rec["choices"]:
                    msg = choice["message"]
                    if arm in ("text", "text-source") and call == 1 and isinstance(msg.get("content"), str) and msg["content"].strip():
                        programs.append(program_detail(msg["content"], call, "text-first"))
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        if fn.get("name") == "run_python":
                            args = fn.get("arguments")
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except ValueError:
                                    continue
                            if isinstance(args, dict) and isinstance(args.get("code"), str):
                                programs.append(program_detail(args["code"], call, "run_python"))
            elif event == "status":
                require(call not in statuses, "duplicate model status")
                statuses[call] = rec
            else:
                raise ValueError(f"unexpected transcript event {event!r}")
    if summary and end:
        require(all(end.get(k) == summary.get(k) for k in ("complete", "requests", "omitted_records_or_fields")),
                "transcript end metadata disagrees with the run report")
    if recorder_complete and end:
        require(summary and end == {"event": "end", **summary} and end.get("complete") is True,
                "recorder and transcript disagree on completeness")
    complete = bool(recorder_complete and end and summary and end.get("complete") is True and requests
                    and end.get("omitted_records_or_fields") == 0
                    and set(requests) == set(range(1, end["requests"] + 1))
                    and requests.keys() == statuses.keys() and responses.keys() <= requests.keys()
                    and all(key in responses for key, row in statuses.items()
                            if row.get("status") == "complete" and row.get("http_status") == 200))
    details = {"transcript_complete": int(complete), "requests_archived": len(requests),
            "responses_archived": len(responses), "programs_recovered": len(programs),
            "programs_parseable": sum(p["parseable"] for p in programs)}
    if repair_event is not None:
        details.update(repair_exposure(requests, responses, complete, arm, repair_event))
    return details, programs


def replay(zf, prefix, case, inventory, hashes):
    require(isinstance(inventory, dict) and type(inventory.get("output_directory")) is bool,
            "measured checkpoint has no directory inventory")
    folder = prefix + "case/output/"
    archived = {name[len(folder):] for name in zf.namelist()
                if name.startswith(folder) and not name.endswith("/")}
    require(archived <= set(OUTPUTS), "unexpected file in exported output")
    directory = inventory["output_directory"]
    if directory:
        require(type(inventory.get("extras")) is bool, "missing extra-file inventory")
    with TemporaryDirectory() as temp:
        root = Path(temp) / "case"
        prepare(root, case)
        for path in INPUTS:
            require(digest((root / path).read_bytes()) == hashes[path], "local fixture differs from frozen data")
        # The original host grader receives an output directory after strict export, even if empty.
        (root / "output").mkdir()
        for name in OUTPUTS:
            size = inventory.get(name)
            if directory:
                require(type(size) is int and size >= 0 or size in ("missing", "not_regular_or_oversized"),
                        f"invalid recorded size for {name}")
            expected = directory and not inventory["extras"] and type(size) is int and size <= 65536
            require(expected == (name in archived), f"inventory and artifact disagree for {name}")
            if expected:
                data = read(zf, folder + name, 65536)
                require(len(data) == size, f"byte count mismatch for {name}")
                (root / "output" / name).write_bytes(data)
        return grade(root, case)


def verify_arm(zf, protocol, protocol_hash, case, repeat, arm):
    prefix = f"{case}/{repeat}/{arm}/"
    first = protocol["design"]["first_arm"][case][str(repeat)]
    settings = protocol["fixed_settings"]
    row = dict.fromkeys(FIELDS)
    row.update(case=case, repeat=repeat, arm=arm, order=1 if arm == first else 2,
               seed=settings["seed"], measured=0, evidence_status="missing_arm")
    metadata = load_json(zf, prefix + "metadata.json")
    report = load_json(zf, prefix + "report.json")
    recorded_io = (metadata or {}).get("model_io_archive_complete", False)
    repair = protocol["id"] == "repair-source-v1"
    first_action = (report or {}).get("first_code_action") or {}
    details, programs = transcript(read(zf, prefix + "model-io.jsonl", 2 * 1024 * 1024 + 512),
                                   (report or {}).get("model_io_archive"), arm, recorded_io, first_action if repair else None)
    row.update(details)
    if repair and first_action:
        require(first_action.get("mode") == "text", "expected text-first mode in both repair arms")
    if metadata is None:
        require(not any(n.startswith(prefix) and not n.endswith("/") for n in zf.namelist()),
                "arm evidence lacks metadata")
        return row, programs
    expected = {"variant": case, "repeat": repeat, "mode": arm, "order": row["order"], "first_mode": first,
                "model": MODEL, "seed": settings["seed"], "temperature": settings["temperature"]}
    for key, value in expected.items():
        require(metadata.get(key) == value, f"metadata {key} disagrees with frozen assignment")
    require(isinstance(metadata.get("git_sha"), str) and SHA.fullmatch(metadata["git_sha"]),
            "expected a full Git revision")
    row["git_sha"] = metadata["git_sha"]
    hashes = protocol["split"]["cases"][case]["sha256"]
    require(metadata.get("protocol_sha256") == protocol_hash, "frozen protocol bytes disagree with recorder")
    require(metadata.get("protocol_input_sha256") == hashes, "preregistered input hashes disagree with recorder")
    require(type(metadata.get("model_io_archive_complete")) is bool, "missing transcript archive state")
    if repair:
        recorder_exposure = metadata.get("repair_context_exposed")
        require("repair_context_exposed" in metadata, "missing exposure metadata")
        if details["transcript_complete"]:
            require(recorder_exposure is bool(details["source_feedback_observed"]),
                    "independent source exposure disagrees with recorder")
        elif recorder_exposure is not None:
            require(type(recorder_exposure) is bool and details["source_feedback_observed"] is not None and
                    recorder_exposure == bool(details["source_feedback_observed"]),
                    "source exposure disagrees with incomplete recorder")
    actual_hashes = {}
    for name in INPUTS:
        data = read(zf, prefix + "case/" + name, 65536)
        if data is not None:
            actual_hashes[name] = digest(data)
            require(actual_hashes[name] == hashes[name], f"frozen input mismatch for {name}")
    require(actual_hashes == metadata.get("input_sha256"), "input checksums disagree with arm metadata")
    require(metadata.get("input_matches_protocol") is (actual_hashes == hashes),
            "frozen inputs and recorder verification disagree")
    require(type(metadata.get("observation")) is bool, "missing observation state")
    checkpoint = (report or {}).get("checkpoint") or {}
    recorded_grade = (report or {}).get("grade")
    measured = bool(report and metadata["phase"] == "experiment" and metadata["exit_code"] in (0, 1)
                    and not report.get("infrastructure_error") and checkpoint.get("measured") is True
                    and isinstance(recorded_grade, dict) and len(actual_hashes) == len(INPUTS))
    require(measured == metadata["observation"], "arm and checkpoint disagree on measurement")
    if report:
        require(report["variant"] == case and report["model"] == MODEL and
                report["budget_sec"] == settings["declared_budget_seconds"], "run configuration mismatch")
        if checkpoint:
            require(checkpoint.get("target_sec") == settings["external_checkpoint_seconds"],
                    "unexpected checkpoint time")
            if checkpoint.get("measured") is False:
                require(recorded_grade is None, "unmeasured checkpoint contained a grade")
    if not measured:
        row["evidence_status"] = "unmeasured"
        return row, programs
    start, stop = checkpoint["start_sec"], checkpoint["end_sec"]
    require(math.isfinite(start) and math.isfinite(stop) and stop >= start >= 0
            and (checkpoint.get("session_was_done") is True or start >= checkpoint["target_sec"] - .001),
            "checkpoint clock mismatch")
    verified = replay(zf, prefix, case, report["inventory"], hashes)
    for field in ("score", "optimal", "feasible", "submitted_cost_cents", "optimal_cost_cents"):
        require(recorded_grade.get(field) == verified[field], f"archived independent grade mismatch for {field}")
    require(metadata["exit_code"] == int(not verified["optimal"]), "grade and process status disagree")
    row.update(measured=1, score=verified["score"], feasible=int(verified["feasible"]),
               optimal=int(verified["optimal"]), submitted_cost_cents=verified["submitted_cost_cents"],
               evidence_status="regraded")
    if repair:
        folder = prefix + "case/output/"
        row["completed_files"] = sum(folder + name in zf.namelist() and zf.getinfo(folder + name).file_size > 0
                                     for name in OUTPUTS)
    event = report.get("first_code_action") or {}
    if event.get("classification") == "verified":
        require(event.get("mode") == ("text" if repair else arm) and type(event.get("millis")) is int and event["millis"] >= 0,
                "invalid first verified action")
        row["first_verified_sec"] = event["millis"] / 1000
    return row, programs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--expected-sha", help="independently known 40-character Actions head revision")
    p.add_argument("--details", type=Path, help="optional generated-source hashes and archive coverage JSON")
    a = p.parse_args()
    try:
        protocol_bytes = a.protocol.read_bytes()
        protocol = json.loads(protocol_bytes)
        protocol_hash = digest(protocol_bytes)
        require(protocol["id"] in ("paired-storage-v1", "repair-source-v1"), "wrong experiment protocol")
        repair = protocol["id"] == "repair-source-v1"
        arms = ("text", "text-source") if repair else ("legacy", "text")
        rows, programs = [], {}
        with ZipFile(a.archive) as zf:
            counts = Counter(zf.namelist())
            require(not any(n > 1 for n in counts.values()), "duplicate ZIP member")
            for case in protocol["split"]["holdout"]:
                for repeat in protocol["design"]["repetition_ids"]:
                    for arm in arms:
                        label = f"{case}/{repeat}/{arm}"
                        try:
                            row, sources = verify_arm(zf, protocol, protocol_hash, case, repeat, arm)
                        except (ValueError, TypeError, KeyError) as err:
                            raise ValueError(f"{label}: {err}") from err
                        rows.append(row)
                        programs[label] = sources
        revisions = {r["git_sha"] for r in rows if r["git_sha"]}
        require(len(revisions) <= 1 and (not a.expected_sha or
                SHA.fullmatch(a.expected_sha) and revisions <= {a.expected_sha}), "run revision mismatch")
        with a.csv.open("w", encoding="utf-8", newline="") as out:
            w = csv.DictWriter(out, fieldnames=FIELDS + REPAIR_FIELDS if repair else FIELDS)
            w.writeheader()
            w.writerows(rows)
        summary = {"planned": len(rows), "regraded": sum(r["measured"] for r in rows),
                   "missing_arms": sum(r["evidence_status"] == "missing_arm" for r in rows),
                   "complete_transcripts": sum(r["transcript_complete"] for r in rows),
                   "git_sha": next(iter(revisions), None)}
        if repair:
            summary["verified_candidate_exposures"] = sum(r.get("source_feedback_observed") == 1 for r in rows)
        if a.details:
            a.details.write_text(json.dumps({**summary, "programs": programs}, indent=2) + "\n")
        print(json.dumps(summary))
        return int(summary["regraded"] != summary["planned"])
    except (OSError, BadZipFile, ValueError, TypeError, KeyError, csv.Error) as err:
        p.error(str(err))


if __name__ == "__main__":
    raise SystemExit(main())
