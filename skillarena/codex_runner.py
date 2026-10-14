"""ChatGPT-authenticated Codex with a narrowly scoped, audited workspace MCP server."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

MODEL = "gpt-6-sol"
EFFORT = "high"
INSTRUCTIONS = """You are a data-processing agent in a controlled evaluation.
Use only the workspace MCP tools to inspect task files and create output.json.
Start by listing available files and skills. Read a relevant skill when one is available.
Read TASK.md and the input files yourself. Follow the task's public requirements exactly.
You may check the JSON syntax with check_output; that tool does not grade correctness.
Do not use shell, web, external resources, or other tools. Do not try to access parent paths.
Do not ask questions: complete the task with the given files. Finish with a short summary.
"""


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)


def run_process(command: list[str], *, cwd: Path, env: dict, timeout: int, stdin: str = "") -> dict:
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", start_new_session=os.name != "nt")
    timed_out = False
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _stop(process)
        stdout, stderr = process.communicate(timeout=10)
    except BaseException:
        _stop(process)
        process.communicate(timeout=10)
        raise
    return {"returncode": process.returncode, "stdout": stdout, "stderr": stderr,
            "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started, 3)}


def find_codex() -> str:
    executable = os.environ.get("SKILLARENA_CODEX_BIN") or shutil.which("codex")
    if not executable or not Path(executable).is_file():
        raise ValueError("Set SKILLARENA_CODEX_BIN to a current Codex executable.")
    return executable


@contextmanager
def isolated_login():
    """Use existing login in an ephemeral home; never copy credentials into a result bundle."""
    forbidden = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY")
    if any(os.environ.get(key) for key in forbidden):
        raise ValueError("API credentials/custom endpoints detected. Only existing ChatGPT login is allowed.")
    source = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    try:
        auth = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("A file-backed Codex ChatGPT login is required.") from exc
    if auth.get("auth_mode") != "chatgpt" or auth.get("OPENAI_API_KEY"):
        raise ValueError("Only ChatGPT login is allowed; API fallback is disabled.")
    with tempfile.TemporaryDirectory(prefix="skillarena-auth-") as name:
        home = Path(name)
        auth_file = home / "auth.json"
        auth_file.write_text(json.dumps(auth), encoding="utf-8")
        auth_file.chmod(0o600)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("OPENAI_", "CODEX_", "SKILLARENA_"))}
        env.update(CODEX_HOME=str(home), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        yield env


def read_quota(executable: str, env: dict) -> dict:
    """Read rate limits without inference. Return no account identifiers or credentials."""
    process = subprocess.Popen([executable, "app-server", "--stdio"], env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding="utf-8", start_new_session=os.name != "nt")
    lines: queue.Queue = queue.Queue()
    def reader():
        for line in process.stdout:
            lines.put(line)
    threading.Thread(target=reader, daemon=True).start()
    def request(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
    def response(identifier):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                obj = json.loads(lines.get(timeout=max(.1, deadline - time.monotonic())))
            except queue.Empty:
                break
            if obj.get("id") == identifier:
                if "error" in obj:
                    raise ValueError("Cannot verify included quota: " + str(obj["error"].get("message", "RPC error")))
                return obj.get("result", {})
        raise ValueError("Cannot verify included quota; no model run was started.")
    try:
        request({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "skillarena", "version": "0.2.0"},
            "capabilities": {"experimentalApi": True}}})
        response(1)
        request({"method": "initialized", "params": {}})
        request({"id": 2, "method": "account/rateLimits/read", "params": {}})
        result = response(2)
        limits = result.get("rateLimits", {})
        return {key: limits.get(key) for key in ("primary", "secondary", "credits", "planType")}
    finally:
        _stop(process)
        process.wait(timeout=10)
        process.stdin.close()
        process.stdout.close()


def require_included_quota(snapshot: dict) -> None:
    """Conservative local gate, not a provider-side billing guarantee."""
    windows = [snapshot.get(key) for key in ("primary", "secondary")]
    if not any(isinstance(window, dict) for window in windows):
        raise ValueError("Included quota is unknown; refusing model execution.")
    for window in windows:
        if window is not None and (not isinstance(window, dict)
                                   or type(window.get("usedPercent")) not in (int, float)
                                   or not 0 <= window["usedPercent"] < 90):
            raise ValueError("Included quota is low or unknown; stopping before paid-credit fallback.")
    credits = snapshot.get("credits")
    if not isinstance(credits, dict) or credits.get("hasCredits") is not False:
        raise ValueError("Paid-credit state is available or unknown; refusing execution under the no-extra-spend policy.")


def run_agent(executable: str, env: dict, workspace: Path, skill: Path | None,
              evidence: Path, timeout: int, max_tools: int) -> dict:
    evidence.mkdir(parents=True, exist_ok=True)
    instructions = evidence / "instructions.txt"
    instructions.write_text(INSTRUCTIONS, encoding="utf-8")
    prompt = "Complete the task described in TASK.md using the workspace tools."
    (evidence / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    # The CLI cwd contains no task/evaluator/skill files. All task I/O is mediated by MCP.
    with tempfile.TemporaryDirectory(prefix="skillarena-context-") as context:
        frozen_server = evidence.parent.parent / "snapshot" / "implementation" / "workspace_mcp.py"
        server_path = frozen_server if frozen_server.is_file() else Path(__file__).with_name("workspace_mcp.py")
        server_args = [str(server_path), "--root", str(workspace),
                       "--audit", str(evidence / "tools.jsonl"), "--max-tool-calls", str(max_tools)]
        if skill:
            server_args.extend(["--skill-root", str(skill)])
        settings = {
            "model_reasoning_effort": EFFORT, "model_provider": "openai",
            "forced_login_method": "chatgpt", "approval_policy": "never",
            "project_doc_max_bytes": 0, "web_search": "disabled",
            "model_instructions_file": str(instructions), "history.persistence": "none",
            "mcp_servers.workspace.command": sys.executable,
            "mcp_servers.workspace.args": server_args,
            "mcp_servers.workspace.required": True,
            "mcp_servers.workspace.startup_timeout_sec": 20,
            "mcp_servers.workspace.default_tools_approval_mode": "approve",
        }
        for feature in ("shell_tool", "apps", "plugins", "hooks", "multi_agent", "multi_agent_v2",
                        "browser_use", "computer_use", "image_generation", "view_image",
                        "skill_search", "tool_suggest", "memories", "workspace_dependencies"):
            settings[f"features.{feature}"] = False
        settings["features.skip_host_skill_discovery"] = True
        command = [executable, "exec", "--ignore-user-config", "--ignore-rules", "--strict-config",
                   "--skip-git-repo-check", "--ephemeral", "--json", "--sandbox", "read-only",
                   "--model", MODEL, "--cd", context]
        for key, value in settings.items():
            command.extend(["--config", f"{key}={json.dumps(value)}"])
        command.append("-")
        process = run_process(command, cwd=Path(context), env=env, timeout=timeout, stdin=prompt)
    # Host-path redaction is disclosed; model/tool payloads are otherwise preserved.
    replacements = {str(Path.home()): "<USER_HOME>", str(workspace): "<WORKSPACE>",
                    str(evidence): "<RUN_EVIDENCE>", env["CODEX_HOME"]: "<CODEX_HOME>", context: "<CONTEXT>"}
    if skill:
        replacements[str(skill)] = "<SKILL>"
    for stream, filename in (("stdout", "events.jsonl"), ("stderr", "stderr.txt")):
        value = process[stream]
        for old, new in sorted(replacements.items(), key=lambda p: -len(p[0])):
            value = value.replace(old, new).replace(json.dumps(old)[1:-1], new)
        (evidence / filename).write_text(value, encoding="utf-8")
    events = []
    malformed_events = 0
    for line in process["stdout"].splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("Event must be an object")
            events.append(event)
        except ValueError:
            malformed_events += bool(line.strip())
    usage = next((event.get("usage") for event in reversed(events) if event.get("type") == "turn.completed"), None)
    allowed_items = {"agent_message", "reasoning", "todo_list", "error"}
    unexpected = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        if item.get("type") == "mcp_tool_call" and item.get("server") == "workspace":
            continue
        if item.get("type") not in allowed_items:
            unexpected.append(item.get("type", "unknown"))
    audit_path = evidence / "tools.jsonl"
    audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()] if audit_path.exists() else []
    completed = any(event.get("type") == "turn.completed" for event in events)
    protocol_valid = not malformed_events and not any(event.get("type") == "turn.failed" for event in events)
    tool_delivery_failure = any(event.get("type") == "item.completed"
                                and event.get("item", {}).get("type") == "mcp_tool_call"
                                and event["item"].get("error") is not None for event in events)
    return {key: process[key] for key in ("returncode", "timed_out", "duration_seconds")} | {
        "completed": completed, "token_usage": usage, "tool_calls": len(audit),
        "started": any(event.get("type") == "turn.started" for event in events),
        "protocol_valid": protocol_valid, "malformed_events": malformed_events,
        "tool_delivery_failure": tool_delivery_failure,
        "skill_loaded": any(item.get("name") == "read_skill" and item.get("status") == "ok" for item in audit),
        "unexpected_tools": unexpected,
        "valid_agent_run": process["returncode"] == 0 and completed and bool(audit) and not unexpected and protocol_valid,
    }
