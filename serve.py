#!/usr/bin/env python3
"""PLE harness entry point: one WebSocket connection = one task."""
import asyncio, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import websockets
from skillkit.harness import Harness
from skillkit.transport import WSTransport
from skillkit.model import from_env


async def solve(ws):
    first = json.loads(await ws.recv())
    if first.get("type") != "task":
        await ws.send(json.dumps({"type": "error", "message": "expected task frame"}))
        return
    limits = first.get("limits") or {}
    timeout = int(limits.get("agent_timeout_sec", 21600))
    workdir = first.get("workdir") or "/app"

    def log(text):
        try:
            return asyncio.create_task(ws.send(json.dumps({"type": "log", "text": str(text)[:2000]})))
        except Exception:
            return None

    transport = WSTransport(ws, workdir, log=lambda t: None)

    # reader: results go to pending futures, cancel raises the flag
    async def reader():
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await transport.dispatch(msg)
        except Exception:
            pass

    reader_task = asyncio.create_task(reader())
    model = from_env()
    h = Harness(transport, model, first.get("instruction", ""), workdir=workdir,
                limits=limits, mcp_servers=first.get("mcp_servers") or [],
                log=lambda t: asyncio.create_task(
                    ws.send(json.dumps({"type": "log", "text": str(t)[:2000]}))))

    def on_usage(u):
        asyncio.create_task(ws.send(json.dumps({
            "type": "usage", "model": model.model,
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": u.get("cache_read_tokens", 0)})))

    run_task = asyncio.create_task(h.run(timeout, on_usage=on_usage))
    cancel_watch = asyncio.create_task(transport.cancelled.wait())
    done, _ = await asyncio.wait({run_task, cancel_watch}, return_when=asyncio.FIRST_COMPLETED)
    if cancel_watch in done and not run_task.done():
        run_task.cancel()
        final = "Cancelled at the time limit. Files already on disk are the deliverable."
    else:
        try:
            final = run_task.result()
        except Exception as e:
            final = f"Harness error: {e}"
    cancel_watch.cancel()
    reader_task.cancel()

    try:
        await ws.send(json.dumps({"type": "log", "text": f"steps={h.steps} "
                                 f"deliverable={h.spec.get('deliverable')}"}))
        await ws.send(json.dumps({"type": "done", "final_message": (final or "")[:20000]}))
    except Exception:
        pass


async def main():
    port = int(os.environ.get("PORT", "8080"))
    # The evaluator protocol requires no keepalive pings: one exec may run up
    # to 600 s, and a ping timeout would drop the connection mid-command.
    # docs/protocol.md: "Run your server without keepalive pings".
    async with websockets.serve(solve, "0.0.0.0", port,
                                max_size=16 * 1024 * 1024,
                                ping_interval=None):
        print(f"listening on 0.0.0.0:{port}", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
