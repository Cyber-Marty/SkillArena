"""Trusted offline verifier for this data workflow task."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(task_dir: Path, args: list[str]) -> int:
    if len(args) != 1:
        print("usage: python verifier.py WORKSPACE", file=sys.stderr)
        return 2

    workspace = Path(args[0])
    oracle_path = task_dir / "oracle" / "output.json"
    try:
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"verifier infrastructure error: {exc}", file=sys.stderr)
        return 2

    if not workspace.is_dir():
        print("verifier infrastructure error: workspace is not a directory", file=sys.stderr)
        return 2

    output_path = workspace / "output.json"
    try:
        actual = json.loads(output_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("wrong output: output.json is missing", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"wrong output: output.json cannot be read as JSON: {exc}", file=sys.stderr)
        return 1

    if not _same_json(actual, oracle):
        print("wrong output: JSON content differs from the expected result", file=sys.stderr)
        return 1

    print("pass")
    return 0


def _same_json(actual: object, expected: object) -> bool:
    """Compare JSON values, keeping booleans distinct from numbers."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _same_json(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_json(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected


if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parent, sys.argv[1:]))
