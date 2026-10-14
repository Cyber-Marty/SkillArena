import os
from pathlib import Path
import subprocess
import sys


def test_codex_adapter_refuses_api_key() -> None:
    adapter = Path(__file__).resolve().parents[1] / "examples" / "python_bug_fix" / "codex_agent.py"
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "fake-key-that-must-not-be-used"
    result = subprocess.run(
        [sys.executable, str(adapter)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "Refusing to run while OPENAI_API_KEY is set" in result.stderr
