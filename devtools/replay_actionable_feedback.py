"""Regrade frozen rejection-feedback Actions bundles from the repository root."""
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path
from zipfile import ZipFile

from verify_paired_storage_evidence import replay, require
from verify_native_feedback_evidence import FENCE

ROOT = Path("docs/experiments/actionable-feedback-v1")
SHA = "33e9cf3e2338e0b140a5c9fb075d5de6b1ada172"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def trial(bundle, case, repeat, arm, protocol, protocol_hash, run_sha):
    prefix = arm + "/"

    def read(name):
        return bundle.read(prefix + name)

    meta = json.loads(read("metadata.json"))
    report = json.loads(read("report.json"))
    expected_first = protocol["design"]["first_arm"][case][str(repeat)]
    hashes = protocol["cases"][case]["input_sha256"]
    for key, value in dict(mode=arm, variant=case, repeat=repeat, first_mode=expected_first,
                           order=1 if arm == expected_first else 2, git_sha=run_sha, seed=17,
                           temperature=0, model="gemma-4-26b", protocol_sha256=protocol_hash).items():
        require(meta[key] == value, key)
    for name, expected in hashes.items():
        require(digest(read("case/" + name)) == expected, name)
    checkpoint = report["checkpoint"]
    require(checkpoint["measured"] and checkpoint["target_sec"] == 395
            and 394.999 <= checkpoint["start_sec"] < 396, "checkpoint")
    grade = replay(bundle, prefix, case, report["inventory"], hashes)
    require(grade == report["grade"], "file grade")
    rows = list(map(json.loads, read("model-io.jsonl").splitlines()))
    require(rows[-1] == {"event": "end", **report["model_io_archive"]}
            and rows[-1]["complete"] and not rows[-1]["omitted_records_or_fields"], "archive")
    requests = {r["call"]: r for r in rows if r["event"] == "request"}
    responses = {r["call"]: r for r in rows if r["event"] == "response"}
    require(set(requests) == set(range(1, rows[-1]["requests"] + 1)), "requests")
    source = FENCE.fullmatch(responses[1]["choices"][0]["message"]["content"])[1]
    require(digest(source.encode()) == protocol["source"]["controlled_source_sha256"], "common program")
    excerpt = "\n".join(f"{n}: {source.splitlines()[n-1]}" for n in range(79, 84))
    observation = requests[2]["body"]["messages"][2]["content"]
    require(observation.endswith(excerpt), "source exposure")
    if protocol["id"] == "actionable-name-error-v1":
        require("NameError: name 'pump_quantities' is not defined" in observation, "expected NameError")
    release = responses[1]["end_sec"]
    require(abs(release-250) <= 2 and release <= requests[2]["start_sec"] <= release+5, "release")
    feedback = {r["call"]: r for r in rows if r["event"] == "patch_feedback"}
    require(bool(feedback), "feedback missing")
    schemas = set()
    completed_retries = repeated = 0

    def arguments(call):
        raw = responses[call]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    for call, req in requests.items():
        if call == 1:
            continue
        body = req["body"]
        tool, = body["tools"]
        schemas.add(json.dumps(tool, sort_keys=True))
        require(tool["function"]["name"] == "replace_line" and body["tool_choice"] == "required"
                and body["max_tokens"] == 96, "request shape")
        messages = [m for m in body["messages"] if m["role"] == "tool" and m["content"].lstrip().startswith("{")]
        if call-1 in feedback:
            event = feedback[call-1]
            expected = {"accepted": False, "reason": event["reason"]}
            instruction = protocol["feedback_contract"]["instructions"][event["reason"]]
            if arm == "native-actionable":
                expected["instruction"] = instruction
            require(len(messages) == 1 and json.loads(messages[0]["content"]) == expected
                    and json.loads(event["content"]) == expected, "feedback payload")
            if call in responses:
                completed_retries += 1
                repeated += arguments(call) == arguments(call-1)
        else:
            require(not messages, "unassigned feedback")
    require(all(call+1 in requests for call in feedback), "missing retry")
    accepted = [r for r in rows if r["event"] == "patch_application" and r["accepted"]]
    calls = [arguments(c) for c in responses if c > 1]
    require(len(schemas) == 1, "tool schema drift")
    return dict(case=case, repeat=repeat, arm=arm, score=grade["score"], reason=grade["reason"],
                cost=grade["submitted_cost_cents"], feedback=len(feedback), completed_retries=completed_retries,
                repeated=repeated, calls=len(calls), unindented=sum(a["replacement"] == a["replacement"].strip() for a in calls if isinstance(a, dict) and isinstance(a.get("replacement"), str)),
                accepted=len(accepted), first_accepted_sec=accepted[0]["end_sec"] if accepted else None,
                schema_sha256=digest(schemas.pop().encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--replication", action="store_true", help="replay the R/S replication")
    selection.add_argument("--name-error", action="store_true", help="replay the T/U NameError test")
    args = parser.parse_args()
    root, run_sha = ROOT, SHA
    if args.replication:
        root = ROOT.with_name("actionable-replication-v1")
        run_sha = "96f19575311504ba4f4327e9ca6708bc3cd87a48"
    elif args.name_error:
        root = ROOT.with_name("actionable-name-error-v1")
        run_sha = "c33fff94fc0572bbf13f2ac24919838d2329a0c8"
    data = (root / "protocol.json").read_bytes()
    protocol = json.loads(data)
    manifest = json.loads((root / "attempts/manifest.json").read_text())
    rows, diffs = [], []
    for case in protocol["split"]["new_diagnostic_inputs"]:
        for repeat in (1, 2, 3):
            path = root / "attempts" / f"ple-replication-{case}-{repeat}-attempt-1.zip"
            require(digest(path.read_bytes()) == manifest[path.name]["sha256"], "artifact checksum")
            with ZipFile(path) as bundle:
                for arm in ("native-feedback", "native-actionable"):
                    rows.append(trial(bundle, case, repeat, arm, protocol, digest(data), run_sha))
            diffs.append(rows[-1]["score"] - rows[-2]["score"])
    require(len({r["schema_sha256"] for r in rows}) == 1, "cross-arm tool drift")
    with (root / "trials.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    macro = [statistics.mean(pair) for pair in zip(diffs[:3], diffs[3:])]
    print(macro, statistics.mean(macro), statistics.variance(macro))


if __name__ == "__main__":
    main()
