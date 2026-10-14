"""Offline contract checks for the frozen data workflow suite."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SUITE = Path(__file__).resolve().parents[1] / "benchmarks" / "data_workflows"
MANIFEST = json.loads((SUITE / "suite.json").read_text(encoding="utf-8"))
TASK_IDS = MANIFEST["tasks"]


def run_verifier(task_id: str, workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SUITE / task_id / "verifier.py"), str(workspace)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_manifest_and_public_fixtures_are_complete() -> None:
    assert MANIFEST == {
        "schema_version": 2,
        "id": "data-workflows-v1",
        "version": "1.0.0",
        "tasks": TASK_IDS,
    }
    assert len(TASK_IDS) == len(set(TASK_IDS)) == 10
    assert TASK_IDS[:2] == ["decimal-invoices", "missing-versus-zero"]
    assert set(TASK_IDS) == {
        path.name for path in SUITE.iterdir() if path.is_dir() and path.name != "__pycache__"
    }
    for task_id in TASK_IDS:
        task = SUITE / task_id
        metadata = json.loads((task / "task.json").read_text(encoding="utf-8"))
        fixture = task / "fixture"
        assert metadata["id"] == task_id
        assert metadata["title"]
        assert metadata["license"] == "MIT"
        assert "synthetic" in metadata["source"]
        assert metadata["tags"]
        assert metadata["prompt"] == (fixture / "TASK.md").read_text(encoding="utf-8")
        assert len(list(fixture.iterdir())) >= 2
        assert not (fixture / "oracle").exists()
        assert not (fixture / "verifier.py").exists()
        assert (task / "oracle" / "output.json").is_file()
        assert (task / "verifier.py").is_file()


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_oracle_submission_is_accepted(task_id: str, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(SUITE / task_id / "fixture", workspace)
    shutil.copy2(SUITE / task_id / "oracle" / "output.json", workspace / "output.json")
    result = run_verifier(task_id, workspace)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_plausible_wrong_answer_is_rejected(task_id: str, tmp_path: Path) -> None:
    answer = copy.deepcopy(json.loads((SUITE / task_id / "oracle" / "output.json").read_text(encoding="utf-8")))
    if task_id == "decimal-invoices":
        answer["invoices"][0]["tax"] = "0.82"  # binary-float/rounding error
    elif task_id == "missing-versus-zero":
        answer["items"][1]["order_qty"] = None  # zero treated as missing
    elif task_id == "csv-cleanup":
        answer["contacts"][0]["city"] = " London "  # whitespace retained
    elif task_id == "contact-dedupe":
        answer["contacts"][1]["id"] = "B02"  # wrong date-tie winner
    elif task_id == "grouped-sales":
        answer["regions"][0]["order_count"] = 3  # lines counted as orders
    elif task_id == "timezone-events":
        answer["events"][0]["utc_time"] = "2025-03-09T01:15:00Z"
    elif task_id == "customer-join":
        answer["orders"][1]["customer_name"] = ""  # empty versus null
    elif task_id == "stable-ranking":
        answer["ranking"][0], answer["ranking"][1] = answer["ranking"][1], answer["ranking"][0]
    elif task_id == "payment-reconciliation":
        answer["invoices"][1]["status"] = "settled"
    elif task_id == "schema-validation":
        answer["errors"][-1]["issues"].pop()  # only first two errors reported
    else:
        raise AssertionError(f"missing adversarial case for {task_id}")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "output.json").write_text(json.dumps(answer), encoding="utf-8")
    result = run_verifier(task_id, workspace)
    assert result.returncode == 1
    assert "wrong output" in result.stderr


def test_missing_or_invalid_submission_is_wrong_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert run_verifier(TASK_IDS[0], workspace).returncode == 1
    (workspace / "output.json").write_text("{broken", encoding="utf-8")
    assert run_verifier(TASK_IDS[0], workspace).returncode == 1


def test_missing_workspace_is_infrastructure_error(tmp_path: Path) -> None:
    result = run_verifier(TASK_IDS[0], tmp_path / "missing")
    assert result.returncode == 2
    assert "infrastructure error" in result.stderr
