#!/usr/bin/env python3
"""Model client for Chat Completions, Responses, and Anthropic Messages.

The Anthropic path exists for one reason: prompt caching. Leaked into the
96%-cached-prompt profile of the dev tasks, an uncached harness pays
10-40x the input cost per turn.
"""
import asyncio, json, os, random

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

PYTHON_TIMEOUT_DEFAULT = 60
PYTHON_TIMEOUT_MAX = 120
PYTHON_SOURCE_MAX = 16_384

TOOLS = [
    {"name": "exec",
     "description": "Run a bash command in the task container, starting in the workdir. "
                    "Only filesystem state persists between calls. Use python3 (python-docx, "
                    "openpyxl, pandas, libreoffice and pdftotext are installed) for anything "
                    "structural: building docx/xlsx, unzipping inputs, parsing PDFs.",
     "parameters": {"type": "object",
                    "properties": {"command": {"type": "string"},
                                   "timeout_sec": {"type": "integer", "default": 120}},
                    "required": ["command"]}},
    {"name": "run_python",
     "description": "Run Python source in the task container, starting in the workdir. "
                    "Pass Python source directly and print the quantities needed for the next step. "
                    "To save a text deliverable, print only its complete contents and set output_path. "
                    "The file is saved only when execution succeeds and output is complete. "
                    "Only filesystem state persists between calls.",
     "parameters": {"type": "object",
                    "properties": {"code": {"type": "string", "minLength": 1,
                                            "maxLength": PYTHON_SOURCE_MAX},
                                   "timeout_sec": {"type": "integer", "default": PYTHON_TIMEOUT_DEFAULT,
                                                   "minimum": 1, "maximum": PYTHON_TIMEOUT_MAX},
                                   "output_path": {"type": "string", "minLength": 1,
                                                   "description": "Optional exact text deliverable path. "
                                                                  "For .json, print one valid JSON value."}},
                    "required": ["code"]}},
    {"name": "read_file",
     "description": "Read a file from the task container. Returns utf-8 text when the bytes "
                    "decode cleanly, otherwise base64 with a marker. 10 MB cap.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                    "required": ["path"]}},
    {"name": "write_file",
     "description": "Write text (or base64 when `b64` is true) to a path in the task container. "
                    "Parent directories are created. Use this for the final deliverable too.",
     "parameters": {"type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"},
                                   "append": {"type": "boolean", "default": False},
                                   "b64": {"type": "boolean", "default": False}},
                    "required": ["path", "content"]}},
    {"name": "mcp_call",
     "description": "Send an HTTP request to one of the task's declared MCP servers "
                    "(streamable HTTP, JSON-RPC). Use it for records the task keeps in an "
                    "external app (OpenProject, issue trackers, etc).",
     "parameters": {"type": "object",
                    "properties": {"method": {"type": "string", "default": "POST"},
                                   "url": {"type": "string"},
                                   "headers": {"type": "object"},
                                   "body": {"type": "string"}},
                    "required": ["url"]}},
    {"name": "finish",
     "description": "End the task. `final_message` is graded by the rubric judge: say what "
                    "you produced, where every file is saved, the governing values you used, "
                    "and the choices that could cost credit.",
     "parameters": {"type": "object", "properties": {"final_message": {"type": "string"}},
                    "required": ["final_message"]}},
]

MCP_OUTPUT_TOOLS = [
    {**tool, "parameters": {**tool["parameters"], "properties": {
        **tool["parameters"]["properties"],
        "output_path": {"type": "string", "description": "Optional task-named text output path. "
                        "Write the single complete tools/call text result verbatim to this file."},
    }}} if tool["name"] == "mcp_call" else tool
    for tool in TOOLS
]


class ModelClient:
    def __init__(self, model_name, base_url, api_key, mode="openai",
                 max_tokens=8000, reasoning_effort=None, log=None):
        self.model = model_name
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.mode = mode
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.log = log or (lambda t: None)
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}

    # ---------- request bodies ----------
    def _to_anthropic(self, messages):
        out = []
        for m in messages:
            role = m["role"]
            if role == "assistant":
                # Claude expects its thinking blocks and their signatures intact
                # when a tool result continues this turn.
                blocks = m.get("anthropic_content") or [{"type": "text", "text": "(ok)"}]
                out.append({"role": "assistant", "content": blocks})
                continue

            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                         "content": m.get("content") or ""}
            else:
                block = {"type": "text", "text": m.get("content") or ""}
            if not out or out[-1]["role"] != "user":
                out.append({"role": "user", "content": []})
            out[-1]["content"].append(block)

        # Cache the newest input, after the tool results and any follow-up text.
        if out and out[-1]["role"] == "user" and out[-1]["content"]:
            out[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        return out

    def _to_openai(self, messages):
        out = []
        for m in messages:
            d = {"role": m["role"], "content": m.get("content")}
            if m.get("tool_calls"):
                d["tool_calls"] = [{"id": tc["id"], "type": "function",
                                    "function": {"name": tc["name"],
                                                 "arguments": json.dumps(tc.get("arguments") or {})}}
                                   for tc in m["tool_calls"]]
                d["content"] = m.get("content") or None
            if m["role"] == "tool":
                d = {"role": "tool", "tool_call_id": m["tool_call_id"],
                     "content": m.get("content") or ""}
            out.append(d)
        return out

    def _to_responses(self, messages):
        items = []
        for message in messages:
            role = message["role"]
            if role == "tool":
                items.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                              "output": message.get("content") or ""})
            elif role == "assistant":
                # Stateless Responses requires the original output items, especially
                # the encrypted reasoning that accompanies function calls.
                items.extend(message["responses_output"])
            else:
                items.append({"role": role, "content": message.get("content") or ""})
        return items

    async def chat(self, messages, system, tools=None):
        tools = tools or TOOLS
        payload = await self._request(messages, system, tools)
        return payload

    async def _request(self, messages, system, tools):
        if httpx is None:
            raise RuntimeError("httpx missing")
        headers = {"content-type": "application/json"}
        if self.mode == "anthropic":
            url = self.base_url + "/v1/messages"
            headers["x-api-key"] = self.api_key or ""
            headers["anthropic-version"] = "2023-06-01"
            body = {"model": self.model, "max_tokens": self.max_tokens,
                    "system": [{"type": "text", "text": system,
                                "cache_control": {"type": "ephemeral"}}],
                    "messages": self._to_anthropic(messages),
                    "tools": [{"name": t["name"], "description": t["description"],
                               "input_schema": t["parameters"]} for t in tools]}
        elif self.mode == "responses":
            url = self.base_url + ("/responses" if self.base_url.endswith("/v1") else "/v1/responses")
            headers["authorization"] = "Bearer " + (self.api_key or "")
            body = {"model": self.model, "max_output_tokens": self.max_tokens,
                    "instructions": system, "input": self._to_responses(messages),
                    "tools": [{"type": "function", **t, "strict": False} for t in tools],
                    "tool_choice": "auto", "store": False,
                    "include": ["reasoning.encrypted_content"]}
            if self.reasoning_effort:
                body["reasoning"] = {"effort": self.reasoning_effort}
        else:
            url = self.base_url + "/chat/completions" if self.base_url.endswith("/v1") \
                else self.base_url + "/v1/chat/completions"
            headers["authorization"] = "Bearer " + (self.api_key or "")
            body = {"model": self.model, "max_tokens": self.max_tokens,
                    "messages": [{"role": "system", "content": system}] + self._to_openai(messages),
                    "tools": [{"type": "function", "function": t} for t in tools],
                    "tool_choice": "auto"}
            if self.reasoning_effort:
                body["reasoning_effort"] = self.reasoning_effort

        last_err = None
        for attempt in range(5):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(1800, connect=30),
                                             trust_env=True) as c:
                    r = await c.post(url, headers=headers, json=body)
                    if r.status_code in (429, 500, 502, 503, 504):
                        last_err = f"{r.status_code} {r.text[:200]}"
                        await asyncio.sleep(min(2 ** attempt + random.random(), 30))
                        continue
                    if r.status_code >= 400:
                        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
                    return self._normalise(r.json())
            except RuntimeError:
                raise
            except Exception as e:
                last_err = repr(e)
                await asyncio.sleep(min(2 ** attempt + random.random(), 30))
        raise RuntimeError(f"model call failed after retries: {last_err}")

    def _normalise(self, data):
        if self.mode == "anthropic":
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            calls = [{"id": b["id"], "name": b["name"], "arguments": b.get("input") or {}}
                     for b in blocks if b.get("type") == "tool_use"]
            u = data.get("usage") or {}
            cache_read = u.get("cache_read_input_tokens", 0) or 0
            cache_write = u.get("cache_creation_input_tokens", 0) or 0
            usage = {"input_tokens": (u.get("input_tokens", 0) or 0) + cache_write + cache_read,
                     "output_tokens": u.get("output_tokens", 0),
                     "cache_read_tokens": cache_read}
        elif self.mode == "responses":
            if data.get("status") == "failed":
                error = data.get("error") or {}
                raise RuntimeError(f"Responses API failed: {error.get('code') or 'unknown error'}")
            items = data.get("output") or []
            text = "".join(part.get("text", "") for item in items if item.get("type") == "message"
                           for part in item.get("content") or [] if part.get("type") == "output_text")
            calls = []
            for item in items:
                if item.get("type") != "function_call":
                    continue
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append({"id": item["call_id"], "name": item["name"], "arguments": args})
            u = data.get("usage") or {}
            usage = {"input_tokens": u.get("input_tokens", 0) or 0,
                     "output_tokens": u.get("output_tokens", 0) or 0,
                     "cache_read_tokens": (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0}
        else:
            ch = (data.get("choices") or [{}])[0].get("message") or {}
            text = ch.get("content") or ""
            calls = []
            for tc in ch.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append({"id": tc.get("id") or f"c{len(calls)}",
                              "name": fn.get("name"), "arguments": args})
            u = data.get("usage") or {}
            usage = {"input_tokens": u.get("prompt_tokens", 0),
                     "output_tokens": u.get("completion_tokens", 0),
                     "cache_read_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}
        for k in self.usage:
            self.usage[k] += usage.get(k, 0)
        result = {"content": text, "tool_calls": calls, "usage": usage}
        if self.mode == "anthropic":
            result["anthropic_content"] = blocks
        elif self.mode == "responses":
            result["responses_output"] = items
        return result


def from_env(log=None):
    api = os.environ.get("MODEL_API", "")
    model = os.environ.get("MODEL_NAME") or api.split("/")[-1] or "unknown"
    base = os.environ.get("MODEL_BASE_URL") or ""
    key = os.environ.get("MODEL_API_KEY") or ""
    mode = "responses" if model == "gpt-6.1-sol" else "openai"
    if "claude" in model.lower() and os.environ.get("ANTHROPIC_BASE_URL"):
        base = os.environ["ANTHROPIC_BASE_URL"]
        key = os.environ.get("ANTHROPIC_API_KEY") or key
        mode = "anthropic"
    if not base:
        base = os.environ.get("OPENAI_BASE_URL", "")
    if mode == "responses" and not key:
        key = os.environ.get("OPENAI_API_KEY", "")
    return ModelClient(model, base, key, mode=mode, log=log)
