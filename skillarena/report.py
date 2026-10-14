"""Render a portable, self-contained HTML report."""

import json
import os
from pathlib import Path

from jinja2 import Environment, PackageLoader


def render_report(metrics_path: Path, output: Path | None = None) -> Path:
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    template = Environment(
        loader=PackageLoader("skillarena", package_path="."), trim_blocks=True, lstrip_blocks=True,
        # Both templates end in .html.j2; extension-based detection treats them
        # as .j2 and would otherwise render untrusted metrics as raw HTML.
        autoescape=True,
    ).get_template("report_v2.html.j2" if data.get("schema_version") == 2 else "report.html.j2")
    target = output or metrics_path.parent / "report.html"
    if (metrics_path.parent / "manifest.json").exists():
        if output is None or metrics_path.parent.resolve() in target.resolve().parents:
            raise ValueError("Sealed bundle is immutable; use report --output outside the bundle")
    if output is not None and target.exists():
        raise ValueError("Report output already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    evidence_base = Path(os.path.relpath(metrics_path.parent, target.parent)).as_posix()
    target.write_text(template.render(data=data, evidence_base=evidence_base), encoding="utf-8")
    return target
