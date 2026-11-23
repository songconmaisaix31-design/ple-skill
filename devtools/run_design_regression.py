#!/usr/bin/env python3
"""Run the original scheduling exercise through the harness and the official WebSocket relay."""

import argparse
import asyncio
import base64
from collections import deque
from contextlib import asynccontextmanager, contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit


IMAGE = "python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
OUTPUTS = ("schedule.csv", "summary.json")
LIMIT = 64 * 1024
WORKDIR = "/app"
PROBE_FILES = {"schedule.csv": b"label,count\nrelay,2\n", "summary.json": b'{"transport":"ready"}\n'}
KNOWN_PATHS = {"task.md", "input/site.json", "input/periods.csv", *OUTPUTS,
               *(f"output/{file}" for file in OUTPUTS)}

# Names are supplied by the experimenter. Neither unknown directory entries
# nor file contents are emitted by this diagnostic.
INVENTORY = """
import json, os, stat, sys
def describe(parent, name):
    try:
        item = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return {"kind": "missing"}
    except OSError:
        return {"kind": "inaccessible"}
    if stat.S_ISREG(item.st_mode):
        return {"kind": "regular", "bytes": item.st_size}
    if stat.S_ISDIR(item.st_mode):
        return {"kind": "directory"}
    return {"kind": "symlink" if stat.S_ISLNK(item.st_mode) else "other"}

root = os.open('/app', os.O_DIRECTORY | os.O_NOFOLLOW)
names = sys.argv[1:]
info = {"output": describe(root, "output"), "workspace_root": {n: describe(root, n) for n in names}}
if info["output"]["kind"] == "directory":
    out = os.open("output", os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    info["expected"] = {n: describe(out, n) for n in names}
    extras = 0
    with os.scandir(out) as entries:
        for entry in entries:
            if entry.name not in names:
                extras += 1
                if extras == 32:
                    break
    info["extra_entries_capped_at_32"] = extras
print(json.dumps(info))
"""

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

# One read-only Docker invocation for both files. Times are nanosecond Unix times
# on the Docker host/containers. Never grade inputs that changed across the cutoff.
SNAPSHOT = """
import base64, json, os, stat, sys
root = os.open('/app', os.O_DIRECTORY | os.O_NOFOLLOW)
limit, cutoff = int(sys.argv[1]), int(sys.argv[2])
names = sys.argv[3:]
meta, files = {}, {}
stable = True
try:
    folder = os.open('output', os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
except (FileNotFoundError, NotADirectoryError):
    meta['output_directory'] = False
    stable = os.fstat(root).st_ctime_ns <= cutoff
else:
    meta['output_directory'] = True
    info = os.fstat(folder)
    stable = info.st_ctime_ns <= cutoff
    with os.scandir(folder) as entries:
        meta['extras'] = any(item.name not in names for item in entries)
    for name in names:
        try:
            st = os.stat(name, dir_fd=folder, follow_symlinks=False)
        except FileNotFoundError:
            meta[name] = 'missing'
            continue
        stable = stable and st.st_ctime_ns <= cutoff
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            meta[name] = 'not_regular_or_oversized'
            continue
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=folder)
        with os.fdopen(fd,'rb') as stream:
            data = stream.read(limit + 1)
            final = os.fstat(fd)
        stable = stable and (st.st_ino,st.st_ctime_ns,st.st_size) == (final.st_ino,final.st_ctime_ns,len(data))
        meta[name] = len(data)
        if len(data) <= limit and not meta['extras']:
            files[name] = base64.b64encode(data).decode('ascii')
    after = os.stat('output', dir_fd=root, follow_symlinks=False)
    stable = stable and (info.st_ino,info.st_ctime_ns) == (after.st_ino,after.st_ctime_ns)
print(json.dumps({'stable':stable,'inventory':meta,'files':files if stable else {}}))
"""


async def capture_at_cutoff(container, destination, cutoff_ns):
    try:
        output = await asyncio.to_thread(docker, "exec", container, "python3", "-I", "-c",
                                         SNAPSHOT, str(LIMIT), str(cutoff_ns), *OUTPUTS, read=True)
    except (OSError, subprocess.TimeoutExpired):
        return {"measured": False, "reason": "snapshot reader unavailable"}, None
    if output.returncode:
        return {"measured": False, "reason": "snapshot reader failed"}, None
    snapshot = json.loads(output.stdout)
    if not snapshot["stable"]:
        return {"measured": False, "reason": "files changed at cutoff"}, snapshot["inventory"]
    destination.mkdir()
    for name in OUTPUTS:
        if name in snapshot["files"]:
            (destination / name).write_bytes(base64.b64decode(snapshot["files"][name], validate=True))
    return {"measured": True}, snapshot["inventory"]


def docker(*args, read=False, data=None):
    return subprocess.run(["docker", *args], check=not read, timeout=30,
                          input=data,
                          stdout=subprocess.PIPE if read else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)


def describe_action(request, result, start, run_start):
    moment = time.monotonic()
    kind = request["type"]
    action = {"action": kind, "end_sec": round(moment - run_start, 2),
              "duration_sec": round(moment - start, 2)}
    if kind in {"read_file", "write_file"}:
        path = os.path.normpath(request["path"]).removeprefix("/app/")
        action["path"] = path if path in KNOWN_PATHS else "other"
    if result is None:
        action["status"] = "interrupted"
    elif type(result.get("exit_code")) is int:
        action["exit_code"] = result["exit_code"]
        action["timed_out"] = bool(result.get("timed_out"))
    else:
        action["status"] = "ok" if result.get("ok") else "error"
    return action


def describe_call(raw):
    fields = {"run_python": ("code",), "exec": ("command",), "read_file": ("path",),
              "write_file": ("path", "content"), "mcp_call": ("url",), "finish": ("final_message",)}
    name = raw.get("name")
    tool = name if isinstance(name, str) and name in fields else "other"
    args = raw.get("arguments", raw.get("input"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, RecursionError):
            return {"tool": tool, "arguments": "invalid_json"}
    kinds = {dict: "object", list: "array", type(None): "null", str: "string", bool: "boolean",
             int: "number", float: "number"}
    row = {"tool": tool, "arguments": kinds.get(type(args), "other")}
    if tool in fields and isinstance(args, dict):
        row["required_strings_present"] = all(isinstance(args.get(k), str) for k in fields[tool])
        if tool == "run_python" and isinstance(args.get("code"), str):
            row["code_chars"] = len(args["code"])
    return row


def describe_model_response(data):
    # The CPU provider uses Chat Completions. Also recognize the public response
    # shapes used by the other clients, without logging messages or provider IDs.
    if data.get("choices"):
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        calls = [call.get("function", {}) for call in msg.get("tool_calls") or []]
        parts = [msg.get("content")]
        finish = choice.get("finish_reason")
    elif isinstance(data.get("output"), list):
        calls = [i for i in data["output"] if i.get("type") == "function_call"]
        parts = [p.get("text") for i in data["output"] if i.get("type") == "message"
                 for p in i.get("content", []) if p.get("type") == "output_text"]
        finish = data.get("status")
    else:
        blocks = data.get("content") or []
        calls = [b for b in blocks if b.get("type") == "tool_use"]
        parts = [b.get("text") for b in blocks if b.get("type") == "text"]
        finish = data.get("stop_reason")
    known = ("stop", "length", "tool_calls", "content_filter", "completed", "incomplete",
             "failed", "end_turn", "max_tokens", "tool_use", "stop_sequence")
    texts = [p for p in parts if isinstance(p, str)]
    usage = data.get("usage") or {}
    metrics = {"finish_reason": finish if finish in known else "other",
               "text_chars": sum(map(len, texts)), "tool_count": len(calls),
               "python_fence": any("```python" in p.lower() for p in texts),
               "tools": [describe_call(c) for c in calls[:8]]}
    tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if type(tokens) is int and tokens >= 0:
        metrics["output_tokens"] = tokens
    return metrics


def first_code_action(lines):
    prefix = "harness: code_action "
    classifications = ("verified", "guard_failed", "guard_timeout", "exec_failed", "exec_timeout",
                       "exec_truncated", "provider_error", "timeout", "cancelled", "truncated",
                       "invalid_native", "invalid_syntax", "empty", "oversized", "non_program", "unexpected_tool")
    stops = ("stop", "tool_calls", "length", "content_filter", "stop_sequence", "end_turn", "tool_use",
             "max_tokens", "completed", "incomplete", "max_output_tokens", "refusal", "unknown")
    for line in lines:
        if not line.startswith(prefix) or len(line) > 640:
            continue
        try:
            event = json.loads(line[len(prefix):])
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("mode") not in ("text", "native"):
            continue
        row = {"mode": event["mode"]}
        for key, allowed in (("classification", classifications), ("finish_reason", stops)):
            if event.get(key) in allowed:
                row[key] = event[key]
        for key in ("millis", "output_tokens", "exec_exit_status"):
            if type(event.get(key)) is int and abs(event[key]) < 2**31:
                row[key] = event[key]
        return row
    return None


class ModelIOArchive:
    """Host-side transcript for the two explicitly opted-in, original CPU fixtures."""

    def __init__(self, path, limit=2 * 1024 * 1024):
        self.path = path
        self.limit = limit
        self.bytes_written = 0
        self.requests = 0
        self.omitted = 0
        path.open("xb").close()

    def write(self, record):
        encoded = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        if self.bytes_written + len(encoded) > self.limit - 256:
            self.omitted += 1
            return
        with self.path.open("ab") as stream:
            stream.write(encoded)
        self.bytes_written += len(encoded)

    def request(self, body):
        self.requests += 1
        allowed = ("model", "messages", "tools", "tool_choice", "max_tokens", "reasoning_effort",
                   "temperature", "seed", "top_p", "stop")
        fields = {key: body[key] for key in allowed if key in body}
        if set(body) - set(allowed) or not isinstance(fields.get("messages"), list):
            self.omitted += 1
        self.write({"event": "request", "call": self.requests, "body": fields})
        return self.requests

    def response(self, call_id, payload):
        # Include exact visible assistant text and native function arguments, which
        # contain the generated Python. Credentials, hidden model state and HTTP
        # headers are not part of the generation transcript.
        choices = []
        for choice in payload.get("choices") or []:
            message = choice.get("message") or {}
            visible = {k: message[k] for k in ("role", "content", "tool_calls") if k in message}
            choices.append({"finish_reason": choice.get("finish_reason"), "message": visible})
        if not choices:
            self.omitted += 1
        self.write({"event": "response", "call": call_id, "choices": choices})

    def finish(self):
        summary = {"complete": self.requests > 0 and self.omitted == 0,
                   "requests": self.requests, "omitted_records_or_fields": self.omitted}
        with self.path.open("ab") as stream:
            stream.write((json.dumps({"event": "end", **summary}) + "\n").encode("ascii"))
        return summary


@contextmanager
def record_model_requests(attempts, first_events, elapsed, archive=None):
    import httpx
    post = httpx.AsyncClient.post

    async def observed(client, *args, **kwargs):
        before = time.monotonic()
        row = {"status": "error"}
        call_id = None
        if archive is not None:
            endpoint = urlsplit(str(args[0] if args else kwargs.get("url", "")))
            if endpoint.hostname in ("127.0.0.1", "localhost", "::1") and endpoint.path == "/v1/chat/completions":
                call_id = archive.request(kwargs.get("json") or {})
        try:
            response = await post(client, *args, **kwargs)
            row.update(status="complete", http_status=response.status_code)
            if response.is_success:
                try:
                    payload = response.json()
                    if call_id is not None:
                        archive.response(call_id, payload)
                    row.update(describe_model_response(payload))
                except (ValueError, TypeError, AttributeError, LookupError, RecursionError):
                    row["response_shape"] = "unrecognized"
                    if call_id is not None:
                        archive.omitted += 1
            return response
        except asyncio.CancelledError:
            row["status"] = "interrupted"
            raise
        finally:
            row["end_sec"] = round(elapsed(), 2)
            row["duration_sec"] = round(time.monotonic() - before, 2)
            if call_id is not None:
                archive.write({"event": "status", "call": call_id, "status": row["status"],
                               "http_status": row.get("http_status"), "end_sec": row["end_sec"]})
            first_events.setdefault("first_model_attempt", row)
            if row.get("tools") or row.get("text_chars"):
                first_events.setdefault("first_model_output", row)
            attempts.append(row)

    with patch.object(httpx.AsyncClient, "post", observed):
        yield


class TransportProbe:
    """Script the model's two turns while retaining the real task relay and sandbox."""

    model = "deterministic-transport-check"

    async def chat(self, messages, system):
        if any(message["role"] == "tool" for message in messages):
            call = {"id": "done", "name": "finish", "arguments": {"final_message": "Transport check complete."}}
        else:
            lines = ["from pathlib import Path", "target = Path('output')", "target.mkdir(exist_ok=True)"]
            for name, data in PROBE_FILES.items():
                lines.append(f"(target / {name!r}).write_bytes({data!r})")
            call = {"id": "probe", "name": "run_python", "arguments": {"code": "\n".join(lines)}}
        return {"content": "", "tool_calls": [call], "usage": {}}


@asynccontextmanager
async def task_container(inputs, fixture_paths):
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
        for relative in fixture_paths:
            await asyncio.to_thread(
                docker, "exec", "-i", name, "python3", "-I", "-c",
                "import pathlib, sys; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
                f"{WORKDIR}/{relative}", data=(inputs / relative).read_bytes(),
            )
        yield name
    finally:
        await asyncio.to_thread(docker, "rm", "-f", name, read=True)


async def measure(workspace, variant, seconds, kit_root, check_transport=False, checkpoint_sec=None,
                  archive_path=None):
    sys.path.insert(0, str(kit_root))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import websockets
    from kit.relay import DockerExecutor, Relay
    from serve import solve
    from design_regression import grade, prepare

    archive = None
    if archive_path is not None:
        if (check_transport or variant not in ("d", "e")
                or archive_path.resolve().is_relative_to(workspace.resolve())):
            raise ValueError("model IO must be archived outside a synthetic D/E task workspace")
        archive = ModelIOArchive(archive_path)
    if check_transport:
        workspace.mkdir()
        (workspace / "task.md").write_text("Save output/schedule.csv and output/summary.json under output/.")
        fixture_paths = ("task.md",)
    else:
        prepare(workspace, variant)
        fixture_paths = ("task.md", "input/site.json", "input/periods.csv")
    prompt = (workspace / "task.md").read_text(encoding="utf-8")
    actions = deque(maxlen=24)
    model_attempts = deque(maxlen=24)
    first_events = {}
    checkpoint = None

    class RecordingRelay(Relay):
        async def dispatch(self, request):
            before = time.monotonic()
            result = None
            try:
                result = await super().dispatch(request)
                return result
            finally:
                actions.append(describe_action(request, result, before, started))

    async with task_container(workspace, fixture_paths) as name:
        relay = RecordingRelay(DockerExecutor(name, user="65534:65534"), workdir=WORKDIR,
                               agent_timeout_sec=seconds)
        model_override = (patch("serve.from_env", return_value=TransportProbe()) if check_transport
                          else record_model_requests(model_attempts, first_events,
                                                     lambda: time.monotonic() - started, archive))
        with model_override:
            async with websockets.serve(solve, "127.0.0.1", 0, max_size=16 * 1024 * 1024,
                                        ping_interval=None) as server:
                address = server.sockets[0].getsockname()
                started = time.monotonic()
                start_wall_ns = time.time_ns()
                socket = await relay.connect(f"ws://127.0.0.1:{address[1]}")
                try:
                    if checkpoint_sec is None:
                        outcome = await relay.run(socket, prompt)
                    else:
                        session = asyncio.create_task(relay.run(socket, prompt))
                        try:
                            await asyncio.wait({session}, timeout=max(0, started + checkpoint_sec - time.monotonic()))
                            completed = session.done()
                            snapshot_start = time.monotonic() - started
                            checkpoint, inventory = await capture_at_cutoff(
                                name, workspace / "output", start_wall_ns + int(checkpoint_sec * 1e9))
                            snapshot_end = time.monotonic() - started
                            checkpoint.update(target_sec=checkpoint_sec, start_sec=round(snapshot_start, 3),
                                              end_sec=round(snapshot_end, 3), ended_by_target=snapshot_end <= checkpoint_sec,
                                              session_was_done=completed)
                        finally:
                            session.cancel()
                            await asyncio.gather(session, return_exceptions=True)
                        if not session.cancelled():
                            session.result()
                        outcome = relay.outcome
                finally:
                    await socket.close()
                elapsed = time.monotonic() - started
        output = workspace / "output"
        if checkpoint is None:
            try:
                metadata = await asyncio.to_thread(docker, "exec", name, "python3", "-I", "-c",
                                                   INVENTORY, *OUTPUTS, read=True)
                inventory = json.loads(metadata.stdout) if metadata.returncode == 0 else None
            except (ValueError, OSError, subprocess.TimeoutExpired):
                inventory = None
            output.mkdir(exist_ok=True)
            for filename in OUTPUTS:
                read = await asyncio.to_thread(docker, "exec", name, "python3", "-I", "-c",
                                              READ_OUTPUT, filename, str(LIMIT), *OUTPUTS, read=True)
                if read.returncode == 0:
                    (output / filename).write_bytes(read.stdout)

    if check_transport:
        matches = {n: (output / n).is_file() and (output / n).read_bytes() == data
                   for n, data in PROBE_FILES.items()}
        passed = all(matches.values()) and outcome.status == "completed" and not outcome.infra
        print(json.dumps({"transport_check": passed, "files_match": matches, "status": outcome.status,
                          "elapsed_sec": round(elapsed, 2), "inventory": inventory, "last_actions": list(actions)}))
        return 0 if passed else 1

    result = grade(workspace, variant) if checkpoint is None or checkpoint["measured"] else None
    report = {"variant": variant, "model": os.environ.get("MODEL_NAME"), "budget_sec": seconds,
              "elapsed_sec": round(elapsed, 1), "status": outcome.status, "requests": outcome.kinds,
              "tokens": outcome.usage, "grade": result, "inventory": inventory,
              "last_actions": list(actions), "final_message_chars": len(outcome.final_message),
              "done_after_cancel": outcome.done_after_cancel}
    report.update(first_events=first_events, last_model_attempts=list(model_attempts))
    if archive is not None:
        report["model_io_archive"] = archive.finish()
    if checkpoint is not None:
        report["checkpoint"] = checkpoint
    first_action = first_code_action(outcome.log)
    if first_action is not None:
        report["first_code_action"] = first_action
    if outcome.infra:
        report["infrastructure_error"] = True
    print(json.dumps(report, ensure_ascii=True, allow_nan=False), flush=True)
    return 2 if outcome.infra or result is None else int(not result["optimal"])


def main():
    from design_regression import VARIANTS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-root", required=True, type=Path, help="Checkout of the pinned official PLE kit")
    parser.add_argument("--variant", choices=VARIANTS, default="a")
    parser.add_argument("--check-transport", action="store_true",
                        help="Verify two exact file exports through the harness and Docker without a model")
    parser.add_argument("--timeout-sec", type=int, default=540)
    parser.add_argument("--checkpoint-only-sec", type=int,
                        help="Capture and grade at this external cutoff, then stop the session")
    parser.add_argument("--keep-dir", type=Path, help="New directory for the original inputs and two outputs")
    parser.add_argument("--archive-model-io", type=Path, metavar="JSONL",
                        help="Save model prompts and generated code for original D/E local CPU trials")
    args = parser.parse_args()
    if not 1 <= args.timeout_sec <= 21600:
        parser.error("time budget must be between 1 and 21600 seconds")
    if args.archive_model_io is not None:
        endpoint = urlsplit(os.environ.get("MODEL_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "")
        if (args.check_transport or args.variant not in ("d", "e") or os.environ.get("MODEL_NAME") != "gemma-4-26b"
                or endpoint.hostname not in ("127.0.0.1", "localhost", "::1")):
            parser.error("--archive-model-io is available only for original D/E trials on the local Gemma CPU endpoint")
        if args.archive_model_io.exists() or not args.archive_model_io.parent.is_dir():
            parser.error("--archive-model-io needs a new file in an existing host directory")
    if args.checkpoint_only_sec is not None and (args.check_transport or not 0 < args.checkpoint_only_sec < args.timeout_sec):
        parser.error("--checkpoint-only-sec needs a full model run and must be shorter than --timeout-sec")
    kit = args.kit_root.resolve()
    if not (kit / "kit" / "relay.py").is_file():
        parser.error("the kit checkout must contain kit/relay.py")
    if args.check_transport:
        args.timeout_sec = min(args.timeout_sec, 45)
    elif not os.environ.get("MODEL_NAME") or not (os.environ.get("MODEL_BASE_URL") or os.environ.get("OPENAI_BASE_URL")):
        parser.error("set MODEL_NAME and MODEL_BASE_URL to a configured model")
    if args.keep_dir:
        workspace = args.keep_dir.resolve()
        if workspace.exists():
            parser.error("--keep-dir must not exist")
        return asyncio.run(measure(workspace, args.variant, args.timeout_sec, kit,
                                   args.check_transport, args.checkpoint_only_sec, args.archive_model_io))
    with tempfile.TemporaryDirectory(prefix="ple-design-") as temporary:
        return asyncio.run(measure(Path(temporary) / "task", args.variant, args.timeout_sec, kit,
                                   args.check_transport, args.checkpoint_only_sec, args.archive_model_io))


if __name__ == "__main__":
    sys.exit(main())
