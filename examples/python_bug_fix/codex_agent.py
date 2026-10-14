"""Run the installed Codex CLI as a model-only code repair adapter."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


MODEL = "gpt-6-sol"
EFFORT = "high"


def main() -> int:
    if os.environ.get("OPENAI_API_KEY"):
        print("Refusing to run while OPENAI_API_KEY is set; use ChatGPT login only.", file=sys.stderr)
        return 2
    auth_path = Path.home() / ".codex" / "auth.json"
    try:
        auth_mode = json.loads(auth_path.read_text(encoding="utf-8")).get("auth_mode")
    except (OSError, ValueError):
        auth_mode = None
    if auth_mode != "chatgpt":
        print("Refusing to run: Codex CLI must be signed in with ChatGPT.", file=sys.stderr)
        return 2
    executable = os.environ.get("SKILLARENA_CODEX_BIN") or shutil.which("codex")
    if not executable or not Path(executable).is_file():
        print("Codex CLI is not installed.", file=sys.stderr)
        return 2
    source = Path(os.environ["SKILLARENA_TASK_DIR"]) / "calculate.py"
    prompt = (
        "You are a code repair model. Do not use tools or read files. Return only a JSON object "
        "matching the provided schema, with the full corrected calculate.py source in 'replacement'. "
        "The file below is the complete input. Keep unrelated code unchanged.\n\n"
        "Task: " + os.environ["SKILLARENA_TASK_PROMPT"] + "\n\n"
        "Current calculate.py:\n```python\n" + source.read_text(encoding="utf-8") + "\n```"
    )
    skill_path = os.environ.get("SKILLARENA_SKILL_PATH")
    if skill_path:
        prompt += "\n\nAdditional skill instructions:\n" + Path(skill_path).read_text(encoding="utf-8")
    command = [
        executable, "exec", "--ignore-user-config", "--skip-git-repo-check",
        "--ephemeral", "--json", "--sandbox", "read-only", "--model", MODEL,
        "--config", f"model_reasoning_effort={EFFORT}",
        "--output-schema", str(Path(__file__).with_name("replacement.schema.json")),
        "--cd", os.getcwd(), prompt,
    ]
    print(f"SKILLARENA_CODEX_MODEL={MODEL} EFFORT={EFFORT} AUTH=chatgpt", flush=True)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode:
        return result.returncode
    messages = []
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            messages.append(event["item"].get("text", ""))
    if not messages:
        print("Codex returned no replacement.", file=sys.stderr)
        return 1
    try:
        replacement = json.loads(messages[-1])["replacement"]
        if not isinstance(replacement, str) or not replacement:
            raise ValueError("replacement must be non-empty text")
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Invalid replacement response: {exc}", file=sys.stderr)
        return 1
    source.write_text(replacement, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
