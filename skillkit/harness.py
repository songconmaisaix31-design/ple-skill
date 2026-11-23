#!/usr/bin/env python3
"""The agent loop.

Shape: spec first (the acceptance contract is written before the model sees
anything), skill routed second, one minimal complete deliverable early, then
guard-driven iteration until the guard passes or time runs out.
"""
import asyncio
import base64
import json
import posixpath
import re

from . import code_action, specgen, router
from .guard import Guard
from .mcp import declared_output_path, exact_copy_contract, exact_tool_text, named_output_paths, result_excerpt
from .model import MCP_OUTPUT_TOOLS, PYTHON_SOURCE_MAX, PYTHON_TIMEOUT_DEFAULT, PYTHON_TIMEOUT_MAX
from .transport import quote_path

MAX_STEPS = 240
WORK_BUDGET = 0.94      # leave time for a final structural check
WRAP_BUDGET = 0.80      # switch to "close it out" mode
FINAL_BUDGET = 0.98     # leave time for the WebSocket done frame
CHECKPOINT_TIMEOUT = 10

NAMED_TEXT_INPUT = re.compile(
    r"(?<![\w./-])(?:\./)?(inputs?/(?:[\w-]+/)*[\w.-]+\.(?:json|csv|txt))"
    r"(?=$|[\s`\"'(),.;:])", re.IGNORECASE,
)
DATA_FILE_TYPES = (".json", ".csv", ".txt")
NAMED_FILE = re.compile(r"(?<![\w./-])([A-Za-z0-9_./-]+\.[A-Za-z][A-Za-z0-9]{1,9})"
                        r"(?![\w/-]|\.[\w.-])")

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
    required_files = spec.get("required_files") or []
    if len(required_files) > 1:
        lines.append("required output paths: " + ", ".join(required_files))
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
        self._guard_result = None
        self._verified_once = False
        self._checkpoint_due = False
        self._first_exec_check = False
        self._mutation_interrupted = False
        self._ctx = router.load_context(self.route["domain"])
        self._mcp_outputs = named_output_paths(instruction, self.workdir) if self.mcp else set()
        self._mcp_copy = exact_copy_contract(instruction, self.workdir, self.mcp, self._mcp_outputs)
        self._mcp_copy_value = None
        self._mcp_copy_ambiguous = False

    # ---------- prompt ----------
    def _single_data_file(self):
        path = self.spec.get("deliverable") or ""
        return (
            path.lower().endswith((".json", ".csv", ".txt"))
            and len(self.spec.get("required_files") or []) <= 1
            and len(self.spec.get("all_named_files") or []) <= 1
            and (self.spec.get("claimed_count") or 1) == 1
        )

    async def _compact_package(self, snapshot):
        outputs = self.spec.get("required_files") or []
        count = self.spec.get("claimed_count")
        if (self.mcp or not 2 <= len(outputs) <= 3 or (count is not None and count != len(outputs))
                or not all(path.lower().endswith(DATA_FILE_TYPES) for path in outputs)):
            return [], snapshot
        if outputs != specgen.build(self.instruction).get("required_files"):
            return [], snapshot

        task_text, separator, tree = snapshot.partition("\n--- tree ---\n")
        header = "--- task.md ---\n"
        if (len(snapshot) >= 7000 or not separator or not task_text.startswith(header)
                or task_text.removeprefix(header).strip() not in {"", self.instruction.strip()}):
            return [], snapshot
        paths = list(dict.fromkeys(NAMED_TEXT_INPUT.findall(self.instruction)))
        if not 1 <= len(paths) <= 3:
            return [], snapshot

        workspace = self.workdir.rstrip("/") + "/"

        def relative(path):
            return posixpath.normpath(path).removeprefix(workspace)

        declared = {relative(path) for path in (*outputs, *paths)} | {"task.md"}
        named = {relative(path) for path in NAMED_FILE.findall(self.instruction)}
        entries = [relative(line) for line in tree.splitlines() if line.startswith("./")]
        if (len(entries) >= 120 or not set(paths) <= set(entries) or not named <= declared
                or not set(entries) <= declared):
            return [], snapshot

        loaded = []
        size = 0
        for path in paths:
            try:
                data = await self.t.read_file(path)
                if not data or len(data) > 4096 or size + len(data) > 8192 or b"\x00" in data:
                    return [], snapshot
                loaded.append((path, data.decode("utf-8-sig")))
                size += len(data)
            except (OSError, ValueError):
                return [], snapshot
        return loaded, "--- tree ---\n" + tree

    def _system(self, snapshot, compact_package=False):
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
        elif compact_package:
            parts = [
                "Produce all declared files in the task workspace. The prompt includes the named input data. "
                "Use one short run_python program to load the original inputs, perform the requested calculation or "
                "transformation, create output directories, and write each actual deliverable at its declared path. "
                "The program writes multiple files itself, so leave output_path unset. Follow any method the task "
                "specifies. If a finite set of options is small, you can enumerate candidates, discard infeasible "
                "ones, and select by the requested objective. Verify computed values and the written files' paths, "
                "formats, fields, and units. Keep tool output concise, then call finish."
            ]
        else:
            parts = [SYSTEM_BASE]
        parts.append("\n=== ACCEPTANCE CONTRACT (auto-parsed from the instruction) ===\n"
                     + _fmt_contract(self.spec))
        if not single_data_file and not compact_package:
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
                         "on subsequent requests. Set output_path on a tools/call request when "
                         "the tool should save its returned text verbatim to a task-named file. "
                         "HTTP acknowledgements and initialization confirmations carry no tool data.")
            if self._mcp_copy:
                parts.append("For the explicitly requested file copy, a confirmed result will "
                             "be saved directly. After it is saved, call finish without rewriting it.")
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
    def _invalidate_checkpoint(self):
        self._guard_result = None
        self.final = ""

    async def _mutate(self, action, *args):
        self._invalidate_checkpoint()
        try:
            return await action(*args)
        except asyncio.CancelledError:
            self._mutation_interrupted = True
            raise

    def _record_write(self, path):
        self._since_guard = 0
        deliverable = self.spec.get("deliverable")
        if not deliverable or self._verified_once:
            return
        target = posixpath.normpath(posixpath.join(self.workdir, deliverable))
        written = posixpath.normpath(posixpath.join(self.workdir, path))
        if written == target or (deliverable.endswith("/") and written.startswith(target + "/")):
            self._checkpoint_due = True

    async def _check_deliverable(self):
        self._checkpoint_due = False
        if self._guard_result is None:
            copy_error = await self._check_mcp_copy()
            status, report = await self.guard.run()
            if copy_error:
                status, report = "FAIL", copy_error + "\n" + report
            self._guard_result = status, report
            path = self.spec.get("deliverable")
            if status in {"PASS", "WARN"}:
                self._verified_once = True
                self.final = f"Deliverable: {path}\nStructural checks: {status}."
                if status == "WARN":
                    self.final += "\n" + report[-800:]
            elif status == "SKIP":
                self.final = "No deliverable path was verified."
            else:
                self.final = f"Deliverable: {path}\nStructural checks: {status}.\n" + report[-800:]
        return self._guard_result

    async def _capture_mcp_copy(self, arguments, response, status, content_type, truncated):
        method, url = arguments.get("method", "POST"), arguments.get("url", "")
        if not isinstance(method, str) or method.upper() != "POST":
            return ""
        if not any(server.get("url") == url and server.get("transport") == "streamable-http"
                   for server in self.mcp):
            return ""
        chosen_path = arguments.get("output_path")
        path = declared_output_path(chosen_path, self.workdir, self._mcp_outputs)
        if chosen_path is not None and path is None:
            return "MCP tool output_path must name a text destination stated in the task."
        exact = self._mcp_copy
        tool = None
        if exact and (path is None or path == exact[2]):
            if url != exact[0] or self._mcp_copy_ambiguous:
                return ""
            _, tool, path = exact
        if path is None:
            return ""
        value = exact_tool_text(tool, arguments.get("body") or "", response, status, content_type, truncated)
        if value is None:
            return "No complete MCP tool text was saved." if chosen_path is not None else ""
        try:
            data = value.encode("utf-8")
        except UnicodeEncodeError:
            return ""
        maximum = self.limits.get("max_write_bytes") or 10_000_000
        if len(data) > maximum:
            return ""
        if tool is not None:
            if self._mcp_copy_value is not None and self._mcp_copy_value != data:
                self._mcp_copy_value = None
                self._mcp_copy_ambiguous = True
                self._invalidate_checkpoint()
                return "MCP returned conflicting values. Automatic copy disabled. Resolve which result the task requires."
            self._mcp_copy_value = data
        result = await self._mutate(self.t.write_file, path, data)
        if not result.get("ok"):
            return f"MCP exact copy could not be saved to {path}."
        self._record_write(path)
        return f"Saved the MCP tool result verbatim to {path}."

    async def _check_mcp_copy(self):
        if not self._mcp_copy or self._mcp_copy_ambiguous:
            return ""
        if self._mcp_copy_value is None:
            return "No confirmed plain-text result was obtained from the named MCP tool."
        _, _, path = self._mcp_copy
        if await self.t.read_file(path) == self._mcp_copy_value:
            return ""
        await self._mutate(self.t.write_file, path, self._mcp_copy_value)
        if await self.t.read_file(path) == self._mcp_copy_value:
            return ""
        return f"Could not verify the exact tool result in {path}."

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
        result = await self._mutate(self.t.write_file, path, data)
        if not result.get("ok"):
            return f"[run_python] write failed: {result.get('error', 'unknown error')}"
        self._record_write(path)
        sample = output[:512]
        if len(output) > len(sample):
            sample += "\n[stdout sample truncated]"
        return f"[run_python] saved {len(data)} bytes to {path}\n{sample}"

    async def _do(self, call, *, on_execution=None):
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
            r = await self._mutate(self.t.exec, command, timeout)
            if on_execution:
                on_execution(r)
            if output_path is not None:
                return await self._save_python_output(output_path, r)
            if r.get("ok") and self.spec.get("deliverable") and not self._verified_once and not self._first_exec_check:
                self._checkpoint_due = self._first_exec_check = True
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
            path = a.get("path", "")
            content = a.get("content", "")
            if a.get("b64"):
                blob = base64.b64decode(content)
            else:
                blob = content.encode()
            if self._mcp_copy_value is not None:
                target = posixpath.normpath(posixpath.join(self.workdir, path))
                if target == self._mcp_copy[2] and (blob != self._mcp_copy_value or a.get("append")):
                    return "The file is managed by the exact MCP copy. Call finish without rewriting it."
            r = await self._mutate(self.t.write_file, path, blob, a.get("append", False))
            if r.get("ok") is False:
                return "[write_file] failed: " + str(r.get("error"))
            self._record_write(path)
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
            body = a.get("body") or ""
            method, url = a.get("method", "POST"), a.get("url", "")
            r = await self._mutate(self.t.http, method, url, hdrs, body.encode())
            if r.get("ok") is False and r.get("status") is None:
                return f"[mcp_call] relay failed: {r.get('error') or 'no HTTP response'}"

            valid_text = True
            try:
                raw = base64.b64decode(r.get("body_b64") or "", validate=True)
                txt = raw.decode("utf-8")
            except UnicodeDecodeError:
                valid_text = False
                txt = raw.decode("utf-8", "replace")
            except (TypeError, ValueError):
                valid_text = False
                txt = "[invalid HTTP response body encoding]"

            status = r.get("status")
            response_headers = r.get("headers") or {}
            content_type = next((value for key, value in response_headers.items()
                                 if key.lower() == "content-type"), "")
            excerpt = result_excerpt(body, txt, status, content_type, r.get("truncated", False))
            result = [excerpt[:4096]] if excerpt else []
            if valid_text and r.get("ok"):
                saved = await self._capture_mcp_copy(a, txt, status, content_type,
                                                     r.get("truncated", False))
                if saved:
                    result.append(saved)
            if len(excerpt) > 4096:
                result.append("[MCP tool result display truncated]")
            result.append(f"[http {status}]")
            for key, value in response_headers.items():
                if key.lower() in {"content-type", "mcp-session-id", "mcp-protocol-version"}:
                    result.append(f"{key}: {value}")
            if txt:
                if excerpt:
                    result.append("[raw MCP response]")
                result.append(txt[:8000])
            if r.get("truncated") or len(txt) > 8000:
                result.append("[HTTP response body truncated]")
            return "\n".join(result)
        return f"[unknown tool] {name}"

    # ---------- loop ----------
    async def run(self, timeout_sec=21600, on_usage=None, on_log=None):
        on_log = on_log or self.log
        clock = asyncio.get_running_loop().time
        start = clock()
        final_deadline = None if timeout_sec is None else start + FINAL_BUDGET * timeout_sec
        work_deadline = wrap_at = None
        if final_deadline is not None:
            reserve = min(CHECKPOINT_TIMEOUT, timeout_sec * 0.15)
            work_deadline = min(start + WORK_BUDGET * timeout_sec, final_deadline - reserve)
            wrap_at = start + WRAP_BUDGET * timeout_sec
        budget = asyncio.timeout_at(work_deadline)
        try:
            async with budget:
                return await self._run(on_usage, on_log, wrap_at, clock, work_deadline)
        except TimeoutError:
            if not budget.expired():
                raise
            if self._mutation_interrupted:
                on_log("work deadline interrupted a task operation")
                return ("The task reached its time budget during a write-capable task operation. "
                        "Deliverable state was not verified.")
            on_log("work deadline hit; checking final deliverable")
            try:
                async with asyncio.timeout_at(final_deadline):
                    await self._check_deliverable()
            except TimeoutError:
                pass
            return "The task reached its time budget.\n" + (
                self.final or "The deliverable could not be verified before the deadline.")

    async def _run(self, on_usage, on_log, wrap_at, clock, work_deadline):
        snapshot = await self._snapshot()
        package_inputs, snapshot = await self._compact_package(snapshot)
        system = self._system(snapshot, compact_package=bool(package_inputs))
        on_log(f"spec: {self.spec.get('deliverable')} mode={self.spec.get('mode')} "
               f"conf={self.spec.get('confidence')} | skill={self.route['domain']}"
               f"/{self.route['family']}")

        prompt = "Task instruction:\n\n" + self.instruction
        supplied_input = bool(package_inputs)
        if package_inputs:
            on_log("using compact prompt for a small declared text package")
            for path, body in package_inputs:
                prompt += f"\n\nInput already obtained with read_file from {path}:\n{body}"
        elif self._single_data_file():
            paths = list(dict.fromkeys(NAMED_TEXT_INPUT.findall(self.instruction)))
            for path in paths[:2]:
                try:
                    data = await self.t.read_file(path)
                    if data and len(data) <= 4096:
                        body = data.decode("utf-8-sig")
                        prompt += f"\n\nInput already obtained with read_file from {path}:\n{body}"
                        supplied_input = True
                except (OSError, ValueError):
                    continue
        if supplied_input:
            prompt += "\n\nBegin. Use the input already supplied and fetch any remaining inputs you need."
        else:
            prompt += "\n\nBegin. First read the inputs you need, then build."
        messages = [{"role": "user", "content": prompt}]

        if mode := code_action.enabled_mode(self, package_inputs):
            program_prompt = prompt + "\n\nDeclared file requirements:\n" + _fmt_contract(self.spec)
            observation = await code_action.first_action(
                self, mode, [{"role": "user", "content": program_prompt}],
                on_usage, on_log, work_deadline, clock,
            )
            if observation:
                messages.append({"role": "user", "content": observation})

        asked = 0
        while self.steps < MAX_STEPS:
            if wrap_at is not None and clock() >= wrap_at:
                messages.append({"role": "user", "content":
                                 "The budget is nearly gone. Check the deliverable is complete, "
                                 "valid and readable, then call finish with a summary."})
                wrap_at = None
            try:
                if self.mcp:
                    resp = await self.model.chat(messages, system, tools=MCP_OUTPUT_TOOLS)
                else:
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
            periodic = self._since_guard == 2
            if (self._checkpoint_due or periodic) and finish_result is None:
                self._since_guard = 99
                try:
                    async with asyncio.timeout(CHECKPOINT_TIMEOUT):
                        status, rep = await self._check_deliverable()
                except TimeoutError:
                    on_log("deliverable checkpoint exceeded its time limit")
                else:
                    on_log(f"guard: {status}")
                    if periodic and status in ("FAIL", "ERROR") and self._periodic_alerts < 2:
                        self._periodic_alerts += 1
                        messages.append({"role": "user",
                                         "content": "GUARD FAILED for the contract path. Fix these "
                                                    "before anything else:\n" + rep})

            if finish_result is not None:
                status, rep = await self._check_deliverable()
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
                self.final = summary or self.final
                return self.final

        await self._check_deliverable()
        return self.final
