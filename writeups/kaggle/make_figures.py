"""Recreate the Kaggle media from the diagnostic archives and public official-run observations."""
import argparse
import csv
import hashlib
import io
import json
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

HERE = Path(__file__).resolve().parent
PAPER, INK, MUTED, TEAL, GOLD, RUST = "#fbfaf6", "#17303a", "#485e66", "#087f74", "#e4ad4b", "#b74730"
PAIRS = {"P/Q": "actionable-feedback-v1", "R/S": "actionable-replication-v1", "T/U": "actionable-name-error-v1"}
ARMS = {"Reason code": "native-feedback", "Code + instruction": "native-actionable"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "text.color": INK,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER})


def draw_diagram(out):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set(xlim=(0, 10), ylim=(0, 6))
    ax.set_position([0, 0, 1, 1])
    ax.axis("off")
    ax.text(.45, 5.55, "How the harness reaches a file", size=24, weight="bold")
    ax.text(.46, 5.12, "Paths, file structure and the time limit constrain the model’s next action.", size=13, color=MUTED)

    def box(x, y, w, h, title, detail, fill=PAPER):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.02,rounding_size=.08",
                                    fc=fill, ec=MUTED, lw=1.3))
        ax.text(x+.16, y+h-.26, title, ha="left", va="top", weight="bold", size=14)
        ax.text(x+.16, y+.23, detail, ha="left", va="bottom", color=MUTED, size=11)

    def arrow(a, b):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=13, lw=1.4, color=MUTED))

    box(.50, 3.22, 2.52, 1.22, "Task and inputs", "Instructions, files\nand time limit")
    box(3.75, 3.22, 2.50, 1.22, "Delivery contract", "Extract paths, formats\nand required members")
    box(6.98, 3.22, 2.48, 1.22, "Agent loop", "Model, routed guidance\nand task-side tools")
    box(6.98, .81, 2.48, 1.22, "Working files", "Write and revise in the\nevaluator’s filesystem")
    box(3.75, .81, 2.50, 1.22, "Structural check", "Check presence, format\nand required members")
    box(.50, .81, 2.52, 1.22, "Deliver", "Report the final state\nbefore the deadline", "#deefe7")
    arrow((3.04, 3.83), (3.72, 3.83)); arrow((6.27, 3.83), (6.95, 3.83))
    arrow((8.24, 3.19), (8.24, 2.06)); arrow((6.94, 1.42), (6.28, 1.42))
    arrow((3.70, 1.42), (3.05, 1.42))
    ax.plot([5.00, 5.00, 7.48], [2.05, 2.65, 2.65], color=MUTED, lw=1.2)
    arrow((7.48, 2.63), (7.48, 3.20))
    ax.text(5.08, 2.74, "repair if time permits", size=10.5, color=MUTED)
    fig.savefig(out / "architecture.png", dpi=160)
    plt.close(fig)


def diagnostic_records(repo):
    records = []
    for split, directory in PAIRS.items():
        exp = repo / "docs" / "experiments" / directory
        with (exp / "trials.csv").open(newline="") as src:
            grades = {(r["case"], int(r["repeat"]), r["arm"]): float(r["score"]) for r in csv.DictReader(src)}
        manifest = json.loads((exp / "attempts" / "manifest.json").read_text())
        assert len(manifest) == 6 and len(grades) == 12, f"Incomplete split {split}"
        for name, info in sorted(manifest.items()):
            raw = (exp / "attempts" / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != info["sha256"]:
                raise ValueError(f"Archive digest mismatch: {name}")
            case, rep = re.search(r"-([p-u])-([1-3])-attempt-", name).groups()
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for arm, mode in ARMS.items():
                    d = json.loads(archive.read(mode + "/report.json"))
                    if not d["checkpoint"]["measured"] or d["checkpoint"]["target_sec"] != 395:
                        raise ValueError(f"Missing 395-second measurement: {name}")
                    score = grades[(case, int(rep), mode)]
                    if score != d["grade"]["score"]:
                        raise ValueError(f"Report/replay score mismatch: {name}")
                    t = d["tokens"]
                    records.append((split, arm, t["input_tokens"] + t["output_tokens"], score))
    return records


def score_vs_cost(out, observations, records):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 6.1))
    fig.subplots_adjust(left=.08, right=.96, top=.77, bottom=.24, wspace=.35)
    fig.text(.055, .92, "Score and reported token use", size=24, weight="bold")
    fig.text(.056, .86, "Usage counts reported input and output tokens, including cached input once.", size=12.5, color=MUTED)
    for ax in (a, b):
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylim(-.10, 1.07)
        ax.set_yticks([0, .25, .5, .75, 1])
        ax.grid(axis="y", alpha=.20)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1000:g}k" if v else "0"))
    a.set_title("Public PLE dev runs", loc="left", size=14, weight="bold")
    a.set_xlabel("Reported tokens per run", labelpad=6)
    a.set_ylabel("Official generation score")
    valid = [(i, r) for i, r in enumerate(observations, start=1)
             if all(r[k] is not None for k in ("score", "input_tokens", "output_tokens"))]
    if valid:
        reported = [r["input_tokens"] + r["output_tokens"] for _, r in valid]
        a.scatter(reported, [r["score"] for _, r in valid], color=TEAL, s=70)
        a.set_xlim(0, max(max(reported) * 1.13, 1))
        a.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        tasks = len({r["task"] for r in observations})
        a.text(.03, .93, f"{tasks} measured task{'s' if tasks != 1 else ''} · usage for {len(valid)} of {len(observations)} runs",
               transform=a.transAxes, color=MUTED, size=10)
        for total, (index, row) in zip(reported, valid):
            a.annotate(f"Run {index}", (total, row["score"]), xytext=(0, 10),
                       textcoords="offset points", ha="center", color=TEAL, size=10)
    else:
        a.set_xticks([])
        a.text(.5, .57, "No run has both an official\nscore and recorded token usage.",
               transform=a.transAxes, ha="center", va="center", color=MUTED, size=13)
    b.set_title("Original repair diagnostics", loc="left", size=14, weight="bold")
    b.set_ylabel("Mean 395-second file score")
    b.set_xlabel("Mean reported tokens per run", labelpad=6)
    anchors = {"P/Q": "P/Q", "R/S": "R/S", "T/U": "T/U"}
    for i, split in enumerate(PAIRS):
        for arm, marker, color in zip(ARMS, ("o", "s"), (MUTED, TEAL)):
            rows = [r for r in records if r[:2] == (split, arm)]
            x, y = statistics.mean(r[2] for r in rows), statistics.mean(r[3] for r in rows)
            b.scatter(x, y, marker=marker, s=72, c=color, zorder=3)
            b.annotate(anchors[split], (x, y), xytext=(0, 10), textcoords="offset points", ha="center", color=color, size=10)
    b.set_xlim(4800, 8500)
    b.set_xticks([5000, 6000, 7000, 8000])
    handles = [Line2D([], [], color=c, marker=m, linestyle="none", label=l) for l,c,m in zip(ARMS,(MUTED,TEAL),("o","s"))]
    b.legend(handles=handles, frameon=False, loc="upper right", fontsize=9.5)
    fig.text(.055, .095, "Each point on the right averages six runs on two inputs, all scored at 395 seconds.", size=11.5)
    fig.text(.055, .053, "Usage excludes unfinished responses whose token counts were unavailable. Monetary charges were unavailable.", size=10.5, color=MUTED)
    fig.savefig(out / "score-vs-cost.png", dpi=160)
    plt.close(fig)


def outcomes(out, data):
    obs, n = data["observations"], data["n_public_tasks"]
    by_task = defaultdict(list)
    run_keys = set()
    for row in obs:
        key = (row["task"], row["run_id"], row.get("run_attempt", 1))
        if key in run_keys:
            raise ValueError(f"Duplicate task run {key}")
        run_keys.add(key)
        by_task[row["task"]].append(row)
    if len(by_task) > n:
        raise ValueError("Distinct task count exceeds the public split")
    counted = Counter()
    for trials in by_task.values():
        scored = [row for row in trials if row["score"] is not None]
        if not scored:
            category = "Run without a recorded score"
        elif all(row["score"] == 0 for row in scored):
            empty_seen = any(row.get("capture_files") == 0 for row in scored)
            category = "Zero score, empty capture observed" if empty_seen else "Zero score"
        elif all(row["score"] > 0 for row in scored):
            category = "Positive score"
        else:
            category = "Both positive and zero scores"
        counted[category] += 1
    counted["No run recorded"] = n - len(by_task)
    ordered = sorted(counted, key=lambda k: -counted[k])
    fig, ax = plt.subplots(figsize=(10, 5.4))
    fig.subplots_adjust(left=.37, right=.91, top=.71, bottom=.24)
    fig.text(.06, .9, "Coverage of the 29 public dev tasks", size=24, weight="bold")
    fig.text(.06, .82, f"{data['model']}  ·  {len(obs)} runs across {len(by_task)} of {n} tasks",
             size=12.5, color=MUTED)
    for j, key in enumerate(ordered):
        color = "#bfc6c4" if key == "No run recorded" else (RUST if "zero" in key.lower() else TEAL)
        ax.barh(j, counted[key], height=.42, color=color)
        ax.text(counted[key]+.45, j, f"{counted[key]} / {n}", va="center", size=13, weight="bold")
    ax.set(yticks=range(len(ordered)), yticklabels=ordered, xlim=(0, n+2.5), xlabel="Number of distinct public tasks")
    ax.invert_yaxis()
    ticks = MaxNLocator(nbins=5, integer=True).tick_values(0, n)
    ax.set_xticks([tick for tick in ticks if 0 <= tick < n] + [n])
    ax.spines[["top","left","right"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.grid(axis="x", alpha=.13)
    fig.text(.06, .06, "Each task counts once. A repeated run can clarify a failure without increasing coverage.", size=11, color=MUTED)
    fig.savefig(out / "dev-failures.png", dpi=160)
    plt.close(fig)


def cover(out):
    fig, ax = plt.subplots(figsize=(12, 6.75))
    fig.patch.set_facecolor("#142f38")
    ax.set_position([0,0,1,1]); ax.set_xlim(0,12); ax.set_ylim(0,6.75); ax.axis("off")
    ax.text(.8, 5.52, "PHYSICAL ENGINEERING’S LAST EXAM", color="#9ad7c2", size=13, weight="bold")
    ax.text(.75, 4.2, "What reaches", color=PAPER, size=48, weight="bold")
    ax.text(.75, 3.05, "the file?", color=PAPER, size=48, weight="bold")
    ax.text(.80, 1.15, "A controlled study of agent repair and file delivery", color="#cbdcdb", size=16)
    for x, y, ecol in [(8.62,3.10,"#548a85"),(8.42,2.88,"#74b5a4"),(8.22,2.66,"#aecdb7")]:
        ax.add_patch(Rectangle((x,y),2.58,2.53,fc="#183e46",ec=ecol,lw=1.8))
    for i, width in enumerate([1.74, 1.16, 1.50, .91]):
        ax.plot([8.57,8.57+width], [4.65-i*.38]*2, color="#a6c6b3", lw=2.8, solid_capstyle="round")
    ax.add_patch(Rectangle((8.54,2.06),2.61,.34,fc=GOLD,ec="none"))
    fig.savefig(out / "cover.png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=HERE.parents[1], help="Repository containing the committed experiment archives")
    parser.add_argument("--observations", type=Path, default=HERE/"official-observations.json")
    parser.add_argument("--out", type=Path, default=HERE/"media")
    args = parser.parse_args()
    data = json.loads(args.observations.read_text())
    records = diagnostic_records(args.repo)
    args.out.mkdir(exist_ok=True, parents=True)
    draw_diagram(args.out)
    score_vs_cost(args.out, data["observations"], records)
    outcomes(args.out, data)
    cover(args.out)


if __name__ == "__main__":
    main()
