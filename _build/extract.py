#!/usr/bin/env python3
"""Deconstruct the 29 PLE dev-set artifacts into a per-domain deliverable skeleton."""
import json, os, re, zipfile, collections
from xml.etree import ElementTree as ET

ROOT = "/home/user/work/ple-template/artifacts"
NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def docx_outline(path, max_items=60):
    """Return (headings, table_shapes) from a .docx"""
    try:
        z = zipfile.ZipFile(path)
        xml = z.read("word/document.xml")
    except Exception as e:
        return [f"<unreadable: {e}>"], []
    try:
        root = ET.fromstring(xml)
    except Exception as e:
        return [f"<bad xml: {e}>"], []
    heads, tables = [], []
    for body in root.iter(NS_W + "body"):
        for child in body:
            tag = child.tag.replace(NS_W, "")
            if tag == "p":
                txt = "".join(t.text or "" for t in child.iter(NS_W + "t")).strip()
                style = ""
                ppr = child.find(NS_W + "pPr")
                if ppr is not None:
                    ps = ppr.find(NS_W + "pStyle")
                    if ps is not None:
                        style = ps.get(NS_W + "val", "")
                if txt and (style.lower().startswith("heading") or style.lower() in ("title", "subtitle")):
                    if len(heads) < max_items:
                        heads.append(f"[{style}] {txt[:90]}")
            elif tag == "tbl":
                cols = 0
                for row in child.findall(NS_W + "tr")[:1]:
                    cols = len(row.findall(NS_W + "tc"))
                tables.append(cols)
    return heads, tables

def xlsx_outline(path):
    try:
        z = zipfile.ZipFile(path)
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = [s.get("name") for s in wb.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")]
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                shared.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
        return sheets, shared[:40]
    except Exception as e:
        return [f"<unreadable: {e}>"], []

def zip_tree(path, depth=0, max_depth=2, prefix=""):
    out = []
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return [f"<unreadable: {e}>"]
    entries = z.namelist()
    for n in sorted(entries)[:80]:
        parts = n.split("/")
        out.append(prefix + n)
        if n.lower().endswith(".zip") and depth < max_depth and len(n) < 200:
            try:
                inner = z.read(n)
                tmp = f"/tmp/_nest_{depth}.zip"
                open(tmp, "wb").write(inner)
                out += zip_tree(tmp, depth + 1, max_depth, prefix + "    ↳ ")
                os.remove(tmp)
            except Exception:
                pass
    return out

def first_instruction(task):
    p = os.path.join(ROOT, task, "trajectory.json")
    if not os.path.exists(p):
        return "", ""
    t = json.load(open(p))
    for s in t.get("steps", []):
        if s.get("source") == "user":
            msg = s.get("message") or ""
            m = re.search(r"write your deliverable to `([^`]+)`", msg, re.I)
            path = m.group(1) if m else ""
            hm = re.search(r"^#+\s*(.+)$", msg, re.M)
            head = hm.group(1).strip()[:100] if hm else ""
            return path, head
    return "", ""

def walk_files(task):
    base = os.path.join(ROOT, task, "files")
    res = []
    for dp, _, fns in os.walk(base):
        for fn in fns:
            res.append(os.path.relpath(os.path.join(dp, fn), base))
    return res

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
 "data-center-site-model":"bim",
 "data-hall-mep-routing":"mep","data-hall-mep-routing-offset":"mep",
 "cooling-water-flush-plan":"mep","heat-rejection-life-cycle-cost":"mep",
 "fire-solve-convergence":"fire","fire-test-validation-memo":"fire",
 "engineers-estimate-check":"cost","les-mesh-resolution":"cfd",
 "permission-to-operate-memo":"permit",
}

rows = []
for task in sorted(os.listdir(ROOT)):
    if task.startswith(".") or not os.path.isdir(os.path.join(ROOT, task)):
        continue
    deliver, title = first_instruction(task)
    files = walk_files(task)
    detail = {}
    for f in files:
        ap = os.path.join(ROOT, task, "files", f)
        low = f.lower()
        if low.endswith(".docx"):
            h, tb = docx_outline(ap)
            detail.setdefault("docx", []).append({"file": f, "heads": h, "tables": tb})
        elif low.endswith(".xlsx"):
            s, sh = xlsx_outline(ap)
            detail.setdefault("xlsx", []).append({"file": f, "sheets": s, "strings": sh})
        elif low.endswith(".zip"):
            detail.setdefault("zip", []).append({"file": f, "tree": zip_tree(ap)})
    fm = ""
    fmp = os.path.join(ROOT, task, "final_message.md")
    if os.path.exists(fmp):
        lines = [l.strip() for l in open(fmp, encoding="utf-8", errors="ignore").read().splitlines() if l.strip()]
        fm = " / ".join(lines[1:6])[:300]
    rows.append({"task": task, "domain": DOMAIN.get(task, "other"), "deliverable": deliver,
                 "title": title, "files": files, "detail": detail, "final": fm})

json.dump(rows, open("/home/user/work/ple-skill/skeleton.json", "w"), ensure_ascii=False, indent=1)
print("tasks parsed:", len(rows))
print("domains:", collections.Counter(r["domain"] for r in rows))
