#!/usr/bin/env python3
"""Deliverable guard for PLE harnesses.

Checks only [hard] constraints: the file exists, opens, and the structural
pieces the graders look for are present. Never judges engineering content.

Usage:
  python validate.py --base <task_workdir> --spec spec.json
  python validate.py --base <dir> --deliverable output/submission.zip   # auto mode

Exit 0 = pass, 1 = hard fail, 2 = warn only.
"""
import argparse, json, os, posixpath, sys, zipfile, csv, io
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

FAIL, WARN = [], []


def ok(msg): print("  PASS  " + msg)


def fail(msg): FAIL.append(msg); print("  FAIL  " + msg)


def warn(msg): WARN.append(msg); print("  WARN  " + msg)


def check_docx(path, label):
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except Exception as e:
        return fail(f"{label}: docx 打不开 ({e})")
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if (tag == "t" and (node.text or "").strip()) or tag in {"drawing", "pict", "object", "sym"}:
            return ok(f"{label}: docx 正文可解析")
    fail(f"{label}: docx 文档正文为空")


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


def archive_hits(names, target, exact=False):
    target = posixpath.normpath(target)
    return [name for name in names
            if not name.endswith("/") and ".." not in name.split("/")
            and (name == target or (not exact and name.endswith("/" + target)))]


def check_zip(path, label, spec):
    try:
        z = zipfile.ZipFile(path)
        names = z.namelist()
    except Exception as e:
        return fail(f"{label}: zip 打不开 ({e})")
    if not names:
        return fail(f"{label}: zip 是空的")
    ok(f"{label}: zip {len(names)} 项")
    exact = spec.get("zip_exact_paths", False)
    for req in spec.get("zip_required", []):
        hits = archive_hits(names, req, exact)
        if not hits:
            fail(f"{label}: 缺必需文件 {req}")
        else:
            ok(f"{label}: 含 {req}")
            if exact and req.lower().endswith(".json"):
                try:
                    with io.TextIOWrapper(z.open(hits[0]), encoding="utf-8-sig") as source:
                        check_json_stream(source, f"{label}!{req}")
                except (OSError, ValueError, zipfile.BadZipFile) as exc:
                    fail(f"{label}!{req}: JSON 不可读 ({exc})")
    for req in spec.get("zip_soft", []):
        hits = archive_hits(names, req, exact)
        if not hits:
            warn(f"{label}: 未见 {req}（二级件，题面若未硬性要求可忽略）")
        else:
            ok(f"{label}: 含 {req}")
    exact_headers = spec.get("zip_csv_rules") or {}
    for name, rule in exact_headers.items():
        hits = archive_hits(names, name, exact)
        if hits:
            try:
                with io.TextIOWrapper(z.open(hits[0]), encoding="utf-8-sig", newline="") as source:
                    check_csv_stream(source, f"{label}!{name}", rule["columns"], rule["exact"])
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                fail(f"{label}!{name}: CSV 不可读 ({exc})")
    for name, cols in (spec.get("csv_headers") or {}).items():
        if name in exact_headers:
            continue
        hit = archive_hits(names, name, exact)
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
                payload = io.BytesIO(z.read(name))
                (check_docx if low.endswith(".docx") else check_xlsx)(payload, f"{label}!{name}")
            except Exception as e:
                warn(f"{label}!{name}: 嵌套检查跳过 ({e})")
    z.close()


def invalid_json_constant(token):
    raise ValueError(f"invalid JSON constant {token}")


def check_json(path, label):
    try:
        with open(path, encoding="utf-8-sig") as source:
            check_json_stream(source, label)
    except OSError as exc:
        fail(f"{label}: JSON 不可读 ({exc})")


def check_json_stream(source, label):
    try:
        json.load(source, parse_constant=invalid_json_constant)
    except (ValueError, OSError, RecursionError) as exc:
        fail(f"{label}: JSON 解析失败 ({exc})")
    else:
        ok(f"{label}: JSON 可解析")


def check_csv(path, label, columns, exact):
    try:
        with open(path, encoding="utf-8-sig", newline="") as source:
            check_csv_stream(source, label, columns, exact)
    except OSError as exc:
        fail(f"{label}: CSV 不可读 ({exc})")


def check_csv_stream(source, label, columns, exact):
    try:
        actual = next(csv.reader(source, strict=True))
    except (csv.Error, OSError, ValueError, StopIteration) as exc:
        fail(f"{label}: CSV 列头不可读 ({exc})")
        return
    if exact and actual != columns:
        fail(f"{label}: CSV 列头不符，要求 {columns}，实际 {actual}")
    elif (missing := [name for name in columns if name not in actual]):
        fail(f"{label}: CSV 缺列 {missing}")
    else:
        ok(f"{label}: CSV 列头匹配")


def declared_path(base, name):
    if not name or "\\" in name or "\x00" in name or ".." in name.split("/"):
        fail(f"交付路径无效：{name}")
        return None
    if os.path.isabs(name):
        return name
    path = os.path.join(base, name)
    if os.path.commonpath((os.path.realpath(base), os.path.realpath(path))) != os.path.realpath(base):
        fail(f"交付路径超出工作目录：{name}")
        return None
    return path


def check_file(path, label, spec, columns=None, exact=True):
    if not os.path.isfile(path):
        return fail(f"交付文件不存在：{label}")
    if os.path.getsize(path) == 0:
        return fail(f"交付文件是 0 字节：{label}")
    ext = posixpath.splitext(label)[1].lower()
    if ext == ".zip":
        check_zip(path, label, spec)
    elif ext == ".docx":
        check_docx(path, label)
    elif ext == ".xlsx":
        check_xlsx(path, label)
    elif ext == ".json":
        check_json(path, label)
    elif ext == ".csv" and columns:
        check_csv(path, label, columns, exact)
    else:
        ok(f"{label}: 文件存在")


def check_directory(path, label, inspect_children=True):
    if not os.path.isdir(path):
        return fail(f"交付目录不存在：{label}")
    files = sorted(f for f in os.listdir(path) if not f.startswith("."))
    if not files:
        return fail("交付目录是空的")
    ok(f"目录 {len(files)} 项：{', '.join(files[:8])}")
    if inspect_children:
        for name in files[:20]:
            file = os.path.join(path, name)
            if os.path.isfile(file) and name.lower().endswith((".docx", ".xlsx")):
                check_file(file, name, {})


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

    required = spec.get("required_files") or []
    headers = spec.get("required_csv_headers") or {}
    unordered = spec.get("required_csv_columns") or {}
    path = declared_path(a.base, deliv)
    if path is not None:
        print(f"[deliverable] {path}")
        is_directory = deliv.endswith("/") or (not required and os.path.isdir(path))
        if is_directory:
            check_directory(path, deliv, inspect_children=not required)
        for name in required or ([] if is_directory else [deliv]):
            file = declared_path(a.base, name)
            if file is None:
                continue
            if is_directory and os.path.commonpath((os.path.realpath(path), os.path.realpath(file))) != os.path.realpath(path):
                fail(f"交付文件超出声明的目录：{name}")
                continue
            check_file(file, name, spec, headers.get(name) or unordered.get(name), exact=name in headers)

    print(f"\nRESULT: {'FAIL' if FAIL else ('WARN' if WARN else 'PASS')} ({len(FAIL)} hard / {len(WARN)} soft)")
    return 1 if FAIL else (2 if WARN else 0)


if __name__ == "__main__":
    sys.exit(main())
