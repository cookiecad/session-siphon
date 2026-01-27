"""Tests for collector daemon module."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_siphon.collector.daemon import (
    is_shutdown_requested,
    request_shutdown,
    reset_shutdown,
    run_collector,
    run_collector_cycle,
    sync_file,
)
from session_siphon.collector.state import CollectorState
from session_siphon.config import CollectorConfig, Config


@pytest.fixture
def tmp_state(tmp_path: Path) -> CollectorState:
    """Create a temporary CollectorState for testing."""
    db_path = tmp_path / "state" / "test.db"
    return CollectorState(db_path)


@pytest.fixture
def tmp_outbox(tmp_path: Path) -> Path:
    """Create a temporary outbox directory."""
    outbox = tmp_path / "outbox"
    outbox.mkdir(parents=True)
    return outbox


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create a test configuration."""
    return Config(
        machine_id="test-machine",
        collector=CollectorConfig(
            interval_seconds=1,
            outbox_path=tmp_path / "outbox",
            state_db=tmp_path / "state" / "collector.db",
        ),
    )


class TestShutdownFlags:
    """Tests for shutdown flag management."""

    def test_initial_state_not_shutdown(self) -> None:
        """Should start with shutdown not requested."""
        reset_shutdown()
        assert is_shutdown_requested() is False

    def test_request_shutdown_sets_flag(self) -> None:
        """Should set shutdown flag when requested."""
        reset_shutdown()
        request_shutdown()
        assert is_shutdown_requested() is True

    def test_reset_shutdown_clears_flag(self) -> None:
        """Should clear shutdown flag when reset."""
        request_shutdown()
        reset_shutdown()
        assert is_shutdown_requested() is False


class TestSyncFile:
    """Tests for sync_file function."""

    def test_syncs_new_jsonl_file(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should sync a new JSONL file."""
        # Create source file
        source_path = tmp_path / "source" / "conv.jsonl"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b'{"message": "hello"}\n')

        result = sync_file(
            source="test_source",
            source_path=source_path,
            state=tmp_state,
            machine_id="test-machine",
            outbox_path=tmp_outbox,
        )

        assert result is True

        # Verify file was copied
        dest_files = list(tmp_outbox.glob("**/*.jsonl"))
        assert len(dest_files) == 1
        assert dest_files[0].read_bytes() == b'{"message": "hello"}\n'

    def test_syncs_new_json_file(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should sync a new JSON file."""
        source_path = tmp_path / "source" / "session.json"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b'{"session": 1}')

        result = sync_file(
            source="test_source",
            source_path=source_path,
            state=tmp_state,
            machine_id="test-machine",
            outbox_path=tmp_outbox,
        )

        assert result is True

        # Verify file was copied
        dest_files = list(tmp_outbox.glob("**/*.json"))
        assert len(dest_files) == 1
        assert dest_files[0].read_bytes() == b'{"session": 1}'

    def test_returns_false_when_up_to_date(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should return False when file is already up to date."""
        source_path = tmp_path / "source" / "conv.jsonl"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b'{"message": "hello"}\n')

        # First sync
        sync_file(
            source="test_source",
            source_path=source_path,
            state=tmp_state,
            machine_id="test-machine",
            outbox_path=tmp_outbox,
        )

        # Second sync should return False (no changes)
        result = sync_file(
            source="test_source",
            source_path=source_path,
            state=tmp_state,
            machine_id="test-machine",
            outbox_path=tmp_outbox,
        )

        assert result is False

    def test_syncs_incremental_jsonl_changes(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should sync only new bytes for JSONL files."""
        source_path = tmp_path / "source" / "conv.jsonl"
        source_path.parent.mkdir(parents=True)

        # Initial content
        source_path.write_bytes(b'{"line": 1}\n')
        sync_file("test_source", source_path, tmp_state, "test-machine", tmp_outbox)

        # Add more content
        source_path.write_bytes(b'{"line": 1}\n{"line": 2}\n')
        result = sync_file(
            "test_source", source_path, tmp_state, "test-machine", tmp_outbox
        )

        assert result is True

        # Verify destination has all content
        dest_files = list(tmp_outbox.glob("**/*.jsonl"))
        assert dest_files[0].read_bytes() == b'{"line": 1}\n{"line": 2}\n'

    def test_handles_file_reset(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should handle file truncation/reset."""
        source_path = tmp_path / "source" / "conv.jsonl"
        source_path.parent.mkdir(parents=True)

        # Initial content
        source_path.write_bytes(b'{"line": 1}\n{"line": 2}\n{"line": 3}\n')
        sync_file("test_source", source_path, tmp_state, "test-machine", tmp_outbox)

        # File gets truncated (smaller)
        source_path.write_bytes(b'{"new": 1}\n')
        result = sync_file(
            "test_source", source_path, tmp_state, "test-machine", tmp_outbox
        )

        assert result is True

        # Verify destination was reset
        dest_files = list(tmp_outbox.glob("**/*.jsonl"))
        assert dest_files[0].read_bytes() == b'{"new": 1}\n'

    def test_updates_state_after_sync(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should update file state after successful sync."""
        source_path = tmp_path / "source" / "conv.jsonl"
        source_path.parent.mkdir(parents=True)
        content = b'{"message": "test"}\n'
        source_path.write_bytes(content)

        sync_file("test_source", source_path, tmp_state, "test-machine", tmp_outbox)

        # Verify state was updated
        file_state = tmp_state.get_file_state("test_source", str(source_path))
        assert file_state is not None
        assert file_state.last_offset == len(content)
        assert file_state.sha256 is not None
        assert file_state.last_synced is not None


class TestRunCollectorCycle:
    """Tests for run_collector_cycle function."""

    def test_discovers_and_syncs_files(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should discover sources and sync files."""
        # Create mock source files
        source_files = {
            "claude_code": [tmp_path / "claude" / "conv.jsonl"],
            "vscode_copilot": [tmp_path / "vscode" / "session.json"],
        }
        for paths in source_files.values():
            for p in paths:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'{"test": true}\n')

        with patch(
            "session_siphon.collector.daemon.discover_all_sources",
            return_value=source_files,
        ):
            synced = run_collector_cycle(tmp_state, "test-machine", tmp_outbox)

        assert synced == 2

    def test_returns_zero_when_no_sources(
        self, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should return 0 when no sources discovered."""
        with patch(
            "session_siphon.collector.daemon.discover_all_sources",
            return_value={},
        ):
            synced = run_collector_cycle(tmp_state, "test-machine", tmp_outbox)

        assert synced == 0

    def test_handles_sync_errors_gracefully(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path, caplog
    ) -> None:
        """Should continue syncing after errors."""
        # Create source files
        good_file = tmp_path / "good.jsonl"
        good_file.write_bytes(b'{"good": true}\n')

        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_bytes(b'{"bad": true}\n')

        source_files = {"test": [bad_file, good_file]}

        def mock_sync(source, source_path, state, machine_id, outbox_path):
            if "bad" in str(source_path):
                raise OSError("Simulated error")
            return True

        with patch(
            "session_siphon.collector.daemon.discover_all_sources",
            return_value=source_files,
        ), patch(
            "session_siphon.collector.daemon.sync_file",
            side_effect=mock_sync,
        ):
            synced = run_collector_cycle(tmp_state, "test-machine", tmp_outbox)

        # Should have synced the good file
        assert synced == 1

        # Should have logged error
        assert "Error syncing file" in caplog.text

    def test_respects_shutdown_flag(
        self, tmp_path: Path, tmp_state: CollectorState, tmp_outbox: Path
    ) -> None:
        """Should stop early when shutdown is requested."""
        reset_shutdown()

        # Create many files
        source_files = {"test": []}
        for i in range(10):
            f = tmp_path / f"file{i}.jsonl"
            f.write_bytes(b'{"test": true}\n')
            source_files["test"].append(f)

        sync_count = 0

        def mock_sync(*args, **kwargs):
            nonlocal sync_count
            sync_count += 1
            if sync_count >= 3:
                request_shutdown()
            return True

        with patch(
            "session_siphon.collector.daemon.discover_all_sources",
            return_value=source_files,
        ), patch(
            "session_siphon.collector.daemon.sync_file",
            side_effect=mock_sync,
        ):
            synced = run_collector_cycle(tmp_state, "test-machine", tmp_outbox)

        # Should have stopped early
        assert synced < 10
        reset_shutdown()


class TestRunCollector:
    """Tests for run_collector main loop."""

    def test_runs_until_shutdown(self, test_config: Config, caplog) -> None:
        """Should run cycles until shutdown is requested."""
        reset_shutdown()
        cycle_count = 0

        def mock_cycle(*args):
            nonlocal cycle_count
            cycle_count += 1
            if cycle_count >= 2:
                request_shutdown()
            return 0

        with patch(
            "session_siphon.collector.daemon.run_collector_cycle",
            side_effect=mock_cycle,
        ):
            run_collector(test_config)

        assert cycle_count >= 2

        assert "Starting collector daemon" in caplog.text
        assert "Collector daemon stopped" in caplog.text

    def test_logs_status_messages(self, test_config: Config, caplog) -> None:
        """Should log status messages."""
        reset_shutdown()

        def mock_cycle(*args):
            request_shutdown()
            return 5

        with patch(
            "session_siphon.collector.daemon.run_collector_cycle",
            side_effect=mock_cycle,
        ):
            run_collector(test_config)

        assert "files_synced=5" in caplog.text

    def test_uses_config_values(self, test_config: Config, caplog) -> None:
        """Should use configuration values."""
        reset_shutdown()

        def mock_cycle(*args):
            request_shutdown()  # Exit after first cycle
            return 0

        with patch(
            "session_siphon.collector.daemon.run_collector_cycle",
            side_effect=mock_cycle,
        ):
            run_collector(test_config)

        assert "test-machine" in caplog.text


class TestMainModule:
    """Tests for __main__ module."""

    def test_main_loads_config_and_runs(self) -> None:
        """Should load config and run collector."""
        mock_config = MagicMock()

        with patch(
            "session_siphon.collector.__main__.load_config",
            return_value=mock_config,
        ) as mock_load, patch(
            "session_siphon.collector.__main__.run_collector"
        ) as mock_run, patch(
            "session_siphon.collector.__main__.sys.exit"
        ):
            from session_siphon.collector.__main__ import main

            main()

        mock_load.assert_called_once()
        mock_run.assert_called_once_with(mock_config)

    def test_signal_handler_requests_shutdown(self) -> None:
        """Signal handler should request shutdown."""
        reset_shutdown()

        from session_siphon.collector.__main__ import signal_handler
        import signal as sig

        signal_handler(sig.SIGINT, None)

        assert is_shutdown_requested() is True
        reset_shutdown()


class TestIntegration:
    """Integration tests for the collector daemon."""

    def test_full_sync_cycle(self, tmp_path: Path) -> None:
        """Should perform full sync cycle with real files."""
        # Setup
        source_dir = tmp_path / "sources"
        source_dir.mkdir()

        outbox = tmp_path / "outbox"
        state_db = tmp_path / "state" / "test.db"

        # Create source files
        jsonl_file = source_dir / "conversation.jsonl"
        jsonl_file.write_bytes(b'{"turn": 1}\n{"turn": 2}\n')

        json_file = source_dir / "session.json"
        json_file.write_bytes(b'{"session_id": "abc123"}')

        config = Config(
            machine_id="integration-test",
            collector=CollectorConfig(
                interval_seconds=1,
                outbox_path=outbox,
                state_db=state_db,
            ),
        )

        # Mock discover_all_sources to return our test files
        sources = {"test_source": [jsonl_file, json_file]}

        reset_shutdown()

        with CollectorState(state_db) as state:
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                synced = run_collector_cycle(state, config.machine_id, outbox)

        # Verify
        assert synced == 2

        # Check JSONL file
        jsonl_dest = list(outbox.glob("**/*.jsonl"))
        assert len(jsonl_dest) == 1
        assert jsonl_dest[0].read_bytes() == b'{"turn": 1}\n{"turn": 2}\n'

        # Check JSON file
        json_dest = list(outbox.glob("**/*.json"))
        assert len(json_dest) == 1
        assert json_dest[0].read_bytes() == b'{"session_id": "abc123"}'

    def test_incremental_sync_preserves_data(self, tmp_path: Path) -> None:
        """Should preserve data across incremental syncs."""
        source_dir = tmp_path / "sources"
        source_dir.mkdir()
        outbox = tmp_path / "outbox"
        state_db = tmp_path / "state" / "test.db"

        jsonl_file = source_dir / "conversation.jsonl"

        config = Config(
            machine_id="test",
            collector=CollectorConfig(
                interval_seconds=1,
                outbox_path=outbox,
                state_db=state_db,
            ),
        )

        sources = {"test_source": [jsonl_file]}

        with CollectorState(state_db) as state:
            # First cycle - initial content
            jsonl_file.write_bytes(b'{"turn": 1}\n')

            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                run_collector_cycle(state, config.machine_id, outbox)

            # Second cycle - append content
            jsonl_file.write_bytes(b'{"turn": 1}\n{"turn": 2}\n')

            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                run_collector_cycle(state, config.machine_id, outbox)

            # Third cycle - append more
            jsonl_file.write_bytes(b'{"turn": 1}\n{"turn": 2}\n{"turn": 3}\n')

            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                run_collector_cycle(state, config.machine_id, outbox)

        # Verify final content
        dest_files = list(outbox.glob("**/*.jsonl"))
        assert len(dest_files) == 1
        assert dest_files[0].read_bytes() == b'{"turn": 1}\n{"turn": 2}\n{"turn": 3}\n'
