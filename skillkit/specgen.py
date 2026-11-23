#!/usr/bin/env python3
"""Auto-generate a deliverable spec from a PLE task instruction (+ task.md)."""
import os, posixpath, re, json

EXT_OK = (".zip", ".docx", ".xlsx", ".ifc", ".pdf", ".csv", ".md", ".py", ".dxf",
          ".txt", ".eml", ".json")
# files that are inputs, never deliverables
INPUT_HINT = ("task.md", "README", "input/", "inputs/", "project/", "criteria/", "owner/", "specs/", "drawings/",
              "schedules/", "site/", "vendor/", "procurement/")

FILE_EXT = "(?:" + "|".join(re.escape(ext) for ext in EXT_OK) + ")"
PATH_END = r"(?=$|[\s`\"',;:!?)\]]|\.(?=\s|$))"
FILE_PATH = rf"(?:`[^`\n]+{FILE_EXT}`|\"[^\"\n]+{FILE_EXT}\"|[A-Za-z0-9_./-]+{FILE_EXT}{PATH_END})"
OUTPUT_ACTION = (r"\b(?:save|write|deliver|store|put|place|publish|create|submit|export)\b")
PASSIVE_ACTION = r"\b(?:saved|written|delivered|stored|placed|published|created|submitted|exported)\b"
DESTINATION = r"(?:\s+(?:[\w-]+\s+){0,8}?(?:as|to|at|in(?:to)?|under|named|called))?\s+"
EXPLICIT_FILE = re.compile(rf"{OUTPUT_ACTION}{DESTINATION}({FILE_PATH})", re.I)
PASSIVE_FILE = re.compile(rf"{PASSIVE_ACTION}{DESTINATION}({FILE_PATH})", re.I)
DIRECTORY_PATH = rf'[`"]?([A-Za-z0-9_./-]+/){PATH_END}'
EXPLICIT_DIR = re.compile(
    rf'{OUTPUT_ACTION}{DESTINATION}(?:{FILE_PATH}\s+(?:under|in|into|to)\s+)?{DIRECTORY_PATH}',
    re.I)
FILE_LIST_TAIL = re.compile(rf"(?:\s*[,]\s*(?:and\s+)?|\s+and\s+)({FILE_PATH})", re.I)
NAMED_PATH = re.compile(rf"(?<![A-Za-z0-9_./-]){FILE_PATH}", re.I)


def _is_input(path):
    low = path.lower()
    return any(hint.lower() in low for hint in INPUT_HINT)


def _explicit_directory(text):
    for match in EXPLICIT_DIR.finditer(text):
        if not _is_input(match[1]):
            return match[1]
    for match in re.finditer(rf'\b(?:under|in|into|to)\s+{DIRECTORY_PATH}', text, re.I):
        if "output" in match[1].lower() and not _is_input(match[1]):
            return match[1]
    match = re.search(r"`(output[A-Za-z0-9_./-]*)`", text, re.I)
    if match and (match[1].endswith("/") or match[1].lower() == "output"):
        return match[1].rstrip("/") + "/"
    return ""


def _explicit_files(text, pattern):
    for match in pattern.finditer(text):
        while match:
            if not _is_input(match[1]):
                yield match[1].strip('`"').strip()
            match = FILE_LIST_TAIL.match(text, match.end())


def extract_root(text):
    """Find the deliverable root or file path the prompt points at."""
    directory = _explicit_directory(text)
    explicit = list(_explicit_files(text, EXPLICIT_FILE)) or list(_explicit_files(text, PASSIVE_FILE))
    if explicit:
        if directory:
            prefix = posixpath.normpath(directory).rstrip("/") + "/"
            named_outputs = set()
            for path in explicit:
                normalized = posixpath.normpath(path)
                named_outputs.add(normalized if "/" in normalized else prefix + normalized)
            for match in NAMED_PATH.finditer(text):
                path = posixpath.normpath(match[0].strip('`"').strip())
                if path.startswith(prefix) and not _is_input(path):
                    named_outputs.add(path)
            if len(named_outputs) > 1 or (count_claim(text) or 0) > 1:
                return directory
            if "/" not in explicit[0]:
                return posixpath.join(directory, explicit[0])
        return explicit[0]
    if directory:
        return directory

    cands = re.findall(r"`([^`\n]{3,200})`", text)
    deliver = []
    for c in cands:
        low = c.lower()
        if not low.endswith(EXT_OK):
            continue
        if _is_input(c):
            continue
        if "output" in low or "submission" in low or low.startswith("/"):
            deliver.append(c)
    # prefer the path mentioned right after write/save/deliver
    m = re.search(r"(?:write|save|deliver|put|place)[^`\n]{0,60}`([^`\n]+)`", text, re.I)
    if m:
        p = m.group(1)
        if p.lower().endswith(EXT_OK) and not _is_input(p):
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
        named_files = {os.path.basename(p) for p in re.findall(r"`([^`\n]{3,120})`", text)
                       if p.lower().endswith(EXT_OK) and not _is_input(p)}
        if root.lower().endswith(EXT_OK):
            named_files.add(os.path.basename(root))
        names = sorted(named_files)

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
    extension = posixpath.splitext(low)[1]
    if extension in (".zip", ".docx", ".xlsx", ".ifc", ".py", ".json", ".txt", ".csv"):
        mode = extension[1:]
    elif low.endswith("/"):
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
