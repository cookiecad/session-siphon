"""Tests for processor state tracking."""

import sqlite3
from pathlib import Path

import pytest

from session_siphon.processor.state import ProcessedFileState, ProcessorState


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "state" / "processor.db"


@pytest.fixture
def state(temp_db_path: Path) -> ProcessorState:
    """Provide a ProcessorState instance with temporary database."""
    return ProcessorState(temp_db_path)


class TestProcessedFileState:
    """Tests for ProcessedFileState dataclass."""

    def test_default_values(self) -> None:
        """ProcessedFileState should have sensible defaults."""
        fs = ProcessedFileState(path="/path/to/file.jsonl")
        assert fs.path == "/path/to/file.jsonl"
        assert fs.last_offset == 0
        assert fs.last_processed is None

    def test_all_fields(self) -> None:
        """ProcessedFileState should accept all field values."""
        fs = ProcessedFileState(
            path="/data/conversations.jsonl",
            last_offset=500,
            last_processed=1706000100,
        )
        assert fs.path == "/data/conversations.jsonl"
        assert fs.last_offset == 500
        assert fs.last_processed == 1706000100


class TestProcessorStateInit:
    """Tests for ProcessorState initialization."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """ProcessorState should create parent directories for database."""
        db_path = tmp_path / "nested" / "dirs" / "state.db"
        state = ProcessorState(db_path)
        try:
            assert db_path.parent.exists()
            assert db_path.exists()
        finally:
            state.close()

    def test_creates_processed_files_table(self, temp_db_path: Path) -> None:
        """ProcessorState should create processed_files table on init."""
        state = ProcessorState(temp_db_path)
        try:
            # Verify table exists by querying it directly
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_files'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            state.close()

    def test_schema_has_correct_columns(self, temp_db_path: Path) -> None:
        """processed_files table should have correct schema."""
        state = ProcessorState(temp_db_path)
        try:
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.execute("PRAGMA table_info(processed_files)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            conn.close()

            assert columns["path"] == "TEXT"
            assert columns["last_offset"] == "INTEGER"
            assert columns["last_processed"] == "INTEGER"
        finally:
            state.close()

    def test_idempotent_schema_creation(self, temp_db_path: Path) -> None:
        """ensure_schema should be idempotent."""
        state1 = ProcessorState(temp_db_path)
        state1.close()

        # Opening again should not raise
        state2 = ProcessorState(temp_db_path)
        state2.ensure_schema()  # Explicit call should also be safe
        state2.close()


class TestProcessorStateGetFile:
    """Tests for get_file_state method."""

    def test_returns_none_for_missing_file(self, state: ProcessorState) -> None:
        """get_file_state should return None for non-existent file."""
        result = state.get_file_state("/nonexistent.jsonl")
        assert result is None
        state.close()

    def test_returns_file_state(self, state: ProcessorState) -> None:
        """get_file_state should return ProcessedFileState for existing file."""
        state.update_file_state(
            "/test.jsonl",
            last_offset=500,
            last_processed=1706000000,
        )

        result = state.get_file_state("/test.jsonl")
        assert result is not None
        assert result.path == "/test.jsonl"
        assert result.last_offset == 500
        assert result.last_processed == 1706000000
        state.close()


class TestProcessorStateGetLastOffset:
    """Tests for get_last_offset method."""

    def test_returns_zero_for_missing_file(self, state: ProcessorState) -> None:
        """get_last_offset should return 0 for non-existent file."""
        result = state.get_last_offset("/nonexistent.jsonl")
        assert result == 0
        state.close()

    def test_returns_offset_for_existing_file(self, state: ProcessorState) -> None:
        """get_last_offset should return offset for existing file."""
        state.update_file_state("/test.jsonl", last_offset=1234)

        result = state.get_last_offset("/test.jsonl")
        assert result == 1234
        state.close()


class TestProcessorStateUpdateFile:
    """Tests for update_file_state method."""

    def test_inserts_new_file(self, state: ProcessorState) -> None:
        """update_file_state should insert new file state."""
        state.update_file_state(
            "/new.jsonl",
            last_offset=500,
        )

        result = state.get_file_state("/new.jsonl")
        assert result is not None
        assert result.last_offset == 500
        assert result.last_processed is None
        state.close()

    def test_updates_existing_file(self, state: ProcessorState) -> None:
        """update_file_state should update existing file state."""
        state.update_file_state("/file.jsonl", last_offset=100)
        state.update_file_state("/file.jsonl", last_offset=500, last_processed=1706000000)

        result = state.get_file_state("/file.jsonl")
        assert result is not None
        assert result.last_offset == 500
        assert result.last_processed == 1706000000
        state.close()

    def test_update_with_no_attrs_is_noop(self, state: ProcessorState) -> None:
        """update_file_state with no attrs should be a no-op for existing."""
        state.update_file_state("/file.jsonl", last_offset=100)
        state.update_file_state("/file.jsonl")  # No attrs

        result = state.get_file_state("/file.jsonl")
        assert result is not None
        assert result.last_offset == 100
        state.close()

    def test_rejects_invalid_attrs(self, state: ProcessorState) -> None:
        """update_file_state should reject invalid attributes."""
        with pytest.raises(ValueError, match="Invalid attributes"):
            state.update_file_state("/file.jsonl", invalid_attr=123)
        state.close()

    def test_all_attrs(self, state: ProcessorState) -> None:
        """update_file_state should accept all valid attributes."""
        state.update_file_state(
            "/file.jsonl",
            last_offset=500,
            last_processed=1706001000,
        )

        result = state.get_file_state("/file.jsonl")
        assert result is not None
        assert result.last_offset == 500
        assert result.last_processed == 1706001000
        state.close()


class TestProcessorStateListFiles:
    """Tests for list_files method."""

    def test_empty_database(self, state: ProcessorState) -> None:
        """list_files should return empty list for empty database."""
        result = state.list_files()
        assert result == []
        state.close()

    def test_lists_all_files(self, state: ProcessorState) -> None:
        """list_files should return all files ordered by path."""
        state.update_file_state("/file3.jsonl", last_offset=300)
        state.update_file_state("/file1.jsonl", last_offset=100)
        state.update_file_state("/file2.jsonl", last_offset=200)

        result = state.list_files()
        assert len(result) == 3

        # Should be ordered by path
        paths = [f.path for f in result]
        assert paths == ["/file1.jsonl", "/file2.jsonl", "/file3.jsonl"]
        state.close()


class TestProcessorStateContextManager:
    """Tests for context manager support."""

    def test_context_manager(self, temp_db_path: Path) -> None:
        """ProcessorState should work as context manager."""
        with ProcessorState(temp_db_path) as state:
            state.update_file_state("/test.jsonl", last_offset=100)
            result = state.get_file_state("/test.jsonl")
            assert result is not None

    def test_closes_on_exit(self, temp_db_path: Path) -> None:
        """ProcessorState should close connection on context exit."""
        with ProcessorState(temp_db_path) as state:
            conn = state._conn

        # After context exit, connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_closes_on_exception(self, temp_db_path: Path) -> None:
        """ProcessorState should close connection even on exception."""
        conn = None
        try:
            with ProcessorState(temp_db_path) as state:
                conn = state._conn
                raise RuntimeError("Test exception")
        except RuntimeError:
            pass

        # Connection should still be closed
        assert conn is not None
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


class TestProcessorStatePersistence:
    """Tests for state persistence across instances."""

    def test_state_persists_across_instances(self, temp_db_path: Path) -> None:
        """State should persist when opening new ProcessorState instance."""
        # First instance: write data
        with ProcessorState(temp_db_path) as state1:
            state1.update_file_state(
                "/persistent.jsonl",
                last_offset=500,
                last_processed=1706001000,
            )

        # Second instance: verify data persisted
        with ProcessorState(temp_db_path) as state2:
            result = state2.get_file_state("/persistent.jsonl")
            assert result is not None
            assert result.last_offset == 500
            assert result.last_processed == 1706001000

    def test_updates_persist(self, temp_db_path: Path) -> None:
        """Updates should persist across instances."""
        # Create initial state
        with ProcessorState(temp_db_path) as state1:
            state1.update_file_state("/file.jsonl", last_offset=0)

        # Update in new instance
        with ProcessorState(temp_db_path) as state2:
            state2.update_file_state("/file.jsonl", last_offset=500)

        # Verify in third instance
        with ProcessorState(temp_db_path) as state3:
            result = state3.get_file_state("/file.jsonl")
            assert result is not None
            assert result.last_offset == 500
