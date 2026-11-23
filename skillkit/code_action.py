"""Optional first-action experiment for small, explicitly declared data packages."""

import ast
import asyncio
import json
import os
import posixpath
import re

from .model import PYTHON_SOURCE_MAX, TOOLS
from .transport import WSTransport


TOKEN_BUDGET = 1600
MAX_INFERENCE_SECONDS = 390
EXEC_SECONDS = 30
GUARD_SECONDS = 10
FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)\n```", re.IGNORECASE | re.DOTALL)
FINISH_REASONS = {"stop", "tool_calls", "length", "content_filter", "stop_sequence", "end_turn",
                  "tool_use", "max_tokens", "completed", "incomplete", "max_output_tokens", "refusal"}
INCOMPLETE_REASONS = {"length", "max_tokens", "incomplete", "max_output_tokens"}
PYTHON_TOOL = next(tool for tool in TOOLS if tool["name"] == "run_python")
TRACEBACK_FRAME = re.compile(r'^  File "([^"\n]+)", line ([1-9][0-9]{0,6})(?:, in [^\n]+)?$', re.MULTILINE)
SOURCE_EXCERPT_LIMIT = 800

OBJECTIVE = """Write one short Python program for the stated data task. Use the Python standard
library. Read the original named input files from the task workspace. Follow the requested method,
calculate the values or perform the transformation, and check any constraints before saving. Create
parent directories as needed and write every required deliverable to its declared path under the
task workspace. Match the requested fields, formats, and units. Print only a short execution summary.
Do not invent missing data or rely on network or external services.
"""
FORMAT = {
    "text": "Return only the complete Python program, either plain source or one Python code fence.",
    "native": "Submit only one run_python call with the complete Python program as code. Leave output_path unset.",
}


def enabled_mode(harness, package_inputs):
    mode = os.environ.get("PLE_CODE_ACTION", "0").strip().lower()
    mode = "text" if mode == "1" else mode
    if (mode not in FORMAT or not package_inputs or harness.mcp
            or not isinstance(harness.t, WSTransport) or harness.t.cancelled.is_set()
            or (mode == "native" and getattr(harness.model, "mode", None) != "openai")):
        return None
    root = posixpath.normpath(harness.workdir).rstrip("/") + "/"
    outputs = harness.spec.get("required_files") or []
    if not 2 <= len(outputs) <= 3 or not all(
        posixpath.normpath(posixpath.join(root, path)).startswith(root) for path in outputs
    ):
        return None
    return mode


def program_from(response, mode):
    calls = response.get("tool_calls") or []
    if mode == "native":
        if len(calls) != 1 or not isinstance(calls[0], dict) or calls[0].get("name") != "run_python":
            return None, "invalid_native"
        arguments = calls[0].get("arguments")
        if not isinstance(arguments, dict) or "output_path" in arguments:
            return None, "invalid_native"
        source = arguments.get("code")
    else:
        if calls:
            return None, "unexpected_tool"
        source = response.get("content")

    if not isinstance(source, str) or not source.strip():
        return None, "empty"
    if len(source) > PYTHON_SOURCE_MAX or "\x00" in source:
        return None, "oversized"
    source = source.strip()
    if mode == "text" and (match := FENCE.fullmatch(source)):
        source = match[1]
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None, "invalid_syntax"
    if not any(isinstance(node.value, ast.Call) if isinstance(node, ast.Expr)
               else not isinstance(node, ast.Pass) for node in tree.body):
        return None, "non_program"
    return source, "valid"


def repair_source_excerpt(program, diagnostics):
    """Locate a line in this submitted program using the final traceback only."""
    header = "Traceback (most recent call last):\n"
    _, found, trace = ("\n" + diagnostics).rpartition("\n" + header)
    trace = trace.rstrip("\n")
    if not found or not trace.startswith('  File '):
        return ""
    # Ignore free-form output and outer call sites when the inner frame belongs
    # to the task's libraries or to some other dynamically constructed program.
    frames = list(TRACEBACK_FRAME.finditer(trace))
    if (not frames or frames[-1][1] != "<run_python>"
            or "\n  File " in trace[frames[-1].end():]):
        return ""
    if not re.fullmatch(r"[A-Za-z_][\w.]*(?::.*)?", trace.rsplit("\n", 1)[-1]):
        return ""
    line_number = int(frames[-1][2])
    lines = program.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if line_number > len(lines):
        return ""
    indices = range(max(1, line_number - 2), min(len(lines), line_number + 2) + 1)
    title = f"\n\nFirst program source near traceback line {line_number}:\n"
    width = (SOURCE_EXCERPT_LIMIT - len(title) + 1) // len(indices) - 1
    excerpt = []
    for index in indices:
        row = f"{index}: {lines[index - 1]}"
        excerpt.append(row if len(row) <= width else row[:width - 1] + "…")
    return title + "\n".join(excerpt)


async def first_action(harness, mode, messages, on_usage, on_log, work_deadline, clock):
    start = clock()
    model_budget = (MAX_INFERENCE_SECONDS if work_deadline is None
                    else min(MAX_INFERENCE_SECONDS, 0.68 * (work_deadline - start)))
    if model_budget < 5:
        return ""

    event = {"mode": mode, "classification": "provider_error", "output_tokens": None,
             "finish_reason": "unknown", "exec_exit_status": None}
    try:
        try:
            async with asyncio.timeout(model_budget):
                response = await harness.model.chat(
                    messages, OBJECTIVE + FORMAT[mode],
                    tools=[PYTHON_TOOL] if mode == "native" else [],
                    max_tokens=TOKEN_BUDGET, tool_choice="required" if mode == "native" else None,
                )
        except TimeoutError:
            event["classification"] = "timeout"
            return "The first Python attempt ran out of inference time. Use the normal tools."
        except (OSError, RuntimeError, TypeError, ValueError):
            return "The first Python request could not run. Use the normal tools."

        harness.steps += 1
        usage = response.get("usage") or {}
        if on_usage:
            on_usage(usage)
        output_tokens = usage.get("output_tokens")
        if type(output_tokens) is int and 0 <= output_tokens <= 1_000_000:
            event["output_tokens"] = output_tokens
        finish_reason = response.get("finish_reason")
        if isinstance(finish_reason, str) and finish_reason in FINISH_REASONS:
            event["finish_reason"] = finish_reason
        if event["finish_reason"] in INCOMPLETE_REASONS:
            event["classification"] = "truncated"
            return "The first Python program was incomplete and was not run. Use the normal tools."
        if event["finish_reason"] in {"refusal", "content_filter"}:
            event["classification"] = "non_program"
            return "The first reply did not contain a Python program. Use the normal tools."

        program, event["classification"] = program_from(response, mode)
        if not program:
            return "The first Python reply was not a complete program. Use the normal tools."

        execution_limit = EXEC_SECONDS
        if work_deadline is not None:
            execution_limit = min(execution_limit, int(work_deadline - clock() - GUARD_SECONDS))
        if execution_limit < 2:
            event["classification"] = "timeout"
            return "No task time was left to run the first program safely. Use the normal tools."
        execution = {}

        def record_execution(result):
            detail = result.get("output") or ""
            execution.update(ok=result.get("ok"), timed_out=result.get("timed_out"),
                             truncated=result.get("truncated"), exit_code=result.get("exit_code"),
                             detail=detail[-900:] if isinstance(detail, str) else "")

        try:
            await harness._do({"name": "run_python", "arguments": {
                "code": program, "timeout_sec": execution_limit,
            }}, on_execution=record_execution)
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        exit_code = execution.get("exit_code")
        if type(exit_code) is int and -255 <= exit_code <= 255:
            event["exec_exit_status"] = exit_code
        if execution.get("timed_out"):
            event["classification"] = "exec_timeout"
        elif execution.get("truncated"):
            event["classification"] = "exec_truncated"
        elif not execution.get("ok") or exit_code != 0:
            event["classification"] = "exec_failed"
        if event["classification"] != "valid":
            observation = "The first Python program did not run cleanly. Inspect any outputs and use the normal tools."
            if detail := execution.get("detail"):
                observation += "\n\nSandbox diagnostics, for debugging only:\n" + detail
                if (event["classification"] == "exec_failed" and type(exit_code) is int and exit_code != 0
                        and os.environ.get("PLE_REPAIR_CONTEXT") == "source"):
                    observation += repair_source_excerpt(program, detail)
            return observation

        try:
            async with asyncio.timeout(GUARD_SECONDS):
                status, report = await harness._check_deliverable()
        except TimeoutError:
            event["classification"] = "guard_timeout"
            return "The first program ran, but structural checks took too long. Verify the files with tools."
        if status not in {"PASS", "WARN"}:
            event["classification"] = "guard_failed"
            return ("The files from the first program did not pass structural checks. Inspect and fix them.\n\n"
                    + report[-700:])
        event["classification"] = "verified"
        return ("The first program ran and the declared paths passed structural checks. Verify the written "
                "engineering values and constraints with tools, fix any issues, then call finish.")
    except asyncio.CancelledError:
        event["classification"] = "cancelled"
        raise
    finally:
        event["millis"] = round((clock() - start) * 1000)
        on_log("code_action " + json.dumps(event, separators=(",", ":")))
