"""Regression checks for the checksum-pinned controlled repair provider."""

import asyncio
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_design_regression as runner
from design_regression import grade, prepare
from skillkit import code_action
from skillkit.code_action import program_from, repair_source_excerpt


class LiveStub:
    model = "gemma-4-26b"
    mode = "openai"

    def __init__(self, content="delegated", tool_calls=None):
        self.calls = 0
        self.content = content
        self.tool_calls = tool_calls or []
        self.last_tools = None
        self.last_kwargs = None

    async def chat(self, messages, system, tools=None, **kwargs):
        self.calls += 1
        self.last_tools, self.last_kwargs = tools, kwargs
        return {"content": self.content, "tool_calls": self.tool_calls,
                "usage": {}, "finish_reason": "stop"}


def check_executable_patch(source):
    encoded = base64.b64encode(source.encode()).decode()
    wrapper = f"import base64; exec(compile(base64.b64decode('{encoded}'), '<run_python>', 'exec'))"
    for variant, expected in (("l", 49), ("m", 54)):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "case"
            prepare(workspace, variant)
            result = subprocess.run([sys.executable, "-I", "-S", "-c", wrapper], cwd=workspace,
                                    timeout=10, capture_output=True, text=True)
            scored = grade(workspace, variant)
            assert result.returncode == 0 and scored["optimal"]
            assert scored["submitted_cost_cents"] == expected


async def check_provider():
    source = runner.controlled_program()
    assert hashlib.sha256(source.encode()).hexdigest() == runner.CONTROLLED_PROGRAM_SHA256
    clock = 0.0

    def elapsed():
        return clock

    with tempfile.TemporaryDirectory() as temporary:
        archive = runner.ModelIOArchive(Path(temporary) / "io.jsonl")
        live = LiveStub()
        old_release = runner.CONTROLLED_RELEASE_SEC
        runner.CONTROLLED_RELEASE_SEC = 0
        try:
            first_events, attempts = {}, []
            model = runner.ControlledFirstModel(live, source, elapsed, archive, attempts, first_events)
            response = await model.chat([{"role": "user", "content": "frozen"}], "system", tools=[])
            recovered, state = program_from(response, "text")
            assert state == "valid" and recovered == source and live.calls == 0
            delegated = await model.chat([{"role": "user", "content": "repair"}], "system")
            assert delegated["content"] == "delegated" and live.calls == 1
            assert first_events["first_model_output"]["scripted"] is True
            summary = archive.finish()
            assert summary == {"complete": True, "requests": 1, "omitted_records_or_fields": 0}
            records = [json.loads(line) for line in archive.path.read_text().splitlines()]
            assert records[0]["body"]["temperature"] == 0 and records[0]["body"]["seed"] == 17
            assert records[1]["scripted"] is True and records[2]["status"] == "complete"

            patch_archive = runner.ModelIOArchive(Path(temporary) / "patch.jsonl")
            patch_live = LiveStub('{"line":81,"replacement":"\'total_pump_units\': sum(combination),"}')
            patch_events, patch_attempts = {}, []
            patch_model = runner.ControlledPatchModel(
                patch_live, source, elapsed, patch_archive, patch_attempts, patch_events)
            await patch_model.chat([{"role": "user", "content": "frozen"}], "system", tools=[])
            patch_archive.request({"model": patch_live.model, "messages": [], "max_tokens": 96})
            repaired = await patch_model.chat([{"role": "user", "content": "repair"}], "system")
            assert repaired["content"] == "" and len(repaired["tool_calls"]) == 1
            assert repaired["tool_calls"][0]["name"] == "run_python"
            recovered = repaired["tool_calls"][0]["arguments"]["code"]
            assert "'total_pump_units': sum(combination)," in recovered
            check_executable_patch(recovered)
            assert patch_events["patch_application"]["accepted"] is True
            assert patch_live.calls == 1
            assert patch_archive.finish()["complete"] is True

            native_archive = runner.ModelIOArchive(Path(temporary) / "native.jsonl")
            native_live = LiveStub("", [{"id": "native-1", "name": "replace_line", "arguments": {
                "line": 81, "replacement": "'total_pump_units': sum(combination),",
            }}])
            native_events, native_attempts = {}, []
            native_model = runner.ControlledNativePatchModel(
                native_live, source, elapsed, native_archive, native_attempts, native_events)
            await native_model.chat([{"role": "user", "content": "frozen"}], "system", tools=[])
            native_archive.request({"model": native_live.model, "messages": [], "max_tokens": 96})
            native = await native_model.chat([{"role": "user", "content": "repair"}], "system")
            assert native["tool_calls"][0]["name"] == "run_python"
            assert native["tool_calls"][0]["id"] == "native-1"
            assert "sum(combination)" in native["tool_calls"][0]["arguments"]["code"]
            check_executable_patch(native["tool_calls"][0]["arguments"]["code"])
            assert native_live.last_tools == [runner.PATCH_TOOL]
            assert native_live.last_kwargs["tool_choice"] == "required"
            assert native_live.last_kwargs["max_tokens"] == 96
            assert native_events["patch_application"]["accepted"] is True
            assert native_archive.finish()["complete"] is True

            invalid_native = (
                [{"id": "bad-name", "name": "run_python", "arguments": {"line": 81, "replacement": "x = 1"}}],
                [
                    {"id": "one", "name": "replace_line", "arguments": {"line": 81, "replacement": "x = 1"}},
                    {"id": "two", "name": "replace_line", "arguments": {"line": 81, "replacement": "x = 2"}},
                ],
            )
            for index, tool_calls in enumerate(invalid_native):
                rejected_archive = runner.ModelIOArchive(Path(temporary) / f"native-rejected-{index}.jsonl")
                rejected_live = LiveStub("", tool_calls)
                rejected_events = {}
                rejected = runner.ControlledNativePatchModel(
                    rejected_live, source, elapsed, rejected_archive, [], rejected_events)
                await rejected.chat([{"role": "user", "content": "frozen"}], "system", tools=[])
                rejected_archive.request({"model": rejected_live.model, "messages": [], "max_tokens": 96})
                reply = await rejected.chat([{"role": "user", "content": "repair"}], "system")
                assert rejected_events["patch_application"]["accepted"] is False
                assert reply["tool_calls"] == tool_calls
                assert rejected_archive.finish()["complete"] is True
        finally:
            runner.CONTROLLED_RELEASE_SEC = old_release


async def check_repair_routing():
    source = runner.controlled_program()
    diagnostics = ('Traceback (most recent call last):\n'
                   '  File "<run_python>", line 81, in <module>\n'
                   "TypeError: 'int' object is not subscriptable\n")

    async def chat(*args, **kwargs):
        return {"content": source, "usage": {}, "finish_reason": "stop"}

    async def execute(call, on_execution):
        assert call["arguments"]["code"] == source
        on_execution({"ok": False, "exit_code": 1, "output": diagnostics})

    async def check():
        return "PASS", ""

    harness = SimpleNamespace(model=SimpleNamespace(chat=chat), steps=0,
                              _do=execute, _check_deliverable=check)
    with patch.dict("os.environ", {"PLE_REPAIR_CONTEXT": "source"}):
        observation = await code_action.first_action(
            harness, "text", [], None, lambda message: None, None, time.monotonic)
    assert observation.endswith(repair_source_excerpt(source, diagnostics))


def main():
    source = runner.controlled_program()
    diagnostics = ('Traceback (most recent call last):\n'
                   '  File "<run_python>", line 81, in <module>\n'
                   "TypeError: 'int' object is not subscriptable\n")
    excerpt = repair_source_excerpt(source, diagnostics)
    assert excerpt.startswith("\n\nFirst program source near traceback line 81:\n")
    assert "81: " in excerpt and len(excerpt) <= 800
    assert repair_source_excerpt(source, "TypeError: no trusted frame") == ""
    valid = '{"line":81,"replacement":"\'total_pump_units\': sum(combination),"}'
    repaired, event = runner.apply_constrained_patch(source, valid)
    assert repaired is not None and event["accepted"] is True
    invalid = (
        '{"line":80,"replacement":"x = 1"}',
        '```json\n{"line":81,"replacement":"x = 1"}\n```',
        '{"line":81,"replacement":"x = 1","extra":true}',
        '{"line":81,"replacement":"x = 1\\ny = 2"}',
        '{"line":81,"replacement":"if:"}',
    )
    for raw in invalid:
        transformed, rejected = runner.apply_constrained_patch(source, raw)
        assert transformed is None and rejected["accepted"] is False
    asyncio.run(check_repair_routing())
    asyncio.run(check_provider())
    print("controlled replay provider, source excerpt, patch guard and delegation verified")


if __name__ == "__main__":
    main()

