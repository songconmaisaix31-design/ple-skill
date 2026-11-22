#!/usr/bin/env python3
"""Deliverable guard for PLE harnesses.

Checks only [hard] constraints: the file exists, opens, and the structural
pieces the graders look for are present. Never judges engineering content.

Usage:
  python validate.py --base <task_workdir> --spec spec.json
  python validate.py --base <dir> --deliverable output/submission.zip   # auto mode

Exit 0 = pass, 1 = hard fail, 2 = warn only.
"""
import argparse, json, os, sys, zipfile, csv, io
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

FAIL, WARN = [], []


def ok(msg): print("  PASS  " + msg)


def fail(msg): FAIL.append(msg); print("  FAIL  " + msg)


def warn(msg): WARN.append(msg); print("  WARN  " + msg)


def check_docx(path, label):
    try:
        z = zipfile.ZipFile(path)
        root = ET.fromstring(z.read("word/document.xml"))
    except Exception as e:
        return fail(f"{label}: docx 打不开 ({e})")
    paras = [p for p in root.iter() if p.tag.split("}")[-1] == "p"]
    if len(paras) < 5:
        fail(f"{label}: docx 只有 {len(paras)} 个段落，疑似空文档")
    else:
        ok(f"{label}: docx {len(paras)} 段可解析")


def check_xlsx(path, label):
    try:
        z = zipfile.ZipFile(path)
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = [s.get("name") for s in wb.iter() if s.tag.split("}")[-1] == "sheet"]
    except Exception as e:
        return fail(f"{label}: xlsx 打不开 ({e})")
    if not sheets:
        fail(f"{label}: xlsx 无 sheet")
    else:
        ok(f"{label}: xlsx {len(sheets)} sheets")


def csv_header(raw):
    try:
        txt = raw.decode("utf-8", "ignore")
        row = next(csv.reader(io.StringIO(txt)))
        return [c.strip() for c in row if c.strip()]
    except Exception:
        return []


def check_zip(path, label, spec):
    try:
        z = zipfile.ZipFile(path)
        names = z.namelist()
    except Exception as e:
        return fail(f"{label}: zip 打不开 ({e})")
    if not names:
        return fail(f"{label}: zip 是空的")
    ok(f"{label}: zip {len(names)} 项")
    for req in spec.get("zip_required", []):
        hits = [n for n in names if n.endswith(req)]
        if not hits:
            fail(f"{label}: 缺必需文件 {req}")
        else:
            ok(f"{label}: 含 {req}")
    for req in spec.get("zip_soft", []):
        hits = [n for n in names if n.endswith(req)]
        if not hits:
            warn(f"{label}: 未见 {req}（二级件，题面若未硬性要求可忽略）")
        else:
            ok(f"{label}: 含 {req}")
    for name, cols in (spec.get("csv_headers") or {}).items():
        hit = [n for n in names if n.endswith(name)]
        if not hit:
            fail(f"{label}: 缺 CSV {name}")
            continue
        hdr = csv_header(z.read(hit[0]))
        missing = [c for c in cols if c not in hdr]
        if missing:
            fail(f"{label}: {name} 缺列 {missing}")
        else:
            ok(f"{label}: {name} 列头齐全 ({len(hdr)} 列)")
    for name in names:
        low = name.lower()
        if spec.get("deep", True) and low.endswith((".docx", ".xlsx")) and not low.startswith("__macosx"):
            try:
                tmp = "/tmp/_v_" + os.path.basename(name)
                open(tmp, "wb").write(z.read(name))
                (check_docx if low.endswith(".docx") else check_xlsx)(tmp, f"{label}!{name}")
                os.remove(tmp)
            except Exception as e:
                warn(f"{label}!{name}: 嵌套检查跳过 ({e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="task working directory")
    ap.add_argument("--spec")
    ap.add_argument("--deliverable", help="auto mode: just check this path")
    a = ap.parse_args()

    spec = json.load(open(a.spec)) if a.spec else {}
    deliv = spec.get("deliverable") or a.deliverable
    if not deliv:
        print("FAIL: 没有指定交付物"); return 1

    path = deliv if os.path.isabs(deliv) else os.path.join(a.base, deliv)
    print(f"[deliverable] {path}")
    if not os.path.exists(path):
        fail(f"交付物不存在：{deliv}")
        print(f"\nRESULT: FAIL ({len(FAIL)} hard)")
        return 1
    size = os.path.getsize(path)
    if size == 0:
        fail("交付物是 0 字节")
    else:
        ok(f"大小 {size} bytes")

    low = deliv.lower()
    if low.endswith("/") or os.path.isdir(path):
        files = sorted(f for f in os.listdir(path) if not f.startswith("."))
        if not files:
            fail("交付目录是空的")
        else:
            ok(f"目录 {len(files)} 项：{', '.join(files[:8])}")
            for f in files[:20]:
                p2 = os.path.join(path, f)
                if f.lower().endswith(".docx") and os.path.isfile(p2):
                    check_docx(p2, f"dir/{f}")
                elif f.lower().endswith(".xlsx") and os.path.isfile(p2):
                    check_xlsx(p2, f"dir/{f}")
        print(f"\nRESULT: {'FAIL' if FAIL else ('WARN' if WARN else 'PASS')} "
              f"({len(FAIL)} hard / {len(WARN)} soft)")
        return 1 if FAIL else (2 if WARN else 0)
    if low.endswith(".zip"):
        check_zip(path, "zip", spec)
    elif low.endswith(".docx"):
        check_docx(path, "docx")
    elif low.endswith(".xlsx"):
        check_xlsx(path, "xlsx")
    else:
        ok("非容器格式，只做存在性检查")

    print(f"\nRESULT: {'FAIL' if FAIL else ('WARN' if WARN else 'PASS')} ({len(FAIL)} hard / {len(WARN)} soft)")
    return 1 if FAIL else (2 if WARN else 0)


if __name__ == "__main__":
    sys.exit(main())
