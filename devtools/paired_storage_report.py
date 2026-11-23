"""Summarize the fixed-seed, paired 395-second storage experiment from a long CSV."""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev, variance


CASES = ("d", "e")
REPEATS = (1, 2, 3)
ARMS = ("legacy", "text")
FIELDS = {"case", "repeat", "arm", "measured", "score", "feasible", "optimal"}


def flag(value, name):
    if value not in ("1", "0"):
        raise ValueError(f"{name} must be 1 or 0")
    return value == "1"


def load_rows(path):
    results = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not FIELDS.issubset(header):
            raise ValueError(f"expected distinct column names including {', '.join(sorted(FIELDS))}")
        for row in reader:
            label = f"CSV line {reader.line_num}"
            if None in row or any(row[name] is None for name in FIELDS):
                raise ValueError(f"{label}: unexpected row length")
            case, repeat, arm = row["case"], row["repeat"], row["arm"]
            if case not in CASES or repeat not in ("1", "2", "3") or arm not in ARMS:
                raise ValueError(f"{label}: unexpected case/repeat/arm {case}/{repeat}/{arm}")
            key = (case, int(repeat), arm)
            if key in results:
                raise ValueError(f"{label}: duplicate planned observation {key}")
            measured = flag(row["measured"], f"{label} measured")
            score = feasible = optimal = None
            if measured:
                score = float(row["score"])
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError(f"{label}: score must be finite and in [0, 1]")
                feasible = flag(row["feasible"], f"{label} feasible")
                optimal = flag(row["optimal"], f"{label} optimal")
                if (score > 0) != feasible or (score == 1) != optimal:
                    raise ValueError(f"{label}: score and flags disagree with the storage grader")
            elif any(row[name].strip() for name in ("score", "feasible", "optimal")):
                raise ValueError(f"{label}: unmeasured run must have blank grades")
            results[key] = {"measured": measured, "score": score, "feasible": feasible, "optimal": optimal}
    return results


def distribution(values):
    return {"n": len(values), "mean": mean(values), "sample_variance": variance(values),
            "sample_std": stdev(values)}


def summarize(rows):
    missing = []
    unmeasured = []
    coverage = {}
    per_repeat = [{"repeat": repeat} for repeat in REPEATS]
    for arm in ARMS:
        counts = {"planned": len(CASES) * len(REPEATS), "measured": 0, "feasible": 0, "optimal": 0}
        for group in per_repeat:
            scores = []
            for case in CASES:
                key = (case, group["repeat"], arm)
                row = rows.get(key)
                if row is None or not row["measured"]:
                    target = missing if row is None else unmeasured
                    target.append({"case": case, "repeat": group["repeat"], "arm": arm})
                    continue
                scores.append(row["score"])
                counts["measured"] += 1
                counts["feasible"] += row["feasible"]
                counts["optimal"] += row["optimal"]
            group[arm] = mean(scores) if len(scores) == len(CASES) else None
        coverage[arm] = counts
    for group in per_repeat:
        group["text_minus_legacy"] = (group["text"] - group["legacy"]
                                     if all(group[arm] is not None for arm in ARMS) else None)
    complete = not (missing or unmeasured)
    aggregate = None
    if complete:
        aggregate = {metric: distribution([group[metric] for group in per_repeat])
                     for metric in (*ARMS, "text_minus_legacy")}
    return {
        "cases": CASES,
        "seed": 17,
        "declared_budget_sec": 720,
        "snapshot_sec": 395,
        "complete": complete,
        "missing_rows": missing,
        "unmeasured_rows": unmeasured,
        "counts_by_arm": coverage,
        "case_macro_score_by_repeat": per_repeat,
        "across_repeat_statistics": aggregate,
    }


def paired_plot(path, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        fig, ax = plt.subplots(figsize=(7.3, 4.3))
        for index, group in enumerate(report["case_macro_score_by_repeat"]):
            x = group["repeat"]
            legacy, text = group["legacy"], group["text"]
            if legacy is not None and text is not None:
                ax.plot([x - .16, x + .16], [legacy, text], color="#657382", lw=1.7, zorder=2)
            for shift, value, color, marker, name in (
                (-.16, legacy, "#3C5C85", "o", "Original tool loop"),
                (.16, text, "#AF4932", "s", "First Python action"),
            ):
                ax.scatter([x + shift] if value is not None else [], [value] if value is not None else [],
                           s=68, color=color, marker=marker, zorder=3, label=name if index == 0 else None)
        ax.grid(axis="y", alpha=.22)
        ax.set(xlim=(.55, 3.45), ylim=(-.055, 1.055), xticks=list(REPEATS),
               xticklabels=[f"Repeat {n}" for n in REPEATS], yticks=[0, .25, .5, .75, 1],
               ylabel="Mean normalized score across D and E")
        fig.suptitle("Held-out storage schedules at 395 seconds", x=.105, ha="left", fontweight="bold")
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1), frameon=False, ncols=2, borderaxespad=0)
        caption = "Fixed seed 17. Each line pairs both policies within a repeat across the same two cases."
        if not report["complete"]:
            caption += "\nA missing point indicates incomplete measurement of that pair of cases."
        fig.text(.105, .046, caption, fontsize=9, color="#394755")
        fig.subplots_adjust(left=.11, right=.97, bottom=.22, top=.78)
        fig.savefig(path, dpi=180)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="one row per case, repeat and arm")
    parser.add_argument("--output", type=Path, help="save summary JSON (default stdout)")
    parser.add_argument("--plot", type=Path, help="save paired figure; requires matplotlib")
    args = parser.parse_args()
    try:
        report = summarize(load_rows(args.csv_file))
        if args.plot:
            paired_plot(args.plot, report)
        output = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    except (ValueError, OSError, csv.Error, ImportError) as error:
        parser.error(str(error))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
