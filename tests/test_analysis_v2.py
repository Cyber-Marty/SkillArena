from copy import deepcopy

import pytest

from skillarena.analysis_v2 import compare_results, summarize_v2


def _metrics(task_count: int = 2, repetitions: int = 2) -> dict:
    tasks = [{"id": f"task-{index}", "sha256": f"{index:064x}"} for index in range(task_count)]
    runs = []
    for task in tasks:
        for repetition in range(1, repetitions + 1):
            for condition, passed in (("baseline", False), ("skill", True)):
                runs.append({
                    "id": f"{task['id']}-{repetition}-{condition}",
                    "task_id": task["id"],
                    "condition": condition,
                    "repetition": repetition,
                    "status": "passed" if passed else "failed",
                    "success": passed,
                    "runner": {
                        "duration_seconds": 2.0,
                        "token_usage": {"input_tokens": 10, "output_tokens": 5},
                    },
                })
    return {
        "schema_version": 2,
        "benchmark": "test",
        "suite": {"id": "suite", "version": "1", "sha256": "a" * 64},
        "runner": {"model": "test-model", "reasoning_effort": "high", "cli_version": "1", "implementation_sha256": "b" * 64},
        "conditions": [
            {"id": "baseline", "skill_sha256": None},
            {"id": "skill", "skill_sha256": "c" * 64},
        ],
        "tasks": tasks,
        "repetitions": repetitions,
        "runs": runs,
    }


def test_summary_counts_and_task_level_delta() -> None:
    summary = summarize_v2(_metrics())
    assert summary["conditions"]["baseline"]["scored"] == 4
    assert summary["conditions"]["baseline"]["pass_rate"] == 0
    assert summary["conditions"]["skill"]["pass_rate"] == 1
    assert summary["conditions"]["skill"]["mean_input_tokens"] == 10
    comparison = summary["comparisons"][0]
    assert (comparison["matched_pairs"], comparison["excluded_pairs"]) == (4, 0)
    assert (comparison["improvements"], comparison["ties"], comparison["regressions"]) == (2, 0, 0)
    assert comparison["delta"] == 1
    assert comparison["ci95"] is None
    assert comparison["descriptive_only"]


def test_partial_and_infrastructure_pairs_are_visible_and_excluded() -> None:
    metrics = _metrics()
    missing = metrics["runs"].pop()
    infra = next(run for run in metrics["runs"] if run["id"] == "task-0-1-skill")
    infra.update(status="infrastructure_error", success=None)
    summary = summarize_v2(metrics)
    assert summary["conditions"]["skill"]["infrastructure_error"] == 1
    assert summary["conditions"]["skill"]["not_run"] == 1
    comparison = summary["comparisons"][0]
    assert comparison["matched_pairs"] == 2
    assert comparison["excluded_pairs"] == 2
    assert comparison["excluded_reasons"] == {"missing": 1, "infrastructure_error": 1, "not_run": 0}
    assert comparison["complete_tasks"] == 0
    assert comparison["delta"] is None
    assert comparison["per_task"][missing["task_id"]]["complete"] is False


def test_task_cluster_bootstrap_is_deterministic_when_eligible() -> None:
    metrics = _metrics(task_count=5)
    uniform = summarize_v2(metrics)["comparisons"][0]
    assert uniform["ci95"] is None  # Do not imply certainty from a degenerate sample.
    for run in metrics["runs"]:
        if run["task_id"] == "task-0" and run["condition"] == "skill":
            run.update(status="failed", success=False)
    first = summarize_v2(metrics)["comparisons"][0]
    second = summarize_v2(metrics)["comparisons"][0]
    assert first["ci95"][0] < first["delta"] <= first["ci95"][1]
    assert first["ci95"] == second["ci95"]
    assert not first["descriptive_only"]
    metrics["runs"].pop()
    partial = summarize_v2(metrics)["comparisons"][0]
    assert partial["ci95"] is None
    assert partial["descriptive_only"]


def test_compare_results_requires_controlled_inputs() -> None:
    left = _metrics()
    right = deepcopy(left)
    right["benchmark"] = "new display name"
    result = compare_results(left, right, "baseline", "skill")
    assert result["compatible"]
    assert result["delta"] == 1
    for field, value in (("suite", {"id": "different", "version": "1", "sha256": "a" * 64}),
                         ("runner", {**right["runner"], "cli_version": "2"}),
                         ("tasks", [{"id": "task-0", "sha256": "f" * 64}, right["tasks"][1]]),
                         ("repetitions", 3)):
        changed = deepcopy(right)
        changed[field] = value
        with pytest.raises(ValueError, match="Incompatible"):
            compare_results(left, changed, "baseline", "skill")


def test_duplicate_slots_and_status_mismatches_rejected() -> None:
    metrics = _metrics()
    duplicate = deepcopy(metrics["runs"][0])
    duplicate["id"] = "unique-id"
    metrics["runs"].append(duplicate)
    with pytest.raises(ValueError, match="Duplicate task/condition/repetition"):
        summarize_v2(metrics)
    metrics["runs"].pop()
    metrics["runs"][0]["status"] = "passed"
    with pytest.raises(ValueError, match="Invalid status or success"):
        summarize_v2(metrics)


def test_token_mean_is_unknown_if_any_scored_run_lacks_usage() -> None:
    metrics = _metrics()
    metrics["runs"][0]["runner"]["token_usage"] = None
    assert summarize_v2(metrics)["conditions"]["baseline"]["mean_input_tokens"] is None
