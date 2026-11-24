"""Re-export a captured task without the optional trajectory, preserving the scored bytes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

from official_export import ENTRY, TEMP, kit, sha256, write


def digest_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def score_files(folder):
    return {p.relative_to(folder).as_posix(): sha256(p) for p in folder.rglob("*")
            if p.is_file() and p.relative_to(folder).as_posix() != "trajectory.json"}


def zip_members(path):
    # Plain zip bundles can wrap original PDFs, spreadsheets and text inputs.
    # Office documents are compared as complete files, not by shared XML boilerplate.
    if path.suffix.lower() != ".zip":
        return
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 10000 or sum(m.file_size for m in members) > 512 * 1024 ** 2:
            raise ValueError("Bundle exceeds the bounded publication inspection.")
        for member in members:
            if not member.is_dir() and member.file_size >= 128:
                with archive.open(member) as stream:
                    yield digest_stream(stream)


def contains_original(outputs, inputs):
    originals = set()
    for path in inputs.rglob("*"):
        if path.is_file() and path.stat().st_size >= 128:
            originals.add(sha256(path))
            originals.update(zip_members(path))
    instruction = inputs / "instruction.md"
    prompt = instruction.read_bytes().strip() if instruction.is_file() else b""
    for path in outputs.rglob("*"):
        if not path.is_file():
            continue
        if sha256(path) in originals or any(d in originals for d in zip_members(path)):
            return True
        if len(prompt) >= 128 and path.suffix.lower() in (".md", ".txt", ".json", ".py", ".csv"):
            if prompt in path.read_bytes():
                return True
    return False


def prepare(task):
    run = TEMP / "run"
    original = run / "artifacts" / task
    witness = {"task": task, "original_export": original.is_dir(), "scored_files_identical": False,
               "trajectory_omitted": False, "original_input_check": "pending"}
    write("publication.json", witness)
    if not original.is_dir():
        raise SystemExit("No original official capture to re-export.")
    record = json.loads((run / "export.json").read_bytes())
    if len(record["rows"]) != 1 or record["rows"][0]["task"] != task or not record["rows"][0]["trial"]:
        raise SystemExit("Expected exactly one source trial in the official export record.")
    trial = Path(record["rows"][0]["trial"])
    if trial.is_absolute() or ".." in trial.parts or not trial.parts:
        raise SystemExit("Trial is outside the recorded run.")
    cap = run / trial / "deliverables"
    if not cap.is_dir() or cap.is_symlink() or any(p.is_symlink() for p in cap.rglob("*")):
        raise SystemExit("The original capture is missing or contains links.")
    with tempfile.TemporaryDirectory(dir=TEMP) as temp:
        pared = Path(temp)
        shutil.copy2(run / "export.json", pared / "export.json")
        shutil.copytree(cap, pared / trial / "deliverables", copy_function=os.link)
        # The official tool rebuilds its own manifest from the unchanged record and
        # capture. The source run is intact. No agent/trajectory.json enters staging.
        kit("artifacts", ENTRY, "--from", pared, capture=True)
    exported = ENTRY / "artifacts" / task
    same = score_files(original) == score_files(exported)
    witness.update(scored_files_identical=same, trajectory_omitted=not (exported / "trajectory.json").exists(),
                   source_contained_trajectory=(original / "trajectory.json").is_file())
    write("publication.json", witness)
    if not same or not witness["trajectory_omitted"]:
        raise SystemExit("Re-export altered a scored file or included a trajectory.")
    try:
        restricted = contains_original(exported, TEMP / "ple-data/tasks" / task)
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
        witness["original_input_check"] = "inspection failed"
        write("publication.json", witness)
        raise SystemExit("Could not inspect a deliverable or source archive. Public export withheld.") from None
    witness["original_input_check"] = "duplicate found" if restricted else "passed"
    write("publication.json", witness)
    if restricted:
        raise SystemExit("A deliverable contains a complete restricted source file. Public export withheld.")


if __name__ == "__main__":
    prepare(sys.argv[1])
