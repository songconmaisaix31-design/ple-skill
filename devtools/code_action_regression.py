#!/usr/bin/env python3
"""Test opt-in CodeAct routing and model payloads without making network requests."""

import asyncio
import base64
import json
import os
from pathlib import Path
import shlex
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skillkit import code_action
from skillkit.harness import Harness
from skillkit.model import ModelClient, TOOLS
from skillkit.transport import LocalTransport, WSTransport


TASK = "Read `inputs/source.json`. Save `output/results.csv` and `output/metadata.json`."
SOURCE = "import json\nprint('calculation complete')"
DIAGNOSTIC = "Last sandbox diagnostic"


class RelayFixture:
    def __init__(self, outcome, extra_file=False):
        self.transport = WSTransport(self)
        self.outcome = outcome
        self.extra_file = extra_file
        self.reads = []
        self.python_calls = 0

    async def send(self, payload):
        frame = json.loads(payload)
        reply = {"type": "result", "id": frame["id"], "ok": True}
        if frame["type"] == "read_file":
            self.reads.append(frame["path"])
            reply["content_b64"] = base64.b64encode(b'{"value": 4}').decode()
        elif frame["type"] == "exec":
            command = frame["command"]
            reply.update(exit_code=0, output="")
            if command.startswith("echo '--- task.md ---'"):
                reply["output"] = "--- task.md ---\n\n--- tree ---\n./inputs/source.json\n"
                if self.extra_file:
                    reply["output"] += "./reference.pdf\n"
            elif "--spec" in command:
                reply["output"] = "RESULT: PASS (0 hard / 0 soft)"
            else:
                args = shlex.split(command)
                assert len(args) == 3 and args[:2] == ["python3", "-c"], args
                assert base64.b64encode(SOURCE.encode()).decode() in args[-1], args
                assert 2 <= frame["timeout_sec"] <= code_action.EXEC_SECONDS, frame
                self.python_calls += 1
                if self.outcome == "exec_failed":
                    reply.update(ok=False, exit_code=7, output="x" * 2000 + DIAGNOSTIC)
        await self.transport.dispatch(reply)


class ModelFixture:
    mode = "openai"

    def __init__(self, requested, outcome, eligible):
        self.requested = requested
        self.outcome = outcome
        self.eligible = eligible
        self.calls = 0

    async def chat(self, messages, system, tools=None, **options):
        self.calls += 1
        if self.calls > 1 or not self.eligible:
            assert tools is None and not options, options
            if not self.eligible:
                assert "Non-negotiables:" in system and "ROUTED SKILL" in system
                assert "Input already obtained" not in messages[0]["content"]
            if self.outcome == "exec_failed":
                observation = messages[-1]["content"]
                assert DIAGNOSTIC in observation and len(observation) < 1200
            return {"tool_calls": [{"name": "finish", "id": "f",
                                    "arguments": {"final_message": "Reviewed with tools."}}], "usage": {}}
        assert options["max_tokens"] == code_action.TOKEN_BUDGET
        assert '"value": 4' in messages[0]["content"] and "output/metadata.json" in messages[0]["content"]
        usage = {"output_tokens": 63}
        if self.requested == "native":
            assert [tool["name"] for tool in tools] == ["run_python"], tools
            assert options["tool_choice"] == "required", options
            return {"tool_calls": [{"name": "run_python", "arguments": {"code": SOURCE}}],
                    "usage": usage, "finish_reason": "tool_calls"}
        assert tools == [] and options["tool_choice"] is None, options
        content = f"```python\n{SOURCE}\n```"
        if self.outcome == "invalid_syntax":
            content = "Here is the code.\n" + content
        return {"content": content, "usage": usage,
                "finish_reason": "length" if self.outcome == "truncated" else "stop"}


async def check_run(setting, outcome="verified", extra_file=False):
    eligible = setting in {"1", "text", "native"} and not extra_file
    relay = RelayFixture(outcome, extra_file)
    model = ModelFixture(setting, outcome, eligible)
    harness = Harness(relay.transport, model, TASK)
    logs, usage = [], []
    with patch.dict(os.environ):
        if setting is None:
            os.environ.pop("PLE_CODE_ACTION", None)
        else:
            os.environ["PLE_CODE_ACTION"] = setting
        result = await harness.run(timeout_sec=100, on_log=logs.append, on_usage=usage.append)
    assert result == "Reviewed with tools.", (result, logs)
    events = [json.loads(line.removeprefix("code_action ")) for line in logs if line.startswith("code_action ")]
    if not eligible:
        assert not events and not relay.reads and not relay.python_calls and model.calls == 1, (logs, relay.reads)
        return
    assert model.calls == 2 and relay.reads == ["inputs/source.json"], (model.calls, relay.reads)
    assert len(events) == 1 and events[0]["classification"] == outcome, events
    assert events[0]["mode"] == ("native" if setting == "native" else "text"), events
    assert events[0]["output_tokens"] == 63 and usage[0] == {"output_tokens": 63}, (events, usage)
    assert events[0]["exec_exit_status"] == {"verified": 0, "exec_failed": 7}.get(outcome), events
    assert DIAGNOSTIC not in str(logs) and SOURCE not in str(logs), logs
    assert relay.python_calls == int(outcome in {"verified", "exec_failed"}), logs


async def check_model_payloads():
    recorded = []

    class HTTPFixture:
        status_code = 200

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **request):
            recorded.append(request["json"])
            return self

        def json(self):
            return {"choices": [{"finish_reason": "tool_calls"}], "stop_reason": "max_tokens",
                    "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}

    with patch("skillkit.model.httpx.AsyncClient", HTTPFixture):
        for mode, reason in [("anthropic", "max_tokens"), ("responses", "max_output_tokens"),
                             ("openai", "tool_calls")]:
            client = ModelClient("fixture", "http://localhost:1", "fixture", mode=mode, max_tokens=50)
            messages = [{"role": "user", "content": "One request."}]
            turn = await client.chat(messages, "System", tools=[], max_tokens=1600)
            payload = recorded[-1]
            key = "max_output_tokens" if mode == "responses" else "max_tokens"
            assert "tools" not in payload and "tool_choice" not in payload and payload[key] == 1600, payload
            assert turn["finish_reason"] == reason, turn
            await client.chat(messages, "System")
            assert len(recorded[-1]["tools"]) == len(TOOLS) and recorded[-1][key] == 50, recorded[-1]


async def main():
    for setting in (None, "0", "legacy", "1", "text", "native"):
        await check_run(setting)
    await check_run("text", extra_file=True)
    for outcome in ("invalid_syntax", "truncated", "exec_failed"):
        await check_run("text", outcome)
    with patch.dict(os.environ, {"PLE_CODE_ACTION": "text"}):
        assert code_action.enabled_mode(Harness(LocalTransport("/tmp"), None, TASK)) is None
        assert code_action.enabled_mode(Harness(WSTransport(None), None, TASK, mcp_servers=[{}])) is None
    await check_model_payloads()
    print("CODE ACTION REGRESSION: PASS (legacy prompt, guarded text/native, fallback, payloads)")


if __name__ == "__main__":
    asyncio.run(main())
