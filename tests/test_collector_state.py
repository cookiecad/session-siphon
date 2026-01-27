"""Tests for collector state tracking."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from session_siphon.collector.state import CollectorState, FileState


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "state" / "collector.db"


@pytest.fixture
def state(temp_db_path: Path) -> CollectorState:
    """Provide a CollectorState instance with temporary database."""
    return CollectorState(temp_db_path)


class TestFileState:
    """Tests for FileState dataclass."""

    def test_default_values(self) -> None:
        """FileState should have sensible defaults."""
        fs = FileState(source="claude", path="/path/to/file.jsonl")
        assert fs.source == "claude"
        assert fs.path == "/path/to/file.jsonl"
        assert fs.mtime is None
        assert fs.size is None
        assert fs.sha256 is None
        assert fs.last_offset == 0
        assert fs.last_synced is None

    def test_all_fields(self) -> None:
        """FileState should accept all field values."""
        fs = FileState(
            source="chatgpt",
            path="/data/conversations.json",
            mtime=1706000000,
            size=12345,
            sha256="abc123",
            last_offset=500,
            last_synced=1706000100,
        )
        assert fs.source == "chatgpt"
        assert fs.path == "/data/conversations.json"
        assert fs.mtime == 1706000000
        assert fs.size == 12345
        assert fs.sha256 == "abc123"
        assert fs.last_offset == 500
        assert fs.last_synced == 1706000100


class TestCollectorStateInit:
    """Tests for CollectorState initialization."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """CollectorState should create parent directories for database."""
        db_path = tmp_path / "nested" / "dirs" / "state.db"
        state = CollectorState(db_path)
        try:
            assert db_path.parent.exists()
            assert db_path.exists()
        finally:
            state.close()

    def test_creates_files_table(self, temp_db_path: Path) -> None:
        """CollectorState should create files table on init."""
        state = CollectorState(temp_db_path)
        try:
            # Verify table exists by querying it directly
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            state.close()

    def test_schema_has_correct_columns(self, temp_db_path: Path) -> None:
        """Files table should have correct schema."""
        state = CollectorState(temp_db_path)
        try:
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.execute("PRAGMA table_info(files)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            conn.close()

            assert columns["source"] == "TEXT"
            assert columns["path"] == "TEXT"
            assert columns["mtime"] == "INTEGER"
            assert columns["size"] == "INTEGER"
            assert columns["sha256"] == "TEXT"
            assert columns["last_offset"] == "INTEGER"
            assert columns["last_synced"] == "INTEGER"
        finally:
            state.close()

    def test_idempotent_schema_creation(self, temp_db_path: Path) -> None:
        """ensure_schema should be idempotent."""
        state1 = CollectorState(temp_db_path)
        state1.close()

        # Opening again should not raise
        state2 = CollectorState(temp_db_path)
        state2.ensure_schema()  # Explicit call should also be safe
        state2.close()


class TestCollectorStateGetFile:
    """Tests for get_file_state method."""

    def test_returns_none_for_missing_file(self, state: CollectorState) -> None:
        """get_file_state should return None for non-existent file."""
        result = state.get_file_state("claude", "/nonexistent.jsonl")
        assert result is None
        state.close()

    def test_returns_file_state(self, state: CollectorState) -> None:
        """get_file_state should return FileState for existing file."""
        state.update_file_state(
            "claude",
            "/test.jsonl",
            mtime=1706000000,
            size=1000,
            sha256="hash123",
        )

        result = state.get_file_state("claude", "/test.jsonl")
        assert result is not None
        assert result.source == "claude"
        assert result.path == "/test.jsonl"
        assert result.mtime == 1706000000
        assert result.size == 1000
        assert result.sha256 == "hash123"
        state.close()

    def test_distinguishes_by_source(self, state: CollectorState) -> None:
        """get_file_state should distinguish files by source."""
        state.update_file_state("claude", "/test.jsonl", mtime=100)
        state.update_file_state("chatgpt", "/test.jsonl", mtime=200)

        result1 = state.get_file_state("claude", "/test.jsonl")
        result2 = state.get_file_state("chatgpt", "/test.jsonl")

        assert result1 is not None
        assert result2 is not None
        assert result1.mtime == 100
        assert result2.mtime == 200
        state.close()


class TestCollectorStateUpdateFile:
    """Tests for update_file_state method."""

    def test_inserts_new_file(self, state: CollectorState) -> None:
        """update_file_state should insert new file state."""
        state.update_file_state(
            "claude",
            "/new.jsonl",
            mtime=1706000000,
            size=500,
        )

        result = state.get_file_state("claude", "/new.jsonl")
        assert result is not None
        assert result.mtime == 1706000000
        assert result.size == 500
        assert result.last_offset == 0  # Default
        state.close()

    def test_updates_existing_file(self, state: CollectorState) -> None:
        """update_file_state should update existing file state."""
        state.update_file_state("claude", "/file.jsonl", mtime=100, size=500)
        state.update_file_state("claude", "/file.jsonl", mtime=200, last_offset=250)

        result = state.get_file_state("claude", "/file.jsonl")
        assert result is not None
        assert result.mtime == 200
        assert result.size == 500  # Unchanged
        assert result.last_offset == 250
        state.close()

    def test_update_with_no_attrs_is_noop(self, state: CollectorState) -> None:
        """update_file_state with no attrs should be a no-op for existing."""
        state.update_file_state("claude", "/file.jsonl", mtime=100)
        state.update_file_state("claude", "/file.jsonl")  # No attrs

        result = state.get_file_state("claude", "/file.jsonl")
        assert result is not None
        assert result.mtime == 100
        state.close()

    def test_rejects_invalid_attrs(self, state: CollectorState) -> None:
        """update_file_state should reject invalid attributes."""
        with pytest.raises(ValueError, match="Invalid attributes"):
            state.update_file_state("claude", "/file.jsonl", invalid_attr=123)
        state.close()

    def test_all_attrs(self, state: CollectorState) -> None:
        """update_file_state should accept all valid attributes."""
        state.update_file_state(
            "claude",
            "/file.jsonl",
            mtime=1706000000,
            size=1234,
            sha256="abc123def456",
            last_offset=500,
            last_synced=1706001000,
        )

        result = state.get_file_state("claude", "/file.jsonl")
        assert result is not None
        assert result.mtime == 1706000000
        assert result.size == 1234
        assert result.sha256 == "abc123def456"
        assert result.last_offset == 500
        assert result.last_synced == 1706001000
        state.close()


class TestCollectorStateListFiles:
    """Tests for list_files method."""

    def test_empty_database(self, state: CollectorState) -> None:
        """list_files should return empty list for empty database."""
        result = state.list_files()
        assert result == []
        state.close()

    def test_lists_all_files(self, state: CollectorState) -> None:
        """list_files should return all files when no source specified."""
        state.update_file_state("claude", "/file1.jsonl", mtime=100)
        state.update_file_state("chatgpt", "/file2.json", mtime=200)
        state.update_file_state("claude", "/file3.jsonl", mtime=300)

        result = state.list_files()
        assert len(result) == 3

        # Should be ordered by source, then path
        sources = [f.source for f in result]
        assert sources == ["chatgpt", "claude", "claude"]
        state.close()

    def test_filters_by_source(self, state: CollectorState) -> None:
        """list_files should filter by source when specified."""
        state.update_file_state("claude", "/file1.jsonl", mtime=100)
        state.update_file_state("chatgpt", "/file2.json", mtime=200)
        state.update_file_state("claude", "/file3.jsonl", mtime=300)

        result = state.list_files(source="claude")
        assert len(result) == 2
        assert all(f.source == "claude" for f in result)
        state.close()

    def test_filters_nonexistent_source(self, state: CollectorState) -> None:
        """list_files should return empty list for non-existent source."""
        state.update_file_state("claude", "/file.jsonl", mtime=100)

        result = state.list_files(source="nonexistent")
        assert result == []
        state.close()


class TestCollectorStateContextManager:
    """Tests for context manager support."""

    def test_context_manager(self, temp_db_path: Path) -> None:
        """CollectorState should work as context manager."""
        with CollectorState(temp_db_path) as state:
            state.update_file_state("claude", "/test.jsonl", mtime=100)
            result = state.get_file_state("claude", "/test.jsonl")
            assert result is not None

    def test_closes_on_exit(self, temp_db_path: Path) -> None:
        """CollectorState should close connection on context exit."""
        with CollectorState(temp_db_path) as state:
            conn = state._conn

        # After context exit, connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_closes_on_exception(self, temp_db_path: Path) -> None:
        """CollectorState should close connection even on exception."""
        conn = None
        try:
            with CollectorState(temp_db_path) as state:
                conn = state._conn
                raise RuntimeError("Test exception")
        except RuntimeError:
            pass

        # Connection should still be closed
        assert conn is not None
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


class TestCollectorStatePersistence:
    """Tests for state persistence across instances."""

    def test_state_persists_across_instances(self, temp_db_path: Path) -> None:
        """State should persist when opening new CollectorState instance."""
        # First instance: write data
        with CollectorState(temp_db_path) as state1:
            state1.update_file_state(
                "claude",
                "/persistent.jsonl",
                mtime=1706000000,
                size=9999,
                sha256="persistent_hash",
                last_offset=500,
                last_synced=1706001000,
            )

        # Second instance: verify data persisted
        with CollectorState(temp_db_path) as state2:
            result = state2.get_file_state("claude", "/persistent.jsonl")
            assert result is not None
            assert result.mtime == 1706000000
            assert result.size == 9999
            assert result.sha256 == "persistent_hash"
            assert result.last_offset == 500
            assert result.last_synced == 1706001000

    def test_updates_persist(self, temp_db_path: Path) -> None:
        """Updates should persist across instances."""
        # Create initial state
        with CollectorState(temp_db_path) as state1:
            state1.update_file_state("claude", "/file.jsonl", mtime=100, last_offset=0)

        # Update in new instance
        with CollectorState(temp_db_path) as state2:
            state2.update_file_state("claude", "/file.jsonl", last_offset=500)

        # Verify in third instance
        with CollectorState(temp_db_path) as state3:
            result = state3.get_file_state("claude", "/file.jsonl")
            assert result is not None
            assert result.mtime == 100
            assert result.last_offset == 500
