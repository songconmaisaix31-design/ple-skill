"""Independently replay the preregistered H/I controlled-repair evidence."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from verify_paired_storage_evidence import (
    FENCE, FIELDS, REPAIR_FIELDS, SHA, digest, load_json, read, require, verify_arm,
)


ARMS = ("text", "text-source")
CONTROLLED_FIELDS = (
    "controlled_first_program_valid", "controlled_release_sec", "repair_dispatch_sec",
    "controlled_timing_valid", "repair_response_completed",
)
PROGRAM_SHA = "f4ece9d6d7e41e93f364db640b51b50c12c947ce1639fd2af991007dd76364f2"


def virtual_protocol(protocol, inherited):
    require(protocol["id"] == "controlled-repair-replay-v1", "wrong experiment protocol")
    require(digest(Path(protocol["_settings_path"]).read_bytes())
            == protocol["inherits"]["settings_protocol_sha256"], "inherited settings protocol changed")
    result = json.loads(json.dumps(inherited))
    result["id"] = "repair-source-v1"
    result["split"]["holdout"] = list(protocol["split"]["new_diagnostic_inputs"])
    result["split"]["cases"] = {
        case: {"split": "holdout", "sha256": protocol["cases"][case]["input_sha256"]}
        for case in result["split"]["holdout"]
    }
    result["design"]["repetition_ids"] = [1, 2, 3]
    result["design"]["first_arm"] = protocol["design"]["first_arm"]
    return result


def controlled_checks(zf, prefix, row, metadata, report, arm):
    require(metadata.get("repair_requested") is True, "repair request was not observed")
    require(metadata.get("controlled_first_program_valid") is True, "controlled first program was not verified")
    require(metadata.get("controlled_timing_valid") is True, "controlled timing window was not verified")
    release = metadata.get("controlled_release_sec")
    dispatch = metadata.get("repair_dispatch_sec")
    require(type(release) in (int, float) and type(dispatch) in (int, float),
            "controlled timing values missing")
    require(abs(release - 250) <= 2 and release <= dispatch <= release + 5,
            "controlled timing values violate the preregistration")
    require(row["repair_requested"] == 1, "archived prompt lacks a repair request")
    require(row["source_feedback_observed"] == int(arm == "text-source"),
            "source exposure disagrees with assigned arm")
    action = (report or {}).get("first_code_action") or {}
    require(action.get("mode") == "text" and action.get("classification") == "exec_failed"
            and action.get("exec_exit_status") == 1, "common first program did not reproduce the frozen failure")

    data = read(zf, prefix + "model-io.jsonl", 2 * 1024 * 1024 + 512)
    records = [json.loads(line) for line in data.splitlines()]
    first = [record for record in records if record.get("event") == "response"
             and record.get("call") == 1 and record.get("scripted") is True]
    require(len(first) == 1, "scripted first response is missing or duplicated")
    source = first[0]["choices"][0]["message"].get("content")
    match = FENCE.fullmatch(source.strip()) if isinstance(source, str) else None
    require(match and hashlib.sha256(match[1].encode()).hexdigest() == PROGRAM_SHA,
            "scripted source bytes disagree with the frozen program")
    statuses = {record.get("call"): record for record in records if record.get("event") == "status"}
    responses = {record.get("call"): record for record in records if record.get("event") == "response"}
    repair_completed = int(
        2 in responses and statuses.get(2, {}).get("status") == "complete"
        and statuses[2].get("http_status") == 200
    )
    row.update(controlled_first_program_valid=1, controlled_release_sec=release,
               repair_dispatch_sec=dispatch, controlled_timing_valid=1,
               repair_response_completed=repair_completed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--settings-protocol", required=True, type=Path)
    parser.add_argument(
        "--expected-sha", required=True, action="append",
        help="allowed immutable Actions revision; repeat for a preregistered technical retry",
    )
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--details", type=Path)
    args = parser.parse_args()
    try:
        protocol_bytes = args.protocol.read_bytes()
        protocol = json.loads(protocol_bytes)
        protocol["_settings_path"] = str(args.settings_protocol)
        inherited = json.loads(args.settings_protocol.read_bytes())
        frozen = virtual_protocol(protocol, inherited)
        protocol_hash = digest(protocol_bytes)
        expected_revisions = set(args.expected_sha)
        require(all(SHA.fullmatch(revision) for revision in expected_revisions),
                "expected revision must be a full SHA")
        rows, programs = [], {}
        with ZipFile(args.archive) as archive:
            counts = Counter(archive.namelist())
            require(not any(count > 1 for count in counts.values()), "duplicate ZIP member")
            for case in protocol["split"]["new_diagnostic_inputs"]:
                for repeat in (1, 2, 3):
                    for arm in ARMS:
                        prefix = f"{case}/{repeat}/{arm}/"
                        label = prefix.rstrip("/")
                        try:
                            row, sources = verify_arm(
                                archive, frozen, protocol_hash, case, repeat, arm)
                            metadata = load_json(archive, prefix + "metadata.json")
                            report = load_json(archive, prefix + "report.json")
                            require(row["measured"] == 1 and metadata is not None and report is not None,
                                    "controlled arm is unmeasured")
                            controlled_checks(archive, prefix, row, metadata, report, arm)
                        except (ValueError, TypeError, KeyError, IndexError) as error:
                            raise ValueError(f"{label}: {error}") from error
                        rows.append(row)
                        programs[label] = sources
        revisions = {row["git_sha"] for row in rows}
        require(revisions and revisions <= expected_revisions, "run revision mismatch")
        fields = FIELDS + REPAIR_FIELDS + CONTROLLED_FIELDS
        with args.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        summary = {
            "planned": len(rows),
            "regraded": sum(row["measured"] for row in rows),
            "complete_transcripts": sum(row["transcript_complete"] for row in rows),
            "candidate_source_exposures": sum(
                row["source_feedback_observed"] for row in rows if row["arm"] == "text-source"),
            "baseline_source_exposures": sum(
                row["source_feedback_observed"] for row in rows if row["arm"] == "text"),
            "completed_repair_responses": {
                arm: sum(row["repair_response_completed"] for row in rows if row["arm"] == arm)
                for arm in ARMS
            },
            "git_shas": sorted(revisions),
        }
        if args.details:
            args.details.write_text(json.dumps({**summary, "programs": programs}, indent=2) + "\n")
        print(json.dumps(summary))
        return int(summary["regraded"] != 12 or summary["candidate_source_exposures"] != 6
                   or summary["baseline_source_exposures"] != 0)
    except (OSError, BadZipFile, ValueError, TypeError, KeyError, csv.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())

