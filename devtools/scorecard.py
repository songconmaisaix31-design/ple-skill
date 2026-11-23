#!/usr/bin/env python3
"""Compare local PLE eval/run.py results without running or grading a task."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from statistics import mean


DEV_TASKS = 29


def is_number(value, *, limit=math.inf):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= limit


def load_results(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not is_number(data.get("score"), limit=1):
        raise ValueError("expected results.json with an official runner score")
    rows = data.get("tasks")
    if not isinstance(rows, list) or not 1 <= len(rows) <= DEV_TASKS:
        raise ValueError(f"expected 1–{DEV_TASKS} task results")

    tasks = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("expected a task result object")
        task_id = row.get("id")
        if not isinstance(task_id, str) or not task_id or task_id in tasks:
            raise ValueError(f"missing or duplicate task ID {task_id!r}")
        if type(row.get("measured")) is not bool or not is_number(row.get("score"), limit=1):
            raise ValueError(f"{task_id}: expected measured and normalized score fields")
        tasks[task_id] = row
    return data, tasks


def token_counts(rows):
    counters = {name: [] for name in ("input", "cache", "output", "total")}
    for row in rows:
        tokens = row.get("tokens") or {}
        if not isinstance(tokens, dict):
            continue
        for key in ("input", "cache", "output"):
            count = tokens.get(key)
            if type(count) is int and count >= 0:
                counters[key].append(count)
        input_count, output_count = tokens.get("input"), tokens.get("output")
        if (type(input_count) is int and input_count >= 0
                and type(output_count) is int and output_count >= 0):
            counters["total"].append(input_count + output_count)
    return counters


def reported_metric(values, selected, *, seconds=False):
    if not values:
        return "unavailable"
    units = f"{sum(values):,.1f} s" if seconds else f"{sum(values):,}"
    return f"{units} ({len(values)}/{selected} tasks reporting)"


def print_run(label, data, tasks, *, details):
    selected = len(tasks)
    rows = list(tasks.values())
    measured = sum(row["measured"] for row in rows)
    zero = sum(row["measured"] and row["score"] == 0 for row in rows)
    failures = Counter(row.get("kind") or "unclassified" for row in rows
                       if row.get("kind") != "ok")
    mode = "artifact replay" if data.get("artifacts") is True else "live evaluation"
    scope = "full dev selection" if selected == DEV_TASKS else "dev subset"
    revision = data.get("tasks_revision") or "unrecorded"
    judge = data.get("judge_model") or "unrecorded"

    print(f"\n{label} | {data.get('model') or 'unrecorded model'} | {mode}")
    print(f"  Dataset revision {revision} | judge {judge}")
    print(f"  Local runner average {data['score']:.6f} ({scope})")
    print(f"  Coverage {selected}/{DEV_TASKS} selected, {measured}/{selected} measured,"
          f" {selected - measured} unmeasured, {zero} measured zero")
    if measured != selected:
        print("  The runner includes unmeasured tasks as zero in its local average.")
    print("  Non-ok outcomes " + (", ".join(f"{kind}={count}" for kind, count in
                                            sorted(failures.items())) or "none"))

    tokens = token_counts(rows)
    for key, description in (("input", "Input tokens"), ("cache", "Cache-read tokens"),
                             ("output", "Output tokens"), ("total", "Input + output tokens")):
        print(f"  {description} {reported_metric(tokens[key], selected)}")
    seconds = [row["seconds"] for row in rows if is_number(row.get("seconds"))]
    timing = "Replay task time" if data.get("artifacts") is True else "Agent task time"
    print(f"  {timing} (sum) {reported_metric(seconds, selected, seconds=True)}")

    if details:
        for task_id, row in sorted(tasks.items()):
            score = f"{row['score']:.6f}" if row["measured"] else "unmeasured"
            print(f"    {task_id} | {score} | {row.get('kind') or 'unclassified'}")


def print_comparison(baseline, candidate, *, details):
    left_label, left_data, left = baseline
    right_label, right_data, right = candidate
    print(f"\nPaired comparison {right_label} minus {left_label}")

    for field, description in (("tasks_revision", "dataset revision"),
                               ("judge_model", "judge")):
        a, b = left_data.get(field), right_data.get(field)
        if not a or not b:
            print(f"  {description.capitalize()} alignment unconfirmed.")
        elif a != b:
            print(f"  Different {description} values ({a} vs {b}).")
    if bool(left_data.get("artifacts")) != bool(right_data.get("artifacts")):
        print("  One report grades exported artifacts and the other evaluates a live harness.")

    shared = left.keys() & right.keys()
    paired = [(task_id, right[task_id]["score"] - left[task_id]["score"])
              for task_id in sorted(shared) if left[task_id]["measured"] and
              right[task_id]["measured"]]
    if not paired:
        print(f"  Score delta unavailable (0/{len(shared)} shared tasks measured by both).")
        return
    print(f"  Mean score delta {mean(delta for _, delta in paired):+.6f} "
          f"({len(paired)}/{len(shared)} shared tasks measured by both).")
    if details:
        for task_id, delta in paired:
            print(f"    {task_id} | {delta:+.6f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", metavar="LABEL=RESULTS_JSON", nargs="+",
                        help="the first result is the baseline for paired comparisons")
    parser.add_argument("--details", action="store_true", help="list individual task results and deltas")
    args = parser.parse_args()

    runs = []
    labels = set()
    for item in args.run:
        label, sep, path = item.partition("=")
        if not sep or not label or not path or label in labels:
            parser.error(f"expected a unique LABEL=RESULTS_JSON argument, got {item!r}")
        try:
            data, tasks = load_results(Path(path))
        except (OSError, ValueError) as exc:
            parser.error(f"{label}: {exc}")
        labels.add(label)
        runs.append((label, data, tasks))

    print("Local evaluator results. Missing token counters are unavailable, including omitted zeros.")
    for run in runs:
        print_run(*run, details=args.details)
    for candidate in runs[1:]:
        print_comparison(runs[0], candidate, details=args.details)


if __name__ == "__main__":
    main()
