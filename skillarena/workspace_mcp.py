"""A small, file-only MCP server for isolated SkillArena trials.

The server intentionally exposes no process, network, or evaluation capability.
The benchmark harness must place the audit file outside the trial workspace.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys
import time
from typing import Any


MAX_FILE_BYTES = 1_048_576
MAX_MESSAGE_BYTES = 2_097_152
MAX_LIST_ENTRIES = 1_000
PROTOCOL_VERSION = "2024-11-05"


class ToolFailure(Exception):
    """A safe error that may be shown to the trial agent."""


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _windows_reserved(part: str) -> bool:
    stem = part.split(".", 1)[0].rstrip(" ").upper()
    return (
        part.endswith((" ", "."))
        or stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
        or stem in {f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"}
    )


class WorkspaceServer:
    def __init__(
        self, root: Path, audit: Path, skill_root: Path | None = None, max_tool_calls: int = 80
    ) -> None:
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        root = root.absolute()
        if not root.is_dir() or _is_link(root):
            raise ValueError("root must be an existing, ordinary directory")
        self.root = root.resolve(strict=True)
        self.skill_root = None
        if skill_root is not None:
            skill_root = skill_root.absolute()
            if not skill_root.is_dir() or _is_link(skill_root):
                raise ValueError("skill_root must be an existing, ordinary directory")
            self.skill_root = skill_root.resolve(strict=True)
            if (
                self.skill_root == self.root
                or self.root in self.skill_root.parents
                or self.skill_root in self.root.parents
            ):
                raise ValueError("skill_root must not overlap the writable workspace")
        audit = audit.absolute()
        if not audit.parent.is_dir():
            raise ValueError("audit parent directory must exist")
        self.audit = audit.resolve(strict=False)
        if self.audit == self.root or self.root in self.audit.parents:
            raise ValueError("audit must be outside the workspace")
        if self.skill_root is not None and (self.audit == self.skill_root or self.skill_root in self.audit.parents):
            raise ValueError("audit must be outside the skill package")
        if self.audit.exists() and _is_link(self.audit):
            raise ValueError("audit must not be a symlink or reparse point")
        self.max_tool_calls = max_tool_calls
        self.tool_calls = 0

    @staticmethod
    def _relative_path(raw: Any) -> Path:
        if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
            raise ToolFailure("path must be a nonempty relative path using / separators")
        try:
            raw.encode("utf-8")
        except UnicodeError as exc:
            raise ToolFailure("path must be UTF-8 text") from exc
        posix = PurePosixPath(raw)
        windows = PureWindowsPath(raw)
        if posix.is_absolute() or windows.is_absolute() or windows.drive or ":" in raw:
            raise ToolFailure("absolute paths are not allowed")
        if any(part == ".." for part in raw.split("/")):
            raise ToolFailure("parent path components are not allowed")
        if any(_windows_reserved(part) for part in posix.parts):
            raise ToolFailure("reserved path components are not allowed")
        return Path(*posix.parts)

    def _path(self, base: Path, raw: Any, *, allow_missing_leaf: bool = False) -> Path:
        relative = self._relative_path(raw)
        candidate = base / relative
        current = base
        for index, part in enumerate(relative.parts):
            current = current / part
            if not current.exists() and not current.is_symlink():
                if allow_missing_leaf and index == len(relative.parts) - 1:
                    return candidate
                raise ToolFailure("path does not exist")
            if _is_link(current):
                raise ToolFailure("symlinks and reparse points are not allowed")
        return candidate

    def _read_text(self, path: Path) -> str:
        if not path.is_file():
            raise ToolFailure("path is not a regular file")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ToolFailure("file is too large")
        try:
            data = path.read_bytes()
            if len(data) > MAX_FILE_BYTES:
                raise ToolFailure("file is too large")
            return data.decode("utf-8")
        except UnicodeError as exc:
            raise ToolFailure("file is not UTF-8 text") from exc

    def _list(self, base: Path, raw: Any) -> dict[str, Any]:
        path = self._path(base, raw)
        if not path.is_dir():
            raise ToolFailure("path is not a directory")
        entries: list[dict[str, Any]] = []
        with os.scandir(path) as iterator:
            for entry in iterator:
                child = Path(entry.path)
                if _is_link(child):
                    continue
                if len(entries) >= MAX_LIST_ENTRIES:
                    raise ToolFailure("directory has too many entries")
                kind = "directory" if entry.is_dir(follow_symlinks=False) else "file"
                if kind == "file" and not entry.is_file(follow_symlinks=False):
                    continue
                item: dict[str, Any] = {"path": child.relative_to(base).as_posix(), "type": kind}
                if kind == "file":
                    item["size"] = child.stat().st_size
                entries.append(item)
        entries.sort(key=lambda item: item["path"])
        return {"entries": entries}

    def _tools(self) -> list[dict[str, Any]]:
        path_field = {"type": "string", "description": "Relative path within the workspace"}
        tools = [
            {
                "name": "list_files",
                "description": "List the immediate files and directories in the trial workspace.",
                "inputSchema": {"type": "object", "properties": {"path": {**path_field, "default": "."}}, "additionalProperties": False},
            },
            {
                "name": "read_file",
                "description": "Read a UTF-8 file in the trial workspace.",
                "inputSchema": {"type": "object", "properties": {"path": path_field}, "required": ["path"], "additionalProperties": False},
            },
            {
                "name": "write_file",
                "description": "Write the agent answer to output.json in the trial workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": path_field, "content": {"type": "string"}},
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "check_output",
                "description": "Check whether output.json contains valid JSON and report JSON types only.",
                "inputSchema": {"type": "object", "properties": {"path": {**path_field, "default": "output.json"}}, "additionalProperties": False},
            },
        ]
        tools.extend(
            [
                {
                    "name": "list_skills",
                    "description": "List files in the supplied read-only skill package, if present.",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                {
                    "name": "read_skill",
                    "description": "Read a UTF-8 file from the supplied read-only skill package, if present.",
                    "inputSchema": {"type": "object", "properties": {"path": {**path_field, "default": "SKILL.md"}}, "additionalProperties": False},
                },
            ]
        )
        return tools

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "list_files": ({"path"}, set()),
            "read_file": ({"path"}, {"path"}),
            "write_file": ({"path", "content"}, {"path", "content"}),
            "check_output": ({"path"}, set()),
            "list_skills": (set(), set()),
            "read_skill": ({"path"}, set()),
        }
        if name not in allowed:
            raise ToolFailure("unknown or unavailable tool")
        keys, required = allowed[name]
        if arguments.keys() - keys or required - arguments.keys():
            raise ToolFailure("invalid tool arguments")
        if name == "list_files":
            return self._list(self.root, arguments.get("path", "."))
        if name == "read_file":
            content = self._read_text(self._path(self.root, arguments["path"]))
            return {"content": content}
        if name == "write_file":
            if arguments["path"] != "output.json":
                raise ToolFailure("writes are limited to output.json")
            content = arguments["content"]
            if not isinstance(content, str):
                raise ToolFailure("content must be a string")
            try:
                encoded = content.encode("utf-8")
            except UnicodeError as exc:
                raise ToolFailure("content must be UTF-8 text") from exc
            if len(encoded) > MAX_FILE_BYTES:
                raise ToolFailure("content is too large")
            path = self._path(self.root, "output.json", allow_missing_leaf=True)
            if path.exists() and not path.is_file():
                raise ToolFailure("output.json is not a regular file")
            path.write_bytes(encoded)
            return {"path": "output.json", "bytes_written": len(encoded)}
        if name == "check_output":
            if arguments.get("path", "output.json") != "output.json":
                raise ToolFailure("check_output is limited to output.json")
            content = self._read_text(self._path(self.root, "output.json"))
            try:
                value = json.loads(content)
            except json.JSONDecodeError as exc:
                return {"valid_json": False, "error": exc.msg, "line": exc.lineno, "column": exc.colno}
            result: dict[str, Any] = {"valid_json": True, "type": _json_type(value)}
            if isinstance(value, dict):
                result["field_types"] = {key: _json_type(val) for key, val in value.items()}
            return result
        if name == "list_skills":
            if self.skill_root is None:
                return {"files": []}
            files: list[str] = []
            for directory, dirs, names in os.walk(self.skill_root, followlinks=False):
                dirs[:] = [item for item in dirs if not _is_link(Path(directory) / item)]
                for item in names:
                    path = Path(directory) / item
                    if not _is_link(path) and path.is_file():
                        files.append(path.relative_to(self.skill_root).as_posix())
                    if len(files) > MAX_LIST_ENTRIES:
                        raise ToolFailure("skill package has too many files")
            return {"files": sorted(files)}
        if self.skill_root is None:
            raise ToolFailure("no skill package is available")
        return {"content": self._read_text(self._path(self.skill_root, arguments.get("path", "SKILL.md")))}

    def _safe_audit_args(self, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            return {"arguments": "[invalid]"}
        safe: dict[str, Any] = {}
        for key in ("path", "content"):
            if key not in arguments:
                continue
            value = arguments[key]
            if key == "content":
                try:
                    safe["content_bytes"] = len(value.encode("utf-8")) if isinstance(value, str) else "[invalid]"
                except UnicodeError:
                    safe["content_bytes"] = "[invalid]"
            else:
                try:
                    safe[key] = self._relative_path(value).as_posix()
                except ToolFailure:
                    safe[key] = "[rejected path]"
        return safe

    def _record(self, sequence: int, name: Any, arguments: Any, result: dict[str, Any], elapsed_ms: float) -> None:
        record = {
            "sequence": sequence,
            "name": name if isinstance(name, str) and name in {tool["name"] for tool in self._tools()} else "[unknown]",
            "arguments": self._safe_audit_args(arguments),
            "result": result,
            "status": "error" if result.get("isError") else "ok",
            "elapsed_ms": round(elapsed_ms, 3),
        }
        with self.audit.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n")

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        if request_id is None:
            return None
        if method == "initialize":
            params = message.get("params") or {}
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            version = requested if requested in {"2024-11-05", "2025-03-26", "2025-06-18"} else PROTOCOL_VERSION
            payload = {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "skillarena-workspace", "version": "0.1.0"},
            }
            return {"jsonrpc": "2.0", "id": request_id, "result": payload}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self._tools()}}
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name") if isinstance(params, dict) else None
            arguments = params.get("arguments", {}) if isinstance(params, dict) else None
            self.tool_calls += 1
            started = time.perf_counter()
            try:
                if self.tool_calls > self.max_tool_calls:
                    raise ToolFailure("tool call limit exceeded")
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise ToolFailure("invalid tool call")
                value = self._call(name, arguments)
                payload = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=True)}], "isError": False}
                audit_result: dict[str, Any] = {"isError": False, "type": name}
                if name == "check_output":
                    audit_result["valid_json"] = value.get("valid_json")
            except ToolFailure as exc:
                payload = {"content": [{"type": "text", "text": json.dumps({"error": str(exc)})}], "isError": True}
                audit_result = {"isError": True, "error": str(exc)}
            except OSError:
                payload = {"content": [{"type": "text", "text": json.dumps({"error": "file operation failed"})}], "isError": True}
                audit_result = {"isError": True, "error": "file operation failed"}
            self._record(self.tool_calls, name, arguments, audit_result, (time.perf_counter() - started) * 1000)
            return {"jsonrpc": "2.0", "id": request_id, "result": payload}
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--skill-root", type=Path)
    parser.add_argument("--max-tool-calls", type=int, default=80)
    args = parser.parse_args(argv)
    try:
        server = WorkspaceServer(args.root, args.audit, args.skill_root, args.max_tool_calls)
    except ValueError as exc:
        parser.error(str(exc))
    while True:
        raw = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if not raw:
            break
        if len(raw) > MAX_MESSAGE_BYTES:
            while raw and not raw.endswith(b"\n"):
                raw = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
            continue
        try:
            message = json.loads(raw)
            if not isinstance(message, dict):
                continue
            response = server.handle(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except (json.JSONDecodeError, UnicodeError):
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
