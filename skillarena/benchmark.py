"""Load and validate a local benchmark definition."""

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


@dataclass(frozen=True)
class Benchmark:
    path: Path
    name: str
    description: str
    task_dir: Path
    prompt: str
    skill_path: Path
    runner_command: tuple[str, ...]
    evaluation_command: tuple[str, ...]
    repetitions: int
    timeout_seconds: int
    metadata: dict[str, str]


def _command(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{key} must be a non-empty list of strings")
    return tuple(value)


def load_benchmark(path: str | Path) -> Benchmark:
    path = Path(path).expanduser().resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read benchmark {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Benchmark must be a YAML mapping")
    name = data.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name):
        raise ValueError("name must contain only letters, digits, _ or - (max 80 chars)")
    task = data.get("task")
    runner = data.get("runner")
    evaluation = data.get("evaluation")
    if not all(isinstance(item, dict) for item in (task, runner, evaluation)):
        raise ValueError("task, runner and evaluation must be mappings")
    task_dir = (path.parent / str(task.get("source", ""))).resolve()
    skill_path = (path.parent / str(data.get("skill", ""))).resolve()
    if not task.get("source") or not task_dir.is_dir():
        raise ValueError(f"task.source must point to a directory: {task_dir}")
    if not data.get("skill") or not skill_path.is_file():
        raise ValueError(f"skill must point to a file: {skill_path}")
    if any(p.is_symlink() for p in task_dir.rglob("*")):
        raise ValueError("task.source must not contain symbolic links")
    prompt = task.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("task.prompt must be a non-empty string")
    if runner.get("type") != "command":
        raise ValueError("runner.type must be 'command'")
    repetitions = data.get("repetitions", 3)
    timeout = data.get("timeout_seconds", 60)
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be an integer from 1 to 100")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("timeout_seconds must be an integer from 1 to 3600")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
    ):
        raise ValueError("metadata must be a string-to-string mapping")
    return Benchmark(
        path=path,
        name=name,
        description=str(data.get("description", "")),
        task_dir=task_dir,
        prompt=prompt,
        skill_path=skill_path,
        runner_command=_command(runner.get("command"), "runner.command"),
        evaluation_command=_command(evaluation.get("command"), "evaluation.command"),
        repetitions=repetitions,
        timeout_seconds=timeout,
        metadata=metadata,
    )
