#!/usr/bin/env python3
"""Deliverable guard: runs skills/_shared/validate.py inside the task container."""
import json, os

from .transport import quote_path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
VALIDATE = os.path.join(ROOT, "_shared", "validate.py")


class Guard:
    def __init__(self, transport, base, spec, log=None):
        self.t = transport
        self.base = base or "/app"
        self.spec = dict(spec or {})
        self.spec.setdefault("deep", True)
        self.log = log or (lambda t: None)
        self._installed = False
        self._valid_path = None

    async def _install(self):
        if self._installed:
            return
        src = open(VALIDATE, "rb").read()
        # Scratch location is transport-specific: /tmp in the task container,
        # a real writable directory in the offline dryrun (Windows friendly).
        self._valid_path = self.t.scratch_path("validate.py")
        await self.t.write_file(self._valid_path, src)
        self._installed = True

    async def run(self):
        if not self.spec.get("deliverable"):
            return "SKIP", "no deliverable path resolved from the instruction"
        await self._install()
        spec_path = self.t.scratch_path("spec.json")
        await self.t.write_file(spec_path, json.dumps(self.spec).encode())
        cmd = "{py} {script} --base {base} --spec {spec}".format(
            py=quote_path(self.t.python_cmd),
            script=quote_path(self._valid_path),
            base=quote_path(self.base),
            spec=quote_path(spec_path))
        r = await self.t.exec(cmd, 120)
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
