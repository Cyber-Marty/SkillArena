import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from skillarena.workspace_mcp import WorkspaceServer


def call(server: WorkspaceServer, name: str, arguments: dict, request_id: int = 1) -> tuple[bool, dict]:
    response = server.handle(
        {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )
    assert response is not None
    result = response["result"]
    return result["isError"], json.loads(result["content"][0]["text"])


def test_file_tools_and_json_check(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "task.txt").write_text("fix this", encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    server = WorkspaceServer(root, audit)

    assert call(server, "list_files", {}) == (
        False, {"entries": [{"path": "task.txt", "type": "file", "size": 8}]}
    )
    assert call(server, "read_file", {"path": "task.txt"}) == (False, {"content": "fix this"})
    assert call(server, "write_file", {"path": "output.json", "content": '{"answer": 42}'}) == (
        False, {"path": "output.json", "bytes_written": 14}
    )
    assert call(server, "check_output", {}) == (
        False, {"valid_json": True, "type": "object", "field_types": {"answer": "number"}}
    )
    assert call(server, "write_file", {"path": "output.json", "content": "{"})[0] is False
    invalid, report = call(server, "check_output", {})
    assert invalid is False
    assert report["valid_json"] is False
    assert len(audit.read_text(encoding="utf-8").splitlines()) == 6


def test_rejects_escape_and_fixture_writes_with_safe_audit(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "fixture.txt").write_text("unchanged", encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    server = WorkspaceServer(root, audit, max_tool_calls=4)

    assert call(server, "read_file", {"path": "../outside.txt"})[0]
    assert call(server, "read_file", {"path": str(tmp_path / "outside.txt")})[0]
    assert call(server, "write_file", {"path": "fixture.txt", "content": "tampered"})[0]
    assert call(server, "write_file", {"path": "output.json", "content": "ok"})[0] is False
    assert call(server, "read_file", {"path": "fixture.txt"})[0]
    assert (root / "fixture.txt").read_text(encoding="utf-8") == "unchanged"
    assert (root / "output.json").read_text(encoding="utf-8") == "ok"

    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [record["sequence"] for record in records] == [1, 2, 3, 4, 5]
    assert records[0]["arguments"]["path"] == "[rejected path]"
    assert records[1]["arguments"]["path"] == "[rejected path]"
    assert records[2]["arguments"]["content_bytes"] == 8
    assert "tampered" not in audit.read_text(encoding="utf-8")


def test_malformed_unicode_is_rejected_without_crashing(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    audit = tmp_path / "audit.jsonl"
    server = WorkspaceServer(root, audit)
    assert call(server, "write_file", {"path": "output.json", "content": "\ud800"})[0]
    assert call(server, "read_file", {"path": "\ud800"})[0]
    assert len(audit.read_text(encoding="utf-8").splitlines()) == 2


def test_skill_tools_have_identical_schema_in_both_arms(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    audit = tmp_path / "audit.jsonl"
    baseline = WorkspaceServer(root, audit)
    baseline_tools = baseline.handle({"id": 1, "method": "tools/list"})["result"]["tools"]
    assert {item["name"] for item in baseline_tools} == {
        "list_files", "read_file", "write_file", "check_output", "list_skills", "read_skill"
    }
    assert call(baseline, "list_skills", {}) == (False, {"files": []})
    assert call(baseline, "read_skill", {})[0]

    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Use this skill", encoding="utf-8")
    (skill / "reference.txt").write_text("reference", encoding="utf-8")
    equipped = WorkspaceServer(root, audit, skill)
    assert equipped.handle({"id": 1, "method": "tools/list"})["result"]["tools"] == baseline_tools
    assert call(equipped, "list_skills", {}) == (False, {"files": ["SKILL.md", "reference.txt"]})
    assert call(equipped, "read_skill", {}) == (False, {"content": "Use this skill"})
    assert call(equipped, "read_skill", {"path": "../workspace/output.json"})[0]
    assert not (root / "SKILL.md").exists()
    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert records[-2]["name"] == "read_skill" and records[-2]["status"] == "ok"
    assert records[-1]["name"] == "read_skill" and records[-1]["status"] == "error"


def test_blocks_symlinks_and_audit_inside_workspace(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        (root / "link.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    server = WorkspaceServer(root, tmp_path / "audit.jsonl")
    assert call(server, "read_file", {"path": "link.txt"})[0]
    assert call(server, "write_file", {"path": "link.txt", "content": "x"})[0]
    assert call(server, "list_files", {}) == (False, {"entries": []})
    with pytest.raises(ValueError, match="audit must be outside"):
        WorkspaceServer(root, root / "audit.jsonl")


def test_stdio_subprocess_handshake_and_tool_call(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "task.txt").write_text("hello", encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    commands = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_file", "arguments": {"path": "task.txt"}}},
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-m", "skillarena.workspace_mcp", "--root", str(root), "--audit", str(audit)],
        input="".join(json.dumps(item) + "\n" for item in commands),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
        env=env,
    )
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert [message["id"] for message in messages] == [1, 2, 3, 4]
    assert messages[0]["result"]["protocolVersion"] == "2024-11-05"
    assert {tool["name"] for tool in messages[2]["result"]["tools"]} == {
        "list_files", "read_file", "write_file", "check_output", "list_skills", "read_skill"
    }
    assert json.loads(messages[3]["result"]["content"][0]["text"]) == {"content": "hello"}
    assert len(audit.read_text(encoding="utf-8").splitlines()) == 1
