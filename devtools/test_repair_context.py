"""Check first-action repair feedback offline, optionally replaying archived D failures."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

sys.path.append(str(Path(__file__).resolve().parents[1]))
from skillkit import code_action


MARKER = "\n\nFirst program source near traceback line "
DIAGNOSTICS = "\n\nSandbox diagnostics, for debugging only:\n"
PROGRAM = "a = 3\nb = 4\nc = int(a)\nvalue = c[0]\nprint(value)\ntotal = 0\nprint(total)"


def traceback_for(line):
    return ('Traceback (most recent call last):\n  File "<string>", line 1, in <module>\n'
            f'  File "<run_python>", line {line}, in <module>\n'
            "TypeError: 'int' object is not subscriptable\n")


def boundaries():
    excerpt = code_action.repair_source_excerpt
    assert excerpt(PROGRAM, traceback_for(4)) == (
        MARKER + "4:\n2: b = 4\n3: c = int(a)\n4: value = c[0]\n5: print(value)\n6: total = 0")
    assert excerpt(PROGRAM, traceback_for(1)).splitlines()[-1] == "3: c = int(a)"
    assert "5: print(value)\n6: total = 0\n7: print(total)" in excerpt(PROGRAM, traceback_for(7))
    huge = "\n".join(["#" + "x" * 1200] * 5)
    sample = excerpt(huge, traceback_for(3))
    assert len(sample) <= 800 and sample.count("…") == 5 and "3: #" in sample
    for invalid in (traceback_for(0), traceback_for(8), '  File "<run_python>", line 2, in fn',
                    traceback_for(3).replace('"<run_python>"', '"library.py"'),
                    traceback_for(3).replace("TypeError:", '  File "library.py", line 15, in fn\nTypeError:'),
                    traceback_for(3).replace("TypeError:", '  File "library.py", line ?, in fn\nTypeError:'),
                    traceback_for(3) + "\n" + traceback_for(2).replace('"<run_python>"', '"other.py"')):
        assert excerpt(PROGRAM, invalid) == ""


async def observation(source, result, mode):
    """Capture the actual feedback path using fixed responses, without executing model source."""
    async def chat(*args, **kwargs):
        return {"content": source, "usage": {}, "finish_reason": "stop"}

    async def execute(call, on_execution):
        assert call["arguments"]["code"] == source
        on_execution(result)

    async def check():
        return "PASS", ""

    h = SimpleNamespace(model=SimpleNamespace(chat=chat), steps=0, _do=execute, _check_deliverable=check)
    with patch.dict(os.environ, {"PLE_REPAIR_CONTEXT": mode}):
        return await code_action.first_action(h, "text", [], None, lambda msg: None, None, time.monotonic)


async def routing():
    result = {"exit_code": 1, "ok": False, "output": traceback_for(4)}
    base = await observation(PROGRAM, result, "off")
    treated = await observation(PROGRAM, result, "source")
    assert MARKER not in base and treated == base + code_action.repair_source_excerpt(PROGRAM, result["output"])
    for updates in ({"ok": True, "exit_code": 0}, {"timed_out": True}, {"truncated": True},
                    {"exit_code": None}, {"output": "Import failed, without a traceback"}):
        outcome = {**result, **updates}
        assert await observation(PROGRAM, outcome, "off") == await observation(PROGRAM, outcome, "source")


async def archived_failures(path):
    with ZipFile(path) as archive:
        for repeat in (1, 2, 3):
            events = [json.loads(line) for line in archive.read(f"d/{repeat}/text/model-io.jsonl").splitlines()]
            raw = next(e for e in events if e["event"] == "response" and e["call"] == 1)
            source, state = code_action.program_from(raw["choices"][0]["message"], "text")
            assert state == "valid"
            followup = next(e for e in events if e["event"] == "request" and e["call"] == 2)
            old = followup["body"]["messages"][-1]["content"]
            result = {"ok": False, "exit_code": 1, "output": old.split(DIAGNOSTICS, 1)[1]}
            assert await observation(source, result, "off") == old
            new = await observation(source, result, "source")
            lines = source.splitlines()
            expected = MARKER + "81:\n" + "\n".join(f"{i}: {lines[i-1]}" for i in range(79, 84))
            assert new == old + expected and len(expected) <= 800


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, help="paired-storage-v1/evidence.zip")
    args = parser.parse_args()
    boundaries()
    asyncio.run(routing())
    if args.evidence is not None:
        asyncio.run(archived_failures(args.evidence))
        print("Three archived D repairs passed.")
    print("Repair feedback bounds, traceback provenance and treatment routing passed.")
