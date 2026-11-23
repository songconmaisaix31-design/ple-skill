#!/usr/bin/env python3
"""PLE harness entry point: one WebSocket connection = one task."""
import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import websockets
from websockets.exceptions import ConnectionClosed
from skillkit.harness import Harness
from skillkit.transport import WSTransport
from skillkit.model import from_env


async def solve(ws):
    first = json.loads(await ws.recv())
    if first.get("type") != "task":
        await ws.send(json.dumps({"type": "error", "message": "expected task frame"}))
        return
    limits = first.get("limits") or {}
    timeout = limits.get("agent_timeout_sec", 21600)
    workdir = first.get("workdir") or "/app"
    transport = WSTransport(ws, workdir)
    pending_frames = set()

    async def send(frame):
        try:
            await ws.send(json.dumps(frame))
        except ConnectionClosed:
            pass

    def emit(frame):
        task = asyncio.create_task(send(frame))
        pending_frames.add(task)
        task.add_done_callback(pending_frames.discard)

    def log(text):
        emit({"type": "log", "text": str(text)[:2000]})

    # reader: results go to pending futures, cancel raises the flag
    async def reader():
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await transport.dispatch(msg)
        finally:
            transport.cancelled.set()

    model = from_env()
    h = Harness(transport, model, first.get("instruction", ""), workdir=workdir,
                limits=limits, mcp_servers=first.get("mcp_servers") or [], log=log)

    def on_usage(u):
        emit({
            "type": "usage", "model": model.model,
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": u.get("cache_read_tokens", 0)})

    reader_task = asyncio.create_task(reader())
    run_task = asyncio.create_task(h.run(timeout, on_usage=on_usage))
    cancel_watch = asyncio.create_task(transport.cancelled.wait())
    try:
        await asyncio.wait({run_task, cancel_watch}, return_when=asyncio.FIRST_COMPLETED)
        if run_task.done():
            final = run_task.result()
        else:
            final = h.final or "Cancelled at the time limit. Review the files already written."
        terminal = {"type": "done", "final_message": final[:20000]}
    except Exception as e:
        terminal = {"type": "error", "message": f"Harness error: {e}"[:2000]}
    finally:
        for task in (run_task, cancel_watch, reader_task):
            task.cancel()
        await asyncio.gather(run_task, cancel_watch, reader_task, return_exceptions=True)

    if pending_frames:
        await asyncio.gather(*pending_frames)
    await send({"type": "log", "text": f"steps={h.steps} deliverable={h.spec.get('deliverable')}"})
    await send(terminal)


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
