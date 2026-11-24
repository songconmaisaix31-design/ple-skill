"""Run deterministic deliverable deadline tests without credentials or Docker."""

import asyncio
from contextlib import suppress
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skillkit.harness import Harness
from skillkit.transport import LocalTransport


OUTPUT = "observations.txt"
WRITE = ("write_file", {"path": OUTPUT, "content": "18.75"})
EXEC = ("exec", {"command": f"echo 18.75 > {OUTPUT}"})
PYTHON = ("run_python", {"code": "print(18.75)", "output_path": OUTPUT})
READ = ("read_file", {"path": OUTPUT})
EMPTY = ("exec", {"command": "echo inspecting"})
CORRUPT = ("run_python", {"code": f"from pathlib import Path\nPath({OUTPUT!r}).write_bytes(b'')"})


class StallingModel:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.stalled = asyncio.Event()
        self.calls = 0

    async def chat(self, messages, system):
        self.calls += 1
        action = next(self.actions, None)
        if action is None:
            self.stalled.set()
            await asyncio.sleep(10)
        name, arguments = action
        return {"tool_calls": [{"id": str(self.calls), "name": name, "arguments": arguments}]}


async def check(actions, status, guards, *, cancel=False):
    with tempfile.TemporaryDirectory() as directory:
        model = StallingModel(actions)
        harness = Harness(LocalTransport(directory), model, f"Write `{OUTPUT}`.", workdir=directory)
        harness.guard.run = AsyncMock(wraps=harness.guard.run)
        if cancel:
            task = asyncio.create_task(harness.run(timeout_sec=10))
            try:
                await asyncio.wait_for(model.stalled.wait(), 3)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            final = harness.final
        else:
            final = await asyncio.wait_for(harness.run(timeout_sec=2), 3)
            assert "time budget" in final, final
        assert model.calls == len(actions) + 1, model.calls
        assert harness.guard.run.await_count == guards, harness.guard.run.await_args_list
        if status is None:
            assert not final, final
        else:
            assert f"Structural checks: {status}" in final and OUTPUT in final, final
        if status == "PASS":
            assert (Path(directory) / OUTPUT).read_text().strip() == "18.75"


async def check_interrupted_operation():
    with tempfile.TemporaryDirectory() as directory:
        transport = LocalTransport(directory)
        original_exec = transport.exec

        async def exec_until_cancelled(command, timeout):
            if command == "pending modification":
                await asyncio.sleep(10)
            return await original_exec(command, timeout)

        transport.exec = exec_until_cancelled
        model = StallingModel([WRITE, ("exec", {"command": "pending modification"})])
        harness = Harness(transport, model, f"Write `{OUTPUT}`.", workdir=directory)
        final = await asyncio.wait_for(harness.run(timeout_sec=2), 3)
        assert "state was not verified" in final and "PASS" not in final, final
        assert model.calls == 2, model.calls


async def main():
    await asyncio.gather(
        check([WRITE, READ, READ], "PASS", 1),
        check([EXEC], "PASS", 1),
        check([PYTHON], "PASS", 1),
        check([EMPTY, EMPTY, EXEC], "PASS", 2),
        check([], "FAIL", 1),
        check([WRITE, CORRUPT], "FAIL", 2),
        check([WRITE], "PASS", 1, cancel=True),
        check([WRITE, CORRUPT], None, 1, cancel=True),
        check_interrupted_operation(),
    )
    print("DEADLINE REGRESSION: PASS (write, exec, Python, missing, corrupt, cancel)")


if __name__ == "__main__":
    asyncio.run(main())
