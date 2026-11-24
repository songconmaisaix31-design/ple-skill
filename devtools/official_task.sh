#!/usr/bin/env bash
# Regrade only the kit-exported file set in a fresh task container.
set -euo pipefail
kit="$RUNNER_TEMP/ple-kit"
entry="$RUNNER_TEMP/ple-entry"
evidence="$RUNNER_TEMP/evidence"
mkdir -p "$evidence" "$RUNNER_TEMP/ple-bin"
python="$kit/.venv/bin/python"
helper="$GITHUB_WORKSPACE/devtools/official_export.py"
export PATH="$RUNNER_TEMP/ple-bootstrap/bin:$RUNNER_TEMP/ple-bin:$PATH"
cd "$kit"
"$python" "$helper" download "$TASK"
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN
UV_TOOL_BIN_DIR="$RUNNER_TEMP/ple-bin" uv tool install 'harbor==0.20.0' --with websockets
uv pip freeze --python "$(uv tool dir)/harbor/bin/python" >"$evidence/harbor-environment.txt"
uv pip freeze --python "$python" >"$evidence/kit-environment.txt"
source "$GITHUB_WORKSPACE/devtools/official_model.sh"
tasks="$RUNNER_TEMP/ple-data/tasks"
run_status=0
timeout -k 90s -s INT 260m "$python" eval/run.py "$entry" --tasks "$TASK" --tasks-dir "$tasks" --trials 1 --attempts 1 --no-export \
  --out "$RUNNER_TEMP/run" >"$RUNNER_TEMP/run.log" 2>&1 || run_status=$?
"$python" "$helper" summarize "$TASK" run "$run_status"
"$python" "$GITHUB_WORKSPACE/devtools/official_target.py" "$TASK" capture
"$python" "$GITHUB_WORKSPACE/devtools/official_public_export.py" "$TASK"
"$python" "$GITHUB_WORKSPACE/devtools/official_target.py" "$TASK" export
"$python" -m kit artifacts "$entry" --json >"$RUNNER_TEMP/review.json" || true
"$python" "$helper" review "$TASK"
tar -C "$entry" -czf "$evidence/export.tar.gz" artifacts
replay_status=0
timeout -k 60s -s INT 60m "$python" eval/run.py --artifacts "$entry" --tasks "$TASK" --tasks-dir "$tasks" \
  --trials 1 --attempts 1 --out "$RUNNER_TEMP/replay" >"$RUNNER_TEMP/replay.log" 2>&1 || replay_status=$?
"$python" "$helper" summarize "$TASK" replay "$replay_status"
"$python" "$helper" verify "$TASK"
