"""Summarize the fixed-seed, paired 395-second storage experiment from a long CSV."""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev, variance


PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "docs/experiments/paired-storage-v1/protocol.json"
PROTOCOL = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
STUDY_ARMS = {"paired-storage-v1": ("legacy", "text"), "repair-source-v1": ("text", "text-source")}
REPAIR_FIELDS = {"repair_requested", "source_feedback_observed", "completed_files"}
FIELDS = {"case", "repeat", "arm", "measured", "score", "feasible", "optimal"}


def flag(value, name):
    if value not in ("1", "0"):
        raise ValueError(f"{name} must be 1 or 0")
    return value == "1"


def load_rows(path, protocol=PROTOCOL):
    arms = STUDY_ARMS[protocol["id"]]
    repair = protocol["id"] == "repair-source-v1"
    cases = protocol["split"]["holdout"]
    repeats = {str(r) for r in protocol["design"]["repetition_ids"]}
    fields = FIELDS | REPAIR_FIELDS if repair else FIELDS
    results = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not fields.issubset(header):
            raise ValueError(f"expected distinct column names including {', '.join(sorted(fields))}")
        for row in reader:
            label = f"CSV line {reader.line_num}"
            if None in row or any(row[name] is None for name in fields):
                raise ValueError(f"{label}: unexpected row length")
            case, repeat, arm = row["case"], row["repeat"], row["arm"]
            if case not in cases or repeat not in repeats or arm not in arms:
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
            if repair:
                trial = results[key]
                for field in ("repair_requested", "source_feedback_observed"):
                    trial[field] = flag(row[field], f"{label} {field}") if row[field] else None
                if trial["source_feedback_observed"] and (arm != arms[1] or not trial["repair_requested"]):
                    raise ValueError(f"{label}: observed source requires a candidate repair request")
                files = row["completed_files"]
                if (measured and files not in ("0", "1", "2")) or (not measured and files):
                    raise ValueError(f"{label}: expected zero to two exported files for measured trials only")
                trial["completed_files"] = int(files) if measured else None
    return results


def distribution(values):
    return {"n": len(values), "mean": mean(values), "sample_variance": variance(values),
            "sample_std": stdev(values)}


def summarize(rows, protocol=PROTOCOL):
    planned_cases = tuple(protocol["split"]["holdout"])
    repeats = tuple(protocol["design"]["repetition_ids"])
    arms = STUDY_ARMS[protocol["id"]]
    baseline, candidate = arms
    repair = protocol["id"] == "repair-source-v1"
    delta_key = "text_source_minus_text" if repair else "text_minus_legacy"
    missing = []
    unmeasured = []
    coverage = {arm: {"planned": len(planned_cases) * len(repeats), "measured": 0, "feasible": 0, "optimal": 0}
                for arm in arms}
    if repair:
        for counts in coverage.values():
            counts.update(repair_requests=0, source_exposures=0, unknown_exposures=0,
                          exported_nonempty_files=0, trials_with_both_files=0)
    metrics = (*arms, delta_key)
    by_repeat = {repeat: {metric: [] for metric in metrics} for repeat in repeats}
    cases = {}
    for case in planned_cases:
        gains = []
        pairs = []
        measured_by_arm = dict.fromkeys(arms, 0)
        for repeat in repeats:
            pair = {"repeat": repeat}
            for arm in arms:
                row = rows.get((case, repeat, arm))
                counts = coverage[arm]
                if repair:
                    counts["repair_requests"] += bool(row and row["repair_requested"])
                    counts["source_exposures"] += bool(row and row["source_feedback_observed"])
                    counts["unknown_exposures"] += row is None or row["source_feedback_observed"] is None
                if row is None or not row["measured"]:
                    target = missing if row is None else unmeasured
                    target.append({"case": case, "repeat": repeat, "arm": arm})
                    pair[arm] = None
                    continue
                pair[arm] = row["score"]
                by_repeat[repeat][arm].append(row["score"])
                measured_by_arm[arm] += 1
                counts["measured"] += 1
                counts["feasible"] += row["feasible"]
                counts["optimal"] += row["optimal"]
                if repair:
                    counts["exported_nonempty_files"] += row["completed_files"]
                    counts["trials_with_both_files"] += row["completed_files"] == 2
            delta = None
            if all(pair[arm] is not None for arm in arms):
                delta = pair[candidate] - pair[baseline]
                by_repeat[repeat][delta_key].append(delta)
                gains.append(delta)
            pairs.append({**pair, delta_key: delta})
        cases[case] = {
            "planned_pairs": len(repeats), "measured_pairs": len(gains), "measured_by_arm": measured_by_arm,
            "wins": sum(d > 0 for d in gains), "ties": gains.count(0), "losses": sum(d < 0 for d in gains),
            "mean_paired_difference": mean(gains) if gains else None, "pairs": pairs,
        }
    per_repeat = []
    for repeat, values in by_repeat.items():
        group = {"repeat": repeat}
        for metric, scores in values.items():
            group[metric] = mean(scores) if len(scores) == len(planned_cases) else None
        per_repeat.append(group)
    complete = not (missing or unmeasured)
    aggregate = None
    decision = "incomplete"
    if complete:
        aggregate = {metric: distribution([group[metric] for group in per_repeat])
                     for metric in metrics}
        case_criterion = all(case["mean_paired_difference"] >= 0 for case in cases.values())
        repeat_criterion = all(group[delta_key] > 0 for group in per_repeat)
        decision = "support_on_this_family" if case_criterion and repeat_criterion else "no_positive_replication"
        if repair and coverage[candidate]["source_exposures"] == 0:
            decision = ("inconclusive_exposure_unverified" if coverage[candidate]["unknown_exposures"]
                        else "inconclusive_no_exposure")
    fixed = protocol["fixed_settings"]
    return {
        "cases": planned_cases,
        "seed": fixed["seed"],
        "declared_budget_sec": fixed["declared_budget_seconds"],
        "snapshot_sec": fixed["external_checkpoint_seconds"],
        "complete": complete,
        "missing_rows": missing,
        "unmeasured_rows": unmeasured,
        "counts_by_arm": coverage,
        "paired_results_by_case": cases,
        "case_macro_score_by_repeat": per_repeat,
        "across_repeat_statistics": aggregate,
        "registered_decision": decision,
        "registered_rule": protocol["decision"],
        "interpretation": (
            "The mean and sample variance (n-1 denominator) describe repetition-level case averages "
            "at one fixed seed. A tied observed difference supplies no evidence of superiority. "
            "An equivalence claim would require a separately specified equivalence margin and test."
        ),
    }


def paired_plot(path, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    baseline, candidate = report["counts_by_arm"]
    repeats = [group["repeat"] for group in report["case_macro_score_by_repeat"]]
    cases = " and ".join(case.upper() for case in report["cases"])
    names = (("Traceback feedback", "Traceback + source") if candidate == "text-source"
             else ("Original tool loop", "First Python action"))
    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        fig, ax = plt.subplots(figsize=(7.3, 4.3))
        for index, group in enumerate(report["case_macro_score_by_repeat"]):
            x = group["repeat"]
            control, treatment = group[baseline], group[candidate]
            if control is not None and treatment is not None:
                ax.plot([x - .16, x + .16], [control, treatment], color="#657382", lw=1.7, zorder=2)
            for shift, value, color, marker, name in (
                (-.16, control, "#3C5C85", "o", names[0]),
                (.16, treatment, "#AF4932", "s", names[1]),
            ):
                ax.scatter([x + shift] if value is not None else [], [value] if value is not None else [],
                           s=68, color=color, marker=marker, zorder=3, label=name if index == 0 else None)
        ax.grid(axis="y", alpha=.22)
        ax.set(xlim=(.55, 3.45), ylim=(-.055, 1.055), xticks=repeats,
               xticklabels=[f"Repeat {n}" for n in repeats], yticks=[0, .25, .5, .75, 1],
               ylabel=f"Mean normalized score across {cases}")
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
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH, help="frozen study protocol JSON")
    parser.add_argument("--output", type=Path, help="save summary JSON (default stdout)")
    parser.add_argument("--plot", type=Path, help="save paired figure; requires matplotlib")
    args = parser.parse_args()
    try:
        protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
        if protocol.get("id") not in STUDY_ARMS:
            raise ValueError("unknown storage experiment protocol")
        report = summarize(load_rows(args.csv_file, protocol), protocol)
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
