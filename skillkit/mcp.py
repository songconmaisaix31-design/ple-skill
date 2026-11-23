"""Extract model-facing tool results from relayed MCP responses."""

import json
import re
from collections import defaultdict


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
    payloads = (_sse_payloads(response)
                if content_type.partition(";")[0].strip().lower() == "text/event-stream"
                else [response])
    replies = _by_id(message for payload in payloads for message in _messages(payload))
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
