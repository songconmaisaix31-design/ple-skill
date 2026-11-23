"""Record and package one paired-run observation from its public fixture evidence."""

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

raw, destination = map(Path, sys.argv[1:3])
arm, position, first, phase, status = sys.argv[3:]
status = int(status)
variant = os.environ["VARIANT"]
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
protocol_path = "docs/experiments/paired-storage-v1/protocol.json"
payload = subprocess.check_output(["git", "show", f"{run_sha}:{protocol_path}"])
split = json.loads(payload)["split"]
preregistered = split["cases"][variant]
input_matches = (variant in split["holdout"] and preregistered["split"] == "holdout"
                 and checksums == preregistered["sha256"])
archive = (report or {}).get("model_io_archive") or {}
io_complete = False
io_file = destination / "model-io.jsonl"
if io_file.is_file() and archive.get("complete") is True and not io_redacted:
    lines = io_file.read_text(encoding="utf-8").splitlines()
    if lines:
        end = json.loads(lines[-1])
        io_complete = end == {"event": "end", **archive}
observation = (phase == "experiment" and status in (0, 1)
               and not secret_in_case and input_matches
               and report is not None and not report.get("infrastructure_error")
               and isinstance(checkpoint, dict) and checkpoint.get("measured") is True
               and isinstance(grade, dict)
               and type(grade.get("optimal")) is bool and status == int(not grade["optimal"]))
cpus = int(subprocess.check_output(["nproc"], text=True).strip())
cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name") and ":" in line), "unknown")
metadata = {"variant": variant, "mode": arm, "repeat": int(os.environ["REPEAT"]),
            "order": int(position), "first_mode": first, "seed": 17, "temperature": 0,
            "git_sha": run_sha, "model": "gemma-4-26b",
            "cpu_model": cpu, "logical_cpus": cpus, "model_threads": min(cpus, 4),
            "phase": phase, "exit_code": status, "observation": observation,
            "protocol_sha256": hashlib.sha256(payload).hexdigest(),
            "input_sha256": checksums, "protocol_input_sha256": preregistered["sha256"],
            "input_matches_protocol": input_matches, "model_io_archive_complete": io_complete}
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
with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
    stream.write(summary + "\n")
sys.exit(0 if observation else 1)
