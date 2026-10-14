import hashlib
import json
from pathlib import Path

import pytest

from skillarena.evidence import hash_tree, seal_bundle, sha256_file, verify_bundle


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    (root / "nested").mkdir(parents=True)
    (root / "z.txt").write_text("last", encoding="utf-8")
    (root / "nested" / "a.txt").write_text("first", encoding="utf-8")
    return root


def _rewrite_manifest(root: Path, edit) -> None:
    path = root / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_seal_is_deterministic_and_verifies_offline(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    first = seal_bundle(root)
    bytes_before = (root / "manifest.json").read_bytes()
    assert [item["path"] for item in first["files"]] == ["nested/a.txt", "z.txt"]
    assert first["schema_version"] == 2
    assert first["algorithm"] == "sha256"
    assert first["evidence_level"] == "author-submitted"
    assert "does not prove authenticity or independent replication" in first["integrity_notice"]
    assert seal_bundle(root) == first
    assert (root / "manifest.json").read_bytes() == bytes_before
    assert hash_tree(root)["nested/a.txt"] == {
        "sha256": hashlib.sha256(b"first").hexdigest(), "size": 5
    }
    assert sha256_file(root / "z.txt") == hashlib.sha256(b"last").hexdigest()
    assert verify_bundle(root) == {
        "valid": True,
        "errors": [],
        "files_checked": 2,
        "manifest_sha256": hashlib.sha256(bytes_before).hexdigest(),
    }


def test_seal_rejects_missing_or_empty_bundle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Cannot access"):
        seal_bundle(tmp_path / "missing")
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ValueError, match="at least one"):
        seal_bundle(root)
    assert not verify_bundle(root)["valid"]


def test_tampered_missing_and_unexpected_files(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    seal_bundle(root)
    (root / "z.txt").write_text("changed", encoding="utf-8")
    tampered = verify_bundle(root)
    assert not tampered["valid"]
    assert any("SHA-256 mismatch: z.txt" in error for error in tampered["errors"])
    (root / "nested" / "a.txt").unlink()
    (root / "extra.txt").write_text("extra", encoding="utf-8")
    changed = verify_bundle(root)
    assert any("Missing file: nested/a.txt" in error for error in changed["errors"])
    assert any("Unexpected file: extra.txt" in error for error in changed["errors"])


@pytest.mark.parametrize("unsafe", ["../outside", "/absolute", "C:/absolute", "a\\b", "a/./b", "a//b", "manifest.json"])
def test_manifest_rejects_unsafe_paths(tmp_path: Path, unsafe: str) -> None:
    root = _bundle(tmp_path)
    seal_bundle(root)
    _rewrite_manifest(root, lambda data: data["files"][0].update(path=unsafe))
    outcome = verify_bundle(root)
    assert not outcome["valid"]
    assert any("Unsafe manifest path" in error for error in outcome["errors"])


def test_manifest_rejects_duplicate_entries_and_invalid_schema(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    seal_bundle(root)
    _rewrite_manifest(root, lambda data: data["files"].append(data["files"][0].copy()))
    assert any("Duplicate manifest path" in error for error in verify_bundle(root)["errors"])
    seal_bundle(root)
    _rewrite_manifest(root, lambda data: data.update(schema_version=True))
    assert any("schema_version" in error for error in verify_bundle(root)["errors"])
    seal_bundle(root)
    _rewrite_manifest(root, lambda data: data["files"][0].update(size=False))
    assert any("Invalid size" in error for error in verify_bundle(root)["errors"])
    seal_bundle(root)
    (root / "manifest.json").write_text('{"files": [], "files": []}', encoding="utf-8")
    assert any("Duplicate JSON key" in error for error in verify_bundle(root)["errors"])


def test_symlinks_are_rejected_when_supported(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    link = root / "link"
    try:
        link.symlink_to(root / "z.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links unavailable")
    with pytest.raises(ValueError, match="Symbolic link"):
        seal_bundle(root)
    link.unlink()
    seal_bundle(root)
    link.symlink_to(root / "z.txt")
    assert any("Symbolic link" in error for error in verify_bundle(root)["errors"])
