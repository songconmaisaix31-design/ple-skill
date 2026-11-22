#!/usr/bin/env python3
"""Offline dryrun: exercises the loop, the guard and the finish-refusal path
without Docker and without a model key.

Sequence the stub plays, on purpose including a bad path:
  1 exec (explore)  2 write an empty file at the contract path
  3 finish            -> guard FAIL -> refused
  4 exec (fix: build a real docx)
  5 finish            -> guard PASS -> done
"""
import argparse, asyncio, os, shutil, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skillkit.harness import Harness
from skillkit.transport import LocalTransport
from skillkit import specgen

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def fake_docx(path, paras=9):
    body = "".join(f"<w:p><w:r><w:t>Paragraph {i+1}: placeholder engineering content.</w:t></w:r></w:p>"
                   for i in range(paras))
    doc = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types"><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
          'officedocument.wordprocessingml.document.main+xml"/></Types>')
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("word/document.xml", doc)


class StubModel:
    def __init__(self, target, src_docx):
        self.target, self.src, self.n = target, src_docx, 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}

    async def chat(self, messages, system, tools=None):
        self.n += 1
        i = self.n

        def call(name, **a):
            return {"content": "", "usage": {}, "tool_calls": [
                {"id": f"s{i}", "name": name, "arguments": a}]}

        if i == 1:
            return call("exec", command="ls -la; echo '--- task.md ---'; cat task.md 2>/dev/null | head -40")
        if i == 2:
            return call("exec", command=f"mkdir -p $(dirname '{self.target}') && : > '{self.target}'")
        if i == 3:
            return call("finish", final_message="Done, the file is there.")
        if i == 4:
            return call("exec", command=f"cp {self.src} '{self.target}' && ls -l '{self.target}'")
        return call("finish", final_message=(
            f"What's in it: {os.path.basename(self.target)}\n"
            "What I decided: placeholder content written by the stub for the dryrun.\n"
            "Choices that could cost credit: all engineering values are placeholders here."))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instruction", help="file holding the task instruction")
    ap.add_argument("--artifact", help="template artifacts/<task> folder to seed the workdir")
    ap.add_argument("--dir", help="existing local directory as the workdir")
    a = ap.parse_args()

    tmp = a.dir and os.path.abspath(a.dir) or tempfile.mkdtemp(prefix="ple-dry-")
    if a.artifact:
        src = os.path.join(a.artifact, "files")
        for root, _, files in os.walk(src):
            for f in files:
                sp = os.path.join(root, f)
                dp = os.path.join(tmp, os.path.relpath(sp, src))
                os.makedirs(os.path.dirname(dp) or tmp, exist_ok=True)
                shutil.copy2(sp, dp)

    inst = open(a.instruction, encoding="utf-8").read() if a.instruction else (
        "Draft our reply as a Word letter and save it as /filesystem/Dryrun_Reply.docx. "
        "Work from the records in the workspace.")
    spec = specgen.build(inst)
    rel = (spec["deliverable"] or "output/answer.docx").lstrip("/")
    spec["deliverable"] = rel
    target = os.path.join(tmp, rel)
    fake_docx("/tmp/ple_stub_docx.docx")

    print(f"workdir    : {tmp}")
    print(f"deliverable: {rel}  mode={spec['mode']} conf={spec['confidence']}")

    h = Harness(LocalTransport(tmp), StubModel(target, "/tmp/ple_stub_docx.docx"),
                inst, workdir=tmp, log=print, spec_override=spec)
    final = await h.run(timeout_sec=120)
    print("\n=== FINAL MESSAGE ===")
    print(final[:1200])
    print(f"\nsteps={h.steps}  file exists={os.path.exists(target)}")
    return 0 if os.path.exists(target) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
