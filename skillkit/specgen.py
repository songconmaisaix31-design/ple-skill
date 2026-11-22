#!/usr/bin/env python3
"""Auto-generate a deliverable spec from a PLE task instruction (+ task.md)."""
import os, re, json

EXT_OK = (".zip", ".docx", ".xlsx", ".ifc", ".pdf", ".csv", ".md", ".py", ".dxf", ".txt", ".eml")
# files that are inputs, never deliverables
INPUT_HINT = ("task.md", "README", "project/", "criteria/", "owner/", "specs/", "drawings/",
              "schedules/", "site/", "vendor/", "procurement/")


def extract_root(text):
    """Find the deliverable root or file path the prompt points at."""
    # 0) "Save the files that make up your answer under `output/`" -> a directory
    m = re.search(r"(?:under|in|into)\s+`([A-Za-z0-9_./-]+/)`", text)
    if m and "output" in m.group(1).lower():
        return m.group(1)
    m = re.search(r"`(output/?[A-Za-z0-9_./-]*)`", text)
    if m:
        g = m.group(1)
        if g.endswith("/") or g == "output":
            return g if g.endswith("/") else "output/"

    # 1) unquoted: "Save it as /filesystem/Foo_Bar.docx" / "Put it in a note saved as ..."
    m = re.search(
        r"(?:save|saved|write|written|deliver|delivered|store|stored|put|place|publish|published)"
        r"\s+(?:[A-Za-z]+\s+){0,4}(?:as|to|at|in)\s+"
        r"([/A-Za-z0-9_][A-Za-z0-9_./\-]{2,140}\.(?:zip|docx|xlsx|ifc|pdf|py|csv|md))",
        text, re.I)
    if m and ("/" in m.group(1) or "output" in m.group(1).lower()):
        return m.group(1).strip()

    cands = re.findall(r"`([^`\n]{3,200})`", text)
    deliver = []
    for c in cands:
        low = c.lower()
        if not low.endswith(EXT_OK):
            continue
        if any(h.lower() in low for h in INPUT_HINT):
            continue
        if "output" in low or "submission" in low or low.startswith("/"):
            deliver.append(c)
    # prefer the path mentioned right after write/save/deliver
    m = re.search(r"(?:write|save|deliver|put|place)[^`\n]{0,60}`([^`\n]+)`", text, re.I)
    if m:
        p = m.group(1)
        if p.lower().endswith(EXT_OK):
            return p.strip()
    return deliver[-1].strip() if deliver else ""


def parse_blocks(text):
    """`### N. `name`` blocks -> {name: section body}"""
    out = {}
    for m in re.finditer(r"###\s*\d+\.\s*`([^`\n]+)`\s*\n(.*?)(?=\n###\s*\d+\.\s*`|\n##\s|\Z)", text, re.S):
        out[m.group(1).strip()] = m.group(2)[:6000]
    return out


def parse_header(body):
    """Pull an explicit column list out of a section body."""
    pats = [
        r"columns?\s*,?\s*exactly\s+(?:these|the following)\s+names?\s*[:.]?\s*\n+```[^\n]*\n(.+?)\n```",
        r"columns?\s*[:.]?\s*\n+```[^\n]*\n(.+?)\n```",
        r"columns?\s+(?:are|must be)\s*[:.]?\s*(.+?)(?:\n\n|\Z)",
    ]
    for p in pats:
        m = re.search(p, body, re.S | re.I)
        if not m:
            continue
        raw = m.group(1)
        cols = [c.strip().strip("`") for c in re.split(r"[,\n]", raw)]
        cols = [c for c in cols if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c)]
        if len(cols) >= 2:
            return cols
    return []


def count_claim(text):
    m = re.search(r"(\d+|one|two|three|four|five|six|seven)\s+(?:files|deliverables)\b", text, re.I)
    if not m:
        return None
    w = m.group(1).lower()
    return {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}.get(w) or int(w)


def build(instruction, task_md=""):
    text = instruction + "\n\n" + (task_md or "")
    root = extract_root(instruction) or extract_root(text)
    blocks = parse_blocks(text)

    # explicit file list from ### blocks, else backticked filenames
    names = list(blocks.keys())
    if not names:
        names = sorted({os.path.basename(p) for p in re.findall(r"`([^`\n]{3,120})`", text)
                        if p.lower().endswith(EXT_OK)})

    headers = {n: parse_header(b) for n, b in blocks.items() if parse_header(b)}
    if not headers:
        for n in names:
            if not n.lower().endswith(".csv"):
                continue
            h = parse_header(text)
            if h:
                headers[n] = h

    mode = "?"
    low = root.lower()
    for ext, m in ((".zip", "zip"), (".docx", "docx"), (".xlsx", "xlsx"), (".ifc", "ifc"), (".py", "py")):
        if low.endswith(ext):
            mode = m
            break
    if mode == "?" and low.endswith("/"):
        mode = "dir"
    if mode == "?" and names:
        exts = {os.path.splitext(n)[1].lower() for n in names}
        if ".zip" in exts or len(names) > 1:
            mode = "zip"
        elif ".docx" in exts:
            mode = "docx"

    # a zip task usually still names the inner files; keep them as required members
    required, soft = [], []
    if mode == "zip":
        HARD_EXT = (".md", ".csv")
        for n in names:
            low = n.lower()
            base = os.path.basename(low)
            # inputs and house templates are filled in, never delivered back
            if base in ("task.md", "readme.md", "criteria.md") or "template" in low:
                continue
            if low.endswith(HARD_EXT):
                required.append(n)
            elif low.endswith((".xlsx", ".dxf", ".json", ".docx")):
                soft.append(n)
        required, soft = required[:10], soft[:10]
        for n in soft:
            if not n.lower().endswith(".csv"):
                headers.pop(n, None)

    spec = {
        "deliverable": root,
        "mode": mode,
        "zip_required": required,
        "zip_soft": soft,
        "csv_headers": {k: v for k, v in headers.items() if k.lower().endswith(".csv")},
        "all_named_files": names[:30],
        "claimed_count": count_claim(text),
        "confidence": "high" if (root and names) else ("mid" if root else "low"),
    }
    return spec


if __name__ == "__main__":
    import sys
    inst = sys.stdin.read()
    print(json.dumps(build(inst), indent=1, ensure_ascii=False))
