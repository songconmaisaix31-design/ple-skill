"""Extract model-facing tool results from relayed MCP responses."""

import json
import re
from collections import defaultdict
from pathlib import PurePosixPath


_IDENTIFIER = r"[\w.-]+"
_FILE = r"[\w./-]+\.(?:txt|md|csv|json|yaml|yml|docx|xlsx|pdf|zip|html|ifc|dxf)(?![\w/-]|\.[\w.-])"
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}
_DESTINATION = re.compile(
    rf"\b(?:create|save|write|copy)\s+(?:(?:a|the)\s+)?(?:(?:plain[- ]text\s+)?file\s+"
    rf"(?:named|called|at)\s+)?`?({_FILE})"
    rf"|\b(?:save|write|copy)\s+[^.!?\n]{{1,100}}?\b(?:to|as|into)\s+`?({_FILE})",
    re.IGNORECASE,
)
_FIDELITY = re.compile(r"\b(?:verbatim|unchanged|as[- ]is|entire\s+content|"
                       r"exactly\s+as\s+(?:returned|received)|exact\s+text)\b", re.IGNORECASE)
_MCP_RESULT = re.compile(r"\b(?:tool\s+returns|returned\s+by\s+the\s+tool|return\s+value|"
                         r"tool\s+(?:response|result|output)|result\s+of\s+the\s+tool)\b", re.IGNORECASE)


def _workspace_text_path(stated, workdir):
    if not isinstance(stated, str) or not re.fullmatch(_FILE, stated, re.IGNORECASE):
        return None
    root = PurePosixPath(workdir)
    path = root / stated
    if root.is_absolute() and path.is_relative_to(root) and ".." not in path.parts:
        if path.suffix.lower() in _TEXT_SUFFIXES:
            return str(path)
    return None


def named_output_paths(instruction, workdir):
    """Return explicitly named destinations for text output within the task workspace."""
    paths = (_workspace_text_path(direct or directional, workdir)
             for direct, directional in _DESTINATION.findall(instruction))
    return {path for path in paths if path is not None}


def exact_copy_contract(instruction, workdir, servers, outputs=None):
    """Recognize one expressly named MCP tool and whole-file text copy."""
    if not servers:
        return None
    clauses = re.split(r"[.!?;](?=\s|$)|\n+", instruction)
    if not any(_FIDELITY.search(clause) and _MCP_RESULT.search(clause) for clause in clauses):
        return None
    paths = named_output_paths(instruction, workdir) if outputs is None else outputs
    files = set(re.findall(rf"(?<![\w./-]){_FILE}", instruction, re.IGNORECASE))
    tools = set(re.findall(rf"\btool\s+(?:named|called)\s+`?({_IDENTIFIER})`?", instruction, re.IGNORECASE))
    names = set(re.findall(rf"\bMCP\s+server\s+(?:(?:named|called)\s+)?`?({_IDENTIFIER})`?",
                           instruction, re.IGNORECASE))
    if len(paths) != 1 or len(files) != 1 or len(tools) != 1 or len(names) != 1:
        return None
    if re.search(r"\b(?:append|transform|translate|summarize|reformat|prefix|suffix|replace|"
                 r"calculate|compute|derive|convert|round|decimal\s+places?|"
                 r"(?:another|second|separate|multiple)\s+files?)\b", instruction, re.I):
        return None
    name = next(iter(names))
    urls = {server.get("url") for server in servers if server.get("name") == name
            and server.get("transport") == "streamable-http" and server.get("url")}
    if len(urls) != 1:
        return None
    return next(iter(urls)), next(iter(tools)), next(iter(paths))


def declared_output_path(stated, workdir, outputs):
    path = _workspace_text_path(stated, workdir)
    return path if path in outputs else None


def _messages(payload):
    try:
        decoded = json.loads(payload)
    except (ValueError, RecursionError):
        return []
    batch = decoded if isinstance(decoded, list) else [decoded]
    return [item for item in batch if isinstance(item, dict) and item.get("jsonrpc") == "2.0"]


def _sse_payloads(body):
    data = []
    for line in re.split(r"\r\n|\r|\n", body)[:-1]:
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
        else:
            name, _, value = line.partition(":")
            if name == "data":
                data.append(value.removeprefix(" "))


def _by_id(messages):
    grouped = defaultdict(list)
    for message in messages:
        rpc_id = message.get("id")
        if type(rpc_id) in (str, int):
            grouped[rpc_id].append(message)
    return grouped


def _replies(response, content_type):
    payloads = (_sse_payloads(response)
                if content_type.partition(";")[0].strip().lower() == "text/event-stream"
                else [response])
    return _by_id(message for payload in payloads for message in _messages(payload))


def exact_tool_text(tool, request, response, status, content_type, truncated):
    """Return only a single, successful, unambiguous tool text block."""
    if status != 200 or truncated:
        return None
    calls = _messages(request)
    if len(calls) != 1:
        return None
    call = calls[0]
    rpc_id, params = call.get("id"), call.get("params")
    if call.get("method") != "tools/call" or not isinstance(params, dict) or type(rpc_id) not in (str, int):
        return None
    called_tool = params.get("name")
    if not isinstance(called_tool, str) or not called_tool or (tool is not None and called_tool != tool):
        return None
    replies = _replies(response, content_type)
    matching = replies.get(rpc_id, [])
    if len(replies) != 1 or len(matching) != 1 or "method" in matching[0] or "error" in matching[0]:
        return None
    result = matching[0].get("result")
    if (not isinstance(result, dict) or result.keys() - {"content", "isError", "_meta"}
            or result.get("isError", False) is not False):
        return None
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return None
    block = content[0]
    if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
        return block["text"]
    return None


def result_excerpt(request, response, status, content_type, truncated):
    """Describe confirmed results without mistaking HTTP metadata for tool data."""
    requests = _messages(request)
    if not requests:
        return ""
    if status == 202:
        return "MCP HTTP 202 acknowledgement. No tool result content."
    if not isinstance(status, int) or not 200 <= status < 300 or truncated:
        return "MCP transport failed or was truncated. No confirmed tool result content."
    calls = _by_id(requests)
    replies = _replies(response, content_type)
    descriptions = []
    for rpc_id, matching_calls in calls.items():
        if len(matching_calls) != 1:
            continue
        call = matching_calls[0]
        method = call.get("method")
        matching_replies = replies.get(rpc_id, [])
        if len(matching_replies) != 1 or "method" in matching_replies[0]:
            descriptions.append("MCP response has no unique match for the request ID. No confirmed tool result content.")
            continue
        reply = matching_replies[0]
        result = reply.get("result")
        if "error" in reply or (isinstance(result, dict) and result.get("isError") is True):
            descriptions.append("MCP request returned an error. No confirmed tool result content.")
            continue
        if method != "tools/call" or not isinstance(result, dict):
            descriptions.append("MCP protocol response. No tool result content.")
            continue

        params = call.get("params")
        tool = params.get("name", "tools/call") if isinstance(params, dict) else "tools/call"
        blocks = result.get("content")
        texts = []
        if isinstance(blocks, list):
            texts.extend(block["text"] for block in blocks if isinstance(block, dict)
                         and block.get("type") == "text" and isinstance(block.get("text"), str))
        if "structuredContent" in result:
            texts.append("Structured content: " + json.dumps(result["structuredContent"], ensure_ascii=False))
        if texts:
            descriptions.append(f"MCP tool result content ({tool}):\n" + "\n".join(texts))
        else:
            descriptions.append("MCP tool returned no text or structured content. See raw response.")
    return "\n".join(descriptions) or "MCP protocol acknowledgement. No confirmed tool result content."
