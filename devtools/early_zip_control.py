"""Exercise the early ZIP reminder with a scripted model and real task-side tools.

Run: python devtools/early_zip_control.py --kit /path/to/pinned/ple-kit
The JSON summary contains fixture results only. Use --save-captures DIR to keep
the correct and wrong-value ZIP copies produced by the kit.
"""
import argparse
import asyncio
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devtools.zip_delivery_control import KIT_COMMIT, LocalCaptureEnvironment, require
from skillkit.harness import Harness
from skillkit.transport import LocalTransport

FLAG = "PLE_EARLY_ZIP_WRITE"
INPUT = "inputs/weighings.csv"
TARGET = "output/shipment.zip"
MEMBER = "net-load.json"
ROWS = "gross_kg,tare_kg\n81,9\n94,18\n59,8\n"
TASK = f"""Read the weighings from `{INPUT}`. Subtract tare from gross for each row.
Save the package as `{TARGET}`.
### 1. `{MEMBER}`
Write JSON with the net mass sum in total_kg and the number of weighings in count."""
HINT = "The requested ZIP is still missing."
LOGS = {
    "missing": "early ZIP target missing; prompted for grounded members",
    "present": "early ZIP target present; skipped prompt",
    "unknown": "early ZIP target unknown; skipped prompt",
}
INSPECT = [
    ("read_file", {"path": INPUT}),
    ("exec", {"command": f"head -n 1 {INPUT}"}),
    ("exec", {"command": f"tail -n 1 {INPUT}"}),
    ("run_python", {"code": f"from pathlib import Path\nprint(len(Path({INPUT!r}).read_text().splitlines()) - 1)"}),
]


def archive_program(wrong):
    calculation = 'int(row["gross_kg"])' if wrong else 'int(row["gross_kg"]) - int(row["tare_kg"])'
    return f"""import csv, json
from pathlib import Path
from zipfile import ZipFile, ZipInfo
with open({INPUT!r}) as stream:
    rows = list(csv.DictReader(stream))
net_load = sum({calculation} for row in rows)
target = Path({TARGET!r})
target.parent.mkdir(exist_ok=True)
with ZipFile(target, 'w') as archive:
    archive.writestr(ZipInfo({MEMBER!r}), json.dumps({{'count': len(rows), 'total_kg': net_load}}))
"""


class Model:
    def __init__(self, mode):
        self.mode = mode
        self.turns = 0
        self.actions = []
        self.history = []
        self.hint_turns = []
        self.seen = 0
        self.wrote = False

    async def chat(self, messages, system, **options):
        self.turns += 1
        fresh = messages[self.seen:]
        self.seen = len(messages)
        self.history.extend((m["tool_call_id"], m["content"]) for m in fresh if m["role"] == "tool")
        hints = [m for m in fresh if m["role"] == "user" and m["content"].startswith(HINT)]
        self.hint_turns.extend([self.turns] * len(hints))
        if self.mode == "reject" and self.turns == 5:
            raise RuntimeError("scripted provider rejected the fifth request")
        if self.turns <= len(INSPECT):
            name, args = INSPECT[self.turns - 1]
        elif self.turns == 5 and (self.mode == "fixed" or (self.mode in {"respond", "wrong"} and hints)):
            name, args = "run_python", {"code": archive_program(self.mode == "wrong")}
            self.wrote = True
        elif self.turns == 5:
            name, args = INSPECT[0]
        else:
            name, args = "finish", {"final_message": "Inspection complete."}
        self.actions.append((name, args))
        return {"usage": {}, "tool_calls": [{"id": str(self.turns), "name": name, "arguments": args}]}


class Transport(LocalTransport):
    def __init__(self, work, fail_probe):
        super().__init__(work)
        self.fail_probe = fail_probe
        self.probes = 0

    async def exec(self, command, timeout_sec=120):
        if "ple-zip-target-missing" in command and "os.lstat(" in command:
            self.probes += 1
            if self.fail_probe:
                raise OSError("fixture transport unavailable during path observation")
        return await super().exec(command, timeout_sec)


async def run_case(capture, *, enabled=True, mode="respond", existing=False, plain=False, fail_probe=False,
                   save_as=None):
    path = "output/shipment.txt" if plain else TARGET
    task = f"Read the weighings in `{INPUT}`. Save the total in `{path}`." if plain else TASK
    expected_state = None if plain or not enabled else ("unknown" if fail_probe else "present" if existing else "missing")
    with TemporaryDirectory(prefix="early-zip-control-") as tmp:
        root = Path(tmp).resolve()
        work = root / "task"
        (work / INPUT).parent.mkdir(parents=True)
        (work / INPUT).write_text(ROWS)
        (work / "task.md").write_text(task)
        target = work / path
        target.parent.mkdir()
        if existing:
            with ZipFile(target, "w") as archive:
                archive.writestr(ZipInfo(MEMBER), '{"count": 1, "total_kg": 7}')
            original = target.read_bytes()
        env = LocalCaptureEnvironment()
        roots = [str(target.parent) + "/"]
        baseline = await capture.listing(env, roots)
        require(set(baseline["files"]) == ({str(target)} if existing else set()), "unexpected capture baseline")
        transport = Transport(work, fail_probe)
        model = Model(mode)
        logs = []
        harness = Harness(transport, model, task, workdir=str(work))
        with patch.dict(os.environ), redirect_stdout(io.StringIO()):
            os.environ.pop(FLAG, None)
            if enabled:
                os.environ[FLAG] = "1"
            final = await harness.run(timeout_sec=40, on_log=logs.append)
        require(harness.spec["deliverable"] == path, "wrong parsed target")
        require([line for line in logs if line in LOGS.values()] ==
                ([LOGS[expected_state]] if expected_state else []), "unexpected observations: " + repr(logs))
        require(transport.probes == int(expected_state is not None), "unexpected observation count")
        require(model.hint_turns == ([5] if expected_state == "missing" else []), "wrong turn or repeated reminder")
        accepted = logs.count("early ZIP reminder sent to model")
        require(accepted == int(expected_state == "missing" and mode != "reject"), "wrong accepted-reminder count")
        require(model.history[:4] == [("1", ROWS), ("2", "gross_kg,tare_kg\n"),
                                      ("3", "59,8\n"), ("4", "3\n")], "unexpected external observations")
        expected_write = mode == "fixed" or (mode in {"respond", "wrong"} and expected_state == "missing")
        require(model.wrote == expected_write and target.is_file() == (existing or expected_write), "unexpected file state")
        if existing:
            require(target.read_bytes() == original, "pre-existing archive changed")
        guard, _ = await harness.guard.run()
        require(guard == ("PASS" if existing or expected_write else "FAIL"), "unexpected structural guard status")

        destination = root / "capture"
        capture.start(destination)
        await capture.capture(env, roots, baseline, destination, final)
        manifest = json.loads((destination / capture.INFO).read_bytes())
        key = str(target).lstrip("/")
        require(manifest["baseline"] and not any(manifest[k] for k in ("error", "skipped", "deleted")),
                "capture was incomplete")
        require(set(manifest["files"]) == ({key} if expected_write else set()), "unexpected files captured")
        copied = destination / "files" / key
        if expected_write:
            require(copied.read_bytes() == target.read_bytes(), "captured bytes changed")
        shutil.rmtree(work)
        result = {"probe_count": transport.probes, "prompt_turns": model.hint_turns, "prompt_accepted": accepted, "guard": guard,
                  "captured_files": len(manifest["files"]), "fixture_score": 0}
        if copied.is_file():
            with ZipFile(copied) as archive:
                require(archive.testzip() is None and archive.namelist() == [MEMBER], "bad member list or CRC")
                values = json.loads(archive.read(MEMBER))
            result["fixture_score"] = int(values == {"count": 3, "total_kg": 199})
            result.update(values=values, sha256=hashlib.sha256(copied.read_bytes()).hexdigest())
        require(result["fixture_score"] == int(expected_write and mode != "wrong"), "unexpected copied ZIP score")
        if mode == "wrong":
            require(result.get("values") == {"count": 3, "total_kg": 234}, "wrong-value control did not run")
        if save_as is not None:
            shutil.copyfile(copied, save_as)
            require(hashlib.sha256(save_as.read_bytes()).hexdigest() == result["sha256"], "saved ZIP hash differs")
            result["capture_filename"] = save_as.name
        return result, (model.actions, model.history)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True, type=Path)
    parser.add_argument("--save-captures", type=Path, metavar="DIR", help="keep the two scored fixture ZIPs")
    args = parser.parse_args()
    kit = args.kit.resolve()
    revision = subprocess.check_output(["git", "-C", str(kit), "rev-parse", "HEAD"], text=True).strip()
    require(revision == KIT_COMMIT, "unexpected kit revision")
    sys.path.insert(0, str(kit))
    from kit import capture

    cases = {
        "respond": {}, "respond_default_off": {"enabled": False},
        "fixed": {"mode": "fixed"}, "fixed_default_off": {"mode": "fixed", "enabled": False},
        "wrong_value": {"mode": "wrong"}, "ignored": {"mode": "ignore"}, "existing": {"existing": True},
        "non_zip": {"plain": True}, "probe_failure": {"fail_probe": True},
        "model_rejection": {"mode": "reject"},
    }
    if args.save_captures is not None:
        args.save_captures.mkdir(parents=True, exist_ok=True)
        cases["respond"]["save_as"] = args.save_captures / "correct.zip"
        cases["wrong_value"]["save_as"] = args.save_captures / "wrong-value.zip"
    results, histories = {}, {}
    for name, options in cases.items():
        results[name], histories[name] = await run_case(capture, **options)
    for enabled, disabled in zip(histories["respond"], histories["respond_default_off"]):
        require(enabled[:4] == disabled[:4], "responsive script differs before the observation")
    require(histories["fixed"] == histories["fixed_default_off"], "fixed script tool results differ")
    require(results["fixed"]["sha256"] == results["fixed_default_off"]["sha256"], "fixed output bytes differ")
    print(json.dumps({"model": "scripted", "score_source": "local fixture on captured files", "kit_commit": revision,
                      "matched_fixed_tool_history": True, "cases": results}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
