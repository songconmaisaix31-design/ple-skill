#!/usr/bin/env python3
"""Static F-01 (fair play) check for this PLE entry.

Official rule, docs/rules.md:

    "Do not hard-code task answers or detect specific tasks to branch on
    them, dev tasks included. The dev-set graders and reference files are
    public so you can evaluate locally, and your harness must never read or
    use them. A harness that reads its own artifacts/ at build or run time
    (from disk, git history, or the network) breaks this rule."

This checker deliberately scans ONLY the files that are part of the runtime:
serve.py, skillkit/, and the skills injected into the model context.
docs/, writeups/ and devtools/ are developer notes and are out of scope --
they are never opened by serve.py or anything it imports.

No dev task id is hard-coded here. Pass --dev-set <official eval/dev_set.yaml>
for an exact id check on a machine that has the official kit.

    python3 devtools/f01_check.py
    python3 devtools/f01_check.py --dev-set ~/ple-work/ple-official/eval/dev_set.yaml
"""
import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RUNTIME_PATTERNS = [
    "serve.py", "dryrun.py", "submission.yaml", "requirements.txt",
    "skillkit/*.py",
    "skills/*/SKILL.md", "skills/*/checklist.md", "skills/_shared/validate.py",
]

# Baseline-derived files must not ship in the entry. They live outside the
# repo (workspace backup) after the F-01 cleanup.
FORBIDDEN_FILES = ["PLE_domain_skeleton.md", "skeleton2.json", "_build"]

REF_MARKERS = [
    "ple-template", "PLE_domain_skeleton", "skeleton2.json", "_build/",
    "graders/", "paper_score.py", "submission-template",
]

# Concrete answer-level values: never acceptable in runtime context.
CONCRETE_PATTERNS = [
    (r"\b\d{1,3}(?:,\d{3}){2,}\b", "6 位以上千分位具体数值"),
    (r"\b[A-Z]{3,}-\d{4}-\d{2,}\b", "具体项目文号"),
    (r"\b\d{2}/\d{2}/20\d{2}\b", "具体日期 MM/DD/YYYY"),
    (r"\b\d+(?:\.\d+)?\s?MW\b", "具体功率结论值"),
]

TASK_BRANCH = re.compile(r"\bif\b[^#\n]*\btask_(?:id|name|slug)\b|==\s*['\"]task", re.I)
ARTIFACT_READ = re.compile(r"(?:open|glob|listdir|read_text|Path)\s*\([^)]*artifacts", re.I)
ID_LINE = re.compile(r"^\s*-\s*id:\s*([a-z0-9][a-z0-9-]+)\s*$", re.M)


def runtime_files():
    out = []
    for pat in RUNTIME_PATTERNS:
        out += [p for p in glob.glob(os.path.join(ROOT, pat)) if os.path.isfile(p)]
    return sorted(set(out))


def read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def collect():
    files = runtime_files()
    text = {p: read(p) for p in files}
    code = {p: t for p, t in text.items() if p.endswith(".py")}
    return files, text, code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-set", default="", help="official eval/dev_set.yaml for exact task-id check")
    a = ap.parse_args()

    files, text, code = collect()
    results = []

    def check(cid, title, bad, detail_ok="扫描干净"):
        ok = not bad
        results.append((cid, title, ok, detail_ok if ok else "; ".join(str(x) for x in bad[:5])))
        return ok

    # C-01 frontmatter must not enumerate dev task ids
    check("C-01", "runtime skill 无 covers: dev task 列表",
          [os.path.relpath(p, ROOT) for p, t in text.items() if re.search(r"^covers:\s*\S", t, re.M)],
          f"{len(files)} 个 runtime 文件已扫")

    # C-02 no path/marker pointing at dev graders or reference artifacts
    hits = [f"{os.path.relpath(p, ROOT)}:{m}" for p, t in text.items()
            for m in REF_MARKERS if m in t]
    check("C-02", "runtime 不引用 dev graders / reference 数据", hits)

    # C-03 no concrete answer-level values in runtime context
    hits = []
    for p, t in text.items():
        for pat, label in CONCRETE_PATTERNS:
            for m in re.finditer(pat, t):
                hits.append(f"{os.path.relpath(p, ROOT)}:{label}:{m.group(0)[:40]}")
    check("C-03", "runtime 无具体答案数值 / 文号 / 日期", hits)

    # C-04 baseline-derived files removed from the entry
    present = [n for n in FORBIDDEN_FILES if os.path.exists(os.path.join(ROOT, n))]
    check("C-04", "baseline 反推数据已移出参赛仓库", present,
          "PLE_domain_skeleton.md / skeleton2.json / _build/ 均不存在")

    # C-05 model_api must stay on the sponsored cloud model
    sub = read(os.path.join(ROOT, "submission.yaml"))
    m = re.search(r"^model_api:\s*(\S+)", sub, re.M)
    api = m.group(1) if m else ""
    check("C-05", "model_api 仍为 google-cloud/*（不得换 local runs 前缀）",
          [] if api.startswith("google-cloud/") else [f"model_api={api or '<missing>'}"],
          f"model_api={api}")

    # C-06 no branching on a task identifier
    hits = [f"{os.path.relpath(p, ROOT)}:{line.strip()[:80]}"
            for p, t in code.items() for line in t.splitlines() if TASK_BRANCH.search(line)]
    check("C-06", "skillkit 无按 task id 的条件分支", hits)

    # C-07 harness must not read its own artifacts/ at build or run time
    hits = [f"{os.path.relpath(p, ROOT)}:{m.group(0)[:60]}"
            for p, t in code.items() for m in ARTIFACT_READ.finditer(t)]
    check("C-07", "serve/skillkit 不读取自己的 artifacts/", hits)

    # C-08 exact dev task id check, only when the official dev_set.yaml is given
    if a.dev_set and os.path.isfile(a.dev_set):
        ids = set(ID_LINE.findall(read(a.dev_set)))
        hits = [f"{os.path.relpath(p, ROOT)}:{i}" for p, t in text.items() for i in ids
                if re.search(r"(?<![a-z0-9-])" + re.escape(i) + r"(?![a-z0-9-])", t)]
        check("C-08", f"runtime 不含 dev_set.yaml 中 {len(ids)} 个 task id", hits,
              f"精确比对 {len(ids)} 个 id，全部未出现")
    else:
        results.append(("C-08", "精确 dev task id 比对（需官方 dev_set.yaml）", None,
                        "SKIP —— 传 --dev-set <path> 可在云主机上补做"))

    width = max(len(t) for _, t, _, _ in results) + 2
    print(f"{'ID':7s} {'CHECK':{width}s} RESULT  DETAIL")
    hard = [r for r in results if r[2] is not None]
    for cid, title, ok, detail in results:
        status = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        print(f"{cid:7s} {title:{width}s} {status:6s}  {detail}")
    passed = sum(1 for r in hard if r[2])
    failed = [r[0] for r in hard if not r[2]]
    print(f"\nF-01 静态合规检查：{'PASS' if not failed else 'FAIL'} "
          f"({passed}/{len(hard)} 硬检查通过)"
          + (f"；未过 {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
