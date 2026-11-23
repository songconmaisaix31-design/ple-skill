"""Rebuild the F/G archive by substituting the whole retry job for the incomplete pair."""
import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from verify_paired_storage_evidence import INPUTS, OUTPUTS, digest, verify_arm


REVISION = "9c1a00a40c8e40212ea1e97c93824366889ddb8e"
FIRST_ATTEMPT = "7cc6c7ed0a3b776879e72fd687aea5367baa268914b41fecfb58603eee538240"
ARMS = ("text", "text-source")
MEMBERS = ("metadata.json", "report.json", "model-io.jsonl",
           *("case/" + name for name in INPUTS), *("case/output/" + name for name in OUTPUTS))


def check_attempt(archive, pairs, protocol, protocol_hash):
    names = archive.namelist()
    allowed = {f"{case}/{repeat}/{arm}/{name}" for case, repeat in pairs
               for arm in ARMS for name in MEMBERS}
    if len(names) != len(set(names)) or set(names) - allowed:
        raise ValueError("duplicate or unexpected archive member")
    incomplete = set()
    for case, repeat in pairs:
        for arm in ARMS:
            row, _ = verify_arm(archive, protocol, protocol_hash, case, repeat, arm)
            if row["git_sha"] != REVISION:
                raise ValueError(f"{case}/{repeat}/{arm}: missing metadata or wrong revision")
            if not row["measured"]:
                incomplete.add((case, repeat))
    return incomplete


def rebuild(first_bytes, retry_bytes, protocol_bytes):
    if digest(first_bytes) != FIRST_ATTEMPT:
        raise ValueError("first attempt differs from the published archive")
    protocol = json.loads(protocol_bytes)
    if protocol["id"] != "repair-source-v1":
        raise ValueError("unexpected experiment")
    pairs = [(case, repeat) for case in protocol["split"]["holdout"]
             for repeat in protocol["design"]["repetition_ids"]]
    protocol_hash = digest(protocol_bytes)
    output = BytesIO()
    with ZipFile(BytesIO(first_bytes)) as first, ZipFile(BytesIO(retry_bytes)) as retry:
        incomplete = check_attempt(first, pairs, protocol, protocol_hash)
        if len(incomplete) != 1 or check_attempt(retry, incomplete, protocol, protocol_hash):
            raise ValueError("expected one incomplete original pair and its complete job retry")
        with ZipFile(output, "w") as merged:
            for case, repeat in pairs:
                archive = retry if (case, repeat) in incomplete else first
                for arm in ARMS:
                    for member in MEMBERS:
                        path = f"{case}/{repeat}/{arm}/{member}"
                        if path in archive.NameToInfo:
                            info = ZipInfo(path, date_time=(2026, 11, 24, 0, 0, 0))
                            info.compress_type = ZIP_DEFLATED
                            info.create_system = 3
                            info.external_attr = 0o100644 << 16
                            merged.writestr(info, archive.read(path))
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "retry", "protocol", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        data = rebuild(args.first.read_bytes(), args.retry.read_bytes(), args.protocol.read_bytes())
        with args.output.open("xb") as out:
            out.write(data)
    except (BadZipFile, OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(f"{digest(data)}  {args.output}")


if __name__ == "__main__":
    main()
