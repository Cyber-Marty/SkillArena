"""Frozen multi-task, multi-condition experiments with explicit inference budgets."""

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys

import yaml

from .codex_runner import (MODEL, EFFORT, INSTRUCTIONS, find_codex, isolated_login,
                           read_quota, require_included_quota, run_agent, run_process)
from .evidence import hash_tree, seal_bundle, sha256_file


def tree_digest(path: Path) -> str:
    files = {name: entry for name, entry in hash_tree(path).items()
             if "__pycache__" not in Path(name).parts and not name.endswith(".pyc")}
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Experiment:
    path: Path
    name: str
    suite_path: Path
    suite: dict
    tasks: tuple[dict, ...]
    conditions: tuple[dict, ...]
    repetitions: int
    seed: int
    timeout_seconds: int
    max_tool_calls: int
    max_agent_runs: int


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError(f"Invalid {name}")
    return value


def _integer(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def load_experiment(path: Path) -> Experiment:
    path = path.resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 2:
            raise ValueError("Expected schema_version: 2")
        name = _id(data.get("name"), "name")
        suite_path = (path.parent / data["suite"]).resolve()
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        if suite.get("schema_version") != 2 or not isinstance(suite.get("version"), str):
            raise ValueError("Invalid suite version")
        _id(suite.get("id"), "suite.id")
        available = suite.get("tasks")
        selected = data.get("tasks", available)
        if not isinstance(available, list) or not available or len(set(available)) != len(available):
            raise ValueError("Invalid suite tasks")
        if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected):
            raise ValueError("tasks must be a non-empty list without duplicates")
        tasks = []
        for task_id in selected:
            _id(task_id, "task id")
            if task_id not in available:
                raise ValueError(f"Unknown task: {task_id}")
            task_root = suite_path.parent / task_id
            task = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
            if task.get("id") != task_id or not isinstance(task.get("prompt"), str):
                raise ValueError(f"Invalid task metadata: {task_id}")
            for required in ("fixture/TASK.md", "verifier.py", "oracle/output.json"):
                if not (task_root / required).is_file():
                    raise ValueError(f"Missing task file: {task_id}/{required}")
            task["path"] = task_root
            task["sha256"] = tree_digest(task_root)
            tasks.append(task)
        conditions = []
        for item in data.get("conditions", []):
            condition = {"id": _id(item.get("id"), "condition id"), "skill_path": None, "skill_sha256": None}
            if item.get("skill") is not None:
                skill = (path.parent / item["skill"]).resolve()
                if not (skill / "SKILL.md").is_file():
                    raise ValueError("Each skill must be a directory containing SKILL.md")
                condition.update(skill_path=skill, skill_sha256=tree_digest(skill))
            conditions.append(condition)
        if len(conditions) < 2 or len({item["id"] for item in conditions}) != len(conditions):
            raise ValueError("Use at least two uniquely named conditions")
        runner = data.get("runner", {})
        if runner.get("type") != "codex-mcp" or runner.get("model") != MODEL or runner.get("reasoning_effort") != EFFORT:
            raise ValueError("Runner must be codex-mcp with gpt-6-sol / high")
        result = Experiment(path, name, suite_path, suite, tuple(tasks), tuple(conditions),
                            _integer(data.get("repetitions", 1), "repetitions", 1, 20),
                            _integer(data.get("seed", 42), "seed", 0, 2**32 - 1),
                            _integer(runner.get("timeout_seconds", 180), "timeout_seconds", 30, 600),
                            _integer(runner.get("max_tool_calls", 40), "max_tool_calls", 4, 100),
                            _integer(data.get("max_agent_runs", 6), "max_agent_runs", 1, 200))
        if len(tasks) * len(conditions) * result.repetitions > result.max_agent_runs:
            raise ValueError("Planned runs exceed max_agent_runs; reduce tasks/repetitions or explicitly raise the cap")
        return result
    except (OSError, KeyError, TypeError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot load experiment: {exc}") from exc


def plan_experiment(experiment: Experiment) -> dict:
    rng = random.Random(experiment.seed)
    conditions = [item["id"] for item in experiment.conditions]
    rng.shuffle(conditions)
    schedule = []
    # Random starting order, balanced cyclic positions across task/repetition blocks.
    block = 0
    for repetition in range(1, experiment.repetitions + 1):
        for task in experiment.tasks:
            shift = block % len(conditions)
            for condition in conditions[shift:] + conditions[:shift]:
                schedule.append({"id": f"{task['id']}-{repetition:02d}-{condition}",
                                 "task_id": task["id"], "condition": condition, "repetition": repetition})
            block += 1
    return {"schema_version": 2, "benchmark": experiment.name, "seed": experiment.seed,
            "ordering": "seeded shuffled conditions, cyclic balanced block order",
            "tasks": len(experiment.tasks), "conditions": conditions,
            "planned_agent_runs": len(schedule), "max_agent_runs": experiment.max_agent_runs,
            "max_tool_calls_per_run": experiment.max_tool_calls,
            "timeout_seconds_per_run": experiment.timeout_seconds,
            "model": MODEL, "reasoning_effort": EFFORT,
            "billing_policy": "existing ChatGPT login; no API keys, no credit top-ups, stop on low/unknown included quota",
            "schedule": schedule}


def _snapshot(experiment: Experiment, output: Path) -> None:
    snapshot = output / "snapshot"
    for task in experiment.tasks:
        shutil.copytree(task["path"], snapshot / "suite" / task["id"], ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for helper in experiment.suite_path.parent.glob("_*.py"):
        shutil.copyfile(helper, snapshot / "suite" / helper.name)
    # Preserve the full roster even when evaluating a predeclared subset.
    shutil.copyfile(experiment.suite_path, snapshot / "suite" / "suite.json")
    conditions = []
    for condition in experiment.conditions:
        target = None
        if condition["skill_path"]:
            target = "skills/" + condition["id"]
            shutil.copytree(condition["skill_path"], snapshot / target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        conditions.append({"id": condition["id"], "skill": target})
    config = {"schema_version": 2, "name": experiment.name, "suite": "suite/suite.json",
              "tasks": [item["id"] for item in experiment.tasks], "conditions": conditions,
              "runner": {"type": "codex-mcp", "model": MODEL, "reasoning_effort": EFFORT,
                         "timeout_seconds": experiment.timeout_seconds, "max_tool_calls": experiment.max_tool_calls},
              "repetitions": experiment.repetitions, "seed": experiment.seed, "max_agent_runs": experiment.max_agent_runs}
    (snapshot / "experiment.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    source = Path(__file__).parent
    implementation = snapshot / "implementation"
    implementation.mkdir(parents=True)
    for path in source.iterdir():
        if path.suffix in (".py", ".j2"):
            shutil.copyfile(path, implementation / path.name)
    for task in experiment.tasks:
        if tree_digest(snapshot / "suite" / task["id"]) != task["sha256"]:
            raise ValueError(f"Task changed after planning: {task['id']}")
    for item in experiment.conditions:
        if item["skill_path"] and tree_digest(snapshot / "skills" / item["id"]) != item["skill_sha256"]:
            raise ValueError(f"Skill changed after planning: {item['id']}")


def _environment(executable: str) -> dict:
    root = Path(__file__).resolve().parent.parent
    def git(*args):
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else None
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
    status = git("status", "--porcelain")
    return {"python": platform.python_version(), "os": platform.system(), "os_release": platform.release(),
            "codex_version": version.stdout.strip(), "source_commit": git("rev-parse", "HEAD"),
            "working_tree_dirty": bool(status) if status is not None else None,
            "dependencies": {name: importlib.metadata.version(name) for name in ("skillarena", "PyYAML", "typer", "Jinja2")}}


def run_experiment(experiment: Experiment, output: Path, progress=print) -> dict:
    from .analysis_v2 import summarize_v2
    from .report import render_report
    output = output.resolve()
    if output.exists():
        raise ValueError("Output directory already exists; use a new directory to preserve evidence")
    inputs = [experiment.suite_path.parent, *(item["skill_path"] for item in experiment.conditions if item["skill_path"])]
    if any(output == path or path in output.parents for path in inputs):
        raise ValueError("Output directory must be outside task and skill sources")
    executable = find_codex()
    with isolated_login() as env:
        quota = read_quota(executable, env)
        require_included_quota(quota)
        output.mkdir(parents=True)
        try:
            _snapshot(experiment, output)
            plan = plan_experiment(experiment)
            write_json(output / "plan.json", plan)
            environment = _environment(executable)
            write_json(output / "environment.json", environment)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            write_json(output / "setup-error.json", {"phase": "before_model_execution", "error": str(exc)})
            seal_bundle(output)
            raise ValueError(f"Pre-run preparation failed; evidence retained in {output}") from exc
        metrics = {"schema_version": 2, "benchmark": experiment.name,
                   "created_at": datetime.now(timezone.utc).isoformat(), "evidence_level": "author-submitted",
                   "suite": {"id": experiment.suite["id"], "version": experiment.suite["version"],
                             "sha256": sha256_file(experiment.suite_path)},
                   "tasks": [{"id": task["id"], "title": task["title"], "sha256": task["sha256"]} for task in experiment.tasks],
                   "conditions": [{"id": item["id"], "skill_sha256": item["skill_sha256"]} for item in experiment.conditions],
                   "runner": {"type": "codex-mcp", "model": MODEL, "reasoning_effort": EFFORT,
                              "timeout_seconds": experiment.timeout_seconds, "max_tool_calls": experiment.max_tool_calls,
                              "cli_version": environment["codex_version"], "instructions_sha256":
                              __import__("hashlib").sha256(INSTRUCTIONS.encode()).hexdigest(),
                              "tool_boundary": "workspace-mcp-v1", "auth": "chatgpt"},
                   "repetitions": experiment.repetitions, "seed": experiment.seed,
                   "runs": [entry | {"status": "not_run", "success": None, "runner": {}} for entry in plan["schedule"]],
                   "limitations": [
                       "Original synthetic data tasks; this is not a representative real-world benchmark.",
                       "The model is an alias, not a pinned provider snapshot. Repeat outcomes may vary.",
                       "Explicit skill discovery through MCP; not native implicit skill routing or arbitrary shell/code execution.",
                       "Hashes verify bundle integrity, not model authenticity or independent replication.",
                       "Check_output validates JSON syntax only. Hidden expected outputs are scored after the agent exits.",
                       "Usage is reported tokens and elapsed time; monetary cost is not independently measured.",
                   ]}
        metrics["runner"]["implementation_sha256"] = tree_digest(output / "snapshot" / "implementation")
        metrics["runner"]["platform"] = {key: environment[key] for key in ("python", "os", "os_release")}
        metrics["suite"]["support_sha256"] = {p.name: sha256_file(p) for p in experiment.suite_path.parent.glob("_*.py")}
        tasks = {task["id"]: task for task in experiment.tasks}
        conditions = {condition["id"]: condition for condition in experiment.conditions}
        try:
            for index, entry in enumerate(metrics["runs"]):
                progress(f"[{index + 1}/{len(metrics['runs'])}] {entry['id']}")
                if index:
                    quota = read_quota(executable, env)
                    require_included_quota(quota)
                task = tasks[entry["task_id"]]
                condition = conditions[entry["condition"]]
                evidence = output / "runs" / entry["id"]
                workspace = evidence / "workspace"
                shutil.copytree(output / "snapshot" / "suite" / task["id"] / "fixture", workspace)
                write_json(evidence / "quota-before.json", quota)
                skill = output / "snapshot" / "skills" / condition["id"] if condition["skill_path"] else None
                before = tree_digest(workspace)
                runner = run_agent(executable, env, workspace, skill, evidence, experiment.timeout_seconds, experiment.max_tool_calls)
                entry["runner"] = runner
                evaluation = run_process([sys.executable, "-I", str(output / "snapshot" / "suite" / task["id"] / "verifier.py"),
                                          str(workspace)], cwd=evidence, env=env, timeout=20)
                # Trusted suite verifiers only; never run code supplied by an imported result bundle.
                write_json(evidence / "evaluation.json", evaluation)
                entry["evaluation"] = {key: evaluation[key] for key in ("returncode", "timed_out", "duration_seconds")}
                entry["workspace_before_sha256"] = before
                entry["workspace_after_sha256"] = tree_digest(workspace)
                if runner["timed_out"] and runner.get("started") and runner.get("tool_calls", 0) > 0:
                    status = "failed"  # The declared time budget is part of task performance.
                elif not runner["valid_agent_run"] or evaluation["returncode"] not in (0, 1):
                    status = "infrastructure_error"
                else:
                    status = "passed" if evaluation["returncode"] == 0 else "failed"
                entry.update(status=status, success=status == "passed" if status != "infrastructure_error" else None)
                write_json(evidence / "run.json", entry)
                metrics["summary"] = summarize_v2(metrics)
                write_json(output / "metrics.json", metrics)
                if status == "infrastructure_error":
                    metrics["stop_reason"] = "Infrastructure failure: no automatic model retries"
                    break
        except (ValueError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
            metrics["stop_reason"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                write_json(output / "quota-after.json", read_quota(executable, env))
            except (ValueError, OSError, subprocess.SubprocessError):
                write_json(output / "quota-after.json", {"status": "unavailable"})
            metrics["summary"] = summarize_v2(metrics)
            metrics["complete"] = all(run["status"] in ("passed", "failed") for run in metrics["runs"])
            write_json(output / "metrics.json", metrics)
            render_report(output / "metrics.json")
            seal_bundle(output)
        return metrics
