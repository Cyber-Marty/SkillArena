"""Portable, offline integrity checks for author-submitted evidence bundles.

Matching hashes show that a bundle has not changed since its manifest was made.
They do not prove authenticity, correct evaluation, or independent replication.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import tempfile


SCHEMA_VERSION = 2
ALGORITHM = "sha256"
EVIDENCE_LEVEL = "author-submitted"
INTEGRITY_NOTICE = (
    "Integrity does not prove authenticity or independent replication."
)
_MANIFEST = "manifest.json"
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_HEX = frozenset("0123456789abcdef")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a regular file, read in bounded chunks."""
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
            raise ValueError(f"Not a regular file: {path}")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _checked_root(root: Path) -> Path:
    root = Path(root).expanduser().absolute()
    try:
        info = root.lstat()
    except OSError as exc:
        raise ValueError(f"Cannot access evidence bundle: {root}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
        raise ValueError(f"Evidence bundle root must be a real directory: {root}")
    return root


def _valid_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return False
    if PureWindowsPath(value).drive or ":" in value:
        return False
    parts = value.split("/")
    if value.casefold() == _MANIFEST:
        return False
    for part in parts:
        if part in ("", ".", "..") or part.endswith((" ", ".")):
            return False
        if any(char in part for char in '<>"|?*'):
            return False
        if part.split(".", 1)[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            return False
    return True


def _scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    portable_names: set[str] = set()
    stack = [(root, "")]
    while stack:
        directory, prefix = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise ValueError(f"Cannot scan evidence bundle: {directory}: {exc}") from exc
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            if not _valid_relative_path(relative) and relative != _MANIFEST:
                raise ValueError(f"Unsafe file name in evidence bundle: {relative}")
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"Cannot inspect evidence file: {relative}: {exc}") from exc
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise ValueError(f"Symbolic link or reparse point in evidence bundle: {relative}")
            if stat.S_ISDIR(info.st_mode):
                stack.append((Path(entry.path), relative))
            elif stat.S_ISREG(info.st_mode):
                if relative != _MANIFEST:
                    if relative.casefold() in portable_names:
                        raise ValueError(f"Ambiguous file names in evidence bundle: {relative}")
                    portable_names.add(relative.casefold())
                    found[relative] = Path(entry.path)
            else:
                raise ValueError(f"Non-regular file in evidence bundle: {relative}")
    return found


def hash_tree(root: Path) -> dict[str, dict[str, str | int]]:
    """Hash all payload files, excluding the root manifest, in path order."""
    files = _scan(_checked_root(root))
    return {
        name: {"sha256": sha256_file(path), "size": path.stat().st_size}
        for name, path in sorted(files.items())
    }


def seal_bundle(root: Path) -> dict:
    """Atomically write a v2 manifest for a nonempty evidence directory."""
    root = _checked_root(root)
    files = _scan(root)
    if not files:
        raise ValueError("Evidence bundle must contain at least one payload file")
    manifest_path = root / _MANIFEST
    if manifest_path.exists() or manifest_path.is_symlink():
        info = manifest_path.lstat()
        if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
            raise ValueError("manifest.json must be a regular file")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "evidence_level": EVIDENCE_LEVEL,
        "integrity_notice": INTEGRITY_NOTICE,
        "files": [
            {"path": name, "sha256": sha256_file(path), "size": path.stat().st_size}
            for name, path in sorted(files.items())
        ],
    }
    payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=root, prefix=".manifest-", delete=False) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, manifest_path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return manifest


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_manifest(manifest: object) -> tuple[dict[str, tuple[str, int]], list[str]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {}, ["Manifest must be a JSON object"]
    expected_keys = {"schema_version", "algorithm", "evidence_level", "integrity_notice", "files"}
    if set(manifest) != expected_keys:
        errors.append("Manifest fields do not match schema v2")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != SCHEMA_VERSION:
        errors.append("Unsupported manifest schema_version")
    if manifest.get("algorithm") != ALGORITHM:
        errors.append("Unsupported manifest algorithm")
    if manifest.get("evidence_level") != EVIDENCE_LEVEL:
        errors.append("Invalid evidence_level")
    if manifest.get("integrity_notice") != INTEGRITY_NOTICE:
        errors.append("Invalid integrity_notice")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        return {}, errors + ["Manifest files must be a nonempty array"]
    checked: dict[str, tuple[str, int]] = {}
    portable_names: set[str] = set()
    ordered_names: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            errors.append(f"Invalid file entry at index {index}")
            continue
        name, digest, size = entry["path"], entry["sha256"], entry["size"]
        if not _valid_relative_path(name):
            errors.append(f"Unsafe manifest path at index {index}: {name!r}")
            continue
        if name.casefold() in portable_names:
            errors.append(f"Duplicate manifest path: {name}")
            continue
        portable_names.add(name.casefold())
        ordered_names.append(name)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in _HEX for c in digest):
            errors.append(f"Invalid SHA-256 digest for {name}")
            continue
        if type(size) is not int or size < 0:
            errors.append(f"Invalid size for {name}")
            continue
        checked[name] = (digest, size)
    if ordered_names != sorted(ordered_names):
        errors.append("Manifest file entries must be sorted by path")
    return checked, errors


def verify_bundle(root: Path) -> dict:
    """Verify a bundle without executing any payload or trusting its origin."""
    result: dict = {"valid": False, "errors": [], "files_checked": 0, "manifest_sha256": None}
    errors: list[str] = result["errors"]
    try:
        root = _checked_root(root)
        files = _scan(root)
    except ValueError as exc:
        errors.append(str(exc))
        return result
    manifest_path = root / _MANIFEST
    try:
        info = manifest_path.lstat()
        if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
            raise ValueError("manifest.json must be a regular file")
        raw = manifest_path.read_bytes()
    except (OSError, ValueError) as exc:
        errors.append(f"Cannot read manifest.json: {exc}")
        return result
    result["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"Invalid manifest JSON: {exc}")
        return result
    expected, schema_errors = _validate_manifest(manifest)
    errors.extend(schema_errors)
    for name in sorted(expected.keys() - files.keys()):
        errors.append(f"Missing file: {name}")
    for name in sorted(files.keys() - expected.keys()):
        errors.append(f"Unexpected file: {name}")
    for name in sorted(expected.keys() & files.keys()):
        path = files[name]
        try:
            actual_hash = sha256_file(path)
            actual_size = path.stat().st_size
        except (OSError, ValueError) as exc:
            errors.append(f"Cannot read file {name}: {exc}")
            continue
        result["files_checked"] += 1
        digest, size = expected[name]
        if actual_hash != digest:
            errors.append(f"SHA-256 mismatch: {name}")
        if actual_size != size:
            errors.append(f"Size mismatch: {name}")
    result["valid"] = not errors
    return result
