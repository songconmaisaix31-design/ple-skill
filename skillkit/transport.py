#!/usr/bin/env python3
"""Transport abstraction: every action the harness takes goes through here.

WSTransport  -> competition protocol (serve.py holds the socket)
LocalTransport -> dryrun against a local directory (no Docker needed)
"""
import asyncio, base64, json, os, subprocess


class Transport:
    """Unified action surface used by the agent loop."""

    async def exec(self, command, timeout_sec=120):
        raise NotImplementedError

    async def read_file(self, path):
        raise NotImplementedError

    async def write_file(self, path, data, append=False):
        raise NotImplementedError

    async def http(self, method, url, headers=None, body=None):
        raise NotImplementedError

    async def close(self):
        pass


class WSTransport(Transport):
    def __init__(self, ws, workdir="/app", log=None):
        self.ws = ws
        self.workdir = workdir
        self._seq = 0
        self._pending = {}
        self._log = log or (lambda t: None)
        self.cancelled = asyncio.Event()

    async def _call(self, payload, wait=600):
        self._seq += 1
        rid = str(self._seq)
        payload["id"] = rid
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self.ws.send(json.dumps(payload, ensure_ascii=False))
        try:
            return await asyncio.wait_for(fut, timeout=wait)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            return {"ok": False, "error": "transport timeout"}

    async def dispatch(self, msg):
        """Route a frame from the evaluator: result -> future, cancel -> flag."""
        t = msg.get("type")
        if t == "result":
            fut = self._pending.pop(str(msg.get("id")), None)
            if fut and not fut.done():
                fut.set_result(msg)
        elif t == "cancel":
            self.cancelled.set()
        return t

    async def exec(self, command, timeout_sec=120):
        r = await self._call({"type": "exec", "command": command,
                              "timeout_sec": min(int(timeout_sec), 600)})
        return {"exit_code": r.get("exit_code", -1), "output": r.get("output", ""),
                "truncated": r.get("truncated", False), "timed_out": r.get("timed_out", False),
                "ok": r.get("ok", r.get("exit_code") == 0)}

    async def read_file(self, path):
        r = await self._call({"type": "read_file", "path": path})
        if not r.get("ok"):
            return None
        return base64.b64decode(r.get("content_b64") or "")

    async def write_file(self, path, data, append=False):
        if isinstance(data, str):
            data = data.encode()
        return await self._call({"type": "write_file", "path": path,
                                 "content_b64": base64.b64encode(data).decode(),
                                 "append": bool(append)})

    async def http(self, method, url, headers=None, body=None):
        blob = body or b""
        if isinstance(blob, str):
            blob = blob.encode()
        return await self._call({"type": "http", "method": method, "url": url,
                                 "headers": headers or {},
                                 "body_b64": base64.b64encode(blob).decode()})


class LocalTransport(Transport):
    """Dryrun backend: executes against a local task directory."""

    def __init__(self, root):
        self.root = os.path.abspath(root)

    def _abs(self, path):
        return path if os.path.isabs(path) else os.path.join(self.root, path.lstrip("./"))

    async def exec(self, command, timeout_sec=120):
        p = await asyncio.create_subprocess_shell(
            command, cwd=self.root, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(p.communicate(), timeout=min(timeout_sec, 600))
            return {"exit_code": p.returncode, "output": out.decode("utf-8", "replace"),
                    "truncated": False, "timed_out": False, "ok": p.returncode == 0}
        except asyncio.TimeoutError:
            p.kill()
            return {"exit_code": 124, "output": "timed out", "truncated": False,
                    "timed_out": True, "ok": False}

    async def read_file(self, path):
        fp = self._abs(path)
        if not os.path.exists(fp):
            return None
        return open(fp, "rb").read()

    async def write_file(self, path, data, append=False):
        fp = self._abs(path)
        os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
        if isinstance(data, str):
            data = data.encode()
        mode = "ab" if append else "wb"
        with open(fp, mode) as f:
            f.write(data)
        return {"ok": True, "size": len(data)}

    async def http(self, method, url, headers=None, body=None):
        return {"ok": False, "error": "local dryrun has no MCP relay"}
