"""Independently replay and audit the frozen L/M native-patch evidence."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from verify_paired_storage_evidence import digest, load_json, read, replay, require


CASES = ("l", "m")
REPEATS = (1, 2, 3)
ARMS = ("patch-source", "native-patch")
PROGRAM_SHA = "f4ece9d6d7e41e93f364db640b51b50c12c947ce1639fd2af991007dd76364f2"
PATCH_MARKER = "Repair action contract: reply with exactly one compact JSON object"
FENCE = re.compile(r"```python\n(.*?)\n```", re.S)
FIELDS = (
    "case", "repeat", "arm", "order", "seed", "score", "feasible", "optimal",
    "measured", "submitted_cost_cents", "evidence_status", "transcript_complete",
    "requests_archived", "responses_archived", "git_sha", "repair_requested",
    "source_feedback_observed", "source_line", "completed_files",
    "controlled_release_sec", "repair_dispatch_sec", "controlled_timing_valid",
    "repair_response_completed", "prompt_patch_interface_used",
    "native_patch_interface_used", "request_shape_valid", "patch_responses_completed",
    "patch_attempts", "patch_accepted", "tool_responses", "native_tool_responses",
    "native_argument_schema_valid", "native_unindented_replacements",
    "nonempty_text_responses", "length_finished_responses",
)


def virtual_protocol(protocol, inherited):
    result = json.loads(json.dumps(inherited))
    result["id"] = "repair-source-v1"
    result["split"]["holdout"] = list(protocol["split"]["new_diagnostic_inputs"])
    result["split"]["cases"] = {
        case: {"split": "holdout", "sha256": protocol["cases"][case]["input_sha256"]}
        for case in CASES
    }
    result["design"]["repetition_ids"] = list(REPEATS)
    result["design"]["first_arm"] = protocol["design"]["first_arm"]
    return result


def parse_transcript(data, summary, arm, source):
    records = [json.loads(line) for line in data.splitlines()]
    require(records and records[-1].get("event") == "end", "transcript lacks end record")
    end, records = records[-1], records[:-1]
    require(end == {"event": "end", **summary} and end.get("complete") is True,
            "transcript end disagrees with report")
    requests, responses, statuses, patches = {}, {}, {}, []
    generated = []
    for record in records:
        event, call = record.get("event"), record.get("call")
        require(type(call) is int and call > 0, "invalid call ID")
        if event == "request":
            require(call not in requests, "duplicate request")
            requests[call] = record
        elif event == "response":
            require(call not in responses, "duplicate response")
            responses[call] = record
            for choice in record.get("choices") or []:
                message = choice.get("message") or {}
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call.get("function") or {}
                    if function.get("name") == "run_python" and isinstance(function.get("arguments"), str):
                        generated.append({"call": call, "interface": "run_python_arguments",
                                          "sha256": digest(function["arguments"].encode())})
        elif event == "status":
            require(call not in statuses, "duplicate status")
            statuses[call] = record
        elif event == "patch_application":
            patches.append(record)
        else:
            raise ValueError(f"unexpected transcript event {event!r}")
    require(set(requests) == set(range(1, end["requests"] + 1)), "request sequence is incomplete")
    require(requests.keys() == statuses.keys(), "request/status coverage differs")
    require(all(call in responses for call, row in statuses.items()
                if row.get("status") == "complete" and row.get("http_status") == 200),
            "completed request lacks response")
    first = responses.get(1)
    require(first and first.get("scripted") is True, "scripted first response missing")
    text = first["choices"][0]["message"].get("content")
    matched = FENCE.fullmatch(text or "")
    require(matched and digest(matched[1].encode()) == PROGRAM_SHA, "frozen first program changed")
    require(source == matched[1], "source mismatch")

    repair = requests.get(2)
    require(repair is not None, "repair request missing")
    messages = repair["body"].get("messages") or []
    require(len(messages) >= 3, "repair prompt lacks observation")
    observation = messages[2].get("content")
    lines = source.splitlines()
    expected_excerpt = "\n\nFirst program source near traceback line 81:\n" + "\n".join(
        f"{number}: {lines[number - 1]}" for number in range(79, 84))
    require(isinstance(observation, str) and observation.endswith(expected_excerpt),
            "repair request lacks exact frozen five-line excerpt")
    require('File "<run_python>", line 81, in <genexpr>' in observation,
            "repair traceback lacks frozen inner frame")
    release = responses[1].get("end_sec")
    dispatch = repair.get("start_sec")
    require(type(release) in (int, float) and type(dispatch) in (int, float)
            and abs(release - 250) <= 2 and release <= dispatch <= release + 5,
            "release/dispatch timing violates protocol")

    live_requests = [row for call, row in requests.items() if call >= 2]
    prompt_flags = [PATCH_MARKER in str((row["body"].get("messages") or [{}])[0].get("content", ""))
                    for row in live_requests]
    expected_general = ["exec", "run_python", "read_file", "write_file", "mcp_call", "finish"]
    request_shape = []
    for row in live_requests:
        body = row["body"]
        tools = [((item.get("function") or {}).get("name")) for item in body.get("tools") or []]
        if arm == "native-patch":
            function = ((body.get("tools") or [{}])[0].get("function") or {})
            parameters = function.get("parameters") or {}
            valid = (not any(prompt_flags) and tools == ["replace_line"]
                     and body.get("tool_choice") == "required"
                     and parameters.get("required") == ["line", "replacement"]
                     and parameters.get("additionalProperties") is False)
        else:
            valid = (all(prompt_flags) and tools == expected_general
                     and body.get("tool_choice") == "auto")
        request_shape.append(valid and body.get("max_tokens") == 96)
    require(all(request_shape), "live request shape disagrees with assigned arm")
    complete_live = [call for call, row in statuses.items()
                     if call >= 2 and row.get("status") == "complete" and row.get("http_status") == 200]
    tool_responses = 0
    native_tool_responses = 0
    native_argument_schema_valid = 0
    native_unindented_replacements = 0
    nonempty_text = 0
    length_finished = 0
    for call, response in responses.items():
        if call < 2:
            continue
        for choice in response.get("choices") or []:
            message = choice.get("message") or {}
            calls = message.get("tool_calls") or []
            tool_responses += int(bool(calls))
            if arm == "native-patch" and len(calls) == 1:
                function = calls[0].get("function") or {}
                if function.get("name") == "replace_line":
                    native_tool_responses += 1
                    try:
                        arguments = json.loads(function.get("arguments"))
                    except (json.JSONDecodeError, TypeError):
                        arguments = None
                    if (isinstance(arguments, dict) and set(arguments) == {"line", "replacement"}
                            and arguments.get("line") == 81
                            and isinstance(arguments.get("replacement"), str)
                            and 0 < len(arguments["replacement"]) <= 160
                            and "\n" not in arguments["replacement"]
                            and "\r" not in arguments["replacement"]):
                        native_argument_schema_valid += 1
                        native_unindented_replacements += int(
                            arguments["replacement"] == arguments["replacement"].strip())
            nonempty_text += int(bool(str(message.get("content") or "")))
            length_finished += int(choice.get("finish_reason") == "length")
    require(len(patches) == len(complete_live), "patch decisions do not cover completed live responses")
    require(all(type(row.get("accepted")) is bool for row in patches), "invalid patch decision")
    return {
        "transcript_complete": 1,
        "requests_archived": len(requests),
        "responses_archived": len(responses),
        "repair_requested": 1,
        "source_feedback_observed": 1,
        "source_line": 81,
        "controlled_release_sec": release,
        "repair_dispatch_sec": dispatch,
        "controlled_timing_valid": 1,
        "repair_response_completed": int(2 in complete_live),
        "prompt_patch_interface_used": int(arm == "patch-source"),
        "native_patch_interface_used": int(arm == "native-patch"),
        "request_shape_valid": 1,
        "patch_responses_completed": len(complete_live),
        "patch_attempts": len(patches),
        "patch_accepted": sum(row.get("accepted") is True for row in patches),
        "tool_responses": tool_responses,
        "native_tool_responses": native_tool_responses,
        "native_argument_schema_valid": native_argument_schema_valid,
        "native_unindented_replacements": native_unindented_replacements,
        "nonempty_text_responses": nonempty_text,
        "length_finished_responses": length_finished,
    }, generated


def verify_arm(archive, protocol, frozen, protocol_hash, case, repeat, arm):
    prefix = f"{case}/{repeat}/{arm}/"
    metadata = load_json(archive, prefix + "metadata.json")
    report = load_json(archive, prefix + "report.json")
    require(metadata is not None and report is not None, "metadata/report missing")
    first = protocol["design"]["first_arm"][case][str(repeat)]
    order = 1 if arm == first else 2
    for key, value in {"variant": case, "repeat": repeat, "mode": arm, "order": order,
                       "first_mode": first, "seed": 17, "temperature": 0,
                       "git_sha": "b5d9defd791a22ad175d078d7aa6b055881fa73c"}.items():
        require(metadata.get(key) == value, f"metadata {key} differs from frozen assignment")
    hashes = protocol["cases"][case]["input_sha256"]
    require(metadata.get("protocol_sha256") == protocol_hash, "protocol hash mismatch")
    require(metadata.get("protocol_input_sha256") == hashes, "protocol input hashes mismatch")
    actual = {}
    for name, expected in hashes.items():
        data = read(archive, prefix + "case/" + name, 65536)
        require(data is not None and digest(data) == expected, f"input mismatch: {name}")
        actual[name] = digest(data)
    require(metadata.get("input_sha256") == actual and metadata.get("input_matches_protocol") is True,
            "recorder input verification mismatch")
    require(metadata.get("repair_context_exposed") is True and metadata.get("repair_requested") is True,
            "recorder repair exposure mismatch")
    require(metadata.get("controlled_first_program_valid") is True
            and metadata.get("controlled_timing_valid") is True, "recorder controlled checks failed")
    source = None
    transcript_data = read(archive, prefix + "model-io.jsonl", 2 * 1024 * 1024 + 512)
    for line in transcript_data.splitlines():
        record = json.loads(line)
        if record.get("event") == "response" and record.get("call") == 1:
            match = FENCE.fullmatch(record["choices"][0]["message"].get("content") or "")
            source = match[1] if match else None
            break
    require(source is not None, "first source unavailable")
    details, generated = parse_transcript(transcript_data, report["model_io_archive"], arm, source)
    require(metadata.get("patch_interface_used") is True,
            "recorder patch-interface state mismatch")
    require(bool(details["prompt_patch_interface_used"]) is metadata.get("prompt_patch_interface_used"),
            "recorder prompt-interface state mismatch")
    require(bool(details["native_patch_interface_used"]) is metadata.get("native_patch_interface_used"),
            "recorder native-interface state mismatch")
    require(report.get("first_code_action", {}).get("classification") == "exec_failed"
            and report["first_code_action"].get("exec_exit_status") == 1,
            "common first failure changed")
    checkpoint = report.get("checkpoint") or {}
    require(checkpoint.get("measured") is True and checkpoint.get("target_sec") == 395,
            "checkpoint was not measured at t=395")
    require(math.isfinite(checkpoint.get("start_sec")) and checkpoint["start_sec"] >= 394.999,
            "checkpoint clock mismatch")
    verified = replay(archive, prefix, case, report["inventory"], hashes)
    recorded = report.get("grade") or {}
    for field in ("score", "optimal", "feasible", "submitted_cost_cents", "optimal_cost_cents"):
        require(recorded.get(field) == verified[field], f"independent grade mismatch: {field}")
    require(metadata.get("observation") is True and metadata.get("exit_code") == int(not verified["optimal"]),
            "measurement/exit state mismatch")
    folder = prefix + "case/output/"
    completed_files = sum(folder + name in archive.namelist() and archive.getinfo(folder + name).file_size > 0
                          for name in ("schedule.csv", "summary.json"))
    row = {field: None for field in FIELDS}
    row.update(case=case, repeat=repeat, arm=arm, order=order, seed=17,
               score=verified["score"], feasible=int(verified["feasible"]),
               optimal=int(verified["optimal"]), measured=1,
               submitted_cost_cents=verified["submitted_cost_cents"],
               evidence_status="regraded", git_sha=metadata["git_sha"],
               completed_files=completed_files, **details)
    return row, generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--settings-protocol", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--details", required=True, type=Path)
    args = parser.parse_args()
    try:
        protocol_bytes = args.protocol.read_bytes()
        protocol = json.loads(protocol_bytes)
        require(protocol.get("id") == "native-patch-v1", "wrong protocol")
        frozen = virtual_protocol(protocol, json.loads(args.settings_protocol.read_bytes()))
        rows, generated = [], {}
        with ZipFile(args.archive) as archive:
            counts = Counter(archive.namelist())
            require(not any(value > 1 for value in counts.values()), "duplicate ZIP member")
            for case in CASES:
                for repeat in REPEATS:
                    for arm in ARMS:
                        label = f"{case}/{repeat}/{arm}"
                        try:
                            row, programs = verify_arm(
                                archive, protocol, frozen, digest(protocol_bytes), case, repeat, arm)
                        except (ValueError, TypeError, KeyError, IndexError) as error:
                            raise ValueError(f"{label}: {error}") from error
                        rows.append(row)
                        generated[label] = programs
        with args.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        coverage = {
            "planned": 12,
            "regraded": len(rows),
            "complete_transcripts": sum(row["transcript_complete"] for row in rows),
            "source_exposures": sum(row["source_feedback_observed"] for row in rows),
            "prompt_interface_uses": sum(row["prompt_patch_interface_used"] for row in rows),
            "native_interface_uses": sum(row["native_patch_interface_used"] for row in rows),
            "request_shapes_valid": sum(row["request_shape_valid"] for row in rows),
            "candidate_patch_attempts": sum(row["patch_attempts"] for row in rows
                                              if row["arm"] == "native-patch"),
            "candidate_accepted_patches": sum(row["patch_accepted"] for row in rows
                                               if row["arm"] == "native-patch"),
            "candidate_native_tool_responses": sum(row["native_tool_responses"] for row in rows),
            "candidate_argument_schema_valid": sum(row["native_argument_schema_valid"] for row in rows),
            "candidate_unindented_replacements": sum(row["native_unindented_replacements"] for row in rows),
            "git_shas": sorted({row["git_sha"] for row in rows}),
            "generated_response_hashes": generated,
        }
        args.details.write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in coverage.items()
                          if key != "generated_response_hashes"}))
    except (OSError, BadZipFile, ValueError, TypeError, KeyError, csv.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
