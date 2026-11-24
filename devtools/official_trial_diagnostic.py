"""Export fixed categories and numerical observations from one official wind pilot."""
import argparse
import json
import math
import os
from pathlib import Path
import re


TASK = "wind-diaphragm-shear"
MODEL = "google-cloud/gemma-4-26b"
DATASET_SHA = "e0c21fa558c3127785656398e3b3bd7da5e5a5a6"
KIT_SHA = "8320f0402fdca9f42476607f72bcfd5271cd50c9"
OUTPUT = "filesystem/final_batch4__structural_task5_wind_diaphragm_shear__blind/output/submission.zip"
KINDS = {"ok", "harness", "no trial", "evaluator", "grader failed", "checks failed",
         "task error", "not started", "no reward", "harbor failed", "not run"}
EXCEPTIONS = {"AgentTimeoutError", "NonZeroAgentExitCodeError", "AgentSafetyRefusalError",
              "OutputTokenExceededError", "ContextWindowExceededError", "UnknownApiError",
              "SandboxBuildFailedError", "EnvironmentStartTimeoutError",
              "VerifierTimeoutError", "ApiConnectionError", "AgentAuthenticationError"}


def tail(path, limit=2**18):
    if path.is_symlink() or not path.is_file():
        return ""
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - limit))
        return stream.read(limit).decode(errors="replace")


def obj(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 2**20:
        return {}
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def number(value):
    return value if type(value) in (float, int) and math.isfinite(value) else None


def summarize(run, log_path, rc):
    report = obj(run / "results.json")
    rows = [r for r in report.get("tasks", []) if isinstance(r, dict) and r.get("id") == TASK]
    row = rows[0] if len(rows) == 1 and report.get("model") == MODEL else {}
    measured = row.get("measured") is True
    score = number(row.get("score")) if measured else None
    if score is not None and not 0 <= score <= 1:
        score = None
    manifest = obj(run / "artifacts/manifest.json")
    entry = manifest.get("tasks", {}).get(TASK, {})
    review_log = tail(log_path)
    matches = re.findall(r"^  (ok|empty|refused|missing)\s+" + TASK + r"(?:\s|$)", review_log, re.M)
    out = {
        "task": TASK, "model": MODEL, "kit_sha": KIT_SHA, "dataset_sha": DATASET_SHA,
        "seed": 17, "temperature": 0, "evaluator_exit": rc, "trial_count": 1,
        "official_score": score, "measured": measured, "reward": number(row.get("reward")),
        "kind": row.get("kind") if row.get("kind") in KINDS else "unavailable",
        "seconds": number(row.get("seconds")), "export_record": (run / "export.json").is_file(),
        "manifest_present": bool(manifest), "task_exported": bool(entry),
        "file_count": len(entry.get("files", {})), "skipped_count": len(entry.get("skipped", [])),
        "declared_zip_exported": OUTPUT in entry.get("files", {}),
        "review_status": matches[-1] if matches else ("ok" if rc == 0 and entry else "unknown"),
        "review_refused": "the server would refuse these artifacts" in review_log,
        "tokens": {k: number((row.get("tokens") or {}).get(k)) for k in ("input", "output", "cache")},
    }
    trial = (run / (row.get("trial") or ".")).resolve()
    logs = review_log
    if trial != run.resolve() and trial.is_relative_to(run.resolve()):
        capture = obj(trial / "deliverables/capture.json")
        info = obj(trial / "result.json").get("exception_info") or {}
        exc = info.get("exception_type")
        out.update(capture_present=bool(capture), capture_error=bool(capture.get("error")),
                   capture_files=len(capture.get("files", {})), declared_zip_captured=OUTPUT in capture.get("files", {}),
                   exception=exc if exc in EXCEPTIONS else ("other" if exc else None))
        logs += str(info.get("exception_message") or "")
        for name in ("serve.log", "skillguard-harness.txt", "egress.log"):
            logs += "\n" + tail(trial / "agent" / name)
    # Only these literal labels can leave the runner. Neither arbitrary paths nor
    # free-form exception messages, commands, prompts or generated files are exported.
    patterns = {
        "context_limit": r"context.length.exceeded|context.window.exceed|prompt is too long|exceeds the available context|maximum context length",
        "out_of_disk": r"no space left",
        "http_4xx": r"\bhttp (?:400|401|403|404|413|429)\b",
        "model_retry_exhausted": r"model call failed after retries",
        "capture_missing": r"no capture\.json",
        "capture_failed": r"copying its deliverables out failed|its capture lacks",
        "export_write_error": r"artifacts could not be written",
        "export_empty": r"no dev task.*has usable artifacts",
    }
    out["observed_log_markers"] = [key for key, pattern in patterns.items() if re.search(pattern, logs, re.I)]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("exit_code", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = summarize(args.run, args.log, args.exit_code)
    report["run_id"] = int(os.environ["GITHUB_RUN_ID"])
    report["run_attempt"] = int(os.environ["GITHUB_RUN_ATTEMPT"])
    sha = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("invalid run commit")
    report["commit"] = sha
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
