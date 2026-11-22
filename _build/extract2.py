#!/usr/bin/env python3
"""v2: also pull csv headers, md headings, docx table headers, and relax path extraction."""
import json, os, re, zipfile, collections
from xml.etree import ElementTree as ET

ROOT = "/home/user/work/ple-template/artifacts"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

def cell_text(c):
    return "".join(t.text or "" for t in c.iter(W + "t")).strip()

def docx_outline(path):
    try:
        z = zipfile.ZipFile(path); root = ET.fromstring(z.read("word/document.xml"))
    except Exception as e:
        return {"err": str(e)}
    heads, tbl_heads, paras = [], [], []
    for body in root.iter(W + "body"):
        for ch in body:
            tag = ch.tag.replace(W, "")
            if tag == "p":
                txt = "".join(t.text or "" for t in ch.iter(W + "t")).strip()
                ppr = ch.find(W + "pPr"); lvl = None; style = ""
                if ppr is not None:
                    ps = ppr.find(W + "pStyle")
                    if ps is not None: style = ps.get(W + "val", "")
                    ol = ppr.find(W + "outlineLvl")
                    if ol is not None: lvl = ol.get(W + "val")
                if not txt: continue
                if lvl is not None or style.lower().startswith("heading"):
                    heads.append(f"H{lvl or '?'}:{txt[:80]}")
                elif len(txt) <= 70 and not txt.endswith((".", "。", ",", ":")):
                    paras.append(txt[:70])
            elif tag == "tbl":
                rows = ch.findall(W + "tr")
                if rows:
                    hdr = [cell_text(c)[:40] for c in rows[0].findall(W + "tc")]
                    if hdr: tbl_heads.append(hdr[:10])
    return {"heads": heads[:30], "suspect_heads": paras[:18], "tables": tbl_heads[:6],
            "table_count": len(tbl_heads)}

def xlsx_outline(path):
    try:
        z = zipfile.ZipFile(path)
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = [x.get("name") for x in wb.iter(S + "sheet")]
        strs = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss.iter(S + "si"):
                strs.append("".join(t.text or "" for t in si.iter(S + "t"))[:50])
        return {"sheets": sheets[:12], "strings": strs[:40]}
    except Exception as e:
        return {"err": str(e)}

def zip_contents(path, depth=0):
    out = {"files": [], "csv": {}, "md": {}, "nested": {}}
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return {"err": str(e)}
    for n in sorted(z.namelist())[:120]:
        out["files"].append(n)
        low = n.lower()
        try:
            if low.endswith(".csv") and not low.startswith("__macosx"):
                head = z.read(n).decode("utf-8", "ignore").splitlines()[:1]
                out["csv"][n] = (head[0][:160] if head else "")
            elif low.endswith(".md"):
                txt = z.read(n).decode("utf-8", "ignore")
                hs = re.findall(r"^#{1,3}\s*(.+)$", txt, re.M)[:10]
                out["md"][n] = hs
            elif low.endswith(".json"):
                txt = z.read(n).decode("utf-8", "ignore")[:600]
                out["md"][n] = ["<json> " + txt.replace("\n", " ")]
            elif low.endswith(".zip") and depth < 2:
                tmp = f"/tmp/n{depth}.zip"; open(tmp, "wb").write(z.read(n))
                out["nested"][n] = zip_contents(tmp, depth + 1)
                os.remove(tmp)
            elif low.endswith((".xlsx", ".docx")) and depth < 1:
                tmp = f"/tmp/n{depth}{low[-5:]}"; open(tmp, "wb").write(z.read(n))
                out["nested"][n] = (xlsx_outline(tmp) if low.endswith(".xlsx") else docx_outline(tmp))
                os.remove(tmp)
        except Exception:
            pass
    return out

def instruction(task):
    p = os.path.join(ROOT, task, "trajectory.json")
    if not os.path.exists(p): return "", "", ""
    t = json.load(open(p))
    msg = ""
    for s in t.get("steps", []):
        if s.get("source") == "user":
            msg = s.get("message") or ""; break
    paths = re.findall(r"`([^`\n]{4,160})`", msg)
    cand = [p for p in paths if not p.endswith("task.md") and not p.startswith(("project/", "criteria/"))]
    outs = [p for p in cand if re.search(r"(output/|/submission|\.docx|\.xlsx|\.zip|\.ifc|\.pdf)", p, re.I)]
    outs = outs[-3:]
    hm = re.search(r"^#+\s*(.+)$", msg, re.M)
    title = hm.group(1).strip()[:110] if hm else ""
    mode = "zip" if re.search(r"submission\.zip", msg) else ("docx" if ".docx" in msg else ("file" if outs else "?"))
    return mode, (outs[0] if outs else ""), title

DOMAIN = {
 "backfeed-energization-reply":"electrical","division-26-specifications":"electrical",
 "lv-cable-sizing":"electrical","data-hall-device-takeoff":"electrical",
 "pre-application-capacity-response":"electrical","solar-supplemental-review":"electrical",
 "solar-witness-test-package":"electrical",
 "seismic-diaphragm-shear":"structural","wind-diaphragm-shear":"structural",
 "roof-deck-design":"structural","footing-settlement-verification":"structural",
 "shoring-design-verification":"structural","frame-extension-method":"structural",
 "eor-review-corrections":"structural","foundation-strategy":"structural",
 "fill-compaction-acceptance":"civil","emergency-spillway-check":"civil",
 "mv-conveyance-study":"civil","landscape-sheet-revision":"civil",
 "data-center-site-model":"bim","data-hall-mep-routing":"mep",
 "data-hall-mep-routing-offset":"mep","cooling-water-flush-plan":"mep",
 "heat-rejection-life-cycle-cost":"mep","fire-solve-convergence":"fire",
 "fire-test-validation-memo":"fire","engineers-estimate-check":"cost",
 "les-mesh-resolution":"cfd","permission-to-operate-memo":"permit",
}

rows = []
for task in sorted(os.listdir(ROOT)):
    if task.startswith(".") or not os.path.isdir(os.path.join(ROOT, task)): continue
    mode, deliver, title = instruction(task)
    detail = {}
    for dp, _, fns in os.walk(os.path.join(ROOT, task, "files")):
        for fn in fns:
            ap = os.path.join(dp, fn); rel = os.path.relpath(ap, os.path.join(ROOT, task, "files"))
            low = fn.lower()
            if low.endswith(".docx"): detail.setdefault("docx", []).append({"file": rel, **docx_outline(ap)})
            elif low.endswith(".xlsx"): detail.setdefault("xlsx", []).append({"file": rel, **xlsx_outline(ap)})
            elif low.endswith(".zip"): detail.setdefault("zip", []).append({"file": rel, **zip_contents(ap)})
            elif low.endswith((".md", ".csv", ".txt", ".eml")):
                detail.setdefault("text", []).append({"file": rel, "size": os.path.getsize(ap)})
    fmp = os.path.join(ROOT, task, "final_message.md")
    final = ""
    if os.path.exists(fmp):
        final = " / ".join([l.strip() for l in open(fmp, encoding="utf-8", errors="ignore").read().splitlines() if l.strip()][1:5])[:260]
    rows.append({"task": task, "domain": DOMAIN.get(task, "other"), "mode": mode,
                 "deliverable": deliver, "title": title, "detail": detail, "final": final})

json.dump(rows, open("/home/user/work/ple-skill/skeleton2.json", "w"), ensure_ascii=False, indent=1)
print("ok", len(rows), collections.Counter(r["domain"] for r in rows))
print("mode:", collections.Counter(r["mode"] for r in rows))
print("deliverable 抽到:", sum(1 for r in rows if r["deliverable"]), "/29")
