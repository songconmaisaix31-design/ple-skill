#!/usr/bin/env python3
"""Run the original scheduling exercise through the harness and the official WebSocket relay."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


IMAGE = "python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
OUTPUTS = ("schedule.csv", "summary.json")
LIMIT = 64 * 1024
WORKDIR = "/app"

# Read only an exact regular file from the output directory. A FIFO, symlink,
# absent file or oversized file counts as a missing deliverable.
READ_OUTPUT = """
import os, stat, sys
directory = os.open('/app/output', os.O_DIRECTORY | os.O_NOFOLLOW)
with os.scandir(directory) as entries:
    if any(entry.name not in sys.argv[3:] for entry in entries):
        sys.exit(1)
fd = os.open(sys.argv[1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
limit = int(sys.argv[2])
with os.fdopen(fd, 'rb') as source:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        sys.exit(1)
    data = source.read(limit + 1)
    if len(data) > limit:
        sys.exit(1)
    sys.stdout.buffer.write(data)
"""


def docker(*args, read=False, data=None):
    return subprocess.run(["docker", *args], check=not read, timeout=30,
                          input=data,
                          stdout=subprocess.PIPE if read else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)


@asynccontextmanager
async def task_container(inputs):
    name = "ple-design-" + uuid.uuid4().hex
    try:
        await asyncio.to_thread(
            docker, "run", "--detach", "--name", name, "--pull=never", "--network=none",
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
            "--memory=256m", "--cpus=1", "--user=65534:65534", "--log-driver=none",
            "--tmpfs", "/app:rw,nosuid,nodev,size=24m,mode=1777",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m,mode=1777", "--workdir", WORKDIR,
            "--entrypoint", "sleep", IMAGE, "infinity",
        )
        await asyncio.to_thread(docker, "exec", name, "mkdir", "-p", f"{WORKDIR}/input")
        for relative in ("task.md", "input/site.json", "input/periods.csv"):
            await asyncio.to_thread(
                docker, "exec", "-i", name, "python3", "-I", "-c",
                "import pathlib, sys; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
                f"{WORKDIR}/{relative}", data=(inputs / relative).read_bytes(),
            )
        yield name
    finally:
        await asyncio.to_thread(docker, "rm", "-f", name, read=True)


async def measure(workspace, variant, seconds, kit_root):
    sys.path.insert(0, str(kit_root))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import websockets
    from kit.relay import DockerExecutor, Relay
    from serve import solve
    from design_regression import grade, prepare

    prepare(workspace, variant)
    prompt = (workspace / "task.md").read_text(encoding="utf-8")
    async with task_container(workspace) as name:
        relay = Relay(DockerExecutor(name, user="65534:65534"), workdir=WORKDIR,
                      agent_timeout_sec=seconds)
        async with websockets.serve(solve, "127.0.0.1", 0, max_size=16 * 1024 * 1024,
                                    ping_interval=None) as server:
            address = server.sockets[0].getsockname()
            started = time.monotonic()
            socket = await relay.connect(f"ws://127.0.0.1:{address[1]}")
            try:
                outcome = await relay.run(socket, prompt)
            finally:
                await socket.close()
            elapsed = time.monotonic() - started
        output = workspace / "output"
        output.mkdir(exist_ok=True)
        for filename in OUTPUTS:
            read = await asyncio.to_thread(docker, "exec", name, "python3", "-I", "-c",
                                          READ_OUTPUT, filename, str(LIMIT), *OUTPUTS, read=True)
            if read.returncode == 0:
                (output / filename).write_bytes(read.stdout)

    result = grade(workspace, variant)
    report = {"variant": variant, "model": os.environ.get("MODEL_NAME"), "budget_sec": seconds,
              "elapsed_sec": round(elapsed, 1), "status": outcome.status, "requests": outcome.kinds,
              "tokens": outcome.usage, "grade": result}
    if outcome.infra:
        report["infrastructure_error"] = True
    print(json.dumps(report, ensure_ascii=True, allow_nan=False), flush=True)
    return 2 if outcome.infra else int(not result["optimal"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-root", required=True, type=Path, help="Checkout of the pinned official PLE kit")
    parser.add_argument("--variant", choices=("a", "b"), default="a")
    parser.add_argument("--timeout-sec", type=int, default=540)
    parser.add_argument("--keep-dir", type=Path, help="New directory for the original inputs and two outputs")
    args = parser.parse_args()
    if not 1 <= args.timeout_sec <= 21600:
        parser.error("time budget must be between 1 and 21600 seconds")
    kit = args.kit_root.resolve()
    if not (kit / "kit" / "relay.py").is_file():
        parser.error("the kit checkout must contain kit/relay.py")
    if not os.environ.get("MODEL_NAME") or not (os.environ.get("MODEL_BASE_URL") or os.environ.get("OPENAI_BASE_URL")):
        parser.error("set MODEL_NAME and MODEL_BASE_URL to a configured model")
    if args.keep_dir:
        workspace = args.keep_dir.resolve()
        if workspace.exists():
            parser.error("--keep-dir must not exist")
        return asyncio.run(measure(workspace, args.variant, args.timeout_sec, kit))
    with tempfile.TemporaryDirectory(prefix="ple-design-") as temporary:
        return asyncio.run(measure(Path(temporary) / "task", args.variant, args.timeout_sec, kit))


if __name__ == "__main__":
    sys.exit(main())
