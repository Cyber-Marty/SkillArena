from pathlib import Path

import pytest
import yaml

from skillarena.benchmark import load_benchmark
from skillarena.engine import run_benchmark
from skillarena.report import render_report


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo.yaml"


def test_demo_runs_in_isolated_workspaces(tmp_path: Path) -> None:
    result = run_benchmark(load_benchmark(DEMO), tmp_path / "results")
    assert result["summary"]["baseline"]["successes"] == 0
    assert result["summary"]["skill"]["successes"] == 3
    assert len(result["runs"]) == 6
    for run in result["runs"]:
        code = (tmp_path / "results" / "artifacts" / run["id"] / "calculate.py").read_text()
        assert ("end_index + 1" in code) == (run["arm"] == "skill")
    assert "numbers[:end_index]" in (DEMO.parent / "python_bug_fix" / "fixture" / "calculate.py").read_text()
    html = render_report(tmp_path / "results" / "metrics.json").read_text()
    assert "synthetic fixture" in html
    assert "Individual runs" in html


def test_invalid_repetitions_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    data = yaml.safe_load(DEMO.read_text())
    data["task"]["source"] = str((DEMO.parent / data["task"]["source"]).resolve())
    data["skill"] = str((DEMO.parent / data["skill"]).resolve())
    data["repetitions"] = 0
    invalid.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="repetitions"):
        load_benchmark(invalid)
