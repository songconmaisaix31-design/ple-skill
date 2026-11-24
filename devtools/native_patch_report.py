"""Summarize the frozen L/M native-patch comparison from replayed files."""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev, variance


CASES = ("l", "m")
REPEATS = (1, 2, 3)
ARMS = ("patch-source", "native-patch")


def distribution(values):
    return {"n": len(values), "mean": mean(values),
            "sample_variance": variance(values), "sample_std": stdev(values)}


def load(path):
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"case", "repeat", "arm", "measured", "score", "repair_requested",
                    "source_feedback_observed", "controlled_timing_valid",
                    "repair_response_completed", "prompt_patch_interface_used",
                    "native_patch_interface_used", "request_shape_valid", "patch_attempts",
                    "patch_accepted", "tool_responses", "native_tool_responses",
                    "native_argument_schema_valid", "native_unindented_replacements",
                    "nonempty_text_responses"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("native-patch CSV lacks required fields")
        for raw in reader:
            key = raw["case"], int(raw["repeat"]), raw["arm"]
            if (key[0] not in CASES or key[1] not in REPEATS or key[2] not in ARMS
                    or key in rows or raw["measured"] != "1"):
                raise ValueError(f"unexpected, duplicate or unmeasured arm {key}")
            score = float(raw["score"])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError(f"invalid score {key}")
            rows[key] = {"score": score, **{
                name: int(raw[name]) for name in required - {"case", "repeat", "arm", "measured", "score"}
            }}
    expected = {(case, repeat, arm) for case in CASES for repeat in REPEATS for arm in ARMS}
    if set(rows) != expected:
        raise ValueError(f"expected 12 arms, found {len(rows)}")
    return rows


def summarize(rows):
    pairs, repeat_rows = {}, []
    for case in CASES:
        observations, differences = [], []
        for repeat in REPEATS:
            baseline = rows[case, repeat, "patch-source"]["score"]
            candidate = rows[case, repeat, "native-patch"]["score"]
            difference = candidate - baseline
            differences.append(difference)
            observations.append({"repeat": repeat, "patch-source": baseline,
                                 "native-patch": candidate,
                                 "native_patch_minus_patch_source": difference})
        pairs[case] = {"pairs": observations, "mean_paired_difference": mean(differences),
                       "wins": sum(value > 0 for value in differences),
                       "ties": sum(value == 0 for value in differences),
                       "losses": sum(value < 0 for value in differences)}
    for repeat in REPEATS:
        baseline = mean(rows[case, repeat, "patch-source"]["score"] for case in CASES)
        candidate = mean(rows[case, repeat, "native-patch"]["score"] for case in CASES)
        repeat_rows.append({"repeat": repeat, "patch-source": baseline, "native-patch": candidate,
                            "native_patch_minus_patch_source": candidate - baseline})
    coverage = {}
    for arm in ARMS:
        selected = [value for key, value in rows.items() if key[2] == arm]
        coverage[arm] = {
            "planned": 6,
            "measured": 6,
            "repair_requests": sum(value["repair_requested"] for value in selected),
            "source_exposures": sum(value["source_feedback_observed"] for value in selected),
            "timing_valid": sum(value["controlled_timing_valid"] for value in selected),
            "first_repair_responses_completed": sum(value["repair_response_completed"] for value in selected),
            "prompt_patch_interface_uses": sum(value["prompt_patch_interface_used"] for value in selected),
            "native_patch_interface_uses": sum(value["native_patch_interface_used"] for value in selected),
            "request_shapes_valid": sum(value["request_shape_valid"] for value in selected),
            "patch_attempts": sum(value["patch_attempts"] for value in selected),
            "accepted_patches": sum(value["patch_accepted"] for value in selected),
            "tool_responses": sum(value["tool_responses"] for value in selected),
            "native_tool_responses": sum(value["native_tool_responses"] for value in selected),
            "native_argument_schema_valid": sum(value["native_argument_schema_valid"] for value in selected),
            "native_unindented_replacements": sum(value["native_unindented_replacements"] for value in selected),
            "nonempty_text_responses": sum(value["nonempty_text_responses"] for value in selected),
        }
    coverage_valid = (
        all(coverage[arm]["repair_requests"] == 6 and coverage[arm]["source_exposures"] == 6
            and coverage[arm]["timing_valid"] == 6 for arm in ARMS)
        and all(coverage[arm]["request_shapes_valid"] == 6 for arm in ARMS)
        and coverage["native-patch"]["native_patch_interface_uses"] == 6
        and coverage["native-patch"]["prompt_patch_interface_uses"] == 0
        and coverage["patch-source"]["prompt_patch_interface_uses"] == 6
        and coverage["patch-source"]["native_patch_interface_uses"] == 0
    )
    positive = (all(row["native_patch_minus_patch_source"] > 0 for row in repeat_rows)
                and all(value["mean_paired_difference"] >= 0 for value in pairs.values()))
    decision = ("support_native_patch" if coverage_valid and positive else
                "stop_candidate_no_gain" if coverage_valid else "inconclusive_coverage")
    return {
        "cases": list(CASES), "seed": 17, "release_sec": 250, "snapshot_sec": 395,
        "complete": True, "counts_by_arm": coverage, "paired_results_by_case": pairs,
        "case_macro_score_by_repeat": repeat_rows,
        "across_repeat_statistics": {
            metric: distribution([row[metric] for row in repeat_rows])
            for metric in ("patch-source", "native-patch", "native_patch_minus_patch_source")
        },
        "registered_decision": decision,
        "failure_diagnosis": (
            "The candidate used the sole required replace_line tool, but returned an indented "
            "replacement that violated the registered host contract; its attempted expression "
            "also continued to index integer pump values. No candidate patch was accepted."
        ),
        "interpretation": (
            "This controlled diagnostic estimates recovery conditional on one fixed induced failure. "
            "It is separate from the official PLE development score."
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
            ax.plot([x - .16, x + .16], [row["patch-source"], row["native-patch"]],
                    color="#657382", lw=1.7)
            ax.scatter([x - .16], [row["patch-source"]], s=68, color="#3C5C85", marker="o",
                       label="Prompt JSON patch" if index == 0 else None, zorder=3)
            ax.scatter([x + .16], [row["native-patch"]], s=68, color="#AF4932", marker="s",
                       label="Required native patch" if index == 0 else None, zorder=3)
        ax.grid(axis="y", alpha=.22)
        ax.set(xlim=(.55, 3.45), ylim=(-.055, 1.055), xticks=REPEATS,
               xticklabels=[f"Repeat {n}" for n in REPEATS],
               yticks=[0, .25, .5, .75, 1], ylabel="Mean normalized score across L and M")
        fig.suptitle("Native patch interface at 395 seconds", x=.105, ha="left", fontweight="bold")
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1), frameon=False, ncols=2)
        fig.text(.105, .046, "Fixed seed 17. Both arms see the same failure and five source lines.",
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
