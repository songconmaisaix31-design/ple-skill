"""Verify the frozen archived-program recovery diagnostic offline, without inference."""
import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tokenize
import zipfile

from design_regression import Site, Period, VARIANTS, prepare, grade


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strip_comments(source):
    lines = source.splitlines()
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type == tokenize.COMMENT:
            line, col = token.start
            lines[line - 1] = lines[line - 1][:col].rstrip()
    clean = "\n".join(lines)
    assert ast.dump(ast.parse(source)) == ast.dump(ast.parse(clean))
    return clean


def archived_source(evidence, spec):
    if digest(evidence.read_bytes()) != spec["archive_sha256"]:
        raise ValueError("unexpected source archive")
    with zipfile.ZipFile(evidence) as zf:
        events = [json.loads(row) for row in zf.read(spec["member"]).splitlines()]
    replies = [e for e in events if e["event"] == "response" and e["call"] == spec["call"]]
    if len(replies) != 1:
        raise ValueError("expected one completed reply")
    text = replies[0]["choices"][0]["message"]["content"].strip()
    source = re.fullmatch(r"```python\n(.*?)\n```", text, re.S).group(1)
    if digest(source.encode()) != spec["source_sha256"]:
        raise ValueError("unexpected source program")
    return source


def run_program(workspace, source):
    # Match the task-side run_python compilation filename, source framing and code path.
    # Only this allowlisted, reviewed and checksum-pinned public fixture is run.
    code = base64.b64encode(source.encode()).decode()
    wrapper = f"import base64; exec(compile(base64.b64decode('{code}'), '<run_python>', 'exec'))"
    return subprocess.run([sys.executable, "-I", "-S", "-c", wrapper], cwd=workspace,
                          env={"PYTHONIOENCODING": "utf-8", "PATH": os.defpath},
                          timeout=10, capture_output=True, text=True)


def lowest_by_state(workspace):
    settings = json.loads((workspace / "input/site.json").read_bytes())
    states = {settings["initial_storage_units"]: 0}
    with (workspace / "input/periods.csv").open() as f:
        for row in csv.DictReader(f):
            costs = {}
            for start, subtotal in states.items():
                for pumped in settings["allowed_pump_units"]:
                    end = start + pumped - int(row["demand_units"])
                    if (pumped <= int(row["max_pump_units"]) and
                            settings["min_storage_units"] <= end <= settings["max_storage_units"]):
                        value = subtotal + pumped * int(row["tariff_cents_per_unit"])
                        costs[end] = min(costs.get(end, value), value)
            states = costs
    return min(cost for state, cost in states.items()
               if settings["min_final_storage_units"] <= state <= settings["max_final_storage_units"])


def check(protocol, prior):
    spec = protocol["source"]
    raw = archived_source(prior, spec)
    program = strip_comments(raw)
    assert digest(program.encode()) == spec["controlled_source_sha256"]
    old = "sum(c[0] for c in combination)"
    assert program.count(old) == 1
    # Host-only positive control. Neither replacement nor reference values enter a task.
    known_fix = program.replace(old, "sum(combination)")
    with tempfile.TemporaryDirectory() as tmp:
        for name, item in protocol["cases"].items():
            case = Site(*item["site"][:-1], tuple(item["site"][-1])), tuple(Period(*v) for v in item["periods"])
            if name in VARIANTS and VARIANTS[name] != case:
                raise ValueError("conflicting fixture definition")
            VARIANTS[name] = case
            for version, code in (("archived", raw), ("common-first-program", program), ("offline-positive", known_fix)):
                work = Path(tmp) / f"{name}-{version}"
                prepare(work, name)
                observed = {k: digest((work / k).read_bytes()) for k in item["input_sha256"]}
                assert observed == item["input_sha256"]
                run = run_program(work, code)
                scored = grade(work, name)
                if version != "offline-positive":
                    frames = re.findall(r'^  File "<run_python>", line (\d+)', run.stderr, re.M)
                    assert run.returncode == 1 and frames[-1] == "81"
                    assert run.stderr.splitlines()[-1] == "TypeError: 'int' object is not subscriptable"
                    assert not (work / "output").exists() and not scored["feasible"] and scored["score"] == 0
                else:
                    assert run.returncode == 0 and scored["optimal"] and scored["score"] == 1
                    assert scored["submitted_cost_cents"] == lowest_by_state(work)
                print(json.dumps({"case": name, "source": version, "exit": run.returncode,
                                  "score": scored["score"], "cost_cents": scored["submitted_cost_cents"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--prior-evidence", required=True, type=Path)
    args = parser.parse_args()
    check(json.loads(args.protocol.read_bytes()), args.prior_evidence)

