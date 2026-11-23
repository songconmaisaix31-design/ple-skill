#!/usr/bin/env python3
"""Host-local adapter for GLM-5.2 on Hugging Face Inference Providers."""

from datetime import timezone
from email.utils import parsedate_to_datetime
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from math import ceil, inf
import os
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL = "glm-5.2"
HF_MODEL = "zai-org/GLM-5.2"
PROVIDER_MODEL = "zai-org/GLM-5.2:deepinfra"
UPSTREAM = "https://router.huggingface.co/v1/chat/completions"
REQUEST_FIELDS = ("messages", "tools", "tool_choice", "reasoning_effort", "max_tokens",
                  "max_completion_tokens", "temperature", "stream")
PATH = "/v1/chat/completions"
MAX_BODY = 8 * 1024 * 1024
DEFAULT_RETRY_DELAY = 31
MAX_LOCAL_WAIT = 120
LOCK = threading.Lock()
NEXT_CALL = 0.0


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *unused, **kwargs):
        return None


def retry_delay(header):
    if not header:
        return DEFAULT_RETRY_DELAY
    value = header.strip()
    if value.isascii() and value.isdecimal():
        digits = value.lstrip("0") or "0"
        return max(DEFAULT_RETRY_DELAY, int(digits)) if len(digits) <= 9 else inf
    try:
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return max(DEFAULT_RETRY_DELAY, ceil(deadline.timestamp() - time.time()))
    except (OverflowError, OSError, TypeError, ValueError):
        return DEFAULT_RETRY_DELAY


def rate_limited(delay):
    # The advertised delay is bounded, but the relay retains the full cooldown.
    return 429, b'{"error":"Hugging Face inference HTTP 429"}', ceil(min(delay, 86400))


def normalize_response(body):
    try:
        result = json.loads(body)
    except ValueError:
        return None
    if not isinstance(result, dict) or result.get("model") not in (MODEL, HF_MODEL, PROVIDER_MODEL):
        return None
    result["model"] = MODEL
    return json.dumps(result, separators=(",", ":")).encode()


def forward(payload, inference_token):
    global NEXT_CALL

    body = {field: payload[field] for field in REQUEST_FIELDS if field in payload}
    body["model"] = PROVIDER_MODEL
    request = Request(UPSTREAM, json.dumps(body).encode(), {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {inference_token}",
    })
    with LOCK:
        delay = NEXT_CALL - time.monotonic()
        if delay > MAX_LOCAL_WAIT:
            return rate_limited(delay)
        time.sleep(max(0, delay))

        try:
            with build_opener(NoRedirect()).open(request, timeout=120) as response:
                body = response.read(MAX_BODY + 1)
                if len(body) <= MAX_BODY:
                    body = normalize_response(body)
                    if body is None:
                        return 502, b'{"error":"Hugging Face response did not match GLM-5.2"}', None
                    if len(body) <= MAX_BODY:
                        return response.status, body, None
        except HTTPError as exc:
            with exc:
                if exc.code == 429:
                    delay = retry_delay((exc.headers or {}).get("Retry-After"))
                    NEXT_CALL = max(NEXT_CALL, time.monotonic() + delay)
                    return rate_limited(delay)
                if 400 <= exc.code <= 599:
                    return exc.code, json.dumps({"error": f"Hugging Face inference HTTP {exc.code}"}).encode(), None
        except OSError:
            pass
    return 502, b'{"error":"Hugging Face inference connection or response failed"}', None


class Relay(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, status, body, retry_after=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/ready":
            self.send_json(200, b'{"ready":true}')
        else:
            self.send_json(404, b'{"error":"invalid path"}')

    def do_POST(self):
        if self.path != PATH:
            self.send_json(404, b'{"error":"invalid path"}')
            return
        bearer = f"Bearer {self.server.proxy_key}".encode()
        supplied = self.headers.get("Authorization", "").encode()
        if not hmac.compare_digest(supplied, bearer):
            self.send_json(401, b'{"error":"local proxy authentication failed"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
        except (ValueError, OSError):
            self.send_json(400, b'{"error":"invalid request body"}')
            return
        if not isinstance(payload, dict) or payload.get("model") != MODEL or payload.get("stream"):
            self.send_json(400, b'{"error":"only non-streaming glm-5.2 is available"}')
            return
        try:
            token = inference_token(self.server.inference_token, self.server.token_file)
        except (OSError, ValueError):
            self.send_json(503, b'{"error":"Hugging Face inference credential unavailable"}')
            return
        self.send_json(*forward(payload, token))


def inference_token(token, token_file):
    if token_file:
        token = token_file.read_text(encoding="ascii").strip()
    if not token or not token.isascii() or not token.isprintable() or " " in token:
        raise ValueError("Hugging Face inference bearer is invalid or missing")
    return token


def main():
    proxy_key = os.environ.get("MODEL_PROXY_KEY", "")
    if not proxy_key:
        raise SystemExit("MODEL_PROXY_KEY must not be empty")
    token = os.environ.get("PLE_HF_INFERENCE_TOKEN", "").strip()
    path = os.environ.get("PLE_HF_INFERENCE_TOKEN_FILE")
    token_file = Path(path) if path else None
    if bool(token) == bool(token_file):
        raise SystemExit("Configure exactly one Hugging Face inference credential source")
    try:
        initial_token = inference_token(token, token_file)
    except (OSError, ValueError):
        raise SystemExit("Hugging Face inference credential unavailable") from None
    if hmac.compare_digest(proxy_key.encode(), initial_token.encode()):
        raise SystemExit("The relay and inference credentials must be separate")
    with ThreadingHTTPServer(("0.0.0.0", 4101), Relay) as server:
        server.proxy_key = proxy_key
        server.inference_token = token
        server.token_file = token_file
        server.serve_forever()


if __name__ == "__main__":
    main()
