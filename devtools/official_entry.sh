#!/usr/bin/env bash
# Prepare the same runtime-only entry in every independent GitHub runner.
set -euo pipefail
: "${RUNNER_TEMP:?}" "${GITHUB_SHA:?}" "${GITHUB_WORKSPACE:?}"
kit="$RUNNER_TEMP/ple-kit"
entry="$RUNNER_TEMP/ple-entry"
git init -q "$kit"
git -C "$kit" fetch --quiet --depth 1 https://github.com/google-research/ple.git 8320f0402fdca9f42476607f72bcfd5271cd50c9
git -C "$kit" checkout --quiet --detach FETCH_HEAD
mkdir "$entry"
paths=(.gitattributes .gitignore LICENSE submission.yaml requirements.txt serve.py skillkit skills)
git -C "$GITHUB_WORKSPACE" archive "$GITHUB_SHA" -- "${paths[@]}" | tar -x -C "$entry"
python3 - "$entry/submission.yaml" <<'PYMODEL'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
raw = p.read_text()
before = "model_api: google-cloud/glm-5.2\n"
if raw.count(before) != 1:
    raise SystemExit("Unexpected source model declaration. Review the export profile.")
p.write_text(raw.replace(before, "model_api: google-cloud/gemma-4-26b\n").replace('  LOG_LEVEL: "info"', '  LOG_LEVEL: "info"\n  PLE_MASK_OLD_TOOL_RESULTS: "1"\n  PLE_LIMIT_RECENT_TOOL_RESULTS: "1"\n  PLE_RECOVER_CONTEXT_ONCE: "1"'))
PYMODEL
git init -q "$entry"
git -C "$entry" add .
runtime=$(git -C "$GITHUB_WORKSPACE" log -1 --format=%H "$GITHUB_SHA" -- "${paths[@]}")
stamp=$(git -C "$GITHUB_WORKSPACE" show -s --format=%cI "$runtime")
GIT_AUTHOR_DATE="$stamp" GIT_COMMITTER_DATE="$stamp" git -C "$entry" -c user.name='PLE evaluation' -c user.email='ple@localhost' commit -qm "Gemma runtime from $runtime"
python3 -m venv "$RUNNER_TEMP/ple-bootstrap"
"$RUNNER_TEMP/ple-bootstrap/bin/pip" -q install 'uv==0.9.28'
export PATH="$RUNNER_TEMP/ple-bootstrap/bin:$PATH"
cd "$kit"
uv venv --python /usr/bin/python3.12 "$kit/.venv"
uv pip sync --python "$kit/.venv/bin/python" "$GITHUB_WORKSPACE/devtools/official-kit-requirements.txt"
"$kit/.venv/bin/python" -m kit validate "$entry"
