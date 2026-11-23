#!/usr/bin/env python3
"""Auto-generate a deliverable spec from a PLE task instruction (+ task.md)."""
import csv, os, posixpath, re, json

EXT_OK = (".zip", ".docx", ".xlsx", ".ifc", ".pdf", ".csv", ".md", ".py", ".dxf",
          ".txt", ".eml", ".json")
# files that are inputs, never deliverables
INPUT_HINT = ("task.md", "README", "input/", "inputs/", "project/", "criteria/", "owner/", "specs/", "drawings/",
              "schedules/", "site/", "vendor/", "procurement/")
INPUT_DOCUMENTS = {"task.md", "readme", "readme.md", "readme.txt"}

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
FILE_LIST = re.compile(
    rf"\b(?:(?:required\s+(?:output\s+)?(?:files|deliverables)|output\s+files)|"
    rf"(?:{OUTPUT_ACTION}[^:\n]{{0,120}}\b(?:files|deliverables)\b[^:\n]{{0,100}}))"
    r"[ \t]*:[ \t]*(?:\*\*)?([^\n]*)", re.I | re.M)
OPTIONAL = re.compile(r"\b(?:optional(?:ly)?|for example|if (?:needed|desired|applicable)|"
                      r"may|can|do not|don't)\b", re.I)
OPTIONAL_SUFFIX = re.compile(r"\s*(?:\(optional\)|if (?:needed|desired|applicable)|(?:or|and/or)\s+)", re.I)
HEADER_DECLARATION = re.compile(
    r"\b(?:column headers?|headers?(?:\s+row)?|columns?)\b\s*"
    r"(?:,?\s*(?:must\s+be|are|exactly(?:\s+(?:these|the following)\s+names?)?|"
    r"in\s+(?:this\s+)?(?:exact\s+)?order)\s*){0,3}:?\s*",
    re.I)
FLEXIBLE_HEADER = re.compile(r"\b(?:in any order|(?:additional|extra)\s+[\w -]*\bcolumns?\b"
                             r"[^.!?\n]{0,50}\b(?:allowed|permitted))\b", re.I)


def _clean_path(raw):
    path = raw.strip('`"').strip()
    if not path or ".." in path.split("/") or "\\" in path or "\x00" in path:
        return ""
    return path


def _is_input(path):
    parts = path.strip('`"').lower().split("/")
    for folder in parts[:-1]:
        if folder in {"output", "outputs", "deliverables", "submission"}:
            return False
        if (folder + "/") in INPUT_HINT:
            return True
    basename = parts[-1]
    return basename in INPUT_DOCUMENTS


def _explicit_directory(text):
    for match in EXPLICIT_DIR.finditer(text):
        if _clean_path(match[1]) and not _is_input(match[1]):
            return match[1]
    for match in re.finditer(rf'\b(?:under|in|into|to)\s+{DIRECTORY_PATH}', text, re.I):
        if "output" in match[1].lower() and _clean_path(match[1]) and not _is_input(match[1]):
            return match[1]
    match = re.search(r"`(output[A-Za-z0-9_./-]*)`", text, re.I)
    if match and (match[1].endswith("/") or match[1].lower() == "output"):
        return match[1].rstrip("/") + "/"
    return ""


def _explicit_files(text, pattern):
    for match in pattern.finditer(text):
        prefix = re.split(r"[.!?;\n]", text[max(0, match.start() - 100):match.start()])[-1]
        if OPTIONAL.search(prefix):
            continue
        while match:
            path = _clean_path(match[1])
            if path and not _is_input(path) and not OPTIONAL_SUFFIX.match(text[match.end():]):
                yield path
            match = FILE_LIST_TAIL.match(text, match.end())


def _listed_files(text):
    for match in FILE_LIST.finditer(text):
        if OPTIONAL.search(match[0].split(":", 1)[0]):
            continue
        lines = [match[1]]
        following = text[match.end():].lstrip("\n").splitlines()
        for line in following:
            bullet = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
            continuation = re.match(rf"^\s*(?:and\s+|,\s*)({FILE_PATH}.*)$", line, re.I)
            if not bullet and not continuation:
                break
            lines.append((bullet or continuation)[1])
        for index, line in enumerate(lines):
            for named in NAMED_PATH.finditer(line):
                path = _clean_path(named[0])
                if path and not _is_input(path) and not OPTIONAL.search(line[:named.start()]):
                    if not OPTIONAL_SUFFIX.match(line[named.end():]):
                        yield path
                if index:
                    break   # the bullet can also mention source or reference files


def _under_directory(path, directory):
    path = posixpath.normpath(path)
    if not directory or path.startswith("/"):
        return path
    directory = posixpath.normpath(directory)
    if path.startswith(directory.rstrip("/") + "/"):
        return path
    if directory.startswith("/") and path.startswith(posixpath.basename(directory) + "/"):
        return posixpath.join(posixpath.dirname(directory), path)
    return posixpath.join(directory, path)


def _declared_outputs(text, directory):
    paths = (*_explicit_files(text, EXPLICIT_FILE), *_explicit_files(text, PASSIVE_FILE),
             *_listed_files(text))
    return list(dict.fromkeys(_under_directory(path, directory) for path in paths))


def extract_root(text):
    """Find the deliverable root or file path the prompt points at."""
    directory = _explicit_directory(text)
    explicit = _declared_outputs(text, directory)
    if explicit:
        return directory if directory and len(explicit) > 1 else explicit[0]
    if directory:
        return directory

    cands = re.finditer(r"`([^`\n]{3,200})`", text)
    deliver = []
    for match in cands:
        prefix = re.split(r"(?<=[.!?;])\s+|\n", text[max(0, match.start() - 100):match.start()])[-1]
        if OPTIONAL.search(prefix) or OPTIONAL_SUFFIX.match(text[match.end():]):
            continue
        c = _clean_path(match[1])
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
        p = _clean_path(m.group(1))
        prefix = re.split(r"(?<=[.!?;])\s+|\n", text[max(0, m.start() - 100):m.start()])[-1]
        if (p.lower().endswith(EXT_OK) and not _is_input(p) and not OPTIONAL.search(prefix)
                and not OPTIONAL_SUFFIX.match(text[m.end():])):
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


def _exact_header(body):
    match = HEADER_DECLARATION.search(body)
    if not match:
        return []
    raw = body[match.end():].lstrip()
    fence = re.match(r"```[^\n]*\n(.*?)\n```", raw, re.S)
    inline = re.match(r"`([^`\n]+)`(?!\s*,)", raw)
    if fence or inline:
        raw = (fence or inline)[1]
    else:
        raw = re.split(r"\s+in (?:this |any )?(?:exact )?order\b|(?<=\.)\s+",
                       raw.split("\n", 1)[0], flags=re.I)[0]
        raw = raw.rstrip(".;, ")
    try:
        values = next(csv.reader([raw], skipinitialspace=True, strict=True))
    except (csv.Error, StopIteration):
        return []
    columns = [value.strip().strip("`") for value in values]
    if fence or inline:
        return columns if columns and all(column.strip() for column in columns) else []
    return columns if len(columns) > 1 and all(re.fullmatch(r"[A-Za-z_][\w.-]*", column) for column in columns) else []


def _required_headers(text, required, directory, blocks):
    csv_paths = {path for path in required if path.lower().endswith(".csv")}
    if not csv_paths:
        return {}
    headers = {}
    for path, body in blocks.items():
        path = _under_directory(path, directory)
        if path in csv_paths and (columns := _exact_header(body)):
            headers[path] = (columns, not FLEXIBLE_HEADER.search(body))
    for match in HEADER_DECLARATION.finditer(text):
        context = re.split(r"(?<=[.?!;)])\s+", text[max(0, match.start() - 160):match.start()])[-1]
        if OPTIONAL.search(context):
            continue
        tail = text[match.start():match.end() + 240]
        names = [_clean_path(item[0]) for item in NAMED_PATH.finditer(context)]
        names = [name for name in names if name.lower().endswith(".csv")]
        named_paths = {_under_directory(name, directory) for name in names}
        referred = re.search(r"\b([\w.-]+)\s+CSV\b", context, re.I)
        if referred and not named_paths:
            named_paths = {path for path in csv_paths if posixpath.basename(path)[:-4].lower() == referred[1].lower()}
        if not named_paths and not re.search(r"\b(?:input|source|reference)\b", context, re.I):
            named_paths = csv_paths
        if len(named_paths) == 1 and (path := next(iter(named_paths))) in csv_paths:
            if columns := _exact_header(tail):
                headers.setdefault(path, (columns, not FLEXIBLE_HEADER.search(tail)))
    return headers


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
    directory = _explicit_directory(instruction) or _explicit_directory(text)
    required_files = _declared_outputs(text, directory)
    # Content filenames listed alongside one named archive still describe archive members.
    primary_outputs = _declared_outputs(instruction, directory) or required_files
    if root.lower().endswith(".zip") and len(primary_outputs) <= 1:
        required_files = []
    if required_files:
        root = required_files[0]
    if len(required_files) > 1 and directory:
        prefix = posixpath.normpath(directory).rstrip("/") + "/"
        if all(path.startswith(prefix) for path in required_files):
            root = directory

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
    if len(required_files) > 1 and mode != "dir":
        mode = "files"

    # a zip task usually still names the inner files; keep them as required members
    required, soft, zip_csv_rules = [], [], {}
    zip_exact_paths = False
    if mode == "zip":
        HARD_EXT = (".md", ".csv")
        zip_exact_paths = bool(re.search(r"\bexact\s+(?:member\s+)?paths?\b", text, re.I))
        explicit_members = bool(blocks and zip_exact_paths and re.search(
            r"\b(?:required\s+members|members?\s+(?:are\s+required|must\b))", text, re.I))
        for n in names:
            low = n.lower()
            base = os.path.basename(low)
            # inputs and house templates are filled in, never delivered back
            if base in ("task.md", "readme.md", "criteria.md") or "template" in low:
                continue
            if explicit_members and _clean_path(n) and not _is_input(n):
                required.append(n)
                if low.endswith(".csv") and (columns := _exact_header(blocks[n])):
                    zip_csv_rules[n] = {"columns": columns, "exact": not FLEXIBLE_HEADER.search(blocks[n])}
            elif low.endswith(HARD_EXT):
                required.append(n)
            elif low.endswith((".xlsx", ".dxf", ".json", ".docx")):
                soft.append(n)
        required, soft = required[:10], soft[:10]
        for n in soft:
            if not n.lower().endswith(".csv"):
                headers.pop(n, None)

    output_headers = _required_headers(text, required_files, directory, blocks)
    spec = {
        "deliverable": root,
        "mode": mode,
        "required_files": required_files,
        "required_csv_headers": {path: columns for path, (columns, exact) in output_headers.items() if exact},
        "required_csv_columns": {path: columns for path, (columns, exact) in output_headers.items() if not exact},
        "zip_required": required,
        "zip_soft": soft,
        "zip_exact_paths": zip_exact_paths,
        "zip_csv_rules": zip_csv_rules,
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
