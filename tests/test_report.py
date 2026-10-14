import json
from pathlib import Path

import pytest

from skillarena.evidence import seal_bundle
from skillarena.report import render_report


ATTACK = '<svg onload="alert(1)">'


def _write_metrics(root: Path, data: dict) -> Path:
    root.mkdir()
    metrics = root / "metrics.json"
    metrics.write_text(json.dumps(data), encoding="utf-8")
    return metrics


def test_legacy_report_escapes_metrics_text(tmp_path: Path) -> None:
    arm = {
        "success_rate": 0.5, "successes": 1, "runs": 2,
        "mean_runner_seconds": 1.0, "mean_input_tokens": None,
        "mean_output_tokens": None,
    }
    metrics = _write_metrics(tmp_path / "legacy", {
        "schema_version": 1,
        "benchmark": ATTACK,
        "description": ATTACK,
        "repetitions": 1,
        "created_at": "2026-01-01",
        "benchmark_sha256": "a" * 64,
        "metadata": {"title": ATTACK},
        "summary": {"baseline": arm, "skill": arm},
        "runs": [{
            "id": ATTACK, "arm": "baseline", "success": False,
            "runner": {"duration_seconds": 1},
            "evaluation": {"duration_seconds": 1},
            "changes": {"files_changed": []},
        }],
        "limitations": [ATTACK],
    })
    html = render_report(metrics).read_text(encoding="utf-8")
    assert "<svg" not in html.lower()
    assert "&lt;svg" in html.lower()
    assert "&lt;svg onload=&#34;alert(1)&#34;&gt;" in html.lower()


def test_v2_export_escapes_text_and_preserves_sealed_bundle(tmp_path: Path) -> None:
    metrics = _write_metrics(tmp_path / "bundle", {
        "schema_version": 2,
        "benchmark": ATTACK,
        "runner": {"model": ATTACK, "reasoning_effort": "high"},
        "tasks": [{"id": ATTACK, "title": ATTACK}],
        "repetitions": 1,
        "evidence_level": "author-submitted",
        "complete": False,
        "summary": {
            "conditions": {"skill": {
                "pass_rate": None, "passed": 0, "scored": 0,
                "infrastructure_error": 0, "not_run": 1,
            }},
            "comparisons": [],
        },
        "runs": [{
            "id": ATTACK, "task_id": ATTACK, "repetition": 1,
            "condition": ATTACK, "status": "failed",
            "runner": {"tool_calls": 1, "skill_loaded": False, "duration_seconds": 1},
        }],
        "limitations": [ATTACK],
        "suite": {"id": ATTACK, "version": "1"},
        "created_at": "2026-01-01",
    })
    seal_bundle(metrics.parent)
    manifest_before = (metrics.parent / "manifest.json").read_bytes()
    metrics_before = metrics.read_bytes()
    with pytest.raises(ValueError, match="immutable"):
        render_report(metrics)
    exported = render_report(metrics, tmp_path / "export.html")
    html = exported.read_text(encoding="utf-8")
    assert "<svg" not in html.lower()
    assert "&lt;svg" in html.lower()
    assert '<a href="bundle/metrics.json">' in html
    assert 'href="bundle/runs/' in html
    assert (metrics.parent / "manifest.json").read_bytes() == manifest_before
    assert metrics.read_bytes() == metrics_before
    assert not (metrics.parent / "report.html").exists()
