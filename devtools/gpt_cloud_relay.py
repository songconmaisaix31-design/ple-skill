#!/usr/bin/env python3
"""Host-local adapter from the PLE model interface to OVHcloud's anonymous GPT endpoint."""

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL = "gpt-oss-120b"
UPSTREAM = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
PATH = "/v1/chat/completions"
MAX_BODY = 8 * 1024 * 1024
CALL_INTERVAL = 31
LOCK = threading.Lock()
NEXT_CALL = 0.0


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *unused, **kwargs):
        return None


def forward(payload):
    global NEXT_CALL

    payload.setdefault("reasoning_effort", "high")
    request = Request(UPSTREAM, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with LOCK:
        time.sleep(max(0, NEXT_CALL - time.monotonic()))
        NEXT_CALL = time.monotonic() + CALL_INTERVAL

    try:
        with build_opener(NoRedirect()).open(request, timeout=120) as response:
            body = response.read(MAX_BODY + 1)
            if len(body) <= MAX_BODY:
                return response.status, body
    except HTTPError as exc:
        with exc:
            status = exc.code
        if 400 <= status <= 599:
            return status, json.dumps({"error": f"GPT provider HTTP {status}"}).encode()
    except OSError:
        pass
    return 502, b'{"error":"GPT provider connection or response failed"}'


class Relay(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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
            self.send_json(400, b'{"error":"only non-streaming gpt-oss-120b is available"}')
            return
        self.send_json(*forward(payload))


def main():
    with ThreadingHTTPServer(("0.0.0.0", 4101), Relay) as server:
        server.proxy_key = os.environ["MODEL_PROXY_KEY"]
        if not server.proxy_key:
            raise SystemExit("MODEL_PROXY_KEY must not be empty")
        server.serve_forever()


if __name__ == "__main__":
    main()
