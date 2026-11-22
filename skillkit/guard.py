#!/usr/bin/env python3
"""Deliverable guard: runs skills/_shared/validate.py inside the task container."""
import json, os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
VALIDATE = os.path.join(ROOT, "_shared", "validate.py")
SPEC_PATH = "/tmp/ple_spec.json"
VALID_PATH = "/tmp/ple_validate.py"


class Guard:
    def __init__(self, transport, base, spec, log=None):
        self.t = transport
        self.base = base or "/app"
        self.spec = dict(spec or {})
        self.spec.setdefault("deep", True)
        self.log = log or (lambda t: None)
        self._installed = False

    async def _install(self):
        if self._installed:
            return
        src = open(VALIDATE, "rb").read()
        await self.t.write_file(VALID_PATH, src)
        self._installed = True

    async def run(self):
        if not self.spec.get("deliverable"):
            return "SKIP", "no deliverable path resolved from the instruction"
        await self._install()
        await self.t.write_file(SPEC_PATH, json.dumps(self.spec).encode())
        r = await self.t.exec(
            f"python3 {VALID_PATH} --base {self.base} --spec {SPEC_PATH}", 120)
        out = r.get("output", "")
        status = "ERROR"
        for line in out.splitlines():
            if line.startswith("RESULT:"):
                head = line.split(":")[1].strip()
                status = "FAIL" if head.startswith("FAIL") else (
                    "WARN" if head.startswith("WARN") else "PASS")
        if r.get("exit_code") == 124:
            status = "ERROR"
        return status, out[-1800:]
