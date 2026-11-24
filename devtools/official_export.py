"""Freeze official task inputs, summarize evaluator observations and verify file regrades."""
import hashlib
import json
import math
import platform
import re
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import yaml


TEMP = Path(os.environ["RUNNER_TEMP"])
KIT = TEMP / "ple-kit"
ENTRY = TEMP / "ple-entry"
EVIDENCE = TEMP / "evidence"
MODEL = "google-cloud/gemma-4-26b"
PILOT = "wind-diaphragm-shear"
OLD_PILOT_REVISION = "e0c21fa558c3127785656398e3b3bd7da5e5a5a6"
sys.path.insert(0, str(KIT))
DEV = yaml.safe_load((KIT / "eval/dev_set.yaml").read_bytes())
TASKS = {task["id"]: task for task in DEV["tasks"]}


def obj(path):
    return json.loads(path.read_bytes())


def write(name, data):
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(data, indent=2) + "\n")


def sha256(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def identity():
    frozen_paths = [".github/workflows/ple-official-export.yml", ".github/actions/official-task",
                    "devtools/official_entry.sh", "devtools/official_model.sh", "devtools/official_export.py",
                    "devtools/official_task.sh", "devtools/official_public_export.py", "devtools/start_cpu_model.sh", "devtools/cloud_model_probe.py",
                    "devtools/official-kit-requirements.txt", "devtools/official_trial_diagnostic.py"]
    tree = subprocess.check_output(["git", "-C", os.environ["GITHUB_WORKSPACE"],
                                    "ls-tree", "-r", os.environ["GITHUB_SHA"], "--", *frozen_paths])
    return {
        "run_id": int(os.environ["GITHUB_RUN_ID"]),
        "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "source_commit": os.environ["GITHUB_SHA"],
        "entry_commit": subprocess.check_output(["git", "-C", ENTRY, "rev-parse", "HEAD"], text=True).strip(),
        "kit_commit": subprocess.check_output(["git", "-C", KIT, "rev-parse", "HEAD"], text=True).strip(),
        "evaluation_tree": hashlib.sha256(tree).hexdigest(),
        "model": MODEL, "llama_cpp_build": "b12651", "seed": 17, "temperature": 0,
        "model_sha256": "52f98e6fc6df62438dff8f57ac049f60b4c36acf93786b6aeeedc129acc02343",
    }


def plan():
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write("remaining=" + json.dumps([key for key in TASKS if key != PILOT]) + "\n")


def download(task):
    from eval.run import has_link, tree_sha256
    from huggingface_hub import snapshot_download
    record = {**identity(), "task": task, "grading": TASKS[task]["grading"],
              "dataset_revision": DEV["tasks_revision"], "expected_sha256": TASKS[task]["sha256"],
              "time_limit_min": TASKS[task]["time_limit_min"], "input_verified": False,
              "limits_minutes": {"generation_wall": 260, "replay_wall": 60, "job_wall": 360},
              "runner": {"label": "ubuntu-24.04", "image_version": os.environ.get("ImageVersion"),
                         "architecture": platform.machine(), "logical_cpus": os.cpu_count(),
                         "memory_bytes": os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"),
                         "free_disk_bytes_at_input": shutil.disk_usage(TEMP).free},
              "cpu_inference": {"max_threads": 4, "context_requested": 16384, "concurrent_slots": 1},
              "harbor": "0.20.0", "judge_model": "gemma-4-26b", "repetitions": 1}
    write("input.json", record)
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("Missing PLE_HF_TOKEN for the gated official task.")
    try:
        snapshot_download(DEV["tasks_repo"], repo_type="dataset", revision=DEV["tasks_revision"],
                          local_dir=TEMP/"ple-data", allow_patterns=[f"tasks/{task}/**"], token=token)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise SystemExit(f"Dataset download failed ({type(exc).__name__}, HTTP {status}).") from None
    folder = TEMP / "ple-data/tasks" / task
    if not (folder / "task.toml").is_file() or has_link(folder):
        raise SystemExit("Official task folder is incomplete or contains a link.")
    actual = tree_sha256(folder)
    record.update(actual_sha256=actual, input_verified=(actual == record["expected_sha256"]))
    if task == PILOT:
        comparison = {"prior_revision": OLD_PILOT_REVISION, "prior_tree_sha256": None,
                      "same_as_current_task": None}
        try:
            previous_dir = TEMP / "ple-prior-input"
            snapshot_download(DEV["tasks_repo"], repo_type="dataset", revision=OLD_PILOT_REVISION,
                              local_dir=previous_dir, allow_patterns=[f"tasks/{task}/**"], token=token)
            previous_task = previous_dir / "tasks" / task
            if (previous_task / "task.toml").is_file() and not has_link(previous_task):
                previous_hash = tree_sha256(previous_task)
                comparison.update(prior_tree_sha256=previous_hash, same_as_current_task=(previous_hash == actual))
        except Exception as exc:
            comparison["lookup_error"] = type(exc).__name__
        record["prior_pilot_input"] = comparison
    write("input.json", record)
    if not record["input_verified"]:
        raise SystemExit("Official task contents differ from the frozen kit manifest.")


def record_model(context, threads):
    # Values come from model.env only after llama-server reports healthy.
    observation = {"context_at_server_start": int(context), "threads": int(threads), "concurrent_slots": 1,
                   "temperature": 0, "seed": 17, "build": "b12651", "model": MODEL}
    write("model-runtime.json", observation)
    path = EVIDENCE / "input.json"
    if path.exists():
        record = obj(path)
        if record["cpu_inference"]["context_requested"] != observation["context_at_server_start"]:
            raise SystemExit("Loaded model context differs from the frozen candidate.")
        record["cpu_inference"].update(observation)
        write("input.json", record)


def summarize(task, phase, exit_code):
    result = TEMP / phase / "results.json"
    data = obj(result) if result.is_file() else {}
    rows = [row for row in data.get("tasks", []) if row.get("id") == task]
    row = rows[0] if len(rows) == 1 and data.get("model") == MODEL else {}
    timed_out = int(exit_code) in (124, 137)
    measured = row.get("measured") is True and not timed_out
    score = row.get("score") if measured else None
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        score = None
    kinds = {"ok", "grader failed", "no trial", "evaluator", "harness", "not started", "task error",
             "checks failed", "no reward", "harbor failed", "artifact", "not run"}
    log = TEMP / (phase + ".log")
    markers = {"disk": "no space left", "capture": "capture failed", "export": "could not be written",
               "empty": "no dev task", "memory": "out of memory", "deadline": "timed out",
               "judge": "judge failed", "refused": "server would refuse", "connection": "connection refused"}
    with log.open("rb") as stream:
        stream.seek(max(0, log.stat().st_size - 1024 * 1024))
        text = stream.read().decode(errors="replace").lower()
    numerical = {k: row.get(k) for k in ("seconds", "reward") if type(row.get(k)) in (float, int)}
    observation = {"task": task, "phase": phase, "exit": int(exit_code), "measured": measured, "score": score,
                   "kind": row.get("kind") if row.get("kind") in kinds else "unknown", **numerical,
                   "diagnostics": [name for name, marker in markers.items() if marker in text]}
    observation["runner_cutoff"] = timed_out
    observation["phase_wall_limit_minutes"] = 260 if phase == "run" else 60
    from official_trial_diagnostic import EXCEPTIONS, number, obj as safe_json, tail
    observation["tokens"] = {k: number((row.get("tokens") or {}).get(k)) for k in ("input", "output", "cache")}
    run_dir = TEMP / phase
    trial = (run_dir / (row.get("trial") or ".")).resolve()
    if trial != run_dir.resolve() and trial.is_relative_to(run_dir.resolve()):
        capture = safe_json(trial / "deliverables/capture.json")
        result = safe_json(trial / "result.json")
        exc = (result.get("exception_info") or {}).get("exception_type")
        observation.update(trial_result_present=bool(result), capture_present=bool(capture),
                           capture_error=bool(capture.get("error")), captured_file_count=len(capture.get("files", {})),
                           exception=exc if exc in EXCEPTIONS else ("other" if exc else None))
        logs = "\n".join([text, str((result.get("exception_info") or {}).get("exception_message") or ""),
                          *(tail(trial / "agent" / name) for name in ("serve.log", "skillguard-harness.txt", "egress.log"))])
        patterns = {"trimmed_recent": r"trimmed recent tool observations", "masked_history": r"masked historical tool observations", "context_limit": r"context.length.exceeded|context.window.exceed|prompt is too long|exceeds the available context|maximum context length",
                    "model_call_failed": r"model call failed after retries", "http_4xx": r"\bhttp (?:400|401|403|404|413|429)\b",
                    "export_empty": r"no dev task.*has usable artifacts"}
        observation["diagnostics"] += [k for k, v in patterns.items() if re.search(v, logs, re.I)]
    manifest = safe_json(run_dir / "artifacts/manifest.json")
    captured = manifest.get("tasks", {}).get(task, {})
    observation.update(export_record_present=(run_dir / "export.json").is_file(), manifest_present=bool(manifest),
                       exported_file_count=len(captured.get("files", {})), skipped_count=len(captured.get("skipped", [])))
    write(phase + ".json", observation)
    print(json.dumps(observation))


def review(task):
    report = obj(TEMP / "review.json")
    row = next((r for r in report.get("tasks", []) if r["id"] == task), {})
    prov = report.get("provenance", {})
    valid = bool(report.get("accepted") and row.get("status") == "ok" and prov.get("manifest") == "ok"
                 and prov.get("harness") == "same" and prov.get("dev_set") == "same" and not prov.get("edited"))
    manifest = ENTRY / "artifacts/manifest.json"
    if valid:
        valid = obj(manifest)["harness"]["model_api"] == MODEL
    write("review.json", {"task": task, "accepted": report["accepted"], "status": row.get("status"),
                          "verified": valid, "files": row.get("files"), "counts": report.get("counts"),
                          "manifest": prov.get("manifest"), "harness": prov.get("harness"), "dev_set": prov.get("dev_set"),
                          "edited_tasks": len(prov.get("edited", []))})
    if not valid:
        raise SystemExit("The official kit found no usable, unchanged export for this task.")


def verify(task):
    run, replay = [obj(EVIDENCE / (name + ".json")) for name in ("run", "replay")]
    for item in (run, replay):
        if item["exit"] or item["score"] is None or item["measured"] is not True:
            raise SystemExit("Generation or file replay did not complete with an observed score.")
    if TASKS[task]["grading"] == "checks" and run["score"] != replay["score"]:
        raise SystemExit("Deterministic checks disagreed between the run and its exported files.")
    data = {**obj(EVIDENCE / "input.json"), "run_score": run["score"], "file_score": replay["score"],
            "archive_sha256": sha256(EVIDENCE / "export.tar.gz"),
            "harbor_environment_sha256": sha256(EVIDENCE / "harbor-environment.txt"),
            "kit_environment_sha256": sha256(EVIDENCE / "kit-environment.txt")}
    write("verified.json", data)


def kit(*args, capture=False):
    return subprocess.run([sys.executable, "-m", "kit", *map(str, args)], cwd=KIT, check=True,
                          stdout=subprocess.PIPE if capture else None, text=True).stdout


def validate_pilot():
    expected = identity()
    candidates = [obj(p) for p in (TEMP / "shards").glob("*/verified.json")]
    for row in candidates:
        if (row.get("run_id") == int(os.environ["PILOT_RUN"]) and row.get("task") == PILOT
                and all(row.get(k) == expected[k] for k in ("entry_commit", "kit_commit", "evaluation_tree", "model"))
                and row.get("actual_sha256") == TASKS[PILOT]["sha256"]):
            return
    raise SystemExit("No verified pilot matches this entry, evaluator and input.")


def assemble():
    # GitHub reruns retain the earlier successes. Keep the first verified attempt
    # for each task of this run, independent of its score.
    expected = identity()
    verified = [(obj(p), p.parent) for p in (TEMP / "shards").glob("*/verified.json")]
    verified.sort(key=lambda item: (item[0]["attempt"], item[0]["task"]))
    merged = {}
    for row, folder in verified:
        task = row["task"]
        if task in merged:
            continue
        if merged:
            first = next(iter(merged.values()))
            if any(row[k] != first[k] for k in ("harbor_environment_sha256", "kit_environment_sha256")):
                raise SystemExit("Dependency versions drifted between official task runs.")
        prior = os.environ.get("PILOT_RUN", "")
        belongs = (row["run_id"] == expected["run_id"] and row["source_commit"] == expected["source_commit"])
        if prior and row["run_id"] == int(prior) and task == PILOT:
            belongs = True
        if (not belongs or task not in TASKS or not row["input_verified"]
                or row["expected_sha256"] != TASKS[task]["sha256"]
                or any(row[k] != expected[k] for k in ("entry_commit", "kit_commit", "evaluation_tree", "model"))):
            raise SystemExit("Shard identifies another task, entry, model, source, or workflow run.")
        archive = folder / "export.tar.gz"
        if row["archive_sha256"] != sha256(archive):
            raise SystemExit("Mismatched shard archive checksum.")
        with tempfile.TemporaryDirectory(dir=TEMP) as stage:
            with tarfile.open(archive) as stream:
                if any(not (m.isfile() or m.isdir()) or Path(m.name).parts[:1] != ("artifacts",)
                       or ".." in Path(m.name).parts for m in stream.getmembers()):
                    raise SystemExit("Unexpected path in export archive.")
                stream.extractall(stage, filter="data")
            path = Path(stage) / "artifacts"
            tasks = obj(path / "manifest.json")["tasks"]
            if set(tasks) != {task}:
                raise SystemExit("Unexpected tasks in shard.")
            row["task_manifest_sha256"] = hashlib.sha256(json.dumps(tasks[task], sort_keys=True).encode()).hexdigest()
            kit("artifacts", ENTRY, "--from", path, capture=True)
        merged[task] = row
    if not merged:
        raise SystemExit("No verified shards to assemble.")
    final_review = json.loads(kit("artifacts", ENTRY, "--json", capture=True))
    prov = final_review["provenance"]
    usable = {r["id"] for r in final_review["tasks"] if r["status"] == "ok"}
    combined = obj(ENTRY / "artifacts/manifest.json")["tasks"]
    for task, row in merged.items():
        signature = hashlib.sha256(json.dumps(combined.get(task), sort_keys=True).encode()).hexdigest()
        if signature != row["task_manifest_sha256"]:
            raise SystemExit("Merging changed a scored task. Regrade the final files before submission.")
    if (usable != set(merged) or not final_review["accepted"] or prov["harness"] != "same"
            or prov["dev_set"] != "same" or prov["edited"]):
        raise SystemExit("Merged official review differs from verified shards.")
    write("submission-scores.json", {"by_task": merged, "missing_tasks": sorted(TASKS.keys() - merged.keys()),
          "usable": len(merged), "denominator": len(TASKS),
          "local_file_score_over_all": sum(r["file_score"] for r in merged.values()) / len(TASKS)})
    print(f"Review accepted {len(merged)} of {len(TASKS)} official tasks.")


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    actions = {"plan": plan, "download": download, "summarize": summarize, "review": review,
               "record-model": record_model, "verify": verify, "validate-pilot": validate_pilot, "assemble": assemble}
    actions[action](*args)
