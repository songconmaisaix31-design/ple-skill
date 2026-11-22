#!/usr/bin/env python3
"""Offline dryrun: exercises the loop, the guard and the finish-refusal path
without Docker and without a model key.

Sequence the stub plays, on purpose including a bad path:
  1 exec (explore)  2 write an empty file at the contract path
  3 finish            -> guard FAIL -> refused
  4 exec (fix: build a real docx)
  5 finish            -> guard PASS -> done

The stub issues only `python helper.py <verb> <args>` commands, so the dryrun
behaves the same on Windows hosts and inside the Linux evaluation container.
"""
import argparse, asyncio, os, shutil, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skillkit.harness import Harness
from skillkit.transport import LocalTransport, quote_path
from skillkit import specgen

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

HELPER = '''
import os, sys
verb = sys.argv[1]
if verb == "probe":
    print("cwd:", os.getcwd())
    print("entries:", ", ".join(sorted(os.listdir("."))[:40]) or "(empty)")
elif verb == "touch":
    p = sys.argv[2]
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    open(p, "wb").close()
    print("touched", p)
elif verb == "copy":
    src, dst = sys.argv[2], sys.argv[3]
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(src, "rb") as a:
        data = a.read()
    with open(dst, "wb") as b:
        b.write(data)
    print("copied", src, "->", dst, len(data), "bytes")
'''


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
    def __init__(self, target, src_docx, helper):
        self.target, self.src, self.helper, self.n = target, src_docx, helper, 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
        self.py = quote_path(sys.executable)
        self.h = quote_path(helper)

    def _cmd(self, verb, *args):
        parts = [self.py, self.h, verb] + [quote_path(a) for a in args]
        return " ".join(parts)

    async def chat(self, messages, system, tools=None):
        self.n += 1
        i = self.n

        def call(name, **a):
            return {"content": "", "usage": {}, "tool_calls": [
                {"id": f"s{i}", "name": name, "arguments": a}]}

        if i == 1:
            return call("exec", command=self._cmd("probe"))
        if i == 2:
            return call("exec", command=self._cmd("touch", self.target))
        if i == 3:
            return call("finish", final_message="Done, the file is there.")
        if i == 4:
            return call("exec", command=self._cmd("copy", self.src, self.target))
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
    helper = os.path.join(tmp, "_ple_stub_helper.py")
    with open(helper, "w", encoding="utf-8") as f:
        f.write(HELPER)
    src_docx = os.path.join(tmp, "_ple_stub_docx.docx")
    fake_docx(src_docx)

    print(f"workdir    : {tmp}")
    print(f"deliverable: {rel}  mode={spec['mode']} conf={spec['confidence']}")

    h = Harness(LocalTransport(tmp), StubModel(target, src_docx, helper),
                inst, workdir=tmp, log=print, spec_override=spec)
    final = await h.run(timeout_sec=120)
    print("\n=== FINAL MESSAGE ===")
    print(final[:1200])
    print(f"\nsteps={h.steps}  file exists={os.path.exists(target)}")
    return 0 if os.path.exists(target) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
