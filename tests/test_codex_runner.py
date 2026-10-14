"""Checks for the real Codex adapter without starting a model process."""

import io
import json
from pathlib import Path

import pytest

from skillarena import codex_runner


def _events(*items: dict) -> str:
    return "".join(json.dumps(item) + "\n" for item in items)


def _run_with_stub(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    skill: Path | None = None,
    stdout: str | None = None,
    audit: list[dict] | None = None,
    returncode: int = 0,
    timed_out: bool = False,
) -> tuple[dict, dict, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "TASK.md").write_text("Complete this task", encoding="utf-8")
    evidence = tmp_path / "evidence"
    captured: dict = {}

    def fake_run_process(command, *, cwd, env, timeout, stdin):
        captured.update(command=command, cwd=cwd, env=env, timeout=timeout, stdin=stdin)
        assert cwd.is_dir()
        assert not (cwd / "TASK.md").exists()
        if audit is not None:
            (evidence / "tools.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in audit), encoding="utf-8"
            )
        return {
            "returncode": returncode,
            "stdout": stdout if stdout is not None else _events(
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "workspace"}},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
            ),
            "stderr": "",
            "timed_out": timed_out,
            "duration_seconds": 1.25,
        }

    monkeypatch.setattr(codex_runner, "run_process", fake_run_process)
    result = codex_runner.run_agent(
        "codex.exe", {"CODEX_HOME": str(tmp_path / "auth-home")}, workspace, skill,
        evidence, timeout=30, max_tools=12,
    )
    return result, captured, evidence


def _settings(command: list[str]) -> dict:
    settings = {}
    for index, token in enumerate(command):
        if token == "--config":
            key, raw = command[index + 1].split("=", 1)
            settings[key] = json.loads(raw)
    return settings


def test_agent_uses_chatgpt_high_reasoning_and_one_local_mcp(monkeypatch, tmp_path: Path) -> None:
    result, captured, evidence = _run_with_stub(
        monkeypatch, tmp_path, audit=[{"name": "write_file", "status": "ok"}]
    )
    command = captured["command"]
    settings = _settings(command)
    assert command[:2] == ["codex.exe", "exec"]
    assert command[command.index("--model") + 1] == codex_runner.MODEL
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert {"--ignore-user-config", "--ignore-rules", "--strict-config", "--ephemeral", "--json"} <= set(command)
    assert settings["model_reasoning_effort"] == "high"
    assert settings["forced_login_method"] == "chatgpt"
    assert settings["model_provider"] == "openai"
    assert settings["approval_policy"] == "never"
    assert settings["web_search"] == "disabled"
    assert settings["features.shell_tool"] is False
    assert settings["features.apps"] is False
    assert settings["features.plugins"] is False
    assert settings["features.skip_host_skill_discovery"] is True
    assert settings["mcp_servers.workspace.command"] == codex_runner.sys.executable
    assert settings["mcp_servers.workspace.required"] is True
    assert settings["mcp_servers.workspace.default_tools_approval_mode"] == "approve"
    assert not any(key.startswith("mcp_servers.") and not key.startswith("mcp_servers.workspace.") for key in settings)
    server_args = settings["mcp_servers.workspace.args"]
    assert server_args[server_args.index("--root") + 1] == str(tmp_path / "workspace")
    assert server_args[server_args.index("--audit") + 1] == str(evidence / "tools.jsonl")
    assert server_args[server_args.index("--max-tool-calls") + 1] == "12"
    assert "--skill-root" not in server_args
    assert result["valid_agent_run"] is True
    assert result["started"] is True
    assert result["token_usage"] == {"input_tokens": 10, "output_tokens": 3}


def test_skill_root_and_loaded_status_come_from_audit(monkeypatch, tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Use me", encoding="utf-8")
    result, captured, _ = _run_with_stub(
        monkeypatch, tmp_path, skill=skill,
        audit=[{"name": "read_skill", "status": "error"}, {"name": "read_skill", "status": "ok"}],
    )
    args = _settings(captured["command"])["mcp_servers.workspace.args"]
    assert args[args.index("--skill-root") + 1] == str(skill)
    assert result["skill_loaded"] is True
    assert result["tool_calls"] == 2


@pytest.mark.parametrize(
    ("stdout", "unexpected", "malformed"),
    [
        (_events({"type": "turn.started"}, {"type": "item.completed", "item": {"type": "command_execution"}}, {"type": "turn.completed"}), ["command_execution"], 0),
        (_events({"type": "turn.started"}, {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "foreign"}}, {"type": "turn.completed"}), ["mcp_tool_call"], 0),
        (_events({"type": "turn.started"}, {"type": "turn.completed"}) + "not-json\n", [], 1),
    ],
)
def test_foreign_tools_and_malformed_protocol_invalidate_run(
    monkeypatch, tmp_path: Path, stdout: str, unexpected: list[str], malformed: int
) -> None:
    result, _, _ = _run_with_stub(
        monkeypatch, tmp_path, stdout=stdout, audit=[{"name": "list_files", "status": "ok"}]
    )
    assert result["valid_agent_run"] is False
    assert result["unexpected_tools"] == unexpected
    assert result["malformed_events"] == malformed
    assert result["protocol_valid"] is (malformed == 0)


def test_timeout_preserves_started_event(monkeypatch, tmp_path: Path) -> None:
    result, _, _ = _run_with_stub(
        monkeypatch, tmp_path, stdout=_events({"type": "turn.started"}),
        audit=[{"name": "list_files", "status": "ok"}], returncode=-9, timed_out=True,
    )
    assert result["timed_out"] is True
    assert result["started"] is True
    assert result["completed"] is False
    assert result["valid_agent_run"] is False


def test_quota_requires_explicit_absence_of_paid_credits() -> None:
    for credits in (None, {}, {"hasCredits": True}):
        with pytest.raises(ValueError, match="Paid-credit state"):
            codex_runner.require_included_quota({"primary": {"usedPercent": 10}, "credits": credits})
    codex_runner.require_included_quota({"primary": {"usedPercent": 10}, "credits": {"hasCredits": False}})


def test_isolated_login_and_quota_result_do_not_expose_credentials(monkeypatch, tmp_path: Path) -> None:
    login_home = tmp_path / "login"
    login_home.mkdir()
    secret = "UNIQUE_TEST_AUTH_TOKEN_45823"
    (login_home / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": secret}}), encoding="utf-8"
    )
    monkeypatch.setenv("CODEX_HOME", str(login_home))
    monkeypatch.setenv("OPENAI_EXAMPLE_OPTION", "must-be-removed")
    monkeypatch.setenv("SKILLARENA_EXAMPLE_OPTION", "must-be-removed")
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    with codex_runner.isolated_login() as env:
        ephemeral_home = Path(env["CODEX_HOME"])
        assert ephemeral_home != login_home
        assert secret in (ephemeral_home / "auth.json").read_text(encoding="utf-8")
        assert secret not in repr(env)
        assert "OPENAI_EXAMPLE_OPTION" not in env
        assert "SKILLARENA_EXAMPLE_OPTION" not in env
    assert not ephemeral_home.exists()

    class FakeProcess:
        stdin = io.StringIO()
        stdout = io.StringIO(_events(
            {"id": 1, "result": {}},
            {"id": 2, "result": {"rateLimits": {
                "primary": {"usedPercent": 10}, "credits": {"hasCredits": False},
                "accountId": secret, "accessToken": secret,
            }}},
        ))

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(codex_runner.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    quota = codex_runner.read_quota("codex.exe", {"CODEX_HOME": "ephemeral"})
    assert quota["primary"] == {"usedPercent": 10}
    assert secret not in json.dumps(quota)
    assert "accountId" not in quota
