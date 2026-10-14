"""Render a portable, self-contained HTML report."""

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape


def render_report(metrics_path: Path) -> Path:
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    template = Environment(
        loader=PackageLoader("skillarena", package_path="."), trim_blocks=True, lstrip_blocks=True,
        autoescape=select_autoescape(["html"])
    ).get_template("report.html.j2")
    target = metrics_path.parent / "report.html"
    target.write_text(template.render(data=data), encoding="utf-8")
    return target
