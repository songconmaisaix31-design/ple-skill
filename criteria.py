#!/usr/bin/env python3
"""Executable acceptance criteria for the PLE harness.

Every criterion in GOAL.md has an ID here. This script is the single source of
truth: it prints PASS / FAIL / BLOCKED / SKIP per criterion and exits non-zero
if any GATE fails.

  python3 criteria.py                       # uses ./ and the local template clone
  python3 criteria.py --template <path>     # point at the competition template
"""
import argparse, asyncio, glob, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RESULTS = []
DEV_TASKS = 29          # size of the public dev set; fewer means data is missing


def data_ready(tasks):
    return len(tasks) >= DEV_TASKS


def rec(cid, title, status, detail, layer="A"):
    RESULTS.append({"id": cid, "title": title, "status": status, "detail": detail, "layer": layer})


def gate_pass(cid, title, cond, detail, layer="A"):
    rec(cid, title, "PASS" if cond else "FAIL", detail, layer)
    return cond


# ---------------- GATE ----------------

def g01_layout():
    need = ["submission.yaml", "serve.py", "requirements.txt", "skillkit/harness.py"]
    missing = [f for f in need if not os.path.exists(os.path.join(HERE, f))]
    return gate_pass("G-01", "仓库根结构完整", not missing,
                     "缺: " + ", ".join(missing) if missing else "submission.yaml / serve.py / requirements.txt / skillkit 齐全")


def g02_submission_yaml():
    path = os.path.join(HERE, "submission.yaml")
    if not os.path.exists(path):
        return gate_pass("G-02", "submission.yaml 合法", False, "文件不存在")
    raw = open(path, encoding="utf-8").read()
    if len(raw.encode()) > 16 * 1024:
        return gate_pass("G-02", "submission.yaml 合法", False, "超过 16 KiB")
    def field(k):
        m = re.search(rf"^{k}:\s*(.+)$", raw, re.M)
        return m.group(1).strip() if m else ""
    name = field("name")
    api = field("model_api")
    serve = raw.split("serve:", 1)[1].splitlines()[0].strip() if "serve:" in raw else ""
    ok_name = bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,38}", name or ""))
    ok_api = bool(re.match(r"(google-cloud|openai|anthropic|gemini|openai-compatible)/.+", api or ""))
    ok_serve = "{src}" in serve
    allow = {"name", "model_api", "model_base_url", "install", "serve", "env"}
    keys = set(re.findall(r"^([a-z_]+):", raw, re.M))
    unknown = keys - allow
    problems = []
    if not ok_name: problems.append(f"name 不合规({name})")
    if not ok_api: problems.append(f"model_api 不合规({api})")
    if not ok_serve: problems.append("serve 未引用 {src}")
    if unknown: problems.append(f"未知顶层键 {sorted(unknown)}")
    return gate_pass("G-02", "submission.yaml 合法", not problems,
                     "; ".join(problems) or f"name={name} model_api={api}")


def g03_no_secret():
    pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})")
    hits = []
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "artifacts", "runs")]
        for f in files:
            if f == ".env" or f.endswith((".png", ".jpg", ".zip")):
                continue
            p = os.path.join(root, f)
            try:
                if pat.search(open(p, errors="ignore").read()):
                    hits.append(os.path.relpath(p, HERE))
            except OSError:
                pass
    return gate_pass("G-03", "无泄漏 API key", not hits, "疑似泄漏: " + ", ".join(hits) if hits else "扫描干净（.env 允许存在）")


def g04_compile():
    targets = ["serve.py", "dryrun.py", "criteria.py"] + glob.glob(os.path.join(HERE, "skillkit", "*.py"))
    targets.append(os.path.join(HERE, "skills", "_shared", "validate.py"))
    bad = []
    for t in targets:
        r = subprocess.run([sys.executable, "-m", "py_compile", t], capture_output=True)
        if r.returncode:
            bad.append(os.path.basename(t) + ": " + r.stderr.decode()[:200])
    return gate_pass("G-04", "全部 Python 可编译", not bad, "; ".join(bad) or f"{len(targets)} 个文件通过")


# ---------------- DATA-DRIVEN ----------------

def load_tasks(template):
    """Development-only: read dev instructions from an EXTERNAL template dir.

    This function is never reached by serve.py / skillkit (the actual harness).
    Official fair-play rule allows local evaluation, but the harness itself
    must never read dev graders or reference files. Path is supplied explicitly;
    no reference-data path is baked into this repo.
    """
    base = os.path.join(template, "artifacts") if template else ""
    out = {}
    if not base or not os.path.isdir(base):
        return out
    for d in sorted(os.listdir(base)):
        tj = os.path.join(base, d, "trajectory.json")
        if not os.path.exists(tj):
            continue
        try:
            steps = json.load(open(tj))["steps"]
            out[d] = ([s for s in steps if s.get("source") == "user"][0]["message"],
                      os.path.join(base, d, "files"))
        except Exception:
            pass
    return out


def truth_domains(path):
    """Development-only ground truth, supplied from OUTSIDE the repo.

    The previous in-repo skeleton2.json was derived from baseline artifacts and
    has been removed (F-01). Without an explicit --truth, G-07 is BLOCKED
    rather than silently scoring 0/29.
    """
    if not path or not os.path.isfile(path):
        return {}
    try:
        sk = json.load(open(path))
        if isinstance(sk, dict):
            sk = list(sk.values())
        return {x["task"]: x.get("domain") for x in sk if isinstance(x, dict) and "task" in x}
    except Exception:
        return {}


def g05_skill_coverage(tasks, truth):
    if not data_ready(tasks):
        rec("G-05", "skill 覆盖 dev 题", "BLOCKED",
            f"只有 {len(tasks)}/{DEV_TASKS} 题题面，判据不可信；请提供 ple-template 或 HF dev 数据", "D")
        return False
    from skillkit import router
    dirs = {d for d in os.listdir(os.path.join(HERE, "skills"))
            if os.path.isdir(os.path.join(HERE, "skills", d))}
    covered, uncovered = 0, []
    for t, (inst, _) in tasks.items():
        rt = router.route(inst)["domain"]
        if rt in dirs:
            covered += 1
        else:
            uncovered.append(t)
    return gate_pass("G-05", "skill 覆盖 dev 题", covered == len(tasks),
                     f"{covered}/{len(tasks)} 有归属 skill" + (f"；缺 {uncovered}" if uncovered else ""), "D")


def g06_spec_paths(tasks):
    if not data_ready(tasks):
        rec("G-06", "specgen 路径解析 ≥ 25/29", "BLOCKED",
            f"只有 {len(tasks)}/{DEV_TASKS} 题题面，阈值不得随数据量退化", "D")
        return False
    from skillkit import specgen
    ok, low = 0, []
    for t, (inst, _) in tasks.items():
        s = specgen.build(inst)
        if s.get("deliverable"):
            ok += 1
        else:
            low.append(t)
    return gate_pass("G-06", "specgen 路径解析 ≥ 25/29", ok >= 25,
                     f"{ok}/{len(tasks)} 命中" + (f"；未命中 {low}" if low else ""), "D")


def g07_router(tasks, truth):
    if not data_ready(tasks):
        rec("G-07", "router 细领域判定 ≥ 23/29", "BLOCKED",
            f"只有 {len(tasks)}/{DEV_TASKS} 题题面，阈值不得随数据量退化", "D")
        return False
    if not truth:
        rec("G-07", "router 细领域判定 ≥ 23/29", "BLOCKED",
            "缺外部 ground truth；用 --truth <path> 指向仓库外的 domain 标注文件", "D")
        return False
    from skillkit import router, specgen
    hit, miss = 0, []
    for t, (inst, _) in tasks.items():
        got = router.route(inst, specgen.build(inst))["subdomain"]
        want = truth.get(t)
        if want == got:
            hit += 1
        elif want:
            miss.append(f"{t}({want}!={got})")
    return gate_pass("G-07", "router 细领域判定 ≥ 23/29", hit >= 23,
                     f"{hit}/{len(tasks)} 命中" + (f"；偏差 {miss}" if miss else ""), "D")


def g08_guard_regression(tasks):
    from skillkit.transport import LocalTransport
    from skillkit.guard import Guard
    from skillkit import specgen
    good, bad, runs = [], [], 0
    for t, (inst, fj) in tasks.items():
        if not os.path.isdir(fj):
            continue
        spec = specgen.build(inst)
        dl = spec.get("deliverable") or ""
        if not dl:
            continue
        rel = dl.lstrip("/")
        cands = [f for f in glob.glob(os.path.join(fj, "app", "files", "*"))
                 + glob.glob(os.path.join(fj, "filesystem", "*")) if os.path.isdir(f)]
        base = next((c for c in cands if os.path.exists(os.path.join(c, rel))), None) \
            or (fj if os.path.exists(os.path.join(fj, rel)) else (cands[0] if cands else fj))
        spec["deliverable"] = rel
        runs += 1
        st, _ = asyncio.run(Guard(LocalTransport(base), base, spec).run())
        (good if st in ("PASS", "WARN") else bad).append(f"{t}:{st}")
    if runs < DEV_TASKS:
        rec("G-08", "guard 对 baseline 回归", "BLOCKED",
            f"只找到 {runs}/{DEV_TASKS} 份 baseline artifacts，不能据此判 PASS", "D")
        return False
    need = 19
    return gate_pass("G-08", f"guard 对 baseline 回归 ≥ {need}/{runs}", len(good) >= need,
                     f"{len(good)}/{runs} PASS/WARN" + (f"；未过 {bad}" if bad else ""), "D")


def g09_dryrun():
    r = subprocess.run([sys.executable, os.path.join(HERE, "dryrun.py")],
                       capture_output=True, cwd=HERE)
    out = r.stdout.decode()
    ok = r.returncode == 0 and "file exists=True" in out and "guard at finish: FAIL" in out \
        and "guard at finish: PASS" in out
    return gate_pass("G-09", "dryrun 闭环（拒绝→修复→放行）", ok,
                     "退出码 %d；%s" % (r.returncode, "守卫拒绝后修复放行" if ok else out[-300:]))


def g12_f01():
    """F-01 static check is part of GATE-A: compliance must not regress."""
    p = os.path.join(HERE, "devtools", "f01_check.py")
    if not os.path.isfile(p):
        return gate_pass("G-12", "F-01 静态合规自检", False, "devtools/f01_check.py 缺失")
    r = subprocess.run([sys.executable, p], capture_output=True, cwd=HERE)
    out = r.stdout.decode(errors="replace")
    ok = r.returncode == 0 and "F-01 静态合规检查：PASS" in out
    detail = "PASS" if ok else (out[-300:] or r.stderr.decode(errors="replace")[-300:])
    return gate_pass("G-12", "F-01 静态合规自检", ok, detail)


def g10_artifacts():
    p = os.path.join(HERE, "artifacts")
    docker = shutil.which("docker") is not None
    if not os.path.isdir(p):
        rec("G-10", "官方导出目录的本地预检",
            "FAIL" if docker else "BLOCKED",
            "未生成 —— 在有 Docker 的机器上跑 eval/run.py" if docker else
            "未生成 —— 本机连 Docker 都不可用", "B")
        return False
    tasks = [d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))]
    files = sum(len(fs) for _, _, fs in os.walk(p))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs)
    manifest = os.path.isfile(os.path.join(p, "manifest.json"))
    ok = manifest and 0 < len(tasks) <= DEV_TASKS and files <= 10000 and size <= 512 * 1024 * 1024
    gate_pass("G-10", "官方导出目录的本地预检", ok,
              f"{len(tasks)}/{DEV_TASKS} 个任务目录，manifest={manifest}，{files} 文件 / {size/1e6:.0f} MB；可用性由 kit artifacts 核验", "B")
    return ok


def g11_known_blockers():
    """Criteria that need Docker + a real model. Reported, never silently assumed."""
    has_docker = shutil.which("docker") is not None
    key = bool(os.environ.get("MODEL_PROXY_URL") or os.environ.get("MODEL_API_KEY")
               or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    rec("T-01", "kit check 十阶段全过", "BLOCKED" if not has_docker else "TODO",
        "需要 Docker + uv + harbor==0.20.0", "B")
    rec("T-02", "至少一题产物通过 kit artifacts，按 29 题计开发集均分",
        "BLOCKED" if not has_docker else "TODO", "需要 Docker 跑 eval/run.py", "B")
    rec("T-03", "真模型端到端跑通 serve.py", "BLOCKED" if not key else "TODO",
        "需要 MODEL_PROXY_URL/KEY 或 MODEL_BASE_URL + MODEL_API_KEY", "B")
    rec("T-04", "dev 分数 ≥ baseline 参照", "TODO", "依赖 T-02 与 T-03", "B")
    rec("F-01", "无按题指纹分支（提交前人工复核最终 commit）", "TODO",
        "静态指纹已由 G-12 自动检查；提交前复核运行日志与最终 commit 内容", "B")
    rec("F-02", "artifacts 为提交版 harness 原样产出", "TODO",
        "manifest.json 哈希需与代码同 commit；改代码必须重跑全量 dev", "B")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=os.environ.get("PLE_TEMPLATE", ""),
                    help="外部 ple-template 目录；仓库不内置任何 dev 题面或 reference 数据")
    ap.add_argument("--truth", default=os.environ.get("PLE_TRUTH", ""),
                    help="仓库外的 domain ground-truth JSON，供 G-07 开发期判据使用")
    a = ap.parse_args()

    tasks = load_tasks(a.template)
    truth = truth_domains(a.truth)
    # Environment prerequisite, deliberately not part of GATE-A: a missing
    # template must never be reported as a code failure or as a silent pass.
    rec("INFO", "dev 题面可读（环境前置）", "PASS" if data_ready(tasks) else "BLOCKED",
        f"{len(tasks)}/{DEV_TASKS} 题" +
        (f" from {a.template}" if a.template else "（未指定外部 template，开发期判据不可用）"), "E")

    g01_layout()
    g02_submission_yaml()
    g03_no_secret()
    g04_compile()
    g05_skill_coverage(tasks, truth)
    g06_spec_paths(tasks)
    g07_router(tasks, truth)
    g08_guard_regression(tasks)
    g09_dryrun()
    g12_f01()
    g10_artifacts()
    g11_known_blockers()

    width = max(len(r["title"]) for r in RESULTS) + 2
    print(f"{'ID':7s} {'CRITERION':{width}s} {'层':2s} STATUS   DETAIL")
    for r in RESULTS:
        print(f"{r['id']:7s} {r['title']:{width}s} {r['layer']:2s} {r['status']:8s} {r['detail'][:110]}")

    layers = {k: [r for r in RESULTS if r["layer"] == k] for k in "ADEB"}
    a_fail = [r for r in layers["A"] if r["status"] != "PASS"]
    d_open = [r for r in layers["D"] if r["status"] != "PASS"]
    b_open = [r for r in layers["B"] if r["status"] != "PASS"]
    print(f"\nGATE-A 代码/仓库自洽（本地可完成）：{'PASS' if not a_fail else 'FAIL'} "
          f"({len(layers['A'])-len(a_fail)}/{len(layers['A'])})")
    print(f"GATE-D dev 数据回归（需 ple-template）：{'PASS' if not d_open else 'OPEN'} "
          f"({len(layers['D'])-len(d_open)}/{len(layers['D'])} 已过)")
    print(f"GATE-B 可提交（需 Docker + 真模型）：{'PASS' if not b_open else 'OPEN'} "
          f"({len(layers['B'])-len(b_open)}/{len(layers['B'])} 已过)")
    if a_fail:
        print("A 层未过：" + ", ".join(f"{r['id']}({r['status']})" for r in a_fail))
    if d_open:
        print("D 层未过：" + ", ".join(f"{r['id']}({r['status']})" for r in d_open))
    if b_open:
        print("B 层未过：" + ", ".join(f"{r['id']}({r['status']})" for r in b_open))
    # 0 = 全部通过; 1 = 本地代码有硬伤; 2 = 代码自洽但还不能提交
    return 1 if a_fail else (2 if d_open or b_open else 0)


if __name__ == "__main__":
    sys.exit(main())
