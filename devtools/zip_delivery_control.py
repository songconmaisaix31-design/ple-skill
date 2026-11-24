"""Offline ZIP delivery control using the production harness and official kit capture.

Run with python devtools/zip_delivery_control.py --kit /path/to/ple-kit.
The model is scripted. All fixture files and generated ZIPs live in a temporary directory.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skillkit.harness import Harness
from skillkit.transport import LocalTransport


KIT_COMMIT = "8320f0402fdca9f42476607f72bcfd5271cd50c9"
TARGET = "output/summary.zip"
MEMBER = "totals.json"
TASK = """Read the original observations in `inputs/counts.json`.
Save the package as `output/summary.zip`. The following member is required:
### 1. `totals.json`
Report the observation count and total as JSON fields count and total."""
PROGRAM = """import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

values = json.loads(Path('inputs/counts.json').read_text())
target = Path('output/summary.zip')
target.parent.mkdir(exist_ok=True)
summary = json.dumps({'count': len(values), 'total': sum(values)}, sort_keys=True)
with ZipFile(target, 'w') as archive:
    archive.writestr(ZipInfo('totals.json'), summary)
"""


class ScriptedModel:
    def __init__(self, write_archive):
        self.write_archive = write_archive
        self.turns = 0

    async def chat(self, messages, system, **options):
        self.turns += 1
        if self.write_archive and self.turns == 1:
            name, arguments = "run_python", {"code": PROGRAM}
        else:
            name, arguments = "finish", {"final_message": "Fixture finished."}
        return {"usage": {}, "tool_calls": [
            {"id": str(self.turns), "name": name, "arguments": arguments},
        ]}


class LocalCaptureEnvironment:
    """Implement the kit's Harbor I/O calls against the local scratch filesystem."""

    async def exec(self, *, command, cwd, timeout_sec, user):
        result = await LocalTransport(cwd).exec(command, timeout_sec)
        return SimpleNamespace(stdout=result["output"])

    async def upload_file(self, source, target):
        shutil.copyfile(source, target)

    async def download_file(self, source, target):
        shutil.copyfile(source, target)


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


async def run_case(capture, write_archive):
    with TemporaryDirectory(prefix="ple-zip-control-") as temporary:
        root = Path(temporary).resolve()
        work = root / "work"
        (work / "inputs").mkdir(parents=True)
        (work / "inputs/counts.json").write_text("[7, 4, 12]\n", encoding="utf-8")
        (work / "task.md").write_text(TASK, encoding="utf-8")
        target = work / TARGET
        roots = [str(work / "output") + "/"]
        environment = LocalCaptureEnvironment()
        before = await capture.listing(environment, roots)
        require(not before["files"], "capture baseline must be empty")

        harness = Harness(LocalTransport(work), ScriptedModel(write_archive), TASK, workdir=str(work))
        final = await harness.run(timeout_sec=60)
        require(harness.spec.get("deliverable") == TARGET, "task contract resolved the wrong ZIP")
        guard, _ = await harness.guard.run()
        destination = root / "capture"
        capture.start(destination)
        await capture.capture(environment, roots, before, destination, final)
        record = json.loads((destination / capture.INFO).read_bytes())
        require(record["baseline"] and not record["error"] and not record["skipped"], "capture failed or skipped files")
        key = target.as_posix().lstrip("/")
        copied = destination / "files" / key
        expected = {key} if write_archive else set()
        require(set(record["files"]) == expected, "captured paths differ from the expected set")
        require(target.is_file() == write_archive and copied.is_file() == write_archive, "wrong ZIP file state")
        observed = {"guard": guard, "captured_files": len(record["files"]), "target_captured": key in record["files"]}
        if write_archive:
            require(guard == "PASS", "guard rejected the valid ZIP")
            data = copied.read_bytes()
            require(target.read_bytes() == data and record["files"][key]["bytes"] == len(data), "copied bytes differ")
            with ZipFile(copied) as archive:
                require(archive.testzip() is None and archive.namelist() == [MEMBER], "invalid ZIP members or CRC")
                require(json.loads(archive.read(MEMBER)) == {"count": 3, "total": 23}, "wrong computed values")
            observed.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), contents_verified=True)
        else:
            require(guard == "FAIL", "guard accepted a missing ZIP")
        return observed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True, help="local checkout of the pinned official kit")
    args = parser.parse_args()
    kit_dir = args.kit.resolve()
    revision = subprocess.check_output(["git", "-C", str(kit_dir), "rev-parse", "HEAD"], text=True).strip()
    require(revision == KIT_COMMIT, "unexpected official kit revision")
    sys.path.insert(0, str(kit_dir))
    from kit import capture

    print(json.dumps({"kit_commit": revision, "model": "scripted", "positive": await run_case(capture, True),
                      "missing": await run_case(capture, False)}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
