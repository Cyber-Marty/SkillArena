"""Offline descriptive analysis of version 2 benchmark metrics.

Pairing is by task and repetition. A task contributes to the reported delta
only when all of its planned repetitions have scored outcomes on both sides.
The bootstrap resamples tasks, not individual repetitions; its interval is
descriptive and does not establish causality or independent replication.
"""

from __future__ import annotations

import random


_SCORED = {"passed", "failed"}
_STATUSES = _SCORED | {"infrastructure_error", "not_run"}
_BOOTSTRAP_SEED = 20260417
_BOOTSTRAP_SAMPLES = 4000


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _items_by_id(value: object, label: str) -> dict[str, dict]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty list")
    items: dict[str, dict] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{label} entries must be objects")
        item_id = _nonempty_string(item.get("id"), f"{label} id")
        if item_id in items:
            raise ValueError(f"Duplicate {label} id: {item_id}")
        items[item_id] = item
    return items


def _validate(metrics: dict) -> tuple[dict[str, dict], dict[str, dict], dict[tuple[str, str, int], dict]]:
    if not isinstance(metrics, dict) or type(metrics.get("schema_version")) is not int or metrics["schema_version"] != 2:
        raise ValueError("Expected metrics schema_version 2")
    _nonempty_string(metrics.get("benchmark"), "benchmark")
    suite = metrics.get("suite")
    if not isinstance(suite, dict):
        raise ValueError("suite must be an object")
    for key in ("id", "version", "sha256"):
        _nonempty_string(suite.get(key), f"suite.{key}")
    runner = metrics.get("runner")
    if not isinstance(runner, dict) or "model" not in runner or "reasoning_effort" not in runner:
        raise ValueError("runner must include model and reasoning_effort")
    conditions = _items_by_id(metrics.get("conditions"), "conditions")
    for condition in conditions.values():
        digest = condition.get("skill_sha256")
        if digest is not None and (not isinstance(digest, str) or not digest):
            raise ValueError("condition skill_sha256 must be a string or null")
    tasks = _items_by_id(metrics.get("tasks"), "tasks")
    for task in tasks.values():
        _nonempty_string(task.get("sha256"), "task.sha256")
    repetitions = metrics.get("repetitions")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    runs = metrics.get("runs")
    if not isinstance(runs, list):
        raise ValueError("runs must be a list")
    slots: dict[tuple[str, str, int], dict] = {}
    ids: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("run entries must be objects")
        run_id = _nonempty_string(run.get("id"), "run id")
        if run_id in ids:
            raise ValueError(f"Duplicate run id: {run_id}")
        ids.add(run_id)
        task_id = run.get("task_id")
        condition = run.get("condition")
        repetition = run.get("repetition")
        if not isinstance(task_id, str) or not isinstance(condition, str) or task_id not in tasks or condition not in conditions:
            raise ValueError(f"Unknown task or condition in run {run_id}")
        if type(repetition) is not int or not 1 <= repetition <= repetitions:
            raise ValueError(f"Invalid repetition in run {run_id}")
        slot = (condition, task_id, repetition)
        if slot in slots:
            raise ValueError(f"Duplicate task/condition/repetition: {slot}")
        status = run.get("status")
        success = run.get("success")
        if not isinstance(status, str) or status not in _STATUSES or success is not ({"passed": True, "failed": False}.get(status)):
            raise ValueError(f"Invalid status or success in run {run_id}")
        run_runner = run.get("runner")
        if not isinstance(run_runner, dict):
            raise ValueError(f"runner data missing in run {run_id}")
        slots[slot] = run
    return conditions, tasks, slots


def _mean(values: list[float | int]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _usage_mean(runs: list[dict], key: str) -> float | None:
    if not runs:
        return None
    values = []
    for run in runs:
        usage = run["runner"].get("token_usage")
        value = usage.get(key) if isinstance(usage, dict) else None
        if type(value) is not int or value < 0:
            return None
        values.append(value)
    return _mean(values)


def _counts(runs: list[dict | None]) -> dict:
    statuses = [run["status"] if run is not None else "not_run" for run in runs]
    counts = {status: statuses.count(status) for status in ("passed", "failed", "infrastructure_error", "not_run")}
    scored = counts["passed"] + counts["failed"]
    completed = scored + counts["infrastructure_error"]
    scored_runs = [run for run in runs if run is not None and run["status"] in _SCORED]
    durations = [run["runner"].get("duration_seconds") for run in scored_runs]
    return {
        "completed": completed,
        "scored": scored,
        **counts,
        "pass_rate": round(counts["passed"] / scored, 6) if scored else None,
        "mean_runner_seconds": _mean(durations) if durations and all(type(v) in (int, float) and v >= 0 for v in durations) else None,
        "mean_input_tokens": _usage_mean(scored_runs, "input_tokens"),
        "mean_output_tokens": _usage_mean(scored_runs, "output_tokens"),
    }


def _condition_summary(condition: str, tasks: dict[str, dict], repetitions: int, slots: dict) -> dict:
    per_task = {
        task_id: _counts([slots.get((condition, task_id, rep)) for rep in range(1, repetitions + 1)])
        for task_id in sorted(tasks)
    }
    all_runs = [slots.get((condition, task_id, rep)) for task_id in sorted(tasks) for rep in range(1, repetitions + 1)]
    return {**_counts(all_runs), "per_task": per_task}


def _bootstrap_ci(task_deltas: list[float]) -> list[float]:
    rng = random.Random(_BOOTSTRAP_SEED)
    count = len(task_deltas)
    estimates = sorted(
        sum(rng.choice(task_deltas) for _ in range(count)) / count
        for _ in range(_BOOTSTRAP_SAMPLES)
    )
    return [round(estimates[int(0.025 * (_BOOTSTRAP_SAMPLES - 1))], 6),
            round(estimates[int(0.975 * (_BOOTSTRAP_SAMPLES - 1))], 6)]


def _pairwise(left_slots: dict, right_slots: dict, left: str, right: str, task_ids: list[str], repetitions: int) -> dict:
    per_task: dict[str, dict] = {}
    task_deltas: list[float] = []
    matched_pairs = excluded_pairs = 0
    excluded_reasons = {"missing": 0, "infrastructure_error": 0, "not_run": 0}
    improvements = ties = regressions = 0
    for task_id in task_ids:
        left_passes = right_passes = matched = 0
        for repetition in range(1, repetitions + 1):
            a = left_slots.get((left, task_id, repetition))
            b = right_slots.get((right, task_id, repetition))
            if a is not None and b is not None and a["status"] in _SCORED and b["status"] in _SCORED:
                matched += 1
                matched_pairs += 1
                left_passes += a["status"] == "passed"
                right_passes += b["status"] == "passed"
            else:
                excluded_pairs += 1
                if a is None or b is None:
                    excluded_reasons["missing"] += 1
                elif "infrastructure_error" in (a["status"], b["status"]):
                    excluded_reasons["infrastructure_error"] += 1
                else:
                    excluded_reasons["not_run"] += 1
        complete = matched == repetitions
        delta = round((right_passes - left_passes) / repetitions, 6) if complete else None
        if complete:
            task_deltas.append(delta)
            if delta > 0:
                improvements += 1
            elif delta < 0:
                regressions += 1
            else:
                ties += 1
        per_task[task_id] = {
            "matched_pairs": matched,
            "excluded_pairs": repetitions - matched,
            "complete": complete,
            "left_pass_rate": round(left_passes / repetitions, 6) if complete else None,
            "right_pass_rate": round(right_passes / repetitions, 6) if complete else None,
            "delta": delta,
            "outcome": (
                "improvement" if delta is not None and delta > 0 else
                "regression" if delta is not None and delta < 0 else
                "tie" if delta == 0 else "incomplete"
            ),
        }
    partial_pairs = excluded_pairs > 0
    # A zero-width interval on uniformly easy tasks is not evidence of equivalence.
    ci_eligible = len(task_deltas) >= 5 and not partial_pairs and len(set(task_deltas)) > 1
    return {
        "left_condition": left,
        "right_condition": right,
        "matched_pairs": matched_pairs,
        "excluded_pairs": excluded_pairs,
        "excluded_reasons": excluded_reasons,
        "complete_tasks": len(task_deltas),
        "partial_pairs": partial_pairs,
        "improvements": improvements,
        "ties": ties,
        "regressions": regressions,
        "delta": _mean(task_deltas),
        "ci95": _bootstrap_ci(task_deltas) if ci_eligible else None,
        "descriptive_only": not ci_eligible,
        "interval_method": "paired task bootstrap, 4000 resamples, seed 20260417",
        "interval_note": "Suppressed for fewer than 5 tasks, incomplete pairs, or no observed task variation; never proves equivalence.",
        "per_task": per_task,
    }


def summarize_v2(metrics: dict) -> dict:
    """Summarize every condition and every pair without running a model."""
    conditions, tasks, slots = _validate(metrics)
    repetitions = metrics["repetitions"]
    condition_ids = sorted(conditions)
    summaries = {
        condition: _condition_summary(condition, tasks, repetitions, slots)
        for condition in condition_ids
    }
    comparisons = [
        _pairwise(slots, slots, left, right, sorted(tasks), repetitions)
        for index, left in enumerate(condition_ids)
        for right in condition_ids[index + 1:]
    ]
    return {"conditions": summaries, "comparisons": comparisons}


def compare_results(a: dict, b: dict, left_condition: str, right_condition: str) -> dict:
    """Compare compatible metrics, rejecting mismatched experimental inputs."""
    left_conditions, left_tasks, left_slots = _validate(a)
    right_conditions, right_tasks, right_slots = _validate(b)
    if left_condition not in left_conditions or right_condition not in right_conditions:
        raise ValueError("Unknown comparison condition")
    if a["suite"] != b["suite"]:
        raise ValueError("Incompatible suite identity, version, or hash")
    if {key: item["sha256"] for key, item in left_tasks.items()} != {key: item["sha256"] for key, item in right_tasks.items()}:
        raise ValueError("Incompatible task IDs or hashes")
    if a["repetitions"] != b["repetitions"]:
        raise ValueError("Incompatible repetitions")
    if a["runner"] != b["runner"]:
        raise ValueError("Incompatible runner model, reasoning effort, or configuration")
    result = _pairwise(left_slots, right_slots, left_condition, right_condition, sorted(left_tasks), a["repetitions"])
    result["compatible"] = True
    result["left_condition_summary"] = _condition_summary(left_condition, left_tasks, a["repetitions"], left_slots)
    result["right_condition_summary"] = _condition_summary(right_condition, right_tasks, b["repetitions"], right_slots)
    return result
