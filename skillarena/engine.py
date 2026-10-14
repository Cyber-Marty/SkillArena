"""Run paired benchmark arms in separate local workspaces."""

from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .benchmark import Benchmark


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)).replace("\\", "/"): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts
    }


def _changes(before: dict[str, bytes], after: dict[str, bytes]) -> dict[str, object]:
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    added = deleted = 0
    for key in changed:
        old = before.get(key, b"").decode("utf-8", errors="replace").splitlines()
        new = after.get(key, b"").decode("utf-8", errors="replace").splitlines()
        for line in difflib.ndiff(old, new):
            added += line.startswith("+ ")
            deleted += line.startswith("- ")
    return {"files_changed": changed, "lines_added": added, "lines_deleted": deleted}


def _execute(command: tuple[str, ...], cwd: Path, env: dict[str, str], timeout: int) -> dict:
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
        return {
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "timed_out": False,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        def decode(value: bytes | str | None) -> str:
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        return {
            "returncode": None, "stdout": decode(exc.stdout), "stderr": decode(exc.stderr),
            "timed_out": True, "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except OSError as exc:
        return {
            "returncode": None, "stdout": "", "stderr": str(exc),
            "timed_out": False, "duration_seconds": round(time.perf_counter() - started, 3),
        }


def _expand(command: tuple[str, ...], benchmark_dir: Path) -> tuple[str, ...]:
    return tuple(part.replace("{benchmark_dir}", str(benchmark_dir)) for part in command)


def _reported_usage(output: str) -> dict | None:
    usage = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed":
            usage = event.get("usage")
    return usage if isinstance(usage, dict) else None


def _run_one(benchmark: Benchmark, output: Path, arm: str, repetition: int) -> dict:
    run_id = f"{repetition:02d}-{arm}"
    workspace = output / "artifacts" / run_id
    shutil.copytree(benchmark.task_dir, workspace)
    before = _files(workspace)
    env = os.environ.copy()
    env.update({
        "SKILLARENA_ARM": arm,
        "SKILLARENA_TASK_DIR": str(workspace),
        "SKILLARENA_TASK_PROMPT": benchmark.prompt,
        "SKILLARENA_SKILL_PATH": str(benchmark.skill_path) if arm == "skill" else "",
    })
    runner = _execute(
        _expand(benchmark.runner_command, benchmark.path.parent), workspace, env,
        benchmark.timeout_seconds,
    )
    changes = _changes(before, _files(workspace))
    # A failed runner is still evaluated so the report shows what remains in the workspace.
    evaluation = _execute(
        _expand(benchmark.evaluation_command, benchmark.path.parent), workspace, env,
        benchmark.timeout_seconds,
    )
    success = runner["returncode"] == 0 and evaluation["returncode"] == 0
    logs = output / "logs"
    logs.mkdir(exist_ok=True)
    for phase, result in (("runner", runner), ("evaluation", evaluation)):
        (logs / f"{run_id}-{phase}.log").write_text(
            f"exit_code: {result['returncode']}\ntimed_out: {result['timed_out']}\n"
            f"duration_seconds: {result['duration_seconds']}\n\n"
            f"STDOUT\n{result['stdout']}\nSTDERR\n{result['stderr']}", encoding="utf-8",
        )
    return {
        "id": run_id, "arm": arm, "repetition": repetition, "success": success,
        "runner": {key: runner[key] for key in ("returncode", "timed_out", "duration_seconds")},
        "evaluation": {key: evaluation[key] for key in ("returncode", "timed_out", "duration_seconds")},
        "changes": changes,
        "token_usage": _reported_usage(runner["stdout"]), "tool_calls": None,
    }


def summarize(runs: list[dict]) -> dict:
    arms = {}
    for arm in ("baseline", "skill"):
        subset = [run for run in runs if run["arm"] == arm]
        if subset:
            measured = [run["token_usage"] for run in subset if run["token_usage"]]
            arms[arm] = {
                "runs": len(subset),
                "successes": sum(run["success"] for run in subset),
                "success_rate": round(sum(run["success"] for run in subset) / len(subset), 4),
                "mean_runner_seconds": round(sum(run["runner"]["duration_seconds"] for run in subset) / len(subset), 3),
                "mean_input_tokens": round(sum(item.get("input_tokens", 0) for item in measured) / len(measured)) if len(measured) == len(subset) else None,
                "mean_output_tokens": round(sum(item.get("output_tokens", 0) for item in measured) / len(measured)) if len(measured) == len(subset) else None,
            }
    if len(arms) == 2:
        arms["absolute_success_rate_change"] = round(
            arms["skill"]["success_rate"] - arms["baseline"]["success_rate"], 4
        )
    return arms


def run_benchmark(benchmark: Benchmark, output: Path) -> dict:
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f"Output directory already exists: {output}")
    if output == benchmark.task_dir or benchmark.task_dir in output.parents:
        raise ValueError("Output directory must be outside task.source")
    output.mkdir(parents=True)
    runs = []
    for repetition in range(1, benchmark.repetitions + 1):
        # Alternate the order to reduce simple time/order effects.
        order = ("baseline", "skill") if repetition % 2 else ("skill", "baseline")
        for arm in order:
            runs.append(_run_one(benchmark, output, arm, repetition))
    digest = hashlib.sha256(benchmark.path.read_bytes()).hexdigest()
    task_digest = hashlib.sha256()
    for name, contents in sorted(_files(benchmark.task_dir).items()):
        task_digest.update(name.encode("utf-8"))
        task_digest.update(b"\0")
        task_digest.update(contents)
    result = {
        "schema_version": 1,
        "benchmark": benchmark.name,
        "description": benchmark.description,
        "benchmark_sha256": digest,
        "task_sha256": task_digest.hexdigest(),
        "skill_sha256": hashlib.sha256(benchmark.skill_path.read_bytes()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repetitions": benchmark.repetitions,
        "runner_type": "command",
        "metadata": benchmark.metadata,
        "runs": runs,
        "summary": summarize(runs),
        "limitations": [
            "Success means the runner and evaluator both exited with code 0.",
            "Token counts appear only if the runner reports Codex turn.completed usage; tool counts are unavailable.",
            "This benchmark does not establish statistical confidence or causality.",
        ],
    }
    (output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
