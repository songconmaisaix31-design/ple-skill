"""Regression checks for the checksum-pinned controlled repair provider."""

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_design_regression as runner
from skillkit.code_action import program_from, repair_source_excerpt


class LiveStub:
    model = "gemma-4-26b"
    mode = "openai"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, system, tools=None, **kwargs):
        self.calls += 1
        return {"content": "delegated", "tool_calls": [], "usage": {}, "finish_reason": "stop"}


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
        finally:
            runner.CONTROLLED_RELEASE_SEC = old_release


def main():
    source = runner.controlled_program()
    diagnostics = ('Traceback (most recent call last):\n'
                   '  File "<run_python>", line 81, in <module>\n'
                   "TypeError: 'int' object is not subscriptable\n")
    excerpt = repair_source_excerpt(source, diagnostics)
    assert excerpt.startswith("\n\nFirst program source near traceback line 81:\n")
    assert "81: " in excerpt and len(excerpt) <= 800
    assert repair_source_excerpt(source, "TypeError: no trusted frame") == ""
    asyncio.run(check_provider())
    print("controlled replay provider, source excerpt and delegation verified")


if __name__ == "__main__":
    main()

