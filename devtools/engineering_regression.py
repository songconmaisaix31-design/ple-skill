#!/usr/bin/env python3
"""Run an original classroom mechanics regression through the PLE harness.

This exercise and its numerical checker are independent of all PLE datasets.
Set MODEL_NAME, MODEL_BASE_URL and, if required, MODEL_API_KEY for a live API.
"""

import argparse
import asyncio
from contextlib import suppress
import json
import math
from pathlib import Path
import shlex
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skillkit.harness import Harness
from skillkit.model import TOOLS, from_env
from skillkit.transport import LocalTransport, quote_path


INPUT = "input/beam.json"
OUTPUT = "output/beam_results.json"
MAX_OUTPUT_BYTES = 16384
MAX_PROGRAM_BYTES = 8192
MAX_CALCULATION_OUTPUT = 4096
CALCULATOR_TOOL = {
    "name": "exec",
    "description": "Run one calculation as `python3 -c '<Python program>'` in an isolated, "
                   "network-disabled Python container. The input file is mounted read-only. "
                   "Use Python for numerical calculations and print the results.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                   "required": ["command"]},
}
EXERCISE_TOOLS = [tool for tool in TOOLS if tool["name"] in {"read_file", "write_file", "finish"}]

BEAM = {
    "span_m": 7.5,
    "downward_point_load_kN": 11.6,
    "point_load_x_m": 2.4,
    "downward_triangular_start_kN_per_m": 0.0,
    "downward_triangular_end_kN_per_m": 7.2,
}

TASK = f"""Analyze an imaginary pin-and-roller beam for a classroom mechanics exercise.
Read {INPUT} for dimensions and load magnitudes. The left pin is at x=0 and
the right roller is at x=span_m. Downward point load acts at point_load_x_m.
The triangular distributed load varies linearly over the entire span, from
its start intensity at the left pin to its end intensity at the right roller.
Ignore self-weight. Use upward-positive reactions and sagging-positive moment.
Find the interior or load-breakpoint location of maximum positive bending moment
by considering both sides of the point load, along with the support values.

Save only the numeric results in {OUTPUT} under `output/` as a JSON object
containing left_reaction, right_reaction, peak_moment, peak_x, and units.
The first four fields must be JSON numbers; preserve at least 3 decimal places
when needed. The units object must use exactly the keys reaction, moment,
and position with values kN, kN*m, and m, respectively. Use read_file to obtain
the inputs, write_file to save the result, and finish to end the task.
"""


def failure(message):
    return {"ok": False, "exit_code": 1, "output": message, "error": message}


class ExerciseTransport(LocalTransport):
    """Serve only the two exercise files and the harness's built-in guard."""

    def __init__(self, workspace, docker_image=None):
        super().__init__(workspace)
        self.workspace = workspace
        self.docker_image = docker_image
        self.guard_paths = tuple(
            Path(self.scratch_path(name)) for name in ("validate.py", "spec.json")
        )
        self.input_read = False
        self.calculations = 0

    async def read_file(self, path):
        if path not in {INPUT, OUTPUT}:
            return None
        content = await super().read_file(path)
        if path == INPUT and content is not None:
            self.input_read = True
        return content

    async def write_file(self, path, data, append=False):
        if path != OUTPUT and Path(path) not in self.guard_paths:
            return failure("unknown exercise path")
        target = (self.workspace / path).resolve()
        if not target.is_relative_to(self.workspace):
            return failure("exercise path is outside the workspace")
        if path == OUTPUT:
            previous_bytes = target.stat().st_size if append and target.is_file() else 0
            if previous_bytes + len(data) > MAX_OUTPUT_BYTES:
                return failure("exercise result is too large")
        return await super().write_file(str(target), data, append)

    async def exec(self, command, timeout_sec=120):
        if command.startswith("echo '--- task.md ---';"):
            return {"ok": True, "exit_code": 0, "output": f"--- tree ---\n./{INPUT}\n"}
        script, spec = self.guard_paths
        args = [self.python_cmd, str(script), "--base", str(self.workspace), "--spec", str(spec)]
        trusted_command = " ".join(quote_path(part) for part in args)
        if command == trusted_command:
            return await self.validate(args)
        if self.docker_image is None:
            return failure("shell commands are disabled for this exercise")
        try:
            parts = shlex.split(command)
        except ValueError:
            return failure("quote the program in `python3 -c '<program>'`")
        if len(parts) != 3 or parts[0] not in {"python", "python3"} or parts[1] != "-c":
            return failure("the calculator accepts only `python3 -c '<program>'`")
        if len(parts[2].encode()) > MAX_PROGRAM_BYTES or "\x00" in parts[2]:
            return failure("calculator program is too large or contains a NUL byte")
        return await self.calculate(parts[2])

    async def validate(self, args):
        process = await asyncio.create_subprocess_exec(
            *args, cwd=self.workspace, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise
        return {"ok": process.returncode == 0, "exit_code": process.returncode,
                "output": stdout.decode(errors="replace")}

    async def calculate(self, program):
        name = f"ple-classroom-calc-{uuid.uuid4().hex}"
        mount = f"type=bind,src={self.workspace / 'input'},dst=/workspace/input,readonly"
        process = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", "--pull=never", "--name", name,
            "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--memory=128m", "--cpus=0.5", "--pids-limit=32", "--user=65534:65534",
            "--log-driver=none", "--workdir=/workspace", "--mount", mount,
            "--entrypoint=python3", self.docker_image, "-I", "-B", "-c", program,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            async with asyncio.timeout(15):
                stdout = await process.stdout.readexactly(MAX_CALCULATION_OUTPUT + 1)
                return failure("calculator output limit exceeded")
        except asyncio.IncompleteReadError as end:
            await process.wait()
            if process.returncode == 0:
                self.calculations += 1
                return {"ok": True, "exit_code": 0, "output": end.partial.decode(errors="replace")}
            return failure("isolated Python failed: " + end.partial.decode(errors="replace"))
        except TimeoutError:
            return failure("isolated Python exceeded the 15-second limit")
        finally:
            if process.returncode is None:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", name,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                )
                with suppress(TimeoutError):
                    await asyncio.wait_for(cleanup.wait(), timeout=5)
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()


class ExerciseModel:
    """Allow only the exercise tools, even if the provider emits other calls."""

    def __init__(self, client, docker_image=None):
        self.client = client
        self.tools = EXERCISE_TOOLS + ([CALCULATOR_TOOL] if docker_image else [])
        self.tool_names = {tool["name"] for tool in self.tools}

    async def chat(self, messages, system):
        response = await self.client.chat(messages, system, tools=self.tools)
        for call in response["tool_calls"]:
            arguments = call["arguments"]
            if call["name"] == "write_file" and (
                not isinstance(arguments, dict) or arguments.get("path") != OUTPUT
            ):
                call["name"] = "unavailable_exercise_path"
            elif call["name"] not in self.tool_names:
                call["name"] = "unavailable_exercise_tool"
        return response


def reference_results():
    """Use force/moment equilibrium and bracket the shear-zero point numerically."""
    span = BEAM["span_m"]
    point = BEAM["downward_point_load_kN"]
    point_x = BEAM["point_load_x_m"]
    start = BEAM["downward_triangular_start_kN_per_m"]
    slope = (BEAM["downward_triangular_end_kN_per_m"] - start) / span

    distributed = start * span + slope * span**2 / 2
    right = (point * point_x + start * span**2 / 2 + slope * span**3 / 3) / span
    left = point + distributed - right

    def moment(x):
        return left * x - point * max(0, x - point_x) - start * x**2 / 2 - slope * x**3 / 6

    candidates = [0, point_x, span]
    for low, high, passing_point in ((0, point_x, 0), (point_x, span, point)):
        def shear(x):
            return left - passing_point - start * x - slope * x**2 / 2

        if shear(low) > 0 > shear(high):
            for _ in range(60):
                mid = (low + high) / 2
                if shear(mid) > 0:
                    low = mid
                else:
                    high = mid
            candidates.append((low + high) / 2)

    peak_x = max(candidates, key=moment)
    return {"left_reaction": left, "right_reaction": right,
            "peak_moment": moment(peak_x), "peak_x": peak_x}


def score(workspace, input_read):
    answers = {}
    path = workspace / OUTPUT
    try:
        if (path.is_symlink() or not path.resolve().is_relative_to(workspace)
                or not path.is_file() or path.stat().st_size > MAX_OUTPUT_BYTES):
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            answers = value
    except (OSError, UnicodeError, ValueError):
        pass

    checks = {"read_input": input_read, "deliverable_json": bool(answers)}
    for key, expected in reference_results().items():
        received = answers.get(key)
        checks[key] = (type(received) in (float, int) and abs(received) < 1e6
                       and math.isclose(received, expected, abs_tol=0.015))
    checks["units"] = answers.get("units") == {"reaction": "kN", "moment": "kN*m", "position": "m"}
    return checks


async def run(timeout, docker_image=None):
    client = from_env()
    if client.model == "unknown" or not client.base_url:
        raise SystemExit("Set MODEL_NAME and MODEL_BASE_URL for the live regression.")
    with tempfile.TemporaryDirectory(prefix="ple-synthetic-beam-") as temporary:
        workspace = Path(temporary).resolve()
        source = workspace / INPUT
        source.parent.mkdir(mode=0o755)
        source.parent.chmod(0o755)
        source.write_text(json.dumps(BEAM, indent=2), encoding="utf-8")
        source.chmod(0o444)
        transport = ExerciseTransport(workspace, docker_image)
        instruction = TASK
        if docker_image:
            instruction += "Use the isolated Python calculator to determine or verify your numbers before writing.\n"
        harness = Harness(transport, ExerciseModel(client, docker_image), instruction, workdir=str(workspace))
        try:
            await harness.run(timeout_sec=timeout)
        except Exception as error:
            print(f"Synthetic exercise stopped before completion ({type(error).__name__}).", file=sys.stderr)
        checks = score(workspace, transport.input_read)
        if docker_image:
            checks["isolated_calculation"] = transport.calculations > 0
        points = sum(checks.values())
        print(f"Synthetic beam regression: {points}/{len(checks)} checks passed; "
              f"model turns: {harness.steps}; completed isolated calculations: {transport.calculations}.")
        if points < len(checks):
            print("Unmet checks: " + ", ".join(key for key, passed in checks.items() if not passed))
        return int(points < len(checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--docker-image", help="Locally installed Python image for isolated calculations")
    args = parser.parse_args()
    if args.timeout_sec < 1:
        parser.error("--timeout-sec must be positive")
    return asyncio.run(run(args.timeout_sec, args.docker_image))


if __name__ == "__main__":
    sys.exit(main())
