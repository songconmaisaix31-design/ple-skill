"""Local protocol smoke test for serve.py (no model, no Docker needed).

Acts as a minimal evaluator: sends one task frame, answers every request frame,
and asserts that the harness eventually emits a `done` frame. The model endpoint
is deliberately unreachable, so the loop exits through its error path and the
final guard check.

Run from anywhere:
    python devtools/protocol_smoke.py
Optional env: PLE_SMOKE_PORT (default 18765).
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PLE_SMOKE_PORT", "18765"))


def wait_port(port, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


async def main():
    src = (REPO / "serve.py").read_text(encoding="utf-8")
    assert "ping_interval=None" in src, "keepalive pings still enabled"
    assert "ping_timeout=60" not in src, "stale ping_timeout"
    print("serve.py: ping_interval=None OK")

    env = os.environ.copy()
    env.update({
        "PORT": str(PORT),
        "MODEL_API": "google-cloud/claude-opus-5-5",
        "MODEL_NAME": "claude-opus-5-5",
        "MODEL_BASE_URL": "http://127.0.0.1:9/v1",  # unreachable on purpose
        "MODEL_API_KEY": "dummy",
    })
    proc = subprocess.Popen([sys.executable, "serve.py"], cwd=str(REPO), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    try:
        assert wait_port(PORT), "serve.py did not start listening"
        print(f"serve.py listening on {PORT}")
        seen = {}
        async with websockets.connect(f"ws://127.0.0.1:{PORT}",
                                     ping_interval=None, max_size=16 * 1024 * 1024) as ws:
            await ws.send(json.dumps({
                "type": "task",
                "instruction": ("Draft our reply as a Word letter and save it as "
                                "/filesystem/Smoke_Reply.docx. Work from the records "
                                "in the workspace."),
                "workdir": "/app",
                "limits": {"agent_timeout_sec": 60},
                "mcp_servers": [],
            }))
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=8)
                except asyncio.TimeoutError:
                    continue
                m = json.loads(raw)
                t = m.get("type")
                seen[t] = seen.get(t, 0) + 1
                if t == "done":
                    print("done frame:", (m.get("final_message") or "")[:180].replace("\n", " | "))
                    break
                if t == "error":
                    raise AssertionError("server sent error: " + str(m.get("message")))
                if t in ("exec", "read_file", "write_file", "http"):
                    reply = {"type": "result", "id": m.get("id"), "ok": True}
                    if t == "exec":
                        reply.update(exit_code=0, output="RESULT: PASS\n",
                                     truncated=False, timed_out=False)
                    elif t == "read_file":
                        reply["content_b64"] = ""
                    elif t == "write_file":
                        reply["size"] = 0
                    else:
                        reply.update(status=200, body_b64="")
                    await ws.send(json.dumps(reply))
            else:
                raise AssertionError("no done frame within deadline")
        print("frame counts:", seen)
        assert "done" in seen and "exec" in seen and "write_file" in seen
        print("PROTOCOL SMOKE: PASS")
    finally:
        proc.terminate()
        try:
            out = proc.communicate(timeout=6)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.communicate()[0]
        print("--- serve.py stdout ---")
        print((out or "")[:900])


if __name__ == "__main__":
    asyncio.run(main())
