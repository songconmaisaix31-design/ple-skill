#!/usr/bin/env python3
import json, collections

rows = json.load(open("/home/user/work/ple-skill/skeleton2.json"))
by_dom = collections.defaultdict(list)
for r in rows: by_dom[r["domain"]].append(r)

ORDER = ["electrical", "structural", "mep", "civil", "fire", "cost", "bim", "cfd", "permit"]
out = ["# PLE dev-set 交付物骨架（29 题反推）\n",
       "来源：`physical-engineerings-last-exam/submission-template` 的 `artifacts/`，即 Pi 1.1.0 + Claude Opus 5.5 在 29 个 dev 任务上的真实产出。",
       "用途：每个 domain 的 skill 施工图。只取**格式惯例**，不取题目答案。\n"]

for dom in ORDER:
    rs = by_dom.get(dom, [])
    if not rs: continue
    out.append(f"\n## {dom}（{len(rs)} 题）\n")
    out.append("| 任务 | 交付形态 | 标题 |")
    out.append("|---|---|---|")
    for r in rs:
        out.append(f"| `{r['task']}` | {r['mode']} | {(r['title'] or '—')[:70]} |")
    out.append("\n### 交付规格明细\n")
    for r in rs:
        out.append(f"#### `{r['task']}`")
        if r["deliverable"]: out.append(f"- 交付路径：`{r['deliverable']}`")
        d = r["detail"]
        for z in d.get("zip", []):
            out.append(f"- zip 内部（{len(z.get('files',[]))} 项）：")
            for f in z.get("files", [])[:16]: out.append(f"  - `{f}`")
            for n, hdr in list(z.get("csv", {}).items())[:6]:
                out.append(f"  - **CSV 列头** `{n}`：{hdr}")
            for n, hs in list(z.get("md", {}).items())[:4]:
                if isinstance(hs, list) and hs and str(hs[0]).startswith("<json>"):
                    out.append(f"  - `{n}`：{str(hs[0])[:120]}")
                    continue
                out.append(f"  - **MD 章节** `{n}`：" + " / ".join(str(x)[:60] for x in hs[:9]))
            for n, sub in z.get("nested", {}).items():
                if isinstance(sub, dict) and "sheets" in sub:
                    out.append(f"  - 嵌套 xlsx `{n}` sheets={sub['sheets']} 首行串={sub['strings'][:10]}")
                elif isinstance(sub, dict) and "files" in sub:
                    out.append(f"  - 嵌套 zip `{n}`：{sub['files'][:10]}")
                elif isinstance(sub, dict):
                    out.append(f"  - 嵌套 `{n}`：tables={sub.get('tables')} heads={(sub.get('heads') or [])[:6]}")
        for x in d.get("xlsx", []):
            out.append(f"- xlsx `{x['file']}` sheets={x.get('sheets')} 串={x.get('strings',[])[:12]}")
        for wfile in d.get("docx", []):
            out.append(f"- docx `{wfile['file']}`")
            if wfile.get("heads"): out.append(f"  - 标题：{' / '.join(wfile['heads'][:10])}")
            if wfile.get("suspect_heads"): out.append(f"  - 疑似章节：{' / '.join(wfile['suspect_heads'][:12])}")
            if wfile.get("tables"): out.append(f"  - 表格列头：{wfile['tables'][:5]}")
        if r["final"]: out.append(f"- 收尾摘要写法：{r['final'][:180]}")
        out.append("")

open("/home/user/work/ple-skill/PLE_domain_skeleton.md", "w").write("\n".join(out))
print("lines:", len(out), "bytes:", len("\n".join(out)))
