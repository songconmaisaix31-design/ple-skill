"""Archive the exact submission commit after the package job passes kit check."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def git(repo, *args, **kwargs):
    return subprocess.run(["git", "-C", repo, *args], check=True, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pack(entry, evidence):
    if json.loads((evidence / "kit-check.json").read_bytes()).get("ready") is not True:
        raise ValueError("kit check did not pass")
    scores = json.loads((evidence / "submission-scores.json").read_bytes())
    if not scores.get("usable", 0):
        raise ValueError("there is no verified file regrade")
    if git(entry, "status", "--porcelain", "--untracked-files=no", capture_output=True).stdout:
        raise ValueError("tracked entry differs from its verified commit")
    commit = git(entry, "rev-parse", "--verify", "HEAD", capture_output=True, text=True).stdout.strip()
    archive = evidence / "submission.tar.gz"
    bundle = evidence / "submission.bundle"
    git(entry, "archive", "--format=tar.gz", "-o", archive, commit)
    with gzip.open(archive, "rb") as stream:
        # git archive puts the commit identifier in the first global pax header.
        header = stream.read(1024)
    embedded = git(entry, "get-tar-commit-id", input=header, capture_output=True).stdout.decode().strip()
    if embedded != commit:
        raise ValueError("archive does not identify the checked commit")
    # The release entry is a fresh repository containing the runtime and reviewed
    # artifacts. Keep its original Git objects so the same SHA can be published.
    git(entry, "bundle", "create", bundle, "HEAD")
    git(entry, "bundle", "verify", bundle, capture_output=True)
    heads = git(entry, "bundle", "list-heads", bundle, capture_output=True, text=True).stdout.splitlines()
    if heads != [commit + " HEAD"]:
        raise ValueError("bundle head differs from the checked commit")
    sha = digest(archive)
    (evidence / "submission.sha256").write_text(sha + "\n")
    (evidence / "submission-identity.json").write_text(json.dumps({
        "competition_model_verified": False,
        "generation_backends": {task: row.get("generation_backend", "unverified")
                                for task, row in scores.get("by_task", {}).items()},
        "submission_commit": commit, "submission_tar_sha256": sha,
        "submission_bundle_sha256": digest(bundle),
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    pack(args.entry.resolve(), args.evidence.resolve())
