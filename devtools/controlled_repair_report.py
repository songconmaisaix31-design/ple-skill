"""Summarize the frozen H/I controlled repair comparison from its replay CSV."""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev, variance


CASES = ("h", "i")
REPEATS = (1, 2, 3)
ARMS = ("text", "text-source")


def distribution(values):
    return {"n": len(values), "mean": mean(values),
            "sample_variance": variance(values), "sample_std": stdev(values)}


def load(path):
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"case", "repeat", "arm", "measured", "score", "repair_requested",
                    "source_feedback_observed", "controlled_timing_valid",
                    "repair_response_completed"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("controlled replay CSV lacks required fields")
        for row in reader:
            case, repeat, arm = row["case"], int(row["repeat"]), row["arm"]
            key = case, repeat, arm
            if case not in CASES or repeat not in REPEATS or arm not in ARMS or key in rows:
                raise ValueError(f"unexpected or duplicate observation {key}")
            if row["measured"] != "1":
                raise ValueError(f"unmeasured controlled arm {key}")
            score = float(row["score"])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError(f"invalid score {key}")
            rows[key] = {
                "score": score,
                "repair_requested": int(row["repair_requested"]),
                "source_exposed": int(row["source_feedback_observed"]),
                "timing_valid": int(row["controlled_timing_valid"]),
                "repair_response_completed": int(row["repair_response_completed"]),
            }
    expected = {(case, repeat, arm) for case in CASES for repeat in REPEATS for arm in ARMS}
    if set(rows) != expected:
        raise ValueError(f"expected 12 arms, found {len(rows)}")
    return rows


def summarize(rows):
    pairs = {}
    case_differences = {}
    repeat_rows = []
    for case in CASES:
        case_pairs, changes = [], []
        for repeat in REPEATS:
            baseline = rows[case, repeat, "text"]["score"]
            candidate = rows[case, repeat, "text-source"]["score"]
            change = candidate - baseline
            changes.append(change)
            case_pairs.append({"repeat": repeat, "text": baseline, "text-source": candidate,
                               "text_source_minus_text": change})
        pairs[case] = {"pairs": case_pairs, "mean_paired_difference": mean(changes),
                       "wins": sum(value > 0 for value in changes),
                       "ties": sum(value == 0 for value in changes),
                       "losses": sum(value < 0 for value in changes)}
        case_differences[case] = changes
    for repeat in REPEATS:
        baseline = mean(rows[case, repeat, "text"]["score"] for case in CASES)
        candidate = mean(rows[case, repeat, "text-source"]["score"] for case in CASES)
        repeat_rows.append({"repeat": repeat, "text": baseline, "text-source": candidate,
                            "text_source_minus_text": candidate - baseline})
    coverage = {
        arm: {
            "planned": 6,
            "measured": 6,
            "repair_requests": sum(rows[key]["repair_requested"] for key in rows if key[2] == arm),
            "source_exposures": sum(rows[key]["source_exposed"] for key in rows if key[2] == arm),
            "timing_valid": sum(rows[key]["timing_valid"] for key in rows if key[2] == arm),
            "completed_repair_responses": sum(
                rows[key]["repair_response_completed"] for key in rows if key[2] == arm),
        }
        for arm in ARMS
    }
    exposure_valid = (
        coverage["text"]["repair_requests"] == 6
        and coverage["text-source"]["repair_requests"] == 6
        and coverage["text"]["source_exposures"] == 0
        and coverage["text-source"]["source_exposures"] == 6
        and coverage["text"]["timing_valid"] == 6
        and coverage["text-source"]["timing_valid"] == 6
    )
    positive = (
        all(row["text_source_minus_text"] > 0 for row in repeat_rows)
        and all(data["mean_paired_difference"] >= 0 for data in pairs.values())
    )
    decision = ("support_conditional_repair" if exposure_valid and positive else
                "stop_candidate_no_gain" if exposure_valid else "inconclusive_exposure_or_timing")
    return {
        "cases": list(CASES),
        "seed": 17,
        "release_sec": 250,
        "snapshot_sec": 395,
        "complete": True,
        "counts_by_arm": coverage,
        "paired_results_by_case": pairs,
        "case_macro_score_by_repeat": repeat_rows,
        "across_repeat_statistics": {
            metric: distribution([row[metric] for row in repeat_rows])
            for metric in ("text", "text-source", "text_source_minus_text")
        },
        "registered_decision": decision,
        "interpretation": (
            "This controlled diagnostic estimates recovery conditional on one fixed induced failure. "
            "It does not estimate natural failure frequency or an official PLE score."
        ),
    }


def plot(path, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        fig, ax = plt.subplots(figsize=(7.3, 4.3))
        for index, row in enumerate(report["case_macro_score_by_repeat"]):
            x = row["repeat"]
            ax.plot([x - .16, x + .16], [row["text"], row["text-source"]],
                    color="#657382", lw=1.7)
            ax.scatter([x - .16], [row["text"]], s=68, color="#3C5C85", marker="o",
                       label="Traceback feedback" if index == 0 else None, zorder=3)
            ax.scatter([x + .16], [row["text-source"]], s=68, color="#AF4932", marker="s",
                       label="Traceback + source" if index == 0 else None, zorder=3)
        ax.grid(axis="y", alpha=.22)
        ax.set(xlim=(.55, 3.45), ylim=(-.055, 1.055), xticks=REPEATS,
               xticklabels=[f"Repeat {n}" for n in REPEATS],
               yticks=[0, .25, .5, .75, 1],
               ylabel="Mean normalized score across H and I")
        fig.suptitle("Controlled repair at 395 seconds", x=.105, ha="left", fontweight="bold")
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1), frameon=False, ncols=2)
        fig.text(.105, .046, "Fixed seed 17. Both arms receive the same failed program at t=250 s.",
                 fontsize=9, color="#394755")
        fig.subplots_adjust(left=.11, right=.97, bottom=.22, top=.78)
        fig.savefig(path, dpi=180)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    try:
        report = summarize(load(args.csv_file))
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        if args.plot:
            plot(args.plot, report)
    except (OSError, ValueError, csv.Error, ImportError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

