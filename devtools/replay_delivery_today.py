"""Read 18 frozen P–U experiment bundles and emit one 395-second file grade per arm."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from replay_actionable_feedback import FENCE, SHA, digest, require, trial

EXPERIMENTS = Path(__file__).resolve().parents[1] / 'docs/experiments'
STUDIES = {
    'actionable-feedback-v1': SHA,
    'actionable-replication-v1': '96f19575311504ba4f4327e9ca6708bc3cd87a48',
    'actionable-name-error-v1': 'c33fff94fc0572bbf13f2ac24919838d2329a0c8',
}
# This audited program closes both output files before printing the receipt below.
SAVED_PROGRAM = '00d8a53eeb28295f933918de0bd666952818b9b140e4cfef0cfbd655bb0f7226'
SAVED_RECEIPT = 'Optimization complete. Files saved to output/.\n'


def measure(bundle, case, repeat, arm, protocol, protocol_hash, revision):
    # Reuses the original independent on-disk grading and protocol checks.
    grade = trial(bundle, case, repeat, arm, protocol, protocol_hash, revision)
    report = json.loads(bundle.read(f'{arm}/report.json'))
    cutoff = report['checkpoint']['target_sec']
    actions = report['last_actions']
    require(Counter(a['action'] for a in actions) == report['requests'], 'incomplete relay history')
    events = list(map(json.loads, bundle.read(f'{arm}/model-io.jsonl').splitlines()))
    requests = {r['call']: r for r in events if r['event'] == 'request'}
    responses = {r['call']: r for r in events if r['event'] == 'response'}
    source = FENCE.fullmatch(responses[1]['choices'][0]['message']['content'])[1]
    accepted = [r for r in events if r['event'] == 'patch_application' and r['accepted']]
    errors = []
    successful_call = saved_end = None
    for patch in accepted:
        call = patch['call']
        tool, = responses[call]['choices'][0]['message']['tool_calls']
        args = json.loads(tool['function']['arguments'])
        require(args == {'line': patch['line'], 'replacement': patch['replacement']}, 'patch mismatch')
        lines = source.splitlines()
        line = lines[args['line'] - 1]
        lines[args['line'] - 1] = line[:len(line) - len(line.lstrip())] + args['replacement']
        require(digest('\n'.join(lines).encode()) == patch['patched_source_sha256'], 'source hash')
        following = requests[call + 1]
        receipt = following['body']['messages'][-1]
        require(receipt['role'] == 'tool' and receipt['tool_call_id'] == tool['id'], 'wrong receipt')
        # A successful repair also triggers harness checks later in this interval.
        # The first relay exec after acceptance is the run_python call itself.
        execution = next(a for a in actions if a['action'] == 'exec' and a['end_sec'] > patch['end_sec'])
        require(execution['end_sec'] <= following['start_sec'] + .006 and not execution['timed_out'], 'exec clock')
        if receipt['content'] == SAVED_RECEIPT:
            require(patch['patched_source_sha256'] == SAVED_PROGRAM and execution['exit_code'] == 0,
                    'unexpected writing program')
            require(successful_call is None and execution['end_sec'] < cutoff, 'unexpected completion')
            successful_call, saved_end = call, execution['end_sec']
        else:
            require(execution['exit_code'] == 1 and receipt['content'].startswith('[exit 1] Traceback'),
                    'unexpected repair outcome')
            errors.append(receipt['content'].strip().splitlines()[-1])

    files = [name for name in ('schedule.csv', 'summary.json') if f'{arm}/case/output/{name}' in bundle.namelist()]
    require(bool(saved_end) == (grade['score'] == 1) == (len(files) == 2), 'delivery evidence mismatch')
    if saved_end is None:
        require(not files and not report['inventory']['output_directory'], 'unexpected partial delivery')
    return dict(case=case, repeat=repeat, arm=arm, score_at_395=grade['score'],
                cost_cents=grade['cost'], output_files=len(files), accepted_patches=len(accepted),
                first_accepted_s=grade['first_accepted_sec'], successful_call=successful_call,
                file_writing_exec_return_s=saved_end, failed_repair_errors=' | '.join(errors),
                outcome='files_graded' if files else 'accepted_but_raised' if accepted else 'no_accepted_patch')


def main():
    writer = None
    for study, revision in STUDIES.items():
        folder = EXPERIMENTS / study
        data = (folder / 'protocol.json').read_bytes()
        protocol = json.loads(data)
        manifest = json.loads((folder / 'attempts/manifest.json').read_text())
        for case in protocol['split']['new_diagnostic_inputs']:
            for repeat in (1, 2, 3):
                path = folder / 'attempts' / f'ple-replication-{case}-{repeat}-attempt-1.zip'
                require(digest(path.read_bytes()) == manifest[path.name]['sha256'], 'archive checksum')
                with ZipFile(path) as bundle:
                    for arm in ('native-feedback', 'native-actionable'):
                        row = measure(bundle, case, repeat, arm, protocol, digest(data), revision)
                        if writer is None:
                            writer = csv.DictWriter(sys.stdout, fieldnames=row, lineterminator='\n')
                            writer.writeheader()
                        writer.writerow(row)


if __name__ == '__main__':
    main()
