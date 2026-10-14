"""Synthetic demo runner. This is not an AI agent or a model benchmark."""

import os
from pathlib import Path


def main() -> None:
    source = Path(os.environ["SKILLARENA_TASK_DIR"]) / "calculate.py"
    # Deterministic behavior only illustrates how a command adapter receives a skill.
    if os.environ.get("SKILLARENA_SKILL_PATH"):
        code = source.read_text(encoding="utf-8")
        source.write_text(code.replace("numbers[:end_index]", "numbers[:end_index + 1]"), encoding="utf-8")


if __name__ == "__main__":
    main()
