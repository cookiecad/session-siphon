"""Tests for processor archiver module."""

from datetime import datetime
from pathlib import Path

import pytest

from session_siphon.processor.archiver import archive_file


class TestArchiveFile:
    """Tests for archive_file function."""

    def test_archives_file_with_date_structure(self, tmp_path: Path) -> None:
        """Should create date-based directory structure in archive."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        # Create file in inbox
        source_file = inbox / "machine-01" / "claude_code" / "conv.jsonl"
        source_file.parent.mkdir(parents=True)
        source_file.write_text('{"test": true}\n')

        # Archive with specific date
        archive_date = datetime(2025, 3, 15)
        result = archive_file(source_file, inbox, archive, archive_date)

        expected = archive / "2025-03-15" / "machine-01" / "claude_code" / "conv.jsonl"
        assert result == expected
        assert result.exists()
        assert result.read_text() == '{"test": true}\n'

    def test_removes_source_file_after_archiving(self, tmp_path: Path) -> None:
        """Should remove source file from inbox after archiving."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        source_file = inbox / "test.jsonl"
        source_file.write_text('{"data": 1}\n')

        archive_file(source_file, inbox, archive)

        assert not source_file.exists()

    def test_preserves_machine_id_in_path(self, tmp_path: Path) -> None:
        """Should preserve machine_id in the archive path structure."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        source_file = inbox / "laptop-01" / "test.jsonl"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("{}\n")

        result = archive_file(source_file, inbox, archive)

        assert "laptop-01" in result.parts

    def test_preserves_source_type_in_path(self, tmp_path: Path) -> None:
        """Should preserve source type (e.g., claude_code) in archive path."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        source_file = inbox / "machine" / "vscode_copilot" / "session.json"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("{}")

        result = archive_file(source_file, inbox, archive)

        assert "vscode_copilot" in result.parts

    def test_creates_nested_archive_directories(self, tmp_path: Path) -> None:
        """Should create all necessary parent directories in archive."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        # Deep nested structure
        source_file = inbox / "machine" / "claude_code" / "projects" / "test" / "conv.jsonl"
        source_file.parent.mkdir(parents=True)
        source_file.write_text('{"nested": true}\n')

        result = archive_file(source_file, inbox, archive)

        assert result.exists()
        assert "projects" in result.parts
        assert "test" in result.parts

    def test_uses_current_date_when_not_specified(self, tmp_path: Path) -> None:
        """Should use current date when archive_date not provided."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        source_file = inbox / "test.jsonl"
        source_file.write_text("{}\n")

        result = archive_file(source_file, inbox, archive)

        today = datetime.now().strftime("%Y-%m-%d")
        assert today in str(result)

    def test_raises_error_for_missing_source(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError if source file doesn't exist."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        source_file = inbox / "nonexistent.jsonl"

        with pytest.raises(FileNotFoundError) as exc_info:
            archive_file(source_file, inbox, archive)

        assert "Source file does not exist" in str(exc_info.value)

    def test_raises_error_for_path_outside_inbox(self, tmp_path: Path) -> None:
        """Should raise ValueError if source is not under inbox path."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        other_dir = tmp_path / "other"
        inbox.mkdir()
        other_dir.mkdir()

        source_file = other_dir / "external.jsonl"
        source_file.write_text("{}\n")

        with pytest.raises(ValueError) as exc_info:
            archive_file(source_file, inbox, archive)

        assert "not under inbox" in str(exc_info.value)

    def test_archives_file_at_inbox_root(self, tmp_path: Path) -> None:
        """Should handle file directly in inbox root."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        source_file = inbox / "direct.jsonl"
        source_file.write_text('{"root": true}\n')

        archive_date = datetime(2025, 6, 20)
        result = archive_file(source_file, inbox, archive, archive_date)

        expected = archive / "2025-06-20" / "direct.jsonl"
        assert result == expected
        assert result.exists()

    def test_preserves_file_content(self, tmp_path: Path) -> None:
        """Should preserve file content exactly when archiving."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        inbox.mkdir()

        content = '{"line": 1}\n{"line": 2}\n{"line": 3}\n'
        source_file = inbox / "multi.jsonl"
        source_file.write_text(content)

        result = archive_file(source_file, inbox, archive)

        assert result.read_text() == content
