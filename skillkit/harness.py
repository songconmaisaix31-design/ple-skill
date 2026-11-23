#!/usr/bin/env python3
"""The agent loop.

Shape: spec first (the acceptance contract is written before the model sees
anything), skill routed second, one minimal complete deliverable early, then
guard-driven iteration until the guard passes or time runs out.
"""
import asyncio
import base64
import json
import re

from . import specgen, router
from .guard import Guard
from .model import PYTHON_SOURCE_MAX, PYTHON_TIMEOUT_DEFAULT, PYTHON_TIMEOUT_MAX
from .transport import quote_path

MAX_STEPS = 240
HARD_BUDGET = 0.94      # fraction of agent_timeout_sec we allow ourselves
WRAP_BUDGET = 0.80      # switch to "close it out" mode

NAMED_TEXT_INPUT = re.compile(
    r"(?<![\w./-])(?:\./)?(inputs?/(?:[\w-]+/)*[\w.-]+\.(?:json|csv|txt))"
    r"(?=$|[\s`\"'(),.;:])", re.IGNORECASE,
)

SYSTEM_BASE = """You are an agent harness solving one engineering task inside a sandboxed container.

You do not chat. You produce deliverables and put them at the exact path the task names.
The grader reads only file paths, names, formats and contents; a rubric judge also reads your
final_message. Nothing else you say counts.

Non-negotiables:
- Follow the task's explicit deliverable requirements. Use the inferred contract below as
  a checklist and verify its exact paths, filenames, column headers and required contents
  against the task instructions and relevant input documents.
- Work inside the task container with exec/run_python/read_file/write_file/mcp_call.
  python3 is present with python-docx, openpyxl, pandas, libreoffice and pdftotext.
- Read the task inputs before writing. Reconcile conflicting documents explicitly and say
  which one governs.
- Land a first complete, openable version of the deliverable early (by roughly step 10-20),
  even if values are rough, then rewrite it in place. Never let the clock expire with
  nothing on disk.
- Every number you assert must come from a document you actually read or a calculation you
  actually ran. Never invent a clause number, a section reference or a test result.
- Check all hard constraints before optimizing a design, and recheck them after changing it.
- Do not hard-code answers or branch on a task's identity. Solve the task in front of you.

Tool notes:
- exec keeps only filesystem state; cd and shell variables do not persist.
- Use run_python for multistep numerical calculations. Group related calculations in a
  short invocation and print the resulting quantities and checks you need for the deliverable.
- For a single explicit text deliverable, print its complete contents and set output_path
  in the first run_python calculation so the tool calculates and saves it in one call.
  When setting output_path, send any diagnostics to stderr.
- write_file creates parent directories. Use append for large files.
- Build docx/xlsx with python-docx/openpyxl scripts you write, then run them with exec.
"""


def _fmt_contract(spec):
    lines = []
    d = spec.get("deliverable")
    lines.append("deliverable path: " + (d or "(not stated in the instruction - read task.md, "
                                          "look for a house template, then state your choice)"))
    lines.append(f"delivery mode: {spec.get('mode')}")
    if spec.get("zip_required"):
        lines.append("required members: " + ", ".join(spec["zip_required"]))
    for name, cols in (spec.get("csv_headers") or {}).items():
        lines.append(f"{name} columns, exactly: " + ", ".join(cols))
    other = [n for n in (spec.get("all_named_files") or [])
             if n != d and n not in (spec.get("zip_required") or [])]
    if other:
        lines.append("also named in the instruction: " + ", ".join(other[:14]))
    if spec.get("confidence") == "low":
        lines.append("WARNING: the deliverable path was not stated. Establish it first "
                     "(cat task.md, look for a house template, follow 'Save it as ...').")
    return "\n".join(lines)


class Harness:
    def __init__(self, transport, model, instruction, workdir="/app",
                 limits=None, mcp_servers=None, log=None, spec_override=None):
        self.t = transport
        self.model = model
        self.instruction = instruction
        self.workdir = workdir or "/app"
        self.limits = limits or {}
        self.mcp = mcp_servers or []
        self.log = log or (lambda t: None)
        self.spec = spec_override or specgen.build(instruction)
        self.route = router.route(instruction, self.spec)
        self.guard = Guard(transport, workdir, self.spec, log=self.log)
        self.final = ""
        self.steps = 0
        self._since_guard = 99
        self._periodic_alerts = 0
        self._finish_refusals = 0
        self._ctx = router.load_context(self.route["domain"])

    # ---------- prompt ----------
    def _single_data_file(self):
        path = self.spec.get("deliverable") or ""
        return (
            path.lower().endswith((".json", ".csv", ".txt"))
            and len(self.spec.get("all_named_files") or []) <= 1
            and (self.spec.get("claimed_count") or 1) == 1
        )

    def _system(self, snapshot):
        single_data_file = self._single_data_file()
        if single_data_file:
            parts = [
                "Deliver the requested file in the task workspace. Use the file contents already "
                "supplied and read any other named inputs. For a calculation, call run_python "
                "with a short program that prints exactly the requested file contents. Set "
                "output_path to the destination so the tool calls write_file on successful completion. Verify the exact path, "
                "field names and units against the task, then call finish. "
                "Use the available tools directly and keep the response concise."
            ]
        else:
            parts = [SYSTEM_BASE]
        parts.append("\n=== ACCEPTANCE CONTRACT (auto-parsed from the instruction) ===\n"
                     + _fmt_contract(self.spec))
        if not single_data_file:
            parts.append(f"\n=== ROUTED SKILL: {self.route['domain']} / {self.route['family']} ===")
            for title, body in self._ctx:
                parts.append(f"\n--- {title} ---\n{body}")
        if self.mcp:
            urls = "\n".join(f"  {s.get('name')}: {s.get('url')} ({s.get('transport')})"
                             for s in self.mcp)
            parts.append("\n=== MCP SERVERS (reachable only through mcp_call) ===\n" + urls
                         + "\nFor Streamable HTTP, POST JSON-RPC initialize first. Send "
                         "notifications/initialized before tools/list or tools/call. Include "
                         "the returned Mcp-Session-Id header (if present) and set the "
                         "MCP-Protocol-Version header to the initialize result's protocolVersion "
                         "on subsequent requests. For SSE, read the JSON-RPC reply on the data lines.")
        parts.append("\n=== WORKSPACE SNAPSHOT (taken by the harness before you started) ===\n"
                     + snapshot)
        return "\n".join(parts)

    async def _snapshot(self):
        cmd = ("echo '--- task.md ---'; cat task.md 2>/dev/null | head -c 6000; "
               "echo; echo '--- tree ---'; ls -la; "
               "find . -maxdepth 3 -type f 2>/dev/null | head -120")
        r = await self.t.exec(cmd, 120)
        out = r.get("output", "")[:7000]
        # the real requirements often live in task.md, not the instruction
        if "--- task.md ---" in out:
            head = out.split("--- tree ---")[0]
            if len(head) > 120:
                merged = specgen.build(self.instruction, head)
                if merged.get("deliverable") or merged.get("all_named_files"):
                    self.spec = merged
                    self.guard.spec = dict(merged)
                    self.guard.spec.setdefault("deep", True)
        return out

    # ---------- tools ----------
    async def _save_python_output(self, path, execution):
        if not execution.get("ok") or execution.get("exit_code") != 0 or execution.get("timed_out"):
            return "[run_python] no file saved: execution did not complete successfully"
        if execution.get("truncated"):
            return "[run_python] no file saved: stdout was truncated"
        output = execution.get("output") or ""
        if not output.strip():
            return "[run_python] no file saved: stdout was empty"
        if path.lower().endswith(".json"):
            def reject_constant(token):
                raise ValueError(f"invalid JSON constant {token}")

            try:
                json.loads(output, parse_constant=reject_constant)
            except (ValueError, RecursionError):
                return "[run_python] no file saved: stdout is not valid JSON"

        data = output.encode()
        result = await self.t.write_file(path, data)
        if not result.get("ok"):
            return f"[run_python] write failed: {result.get('error', 'unknown error')}"
        self._since_guard = min(self._since_guard, 0)
        sample = output[:512]
        if len(output) > len(sample):
            sample += "\n[stdout sample truncated]"
        return f"[run_python] saved {len(data)} bytes to {path}\n{sample}"

    async def _do(self, call):
        name = call["name"]
        a = call.get("arguments") or {}
        if name in {"exec", "run_python"}:
            output_path = None
            if name == "run_python":
                source = a.get("code")
                if not isinstance(source, str) or not source.strip():
                    return "[run_python] code must be a nonempty Python source string"
                if len(source) > PYTHON_SOURCE_MAX or "\x00" in source:
                    return f"[run_python] code must be at most {PYTHON_SOURCE_MAX} characters without NUL bytes"
                timeout = a.get("timeout_sec", PYTHON_TIMEOUT_DEFAULT)
                if type(timeout) is not int or not 1 <= timeout <= PYTHON_TIMEOUT_MAX:
                    return f"[run_python] timeout_sec must be an integer from 1 to {PYTHON_TIMEOUT_MAX}"
                if "output_path" in a:
                    output_path = a["output_path"]
                    if not isinstance(output_path, str) or not output_path.strip() or "\x00" in output_path:
                        return "[run_python] output_path must be a nonempty file path without NUL bytes"
                # Encode model source as data, including shell metacharacters and newlines.
                encoded = base64.b64encode(source.encode()).decode("ascii")
                program = f"import base64; exec(compile(base64.b64decode('{encoded}'), '<run_python>', 'exec'))"
                if output_path is not None:
                    # The exec relay combines stdout and stderr. Keep diagnostics out of this file.
                    program = "import os; fd = os.open(os.devnull, os.O_WRONLY); os.dup2(fd, 2); os.close(fd); " + program
                command = f"{quote_path(self.t.python_cmd)} -c {quote_path(program)}"
            else:
                command, timeout = a.get("command", ""), a.get("timeout_sec", 120)
            r = await self.t.exec(command, timeout)
            if output_path is not None:
                return await self._save_python_output(output_path, r)
            body = (r.get("output") or "")[:14000]
            tag = "" if r.get("ok") else f"[exit {r.get('exit_code')}] "
            return f"{tag}{body}"
        if name == "read_file":
            data = await self.t.read_file(a.get("path", ""))
            if data is None:
                return "[read_file] not found: " + str(a.get("path"))
            try:
                txt = data.decode("utf-8")
                return txt[:14000] + ("\n[truncated]" if len(txt) > 14000 else "")
            except UnicodeDecodeError:
                return "[binary, %d bytes]" % len(data)
        if name == "write_file":
            content = a.get("content", "")
            if a.get("b64"):
                blob = base64.b64decode(content)
            else:
                blob = content.encode()
            r = await self.t.write_file(a.get("path", ""), blob, a.get("append", False))
            self._since_guard = min(self._since_guard, 0)
            if r.get("ok") is False:
                return "[write_file] failed: " + str(r.get("error"))
            return f"[write_file] ok {r.get('size', len(blob))} bytes -> {a.get('path')}"
        if name == "mcp_call":
            hdrs = {"content-type": "application/json",
                    "accept": "application/json, text/event-stream"}
            supplied_headers = a.get("headers") or {}
            if not isinstance(supplied_headers, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in supplied_headers.items()
            ):
                return "[mcp_call] headers must be a mapping of strings to strings"
            hdrs.update({key.lower(): value for key, value in supplied_headers.items()})
            r = await self.t.http(a.get("method", "POST"), a.get("url", ""), hdrs,
                                  (a.get("body") or "").encode())
            if r.get("ok") is False and r.get("status") is None:
                return f"[mcp_call] relay failed: {r.get('error') or 'no HTTP response'}"

            try:
                txt = base64.b64decode(r.get("body_b64") or "", validate=True).decode("utf-8", "replace")
            except (TypeError, ValueError):
                txt = "[invalid HTTP response body encoding]"

            result = [f"[http {r.get('status')}]"]
            for key, value in (r.get("headers") or {}).items():
                if key.lower() in {"content-type", "mcp-session-id", "mcp-protocol-version"}:
                    result.append(f"{key}: {value}")
            if txt:
                result.append(txt[:8000])
            if r.get("truncated") or len(txt) > 8000:
                result.append("[HTTP response body truncated]")
            return "\n".join(result)
        return f"[unknown tool] {name}"

    # ---------- loop ----------
    async def run(self, timeout_sec=21600, on_usage=None, on_log=None):
        on_log = on_log or self.log
        clock = asyncio.get_running_loop().time
        deadline = None if timeout_sec is None else clock() + timeout_sec * HARD_BUDGET
        wrap_at = None if deadline is None else deadline - timeout_sec * (HARD_BUDGET - WRAP_BUDGET)
        budget = asyncio.timeout_at(deadline)
        try:
            async with budget:
                return await self._run(on_usage, on_log, wrap_at, clock)
        except TimeoutError:
            if not budget.expired():
                raise
            on_log("hard deadline hit")
            return self.final or "The harness reached its time budget. Review the files already written."

    async def _run(self, on_usage, on_log, wrap_at, clock):
        snapshot = await self._snapshot()
        system = self._system(snapshot)
        on_log(f"spec: {self.spec.get('deliverable')} mode={self.spec.get('mode')} "
               f"conf={self.spec.get('confidence')} | skill={self.route['domain']}"
               f"/{self.route['family']}")

        prompt = "Task instruction:\n\n" + self.instruction
        if self._single_data_file():
            paths = list(dict.fromkeys(NAMED_TEXT_INPUT.findall(self.instruction)))
            for path in paths[:2]:
                data = await self.t.read_file(path)
                if data and len(data) <= 4096:
                    try:
                        body = data.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        continue
                    prompt += f"\n\nInput already obtained with read_file from {path}:\n{body}"
        prompt += "\n\nBegin. Use the input already supplied and fetch any remaining inputs you need."
        messages = [{"role": "user", "content": prompt}]

        asked = 0
        while self.steps < MAX_STEPS:
            if wrap_at is not None and clock() >= wrap_at:
                messages.append({"role": "user", "content":
                                 "The budget is nearly gone. Check the deliverable is complete, "
                                 "valid and readable, then call finish with a summary."})
                wrap_at = None
            try:
                resp = await self.model.chat(messages, system)
            except Exception as e:
                if self.steps == 0:
                    raise
                on_log(f"model error: {e}")
                break
            self.steps += 1
            if on_usage:
                on_usage(resp["usage"])
            calls = resp.get("tool_calls") or []
            turn = {"role": "assistant", "content": resp.get("content", ""), "tool_calls": calls}
            if "anthropic_content" in resp:
                turn["anthropic_content"] = resp["anthropic_content"]
            if "responses_output" in resp:
                turn["responses_output"] = resp["responses_output"]
            messages.append(turn)

            if not calls:
                asked += 1
                if asked >= 3:
                    on_log("model stopped calling tools; forcing finish")
                    break
                messages.append({"role": "user",
                                 "content": "Keep going with tools. The deliverable is not "
                                            "confirmed yet - call a tool, or call finish if it "
                                            "really is complete."})
                continue

            asked = 0
            finish_result = None
            summary = ""
            for call in calls:
                result = {"role": "tool", "tool_call_id": call["id"], "content": ""}
                messages.append(result)
                if call["name"] == "finish":
                    arguments = call.get("arguments")
                    final_message = arguments.get("final_message") if isinstance(arguments, dict) else None
                    if finish_result is not None:
                        result["content"] = "A finish request was already made this turn."
                    elif isinstance(final_message, str):
                        finish_result = result
                        summary = final_message
                    else:
                        result["content"] = "finish requires a final_message string."
                    continue
                try:
                    result["content"] = await self._do(call)
                except (TypeError, ValueError, AttributeError) as e:
                    result["content"] = f"Invalid arguments for {call['name']}: {e}"

            # guard: only when something was actually written since the last check
            if self._since_guard >= 0:
                self._since_guard += 1
            else:
                self._since_guard = 0
            if self._since_guard == 2 and finish_result is None:
                status, rep = await self.guard.run()
                on_log(f"guard: {status}")
                self._since_guard = 99
                if status in ("FAIL", "ERROR") and self._periodic_alerts < 2:
                    self._periodic_alerts += 1
                    messages.append({"role": "user",
                                     "content": "GUARD FAILED for the contract path. Fix these "
                                                "before anything else:\n" + rep})

            if finish_result is not None:
                status, rep = await self.guard.run()
                on_log(f"guard at finish: {status}")
                if status in ("FAIL", "ERROR"):
                    self._finish_refusals += 1
                    if self._finish_refusals < 3:
                        finish_result["content"] = ("REFUSED. The deliverable does not satisfy the contract yet:\n"
                                                    + rep + "\nFix it, then finish again.")
                        self._since_guard = 99
                        continue
                    # three refusals: the contract itself may be wrong (the task may
                    # accept a different name than the parser inferred). Ship it with
                    # the discrepancy stated rather than spin out the clock.
                    on_log("guard refused three times; shipping with a stated discrepancy")
                    summary = ("CONTRACT DISCREPANCY - the parser-inferred path could not be "
                               "satisfied:\n" + rep[-900:] + "\n\n" + summary)
                self.final = summary
                break

        if not self.final:
            status, rep = await self.guard.run()
            self.final = ("Deliverable: " + str(self.spec.get("deliverable")) +
                          f"\nGuard at exit: {status}\n" + rep[-1200:])
        return self.final
