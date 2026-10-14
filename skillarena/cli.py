"""SkillArena command line interface."""

import json
from pathlib import Path
import shutil

import typer
import yaml

from .benchmark import load_benchmark
from .engine import run_benchmark
from .report import render_report


app = typer.Typer(help="Local A/B benchmarks for AI agent skills.", no_args_is_help=True)


@app.command()
def run(
    benchmark: Path = typer.Argument(..., help="Benchmark YAML file"),
    output: Path = typer.Option(Path("results"), "--output", "-o", help="New results directory"),
    execute: bool = typer.Option(False, "--execute", help="Explicitly permit real model runs for schema v2"),
) -> None:
    """Run both arms and write metrics, logs, artifacts and an HTML report."""
    try:
        schema = yaml.safe_load(benchmark.read_text(encoding="utf-8"))
        if isinstance(schema, dict) and schema.get("schema_version") == 2:
            from .suite import load_experiment, run_experiment
            if not execute:
                raise ValueError("Real agent evaluation requires --execute. Use 'skillarena plan FILE' for an offline preview.")
            result = run_experiment(load_experiment(benchmark), output, progress=typer.echo)
            typer.echo(f"Report: {output.resolve() / 'report.html'}")
            typer.echo(f"Evidence: {output.resolve() / 'manifest.json'}")
            if not result["complete"]:
                typer.echo(result.get("stop_reason", "Experiment incomplete"), err=True)
                raise typer.Exit(1)
            return
        result = run_benchmark(load_benchmark(benchmark), output)
        report = render_report(output.resolve() / "metrics.json")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc
    summary = result["summary"]
    typer.echo(f"Benchmark: {result['benchmark']}")
    typer.echo(f"Baseline: {summary['baseline']['successes']}/{summary['baseline']['runs']}")
    typer.echo(f"With skill: {summary['skill']['successes']}/{summary['skill']['runs']}")
    typer.echo(f"Report: {report}")


@app.command()
def report(metrics: Path = typer.Argument(Path("results/metrics.json")),
           output: Path | None = typer.Option(None, "--output", "-o")) -> None:
    """Rebuild the HTML report from an existing metrics.json."""
    try:
        if (metrics.resolve().parent / "manifest.json").exists():
            from .evidence import verify_bundle
            checked = verify_bundle(metrics.resolve().parent)
            if not checked["valid"]:
                raise ValueError("Evidence integrity check failed")
        typer.echo(render_report(metrics.resolve(), output))
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def compare(first: Path, second: Path | None = None,
            left: str = typer.Option("v1", "--left"),
            right: str = typer.Option("v2", "--right"),
            output: Path | None = typer.Option(None, "--output", "-o")) -> None:
    """Compare v2 skill conditions, or compare two legacy result directories."""
    try:
        from .evidence import verify_bundle
        for path in {first.resolve(), (second or first).resolve()}:
            if (path / "manifest.json").exists():
                checked = verify_bundle(path)
                if not checked["valid"]:
                    raise ValueError("Evidence integrity check failed: " + "; ".join(checked["errors"]))
        data = json.loads((first / "metrics.json").read_text(encoding="utf-8"))
        if data.get("schema_version") == 2:
            from .analysis_v2 import compare_results
            from .evidence import verify_bundle
            from .suite import write_json
            for path in {first.resolve(), (second or first).resolve()}:
                checked = verify_bundle(path)
                if not checked["valid"]:
                    raise ValueError("Evidence integrity check failed: " + "; ".join(checked["errors"]))
            other = json.loads(((second or first) / "metrics.json").read_text(encoding="utf-8"))
            comparison = compare_results(data, other, left, right)
            typer.echo(json.dumps(comparison, indent=2, ensure_ascii=False))
            if output:
                for path in {first.resolve(), (second or first).resolve()}:
                    if output.resolve() == path or path in output.resolve().parents:
                        raise ValueError("Comparison output must be outside sealed input bundles")
                if output.exists():
                    raise ValueError("Comparison output already exists")
                write_json(output, comparison)
            return
        if second is None:
            raise ValueError("Legacy comparison requires two result directories")
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
def plan(benchmark: Path) -> None:
    """Preview a frozen v2 schedule and inference budget; no model calls."""
    from .suite import load_experiment, plan_experiment
    try:
        typer.echo(json.dumps(plan_experiment(load_experiment(benchmark)), indent=2))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def verify(bundle: Path) -> None:
    """Verify file integrity offline; never execute bundle contents."""
    from .evidence import verify_bundle
    result = verify_bundle(bundle)
    typer.echo(json.dumps(result, indent=2))
    typer.echo("Integrity does not prove authenticity or independent replication.")
    if not result["valid"]:
        raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Check local ChatGPT login and included quota without model inference."""
    from .codex_runner import find_codex, isolated_login, read_quota, require_included_quota
    try:
        executable = find_codex()
        with isolated_login() as env:
            quota = read_quota(executable, env)
            require_included_quota(quota)
        typer.echo(json.dumps({"model": "gpt-6-sol", "reasoning_effort": "high", "auth": "chatgpt",
                               "included_quota_check": "passed", "quota": quota}, indent=2))
    except (OSError, ValueError) as exc:
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
