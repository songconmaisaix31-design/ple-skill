"""Offline controls for one context-recovery attempt through Harness and ModelClient.

Only the HTTP model server is scripted. Programs, writes, reads, and structural
checks run in temporary task workspaces through LocalTransport.
"""

import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skillkit.harness import Harness
from skillkit.model import ModelClient
from skillkit.transport import LocalTransport


TARGET = "output/total.json"
TASK = ("Read the integer entries in `inputs/entries.txt`. Save their sum in the "
        "JSON field total in `output/total.json`.")
PARTIAL = "work/running-total.txt"
HISTORY_MARK = "intermediate-observation"
PROGRAM = f"""from pathlib import Path
values = map(int, Path('inputs/entries.txt').read_text().split())
partial = Path({PARTIAL!r})
partial.parent.mkdir(exist_ok=True)
with partial.open('x') as stream:
    stream.write(str(sum(values)))
print({HISTORY_MARK!r} * 300)
"""
OVERFLOW = {"code": 400, "type": "exceed_context_size_error", "n_prompt_tokens": 16700,
            "n_ctx": 16384, "message": "request (16700 tokens) exceeds the available context "
                                       "size (16384 tokens), try increasing it"}


def reply(*calls):
    wire_calls = [{"id": call_id, "type": "function",
                   "function": {"name": name, "arguments": json.dumps(arguments)}}
                  for call_id, name, arguments in calls]
    return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": wire_calls,
    }}], "usage": {"prompt_tokens": 12, "completion_tokens": 4}})


def reject(detail=OVERFLOW, status=400):
    return httpx.Response(status, json={"error": detail})


OPENING = reply(("compute", "run_python", {"code": PROGRAM}),
                ("check", "read_file", {"path": PARTIAL}))
FIND_PARTIAL = reply(("inspect", "exec", {"command": "ls -1 work"}))
FINISH = reply(("finish", "finish", {"final_message": "Saved the checked total in output/total.json."}))


def read_found_file(messages):
    filename = messages[-1]["content"].strip()
    assert filename == Path(PARTIAL).name
    return reply(("reread", "read_file", {"path": "work/" + filename}))


def save_observed_total(messages):
    total = int(messages[-1]["content"])
    return reply(("write", "write_file", {"path": TARGET, "content": json.dumps({"total": total})}))


def check_sequence(messages):
    """The wire messages must answer every requested tool exactly once, in order."""
    pending = []
    for message in messages:
        if message["role"] == "tool":
            assert pending and pending.pop(0) == message["tool_call_id"], message
        else:
            assert not pending, pending
            pending = [call["id"] for call in message.get("tool_calls", [])]
    assert not pending, pending


async def run_case(name, responses, *, enabled=True, reset=False, delivered=False, initial_error=False):
    bodies = []

    def serve(request):
        body = json.loads(request.content)
        index = len(bodies)
        bodies.append(body)
        if index >= len(responses):
            raise RuntimeError("unexpected model call in control " + name)
        action = responses[index]
        return action(body["messages"]) if callable(action) else action

    # Reuse the production request serializer and status handling, with no network.
    client_type = httpx.AsyncClient
    stub = httpx.MockTransport(serve)

    def local_client(**options):
        return client_type(transport=stub, **options)

    with TemporaryDirectory(prefix="context-control-") as directory:
        work = Path(directory)
        (work / "inputs").mkdir()
        (work / "inputs/entries.txt").write_text("4\n13\n8\n", encoding="utf-8")
        (work / "task.md").write_text(TASK, encoding="utf-8")
        model = ModelClient("control", "http://fixture.invalid/v1", "", max_tokens=8000)
        harness = Harness(LocalTransport(work), model, TASK, workdir=directory)
        with patch.dict(os.environ), patch("skillkit.model.httpx.AsyncClient", local_client):
            os.environ.pop("PLE_RECOVER_CONTEXT_ONCE", None)
            os.environ.pop("PLE_MASK_OLD_TOOL_RESULTS", None)
            if enabled:
                os.environ["PLE_RECOVER_CONTEXT_ONCE"] = "1"
            try:
                final = await harness.run(timeout_sec=30)
            except RuntimeError as exc:
                assert initial_error and str(exc).startswith("HTTP 400:"), (name, exc)
            else:
                assert not initial_error, name
                assert ("Saved the checked total" in final) == delivered, (name, final)
                assert ("Structural checks: FAIL" in final) == (not delivered), (name, final)

        assert len(bodies) == len(responses), (name, len(bodies), len(responses))
        envelope = {k: v for k, v in bodies[0].items() if k != "messages"}
        system_message = bodies[0]["messages"][0]
        for body in bodies:
            assert {k: v for k, v in body.items() if k != "messages"} == envelope, name
            assert body["messages"][0] == system_message, name
            check_sequence(body["messages"])
        expected_steps = sum(callable(action) or action.is_success for action in responses)
        assert harness.steps == expected_steps and model.usage["input_tokens"] == 12 * expected_steps, name
        assert (work / TARGET).is_file() == delivered, name
        if len(bodies) >= 2:
            attempted = bodies[1]["messages"]
            assert [m["role"] for m in attempted] == ["system", "user", "assistant", "tool", "tool"]
            assert HISTORY_MARK * 100 in attempted[-2]["content"] and attempted[-1]["content"] == "25"
            assert (work / PARTIAL).read_text() == "25"
        if reset:
            fresh = bodies[2]["messages"]
            assert [m["role"] for m in fresh] == ["system", "user"], (name, fresh)
            assert TASK in fresh[1]["content"] and len(fresh[1]["content"]) < len(TASK) + 400
            assert len(json.dumps(fresh)) < len(json.dumps(attempted))
            for body in bodies[2:]:
                assert body["messages"][:2] == fresh and HISTORY_MARK not in json.dumps(body), name
        if delivered:
            assert json.loads((work / TARGET).read_text()) == {"total": 25}
            guard, _ = await harness.guard.run()
            assert guard == "PASS", (name, guard)
        return {"calls": len(bodies), "successful_turns": harness.steps, "file_verified": delivered}


async def main():
    cases = {}
    cases["recovery"] = await run_case("recovery", [OPENING, reject(), FIND_PARTIAL,
                                        read_found_file, save_observed_total, FINISH],
                                       reset=True, delivered=True)
    cases["default_off"] = await run_case("default_off", [OPENING, reject()], enabled=False)
    cases["initial_rejection"] = await run_case("initial_rejection", [reject()], initial_error=True)
    cases["second_rejection"] = await run_case("second_rejection", [OPENING, reject(), reject()],
                                                reset=True)
    cases["later_rejection"] = await run_case("later_rejection", [OPENING, reject(), FIND_PARTIAL,
                                              reject()], reset=True)
    ambiguous = {"code": 400, "type": "invalid_request_error", "message": OVERFLOW["message"]}
    for name, refusal in (
        ("unrelated_400", reject({"code": 400, "type": "invalid_request_error",
                                  "message": "invalid tool schema"})),
        ("message_only", reject(ambiguous)),
        ("inconsistent_counts", reject({**OVERFLOW, "n_prompt_tokens": 12})),
        ("wrong_status", reject(OVERFLOW, status=403)),
        ("truncated_body", httpx.Response(400, text='{"error":{"type":"exceed_context_size_error"')),
    ):
        cases[name] = await run_case(name, [OPENING, refusal])
    print(json.dumps(cases, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
