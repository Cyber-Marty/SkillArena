"""SkillArena command line interface."""

import json
from pathlib import Path
import shutil

import typer

from .benchmark import load_benchmark
from .engine import run_benchmark
from .report import render_report


app = typer.Typer(help="Local A/B benchmarks for AI agent skills.", no_args_is_help=True)


@app.command()
def run(
    benchmark: Path = typer.Argument(..., help="Benchmark YAML file"),
    output: Path = typer.Option(Path("results"), "--output", "-o", help="New results directory"),
) -> None:
    """Run both arms and write metrics, logs, artifacts and an HTML report."""
    try:
        result = run_benchmark(load_benchmark(benchmark), output)
        report = render_report(output.resolve() / "metrics.json")
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc
    summary = result["summary"]
    typer.echo(f"Benchmark: {result['benchmark']}")
    typer.echo(f"Baseline: {summary['baseline']['successes']}/{summary['baseline']['runs']}")
    typer.echo(f"With skill: {summary['skill']['successes']}/{summary['skill']['runs']}")
    typer.echo(f"Report: {report}")


@app.command()
def report(metrics: Path = typer.Argument(Path("results/metrics.json"))) -> None:
    """Rebuild the HTML report from an existing metrics.json."""
    try:
        typer.echo(render_report(metrics.resolve()))
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def compare(first: Path, second: Path) -> None:
    """Print success rates from two result directories."""
    try:
        a, b = (json.loads((path / "metrics.json").read_text(encoding="utf-8")) for path in (first, second))
        for label, result in ((str(first), a), (str(second), b)):
            summary = result["summary"]
            typer.echo(
                f"{label}: baseline {summary['baseline']['success_rate']:.0%}, "
                f"skill {summary['skill']['success_rate']:.0%} "
                f"(change {summary['absolute_success_rate_change']:+.0%})"
            )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def init(destination: Path = typer.Argument(Path("my-benchmark"))) -> None:
    """Copy the starter benchmark into a new directory."""
    source = Path(__file__).resolve().parent / "starter"
    if not source.is_dir():
        typer.echo("Starter example is available in the GitHub repository.", err=True)
        raise typer.Exit(2)
    if destination.exists():
        typer.echo(f"Error: destination already exists: {destination}", err=True)
        raise typer.Exit(2)
    shutil.copytree(source, destination)
    typer.echo(f"Created {destination}")


if __name__ == "__main__":
    app()
