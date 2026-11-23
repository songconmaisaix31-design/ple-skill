"""Exercise serve.py over WebSocket against a local Anthropic Messages stub.

Run with `python devtools/protocol_smoke.py`. Requires the harness dependencies
but needs no network service, model key, Docker, or competition data.
"""

import asyncio
import base64
import json
import os
import shlex
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import websockets

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from skillkit import specgen
from skillkit.harness import Harness
from skillkit.mcp import exact_copy_contract
from skillkit.transport import LocalTransport

MODEL = "claude-opus-5-5"
DELIVERABLE = "/app/smoke.txt"
DOCUMENT = b"Offline protocol smoke deliverable.\n"
SUMMARY = "Saved the requested note in /app/smoke.txt."
USAGE = {"input_tokens": 7, "cache_creation_input_tokens": 11,
         "cache_read_input_tokens": 19, "output_tokens": 23}
PYTHON_LITERAL = "计算 'single' \"double\" ; $(printf changed) `printf changed`"
PYTHON_SOURCE = f"label = {PYTHON_LITERAL!r}\nprint(label)\nprint(sum(range(4)))"


def check_contracts():
    rules = [
        ("Read `input/source.json`. Save the report as\n`output/report.json` under `output/`.",
         "output/report.json"),
        ("Write two files to `output/`: `output/report.json` and `output/details.csv`.", "output/"),
        ("Read `input/source.json`, then inspect task.md.", ""),
    ]
    for instruction, expected in rules:
        actual = specgen.build(instruction)["deliverable"]
        assert actual == expected, (instruction, actual)


async def check_python_output():
    destination = "output/result.json"
    with tempfile.TemporaryDirectory() as directory:
        transport = LocalTransport(directory)
        harness = Harness(transport, None, f"Write the result to `{destination}`.")
        output = Path(directory) / destination

        async def run_python(code):
            return await harness._do({"name": "run_python", "arguments": {"code": code, "output_path": destination}})

        result = await run_python("import sys\nprint('diagnostic', file=sys.stderr)\nprint('{\"count\": 7}')")
        assert "saved" in result and output.read_bytes() == b'{"count": 7}\n', result

        for code in ("print('{invalid')", "print('{\"count\": 9}')\nraise SystemExit(3)"):
            assert "no file saved" in await run_python(code)
            assert output.read_bytes() == b'{"count": 7}\n'

        truncated = {"ok": True, "exit_code": 0, "output": '{"count": 9}\n', "truncated": True}
        with patch.object(transport, "exec", AsyncMock(return_value=truncated)):
            assert "stdout was truncated" in await run_python("print('{\"count\": 9}')")
        assert output.read_bytes() == b'{"count": 7}\n'


async def check_mcp_results():
    url = "http://127.0.0.1:8123/tools"
    transport = SimpleNamespace(http=AsyncMock())
    harness = Harness(transport, None, "Read the latest measurement.", mcp_servers=[
        {"name": "measurements", "url": url, "transport": "streamable-http"},
    ])
    request = {"jsonrpc": "2.0", "id": 17, "method": "tools/call", "params": {"name": "latest"}}
    measured = {"content": [{"type": "text", "text": "Measured value: 4.25"}],
                "structuredContent": {"unit": "m"}}
    reply = {"jsonrpc": "2.0", "id": 17, "result": measured}

    async def call(raw, status=200, content_type="application/json", rpc=request, truncated=False):
        transport.http.return_value = {
            "ok": True, "status": status, "truncated": truncated,
            "headers": {"Content-Type": content_type, "Mcp-Session-Id": "synthetic-id"},
            "body_b64": base64.b64encode(raw.encode()).decode(),
        }
        return await harness._do({"name": "mcp_call", "arguments": {"url": url, "body": json.dumps(rpc)}})

    sse = (": comment\r\nevent: message\r\ndata: {\r\n"
           f"data: \"jsonrpc\": \"2.0\", \"id\": 17, \"result\": {json.dumps(measured)}\r\n"
           "data: }\r\n\r\n")
    for result in [await call(json.dumps(reply)), await call(sse, content_type="text/event-stream; charset=utf-8")]:
        assert result.startswith("MCP tool result content (latest):\nMeasured value: 4.25\n"), result
        assert 'Structured content: {"unit": "m"}' in result, result
        assert "Mcp-Session-Id: synthetic-id\n[raw MCP response]" in result, result

    batch = [request, {**request, "id": "17", "params": {"name": "secondary"}}]
    both = await call(json.dumps([{**reply, "id": "17"}, reply]), rpc=batch)
    assert both.startswith("MCP tool result content (latest):") and "MCP tool result content (secondary):" in both

    for invalid in [{**reply, "id": "17"}, {**reply, "id": 999},
                    {**reply, "result": {**measured, "isError": True}},
                    {"jsonrpc": "2.0", "id": 17, "error": {"message": "server could not read"}}]:
        result = await call(json.dumps(invalid))
        assert "No confirmed tool result content." in result.splitlines()[0], result
        assert "[raw MCP response]\n" + json.dumps(invalid) in result, result

    result = await call(json.dumps(reply), status=202)
    assert result.startswith("MCP HTTP 202 acknowledgement. No tool result content."), result
    result = await call(json.dumps(reply), truncated=True)
    assert "No confirmed tool result content." in result.splitlines()[0] and "[HTTP response body truncated]" in result
    partial = await call(sse.rstrip() + "\r\n", content_type="text/event-stream")
    assert "No confirmed tool result content." in partial.splitlines()[0], partial


async def check_exact_mcp_copy():
    url = "http://127.0.0.1:8123/measurements"
    servers = [{"name": "measurements", "url": url, "transport": "streamable-http"}]
    workspace = "/workspace"
    filename = "readings/measurement.txt"
    path = f"{workspace}/{filename}"
    instruction = ("Invoke the tool called `latest` on MCP server `measurements`. "
                   f"Copy the tool output unchanged to `{filename}`.")
    assert exact_copy_contract(instruction, workspace, servers) == (url, "latest", path)
    for unsupported in (
        instruction.replace(filename, "../measurement.txt"),
        instruction.replace(filename, "/tmp/measurement.txt"),
        instruction.replace("Copy the tool output unchanged", "Summarize the tool output"),
        instruction + " Also write `report.md`.",
        instruction + " Append the units.",
        instruction.replace("`measurements`", "`unknown`"),
        ("Invoke the tool called `latest` on MCP server `measurements`. "
         f"Using the tool response, write `{filename}` with exactly three decimal places."),
    ):
        assert exact_copy_contract(unsupported, workspace, servers) is None, unsupported

    original = "  读数 4.25\r\n"
    files = {}
    request = {"jsonrpc": "2.0", "id": 41, "method": "tools/call", "params": {"name": "latest"}}

    def response(text=original, rpc_id=41, **fields):
        payload = {"jsonrpc": "2.0", "id": rpc_id, "result": {
            "content": [{"type": "text", "text": text}], **fields,
        }}
        body = f"event: message\ndata: {json.dumps(payload)}\n\n".encode()
        return {"ok": True, "status": 200, "headers": {"Content-Type": "text/event-stream"},
                "body_b64": base64.b64encode(body).decode()}

    async def exec_stub(command, timeout):
        if command == "overwrite with model confirmation":
            files[path] = b"File written successfully."
        return {"ok": True, "output": ""}

    async def write_stub(target, data, append=False):
        assert target == path and not append
        files[target] = data
        return {"ok": True}

    http = AsyncMock()
    transport = SimpleNamespace(http=http, exec=exec_stub, write_file=write_stub,
                                read_file=AsyncMock(side_effect=files.get))
    calls = [
        {"id": "read", "name": "mcp_call", "arguments": {"url": url, "body": json.dumps(request)}},
        {"id": "write", "name": "write_file", "arguments": {"path": filename, "content": "Result copied."}},
        {"id": "exec", "name": "exec", "arguments": {"command": "overwrite with model confirmation"}},
        {"id": "finish", "name": "finish", "arguments": {"final_message": "The measurement is saved."}},
    ]
    model = SimpleNamespace(chat=AsyncMock(return_value={"tool_calls": calls}))
    harness = Harness(transport, model, instruction, workdir=workspace, mcp_servers=servers)
    with patch.object(harness.guard, "run", AsyncMock(return_value=("PASS", ""))):
        for invalid in (
            response(rpc_id="41"), response(structuredContent={"unit": "m"}),
            response(isError=True), {**response(), "truncated": True}, {**response(), "status": 202},
            response(content=[{"type": "text", "text": original}, {"type": "image", "data": "AA=="}]),
        ):
            http.return_value = invalid
            await harness._do(calls[0])
            assert not files, files

        http.return_value = response()
        await harness._do({**calls[0], "arguments": {**calls[0]["arguments"], "url": url + "/another"}})
        assert not files, files
        assert await harness.run() == "The measurement is saved."
        mcp_tools = model.chat.call_args.kwargs["tools"]
        mcp_schema = next(tool for tool in mcp_tools if tool["name"] == "mcp_call")
        assert "output_path" in mcp_schema["parameters"]["properties"]
        assert files[path] == original.encode(), files
        assert "managed by the exact MCP copy" in await harness._do(calls[1])

        http.return_value = response("A conflicting measurement.")
        assert "conflicting values" in await harness._do(calls[0])
        assert files[path] == original.encode(), files

    files.clear()
    staged = Harness(transport, model, f"Save `{filename}` after processing the measurements.",
                     workdir=workspace, mcp_servers=servers)
    http.return_value = response()
    assert "verbatim" not in await staged._do(calls[0])
    assert not files, files
    direct = {**calls[0], "arguments": {**calls[0]["arguments"], "output_path": filename}}
    assert "Saved the MCP tool result verbatim" in await staged._do(direct)
    assert files[path] == original.encode()
    await staged._do({**calls[1], "arguments": {"path": path, "content": "Adjusted measurement."}})
    assert files[path] == b"Adjusted measurement."


def tool(call_id, name, **arguments):
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


FIRST_TURN = [
    {"type": "thinking", "thinking": "Inspect the workspace.", "signature": "stub-signature"},
    {"type": "redacted_thinking", "data": "c3R1Yi1yZWRhY3RlZA=="},
    {"type": "text", "text": "I will inspect the workspace."},
    tool("toolu_inspect", "exec", command="ls"),
    tool("toolu_calculate", "run_python", code=PYTHON_SOURCE, timeout_sec=19),
    tool("toolu_bad_timeout", "run_python", code=PYTHON_SOURCE, timeout_sec=7.5),
    tool("toolu_early_finish", "finish", final_message="No note yet."),
    tool("toolu_extra_finish", "finish", final_message="Still no note."),
]


class MessagesStub:
    def __init__(self):
        self.requests = {"positive": 0, "cancel": 0, "reject": 0}
        self.in_flight = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.failures = []

    async def handle(self, reader, writer):
        headers = (await reader.readuntil(b"\r\n\r\n")).decode("ascii").split("\r\n")
        fields = {}
        for line in filter(None, headers[1:]):
            name, value = line.split(":", 1)
            fields[name.lower()] = value.strip()
        request = json.loads(await reader.readexactly(int(fields["content-length"])))
        status = 200
        try:
            assert headers[0] == "POST /v1/messages HTTP/1.1", headers[0]
            assert fields.get("x-api-key") == "offline-smoke", fields
            assert request["model"] == MODEL, request["model"]
            python_tool = next(tool for tool in request["tools"] if tool["name"] == "run_python")
            assert python_tool["input_schema"]["required"] == ["code"], python_tool
            assert python_tool["input_schema"]["properties"]["timeout_sec"]["type"] == "integer", python_tool
            scenario = next(name for name in self.requests if f"[{name}]" in
                            request["messages"][0]["content"][0]["text"])
            self.requests[scenario] += 1
            if scenario == "cancel":
                self.in_flight.set()
                await reader.read()
                self.cancelled.set()
                writer.close()
                await writer.wait_closed()
                return
            if scenario == "reject":
                status, payload = 400, {"error": "synthetic invalid request"}
            else:
                payload = {"content": self.positive_turn(request["messages"]), "usage": USAGE}
        except (AssertionError, IndexError, KeyError, StopIteration, TypeError) as error:
            self.failures.append(repr(error))
            status, payload = 400, {"error": f"stub assertion failed: {error}"}
        body = json.dumps(payload).encode()
        reason = "OK" if status == 200 else "Bad Request"
        response_headers = (f"HTTP/1.1 {status} {reason}\r\n"
                            "Content-Type: application/json\r\n"
                            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n")
        writer.write(response_headers.encode() + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    def positive_turn(self, messages):
        if self.requests["positive"] == 1:
            return FIRST_TURN
        assert self.requests["positive"] == 2, "model called after successful finish"
        assert messages[-2] == {"role": "assistant", "content": FIRST_TURN}, messages[-2]
        assert messages[-1]["role"] == "user", messages[-1]
        results = messages[-1]["content"]
        assert [block["tool_use_id"] for block in results] == [
            "toolu_inspect", "toolu_calculate", "toolu_bad_timeout", "toolu_early_finish", "toolu_extra_finish"
        ], results
        assert all(block["type"] == "tool_result" for block in results), results
        assert results[0]["content"] == "empty workspace", results
        assert results[1]["content"] == f"{PYTHON_LITERAL}\n6\n", results
        assert "timeout_sec must be an integer" in results[2]["content"], results
        assert "REFUSED" in results[3]["content"], results
        assert results[4]["content"], results
        return [tool("toolu_write", "write_file", path=DELIVERABLE, content=DOCUMENT.decode()),
                tool("toolu_finish", "finish", final_message=SUMMARY)]


async def exchange(url, scenario, stub, timeout=60):
    files = {}
    frames = []
    guards = []
    async with websockets.connect(url, ping_interval=None, proxy=None) as ws:
        await ws.send(json.dumps({
            "type": "task", "protocol": 1, "session": scenario,
            "instruction": f"[{scenario}] Write a short note to `{DELIVERABLE}`.",
            "workdir": "/app", "limits": {"agent_timeout_sec": timeout}, "mcp_servers": [],
        }))
        while True:
            frame = json.loads(await ws.recv())
            frames.append(frame)
            kind = frame["type"]
            if kind in {"done", "error"}:
                break
            if kind not in {"exec", "write_file"}:
                continue
            reply = {"type": "result", "id": frame["id"], "ok": True}
            if kind == "write_file":
                data = files[frame["path"]] = base64.b64decode(frame["content_b64"], validate=True)
                reply["size"] = len(data)
            else:
                command = frame["command"]
                reply["exit_code"] = 0
                if "--spec" in command:
                    passed = files.get(DELIVERABLE) == DOCUMENT
                    guards.append(passed)
                    reply["output"] = "RESULT: PASS\n" if passed else "RESULT: FAIL\nmissing note\n"
                elif command.startswith("python3 -c "):
                    args = shlex.split(command)
                    assert len(args) == 3 and frame["timeout_sec"] == 19, frame
                    assert base64.b64encode(PYTHON_SOURCE.encode()).decode() in args[-1], frame
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, "-c", args[-1], stdout=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await process.communicate()
                    assert process.returncode == 0, frame
                    reply["output"] = stdout.decode()
                else:
                    reply["output"] = "empty workspace"
            await ws.send(json.dumps(reply))
            if scenario == "cancel":
                assert kind == "exec", frame
                await stub.in_flight.wait()
                await ws.send(json.dumps({"type": "cancel", "reason": "timeout"}))
    return frames, files, guards


def serve_port():
    if "PLE_SMOKE_PORT" in os.environ:
        return int(os.environ["PLE_SMOKE_PORT"])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def main():
    check_contracts()
    await check_python_output()
    await check_mcp_results()
    await check_exact_mcp_copy()
    stub = MessagesStub()
    async with await asyncio.start_server(stub.handle, "127.0.0.1", 0) as server:
        stub_port = server.sockets[0].getsockname()[1]
        port = serve_port()
        url = f"ws://127.0.0.1:{port}"
        # The stub is loopback-only. Keep host proxy settings out of this child
        # since httpx initializes configured proxy transports even for NO_PROXY hosts.
        env = {key: value for key, value in os.environ.items() if not key.lower().endswith("_proxy")}
        env.update(PORT=str(port), MODEL_API=f"google-cloud/{MODEL}", MODEL_NAME=MODEL,
                   ANTHROPIC_BASE_URL=f"http://127.0.0.1:{stub_port}", ANTHROPIC_API_KEY="offline-smoke")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "serve.py", cwd=REPO, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            async with asyncio.timeout(15):
                startup = await proc.stdout.readline()
                assert f"listening on 0.0.0.0:{port}" in startup.decode(), startup

                frames, files, guards = await exchange(url, "positive", stub, timeout=None)
                assert not stub.failures, stub.failures
                assert guards == [False, True], guards
                assert files[DELIVERABLE] == DOCUMENT, files.keys()
                assert sum(frame.get("command", "").startswith("python3 -c ") for frame in frames) == 1
                assert frames[-1] == {"type": "done", "final_message": SUMMARY}, frames[-1]
                usage = {"type": "usage", "model": MODEL, "input_tokens": 37,
                         "output_tokens": 23, "cache_read_tokens": 19}
                assert [frame for frame in frames if frame["type"] == "usage"] == [usage, usage], frames

                cancelled, _, _ = await exchange(url, "cancel", stub)
                assert cancelled[-1]["type"] == "done", cancelled[-1]
                assert "cancel" in cancelled[-1]["final_message"].lower(), cancelled[-1]
                await stub.cancelled.wait()

                rejected, _, _ = await exchange(url, "reject", stub)
                assert rejected[-1]["type"] == "error" and "HTTP 400" in rejected[-1]["message"], rejected[-1]
                assert stub.requests == {"positive": 2, "cancel": 1, "reject": 1}, stub.requests
                assert not stub.failures, stub.failures
        finally:
            if proc.returncode is None:
                proc.terminate()
            output, _ = await proc.communicate()
            if output:
                print(output.decode(errors="replace").rstrip(), file=sys.stderr)
    print("PROTOCOL SMOKE: PASS (output contracts, Python forwarding and save, MCP results, native turns, guard retry, cancel, HTTP 400)")


if __name__ == "__main__":
    asyncio.run(main())
