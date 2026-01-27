"""Tests for collector file copier module."""

import hashlib
from pathlib import Path

import pytest

from session_siphon.collector.copier import (
    compute_sha256,
    copy_json_snapshot,
    copy_jsonl_incremental,
    map_source_to_outbox,
    needs_sync,
)
from session_siphon.collector.state import FileState


class TestComputeSha256:
    """Tests for compute_sha256 function."""

    def test_computes_hash_of_small_file(self, tmp_path: Path) -> None:
        """Should compute correct SHA-256 hash for small file."""
        test_file = tmp_path / "test.txt"
        content = b"hello world"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = compute_sha256(test_file)

        assert result == expected

    def test_computes_hash_of_empty_file(self, tmp_path: Path) -> None:
        """Should compute correct hash for empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest()
        result = compute_sha256(test_file)

        assert result == expected

    def test_computes_hash_of_large_file(self, tmp_path: Path) -> None:
        """Should compute correct hash for file larger than chunk size."""
        test_file = tmp_path / "large.bin"
        # Create file larger than 64KB chunk size
        content = b"x" * (100 * 1024)
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = compute_sha256(test_file)

        assert result == expected

    def test_returns_hex_string(self, tmp_path: Path) -> None:
        """Should return lowercase hex string."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test")

        result = compute_sha256(test_file)

        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestMapSourceToOutbox:
    """Tests for map_source_to_outbox function."""

    def test_maps_home_relative_path(self, tmp_path: Path) -> None:
        """Should create correct path structure for files under home."""
        source_path = Path.home() / ".claude" / "projects" / "test" / "conv.jsonl"
        outbox_path = tmp_path / "outbox"

        result = map_source_to_outbox(
            source="claude_code",
            source_path=source_path,
            machine_id="laptop-01",
            outbox_path=outbox_path,
        )

        expected = outbox_path / "laptop-01" / "claude_code" / ".claude" / "projects" / "test" / "conv.jsonl"
        assert result == expected

    def test_maps_absolute_path_not_under_home(self, tmp_path: Path) -> None:
        """Should handle paths not under home directory."""
        source_path = Path("/data/app/conversations.json")
        outbox_path = tmp_path / "outbox"

        result = map_source_to_outbox(
            source="custom",
            source_path=source_path,
            machine_id="server-01",
            outbox_path=outbox_path,
        )

        expected = outbox_path / "server-01" / "custom" / "data" / "app" / "conversations.json"
        assert result == expected

    def test_includes_machine_id_in_path(self, tmp_path: Path) -> None:
        """Should include machine_id in the path structure."""
        source_path = Path.home() / "test.jsonl"
        outbox_path = tmp_path / "outbox"

        result = map_source_to_outbox(
            source="test_source",
            source_path=source_path,
            machine_id="my-machine",
            outbox_path=outbox_path,
        )

        assert "my-machine" in result.parts

    def test_includes_source_in_path(self, tmp_path: Path) -> None:
        """Should include source identifier in the path structure."""
        source_path = Path.home() / "test.jsonl"
        outbox_path = tmp_path / "outbox"

        result = map_source_to_outbox(
            source="vscode_copilot",
            source_path=source_path,
            machine_id="machine",
            outbox_path=outbox_path,
        )

        assert "vscode_copilot" in result.parts


class TestCopyJsonlIncremental:
    """Tests for copy_jsonl_incremental function."""

    def test_copies_entire_file_from_zero_offset(self, tmp_path: Path) -> None:
        """Should copy entire file when starting from offset 0."""
        source = tmp_path / "source.jsonl"
        dest = tmp_path / "dest" / "output.jsonl"
        content = b'{"line": 1}\n{"line": 2}\n'
        source.write_bytes(content)

        new_offset = copy_jsonl_incremental(source, dest, from_offset=0)

        assert dest.exists()
        assert dest.read_bytes() == content
        assert new_offset == len(content)

    def test_appends_new_bytes_only(self, tmp_path: Path) -> None:
        """Should append only new bytes when starting from non-zero offset."""
        source = tmp_path / "source.jsonl"
        dest = tmp_path / "dest.jsonl"

        # Initial content
        initial = b'{"line": 1}\n'
        source.write_bytes(initial)
        dest.write_bytes(initial)

        # Source gets more content
        appended = b'{"line": 2}\n'
        source.write_bytes(initial + appended)

        # Copy incrementally
        new_offset = copy_jsonl_incremental(source, dest, from_offset=len(initial))

        assert dest.read_bytes() == initial + appended
        assert new_offset == len(initial) + len(appended)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories for destination."""
        source = tmp_path / "source.jsonl"
        dest = tmp_path / "nested" / "dirs" / "dest.jsonl"
        source.write_bytes(b'{"test": true}\n')

        copy_jsonl_incremental(source, dest, from_offset=0)

        assert dest.exists()
        assert dest.parent.exists()

    def test_returns_current_offset_when_no_new_data(self, tmp_path: Path) -> None:
        """Should return same offset when file hasn't grown."""
        source = tmp_path / "source.jsonl"
        content = b'{"line": 1}\n'
        source.write_bytes(content)

        new_offset = copy_jsonl_incremental(source, tmp_path / "dest.jsonl", from_offset=len(content))

        assert new_offset == len(content)

    def test_handles_large_offset(self, tmp_path: Path) -> None:
        """Should handle offset larger than file size gracefully."""
        source = tmp_path / "source.jsonl"
        source.write_bytes(b"small")

        new_offset = copy_jsonl_incremental(source, tmp_path / "dest.jsonl", from_offset=1000)

        assert new_offset == 1000

    def test_multiple_incremental_copies(self, tmp_path: Path) -> None:
        """Should handle multiple incremental copies correctly."""
        source = tmp_path / "source.jsonl"
        dest = tmp_path / "dest.jsonl"

        # First write
        line1 = b'{"n": 1}\n'
        source.write_bytes(line1)
        offset = copy_jsonl_incremental(source, dest, from_offset=0)
        assert offset == len(line1)

        # Second write
        line2 = b'{"n": 2}\n'
        source.write_bytes(line1 + line2)
        offset = copy_jsonl_incremental(source, dest, from_offset=offset)
        assert offset == len(line1) + len(line2)

        # Third write
        line3 = b'{"n": 3}\n'
        source.write_bytes(line1 + line2 + line3)
        offset = copy_jsonl_incremental(source, dest, from_offset=offset)

        # Verify final state
        assert dest.read_bytes() == line1 + line2 + line3
        assert offset == len(line1) + len(line2) + len(line3)


class TestCopyJsonSnapshot:
    """Tests for copy_json_snapshot function."""

    def test_copies_entire_file(self, tmp_path: Path) -> None:
        """Should copy entire file to destination."""
        source = tmp_path / "source.json"
        dest = tmp_path / "dest.json"
        content = b'{"key": "value"}'
        source.write_bytes(content)

        copy_json_snapshot(source, dest)

        assert dest.exists()
        assert dest.read_bytes() == content

    def test_overwrites_existing_destination(self, tmp_path: Path) -> None:
        """Should overwrite existing destination file."""
        source = tmp_path / "source.json"
        dest = tmp_path / "dest.json"

        # Initial destination
        dest.write_bytes(b'{"old": "content"}')

        # New source
        new_content = b'{"new": "content"}'
        source.write_bytes(new_content)

        copy_json_snapshot(source, dest)

        assert dest.read_bytes() == new_content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories for destination."""
        source = tmp_path / "source.json"
        dest = tmp_path / "deep" / "nested" / "path" / "dest.json"
        source.write_bytes(b'{}')

        copy_json_snapshot(source, dest)

        assert dest.exists()
        assert dest.parent.exists()

    def test_preserves_metadata(self, tmp_path: Path) -> None:
        """Should preserve file metadata (using shutil.copy2)."""
        source = tmp_path / "source.json"
        dest = tmp_path / "dest.json"
        source.write_bytes(b'{"test": true}')

        copy_json_snapshot(source, dest)

        # Verify mtime is preserved (within small tolerance)
        assert abs(source.stat().st_mtime - dest.stat().st_mtime) < 1


class TestNeedsSync:
    """Tests for needs_sync function."""

    def test_new_file_needs_sync(self, tmp_path: Path) -> None:
        """Should indicate sync needed for new file (no state)."""
        source = tmp_path / "new.jsonl"
        source.write_bytes(b'{"test": true}\n')

        needs, reason, hash_val = needs_sync(source, state=None)

        assert needs is True
        assert reason == "new_file"
        assert hash_val == compute_sha256(source)

    def test_nonexistent_file_does_not_need_sync(self, tmp_path: Path) -> None:
        """Should indicate no sync for missing file."""
        source = tmp_path / "missing.jsonl"

        needs, reason, hash_val = needs_sync(source, state=None)

        assert needs is False
        assert reason == "file_not_found"
        assert hash_val == ""

    def test_jsonl_with_new_bytes_needs_sync(self, tmp_path: Path) -> None:
        """Should indicate sync needed for JSONL with new bytes."""
        source = tmp_path / "growing.jsonl"
        source.write_bytes(b'{"line": 1}\n{"line": 2}\n')

        state = FileState(
            source="test",
            path=str(source),
            last_offset=12,  # Only first line was synced
            sha256="old_hash",
        )

        needs, reason, hash_val = needs_sync(source, state=state)

        assert needs is True
        assert reason == "new_bytes"

    def test_jsonl_up_to_date(self, tmp_path: Path) -> None:
        """Should indicate no sync for fully synced JSONL."""
        source = tmp_path / "current.jsonl"
        content = b'{"line": 1}\n'
        source.write_bytes(content)
        current_hash = compute_sha256(source)

        state = FileState(
            source="test",
            path=str(source),
            last_offset=len(content),
            sha256=current_hash,
        )

        needs, reason, hash_val = needs_sync(source, state=state)

        assert needs is False
        assert reason == "up_to_date"

    def test_jsonl_file_reset_needs_sync(self, tmp_path: Path) -> None:
        """Should indicate sync needed when JSONL file was truncated."""
        source = tmp_path / "reset.jsonl"
        source.write_bytes(b'{"new": 1}\n')  # Smaller than before

        state = FileState(
            source="test",
            path=str(source),
            last_offset=100,  # Previous offset was larger
            sha256="old_hash",
        )

        needs, reason, hash_val = needs_sync(source, state=state)

        assert needs is True
        assert reason == "file_reset"

    def test_jsonl_content_changed_needs_sync(self, tmp_path: Path) -> None:
        """Should indicate sync when JSONL content changed (same size, different hash)."""
        source = tmp_path / "modified.jsonl"
        content = b'{"new": "data"}\n'
        source.write_bytes(content)

        state = FileState(
            source="test",
            path=str(source),
            last_offset=len(content),  # Same size
            sha256="different_hash",  # But different hash
        )

        needs, reason, hash_val = needs_sync(source, state=state)

        assert needs is True
        assert reason == "content_changed"

    def test_json_hash_changed_needs_sync(self, tmp_path: Path) -> None:
        """Should indicate sync needed when JSON hash changed."""
        source = tmp_path / "changed.json"
        source.write_bytes(b'{"new": "content"}')

        state = FileState(
            source="test",
            path=str(source),
            sha256="old_hash_value",
        )

        needs, reason, hash_val = needs_sync(source, state=state)

        assert needs is True
        assert reason == "hash_changed"

    def test_json_up_to_date(self, tmp_path: Path) -> None:
        """Should indicate no sync when JSON hash unchanged."""
        source = tmp_path / "same.json"
        content = b'{"unchanged": true}'
        source.write_bytes(content)
        current_hash = compute_sha256(source)

        state = FileState(
            source="test",
            path=str(source),
            sha256=current_hash,
        )

        needs, reason, hash_val = needs_sync(source, state=state)

        assert needs is False
        assert reason == "up_to_date"
        assert hash_val == current_hash

    def test_returns_current_hash(self, tmp_path: Path) -> None:
        """Should always return current hash when file exists."""
        source = tmp_path / "test.json"
        content = b'{"test": true}'
        source.write_bytes(content)
        expected_hash = compute_sha256(source)

        _, _, hash_val = needs_sync(source, state=None)

        assert hash_val == expected_hash
