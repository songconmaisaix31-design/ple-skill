"""Record and package one paired-run observation from its public fixture evidence."""

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def carries_source_excerpt(record):
    if record.get("event") != "request" or record.get("call", 0) < 2:
        return False
    messages = record.get("body", {}).get("messages", [])
    # The harness appends its first-action observation immediately after the
    # task. A wrap-up reminder can follow it in the same outbound request.
    if (len(messages) < 3 or [msg.get("role") for msg in messages[:3]] != ["system", "user", "user"]):
        return False
    observation = messages[2].get("content")
    prefix = ("The first Python program did not run cleanly. Inspect any outputs and use the normal tools."
              "\n\nSandbox diagnostics, for debugging only:\n")
    return (isinstance(observation, str) and observation.startswith(prefix)
            and re.search(r"\n\nFirst program source near traceback line [1-9][0-9]*:\n"
                          r"(?:[1-9][0-9]*: [^\n]*(?:\n|$)){1,5}\Z", observation) is not None)


raw, destination = map(Path, sys.argv[1:3])
arm, position, first_arm, phase, status = sys.argv[3:]
status = int(status)
variant = os.environ["VARIANT"]
controlled_trial = variant in ("h", "i")
key = os.environ["MODEL_PROXY_KEY"].encode()
inputs = ("case/task.md", "case/input/site.json", "case/input/periods.csv")
outputs = ("case/output/schedule.csv", "case/output/summary.json")
logs = ("startup.log", "probe.log", "server.log", "experiment.log", "model-io.jsonl")
checksums = {}
secret_in_case = False
io_redacted = False
for relative in (*inputs, *outputs, *logs):
    source = raw / relative
    if not source.is_file() or source.is_symlink():
        continue
    data = source.read_bytes()
    if relative in (*inputs, *outputs) and key in data:
        secret_in_case = True
        continue
    if relative == "model-io.jsonl":
        io_redacted = key in data
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data.replace(key, b"[REDACTED]"))
    if relative in inputs:
        checksums[relative.removeprefix("case/")] = hashlib.sha256(data).hexdigest()

report = None
log = destination / "experiment.log"
if log.exists():
    for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("variant") == variant and "grade" in candidate:
            report = candidate
            break
grade = (report or {}).get("grade")
checkpoint = (report or {}).get("checkpoint") or {}
run_sha = os.environ["GITHUB_SHA"]
repair_trial = variant in ("f", "g") or controlled_trial
experiment = ("controlled-repair-replay-v1" if controlled_trial else
              "repair-source-v1" if repair_trial else "paired-storage-v1")
protocol_path = f"docs/experiments/{experiment}/protocol.json"
payload = subprocess.check_output(["git", "show", f"{run_sha}:{protocol_path}"])
protocol = json.loads(payload)
split = protocol["split"]
preregistered = protocol["cases"][variant] if controlled_trial else split["cases"][variant]
expected_inputs = preregistered["input_sha256"] if controlled_trial else preregistered["sha256"]
expected_split = split["new_diagnostic_inputs"] if controlled_trial else split["holdout"]
input_matches = (variant in expected_split and checksums == expected_inputs
                 and (controlled_trial or preregistered["split"] == "holdout"))
archive = (report or {}).get("model_io_archive") or {}
io_complete = False
source_exposed = None
repair_requested = None
controlled_source_valid = None
release_sec = repair_dispatch_sec = None
timing_valid = None
io_file = destination / "model-io.jsonl"
if io_file.is_file() and archive.get("complete") is True and not io_redacted:
    try:
        lines = io_file.read_text(encoding="utf-8").splitlines()
        io_complete = bool(lines) and json.loads(lines[-1]) == {"event": "end", **archive}
        if repair_trial and io_complete:
            records = [json.loads(line) for line in lines[:-1]]
            source_exposed = any(carries_source_excerpt(record) for record in records)
            repair = [record for record in records if record.get("event") == "request"
                      and record.get("call", 0) >= 2
                      and len(record.get("body", {}).get("messages", [])) >= 3
                      and str(record["body"]["messages"][2].get("content", "")).startswith(
                          "The first Python program did not run cleanly.")]
            repair_requested = bool(repair)
            if controlled_trial:
                scripted_first = [record for record in records if record.get("event") == "response"
                                  and record.get("call") == 1 and record.get("scripted") is True]
                content = (scripted_first[0]["choices"][0]["message"].get("content")
                           if len(scripted_first) == 1 else "")
                match = re.fullmatch(r"```python\n(.*?)\n```", content or "", re.DOTALL)
                controlled_source_valid = bool(
                    match and hashlib.sha256(match[1].encode()).hexdigest()
                    == "f4ece9d6d7e41e93f364db640b51b50c12c947ce1639fd2af991007dd76364f2")
                release_sec = scripted_first[0].get("end_sec") if len(scripted_first) == 1 else None
                repair_dispatch_sec = repair[0].get("start_sec") if repair else None
                timing_valid = (type(release_sec) in (int, float)
                                and type(repair_dispatch_sec) in (int, float)
                                and abs(release_sec - 250) <= 2
                                and release_sec <= repair_dispatch_sec <= release_sec + 5)
    except (ValueError, TypeError, AttributeError):
        io_complete = False
observation = (phase == "experiment" and status in (0, 1)
               and not secret_in_case and input_matches
               and report is not None and not report.get("infrastructure_error")
               and isinstance(checkpoint, dict) and checkpoint.get("measured") is True
               and isinstance(grade, dict)
               and type(grade.get("optimal")) is bool and status == int(not grade["optimal"]))
if controlled_trial:
    action = (report or {}).get("first_code_action") or {}
    observation = (observation and controlled_source_valid is True and timing_valid is True
                   and repair_requested is True and action.get("classification") == "exec_failed"
                   and action.get("exec_exit_status") == 1
                   and source_exposed == (arm == "text-source"))
cpus = int(subprocess.check_output(["nproc"], text=True).strip())
cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name") and ":" in line), "unknown")
metadata = {"variant": variant, "mode": arm, "repeat": int(os.environ["REPEAT"]),
            "order": int(position), "first_mode": first_arm, "seed": 17, "temperature": 0,
            "git_sha": run_sha, "model": "gemma-4-26b",
            "cpu_model": cpu, "logical_cpus": cpus, "model_threads": min(cpus, 4),
            "phase": phase, "exit_code": status, "observation": observation,
            "protocol_sha256": hashlib.sha256(payload).hexdigest(),
            "input_sha256": checksums, "protocol_input_sha256": expected_inputs,
            "input_matches_protocol": input_matches, "model_io_archive_complete": io_complete}
if repair_trial:
    metadata.update(repair_requested=repair_requested, repair_context_exposed=source_exposed)
if controlled_trial:
    metadata.update(controlled_first_program_valid=controlled_source_valid,
                    controlled_release_sec=release_sec, repair_dispatch_sec=repair_dispatch_sec,
                    controlled_timing_valid=timing_valid)
(destination / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
if report is not None:
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("PLE_REPLICATION_RESULT " + json.dumps({**metadata, "report": report}), flush=True)
recoverable = (*inputs, *outputs, "model-io.jsonl", "metadata.json", "report.json")
files = {relative: base64.b64encode((destination / relative).read_bytes()).decode("ascii")
         for relative in recoverable if (destination / relative).is_file()}
blob = gzip.compress(json.dumps({"files_base64": files}, separators=(",", ":")).encode(), mtime=0)
if len(blob) <= 1024**2:
    encoded = base64.b64encode(blob).decode("ascii")
    width = 5600
    marker = {"version": 1, "variant": variant, "repeat": metadata["repeat"], "mode": arm,
              "encoding": "gzip+base64", "sha256": hashlib.sha256(blob).hexdigest(),
              "count": (len(encoded) + width - 1) // width}
    for part, offset in enumerate(range(0, len(encoded), width), start=1):
        chunk = {**marker, "part": part, "data": encoded[offset:offset + width]}
        print("PLE_EVIDENCE_CHUNK " + json.dumps(chunk, separators=(",", ":")), flush=True)
else:
    print(f"PLE_EVIDENCE_UNAVAILABLE {variant}/{metadata['repeat']}/{arm}: compressed payload exceeds 1 MiB")
label = "measured" if observation else "infrastructure failure"
summary = f"- {variant}/{metadata['repeat']} arm {position} ({arm}): {label}, exit {status}"
if isinstance(grade, dict) and "optimal" in grade:
    summary += f", optimal={grade['optimal']}"
if repair_trial:
    summary += f", repair source exposed={source_exposed}"
with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
    stream.write(summary + "\n")
sys.exit(0 if observation else 1)

