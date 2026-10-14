from contextlib import nullcontext
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillarena import suite
from skillarena.cli import app
from skillarena.codex_runner import require_included_quota, isolated_login
from skillarena.evidence import verify_bundle


ROOT = Path(__file__).resolve().parents[1]


def test_plan_balances_conditions_and_caps_calls():
    experiment = suite.load_experiment(ROOT / "examples/agent_suite.yaml")
    plan = suite.plan_experiment(experiment)
    assert plan["planned_agent_runs"] == 30
    assert plan == suite.plan_experiment(experiment)
    schedule = plan["schedule"]
    for condition in ("baseline", "v1", "v2"):
        positions = [i % 3 for i, item in enumerate(schedule) if item["condition"] == condition]
        assert max(positions.count(i) for i in range(3)) - min(positions.count(i) for i in range(3)) <= 1


def test_real_run_requires_explicit_execute(tmp_path):
    result = CliRunner().invoke(app, ["run", str(ROOT / "examples/agent_smoke.yaml"), "-o", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "--execute" in result.output
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("snapshot", [
    {}, {"primary": {"usedPercent": 90}}, {"primary": {"usedPercent": "0"}},
    {"primary": {"usedPercent": 0}, "credits": {"hasCredits": True, "unlimited": False}},
])
def test_quota_fails_closed(snapshot):
    with pytest.raises(ValueError):
        require_included_quota(snapshot)


def test_api_key_is_refused_before_auth_read(monkeypatch):
    monkeypatch.setenv("CODEX_API_KEY", "test-not-a-real-key")
    with pytest.raises(ValueError, match="API credentials"):
        with isolated_login():
            pytest.fail("must not yield")


def offline_dependencies(monkeypatch):
    monkeypatch.setattr(suite, "find_codex", lambda: "fake-codex")
    monkeypatch.setattr(suite, "isolated_login", lambda: nullcontext(os.environ.copy()))
    monkeypatch.setattr(suite, "read_quota", lambda *args: {"primary": {"usedPercent": 0}, "credits": {"hasCredits": False}})
    monkeypatch.setattr(suite, "_environment", lambda _: {
        "python": "3.test", "os": "test", "os_release": "test", "codex_version": "fake-offline",
        "source_commit": None, "working_tree_dirty": False, "dependencies": {}})


def experiment_one_task():
    experiment = suite.load_experiment(ROOT / "examples/agent_smoke.yaml")
    return replace(experiment, tasks=experiment.tasks[:1], conditions=experiment.conditions[:2])


def test_offline_engine_scores_seals_and_compares(monkeypatch, tmp_path):
    offline_dependencies(monkeypatch)
    experiment = experiment_one_task()
    oracle = (experiment.tasks[0]["path"] / "oracle/output.json").read_text(encoding="utf-8")
    def fake_agent(executable, env, workspace, skill, evidence, timeout, max_tools):
        (workspace / "output.json").write_text(oracle if skill else "{}", encoding="utf-8")
        (evidence / "tools.jsonl").write_text('{"test_only": true}\n', encoding="utf-8")
        return {"returncode": 0, "completed": True, "timed_out": False, "duration_seconds": 1,
                "valid_agent_run": True, "tool_calls": 3, "skill_loaded": bool(skill), "token_usage": None}
    monkeypatch.setattr(suite, "run_agent", fake_agent)
    output = tmp_path / "bundle"
    metrics = suite.run_experiment(experiment, output, progress=lambda _: None)
    assert metrics["complete"]
    assert metrics["summary"]["conditions"]["baseline"]["passed"] == 0
    assert metrics["summary"]["conditions"]["v1"]["passed"] == 1
    assert verify_bundle(output)["valid"]
    assert (output / "report.html").exists()
    exported = tmp_path / "export.html"
    assert CliRunner().invoke(app, ["report", str(output / "metrics.json")]).exit_code == 2
    assert CliRunner().invoke(app, ["report", str(output / "metrics.json"), "--output", str(exported)]).exit_code == 0
    assert verify_bundle(output)["valid"]
    replay = suite.load_experiment(output / "snapshot/experiment.yaml")
    assert replay.tasks[0]["sha256"] == experiment.tasks[0]["sha256"]
    result = CliRunner().invoke(app, ["compare", str(output), "--left", "baseline", "--right", "v1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["delta"] == 1
    # Tampering must be rejected before a version comparison.
    (output / "metrics.json").write_text("{}", encoding="utf-8")
    assert CliRunner().invoke(app, ["compare", str(output)]).exit_code == 2


def test_infrastructure_failure_preserves_unrun_slots(monkeypatch, tmp_path):
    offline_dependencies(monkeypatch)
    def fake_agent(*args):
        return {"returncode": 2, "completed": False, "timed_out": False, "duration_seconds": 0,
                "valid_agent_run": False, "tool_calls": 0, "skill_loaded": False, "token_usage": None}
    monkeypatch.setattr(suite, "run_agent", fake_agent)
    output = tmp_path / "bundle"
    metrics = suite.run_experiment(experiment_one_task(), output, progress=lambda _: None)
    assert not metrics["complete"]
    assert [run["status"] for run in metrics["runs"]] == ["infrastructure_error", "not_run"]
    assert verify_bundle(output)["valid"]
