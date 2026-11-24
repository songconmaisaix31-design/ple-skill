"""Exercise one synthetic tool call on Google's hosted Gemma and emit bounded evidence."""

import http.client
import json
import os
import re


HOST = "generativelanguage.googleapis.com"
PATH = "/v1beta/openai/chat/completions"
MODEL = "gemma-4-26b-a4b-it"
MAX_RESPONSE = 256 * 1024
FUNCTION = {
    "name": "hello",
    "description": "Look up a greeting for a person.",
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
}


def send_request(key):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Call the hello tool once with the name Ada."}],
        "tools": [{"type": "function", "function": FUNCTION}],
        "temperature": 0,
        "max_tokens": 512,
    }
    # HTTPSConnection sends one request to this host and never follows redirects.
    connection = http.client.HTTPSConnection(HOST, timeout=90)
    try:
        connection.request("POST", PATH, body=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        })
        response = connection.getresponse()
        return response.status, response.read(MAX_RESPONSE + 1) if response.status == 200 else b""
    finally:
        connection.close()


def verify(raw, evidence):
    if len(raw) > MAX_RESPONSE:
        return "response_too_large"
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            return "malformed_response"
        if body.get("model") not in (MODEL, "models/" + MODEL):
            return "unexpected_model"
        evidence["response_model"] = body["model"]
        choice, = body["choices"]
        call, = choice["message"]["tool_calls"]
        function = call["function"]
        if call["type"] != "function" or function["name"] != FUNCTION["name"]:
            return "unexpected_tool"
        if not isinstance(function["arguments"], str) or json.loads(function["arguments"]) != {"name": "Ada"}:
            return "unexpected_arguments"
        usage = body.get("usage")
        fields = ("prompt_tokens", "completion_tokens", "total_tokens")
        if not isinstance(usage, dict) or not all(type(usage.get(k)) is int and usage[k] > 0 for k in fields):
            return "invalid_usage"
        if usage["total_tokens"] < usage["prompt_tokens"] + usage["completion_tokens"]:
            return "invalid_usage"
        evidence["usage"] = {k: usage[k] for k in fields}
    except (ValueError, KeyError, TypeError, RecursionError):
        return "malformed_response"
    return "passed"


def probe(env, send=send_request):
    sha = env.get("GITHUB_SHA", "")
    run = env.get("GITHUB_RUN_ID", "")
    attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    evidence = {
        "source_sha": sha if re.fullmatch("[0-9a-f]{40}", sha) else None,
        "run_id": run if re.fullmatch("[1-9][0-9]{0,19}", run) else None,
        "run_attempt": attempt if re.fullmatch("[1-9][0-9]{0,9}", attempt) else None,
        "endpoint": "https://" + HOST + PATH,
        "requested_model": MODEL,
        "http_status": None,
    }
    key = env.get("PLE_GEMINI_API_KEY", "").strip()
    if not all(evidence[k] for k in ("source_sha", "run_id", "run_attempt")):
        result = "invalid_run_identity"
    elif not key:
        result = "missing_credential"
    else:
        try:
            status, raw = send(key)
            evidence["http_status"] = status
            result = verify(raw, evidence) if status == 200 else "http_error"
        except (OSError, ValueError, http.client.HTTPException):
            result = "transport_error"
    evidence["result"] = result
    return evidence


if __name__ == "__main__":
    report = probe(os.environ)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["result"] == "passed" else 1)
