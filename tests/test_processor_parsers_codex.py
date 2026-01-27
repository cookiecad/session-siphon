"""Tests for Codex parser."""

import json
from pathlib import Path

import pytest

from session_siphon.processor.parsers import CodexParser, ParserRegistry
from session_siphon.processor.parsers.base import CanonicalMessage


@pytest.fixture
def parser() -> CodexParser:
    """Create a fresh parser instance."""
    return CodexParser()


@pytest.fixture
def sample_jsonl_file(tmp_path: Path) -> Path:
    """Create a sample Codex JSONL file."""
    file_path = tmp_path / "rollout-2026-01-22T10-52-33-019be668-4c23-7792-8b9c-7995e5bfdeee.jsonl"

    lines = [
        # Session metadata
        {
            "timestamp": "2026-01-22T15:52:33.575Z",
            "type": "session_meta",
            "payload": {
                "id": "019be668-4c23-7792-8b9c-7995e5bfdeee",
                "timestamp": "2026-01-22T15:52:33.571Z",
                "cwd": "/home/user/project",
                "originator": "codex_vscode",
                "cli_version": "0.88.0-alpha.17",
            },
        },
        # User message via response_item
        {
            "timestamp": "2026-01-22T15:52:33.740Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Help me debug this code.",
                    }
                ],
            },
        },
        # User message via event_msg
        {
            "timestamp": "2026-01-22T15:52:33.740Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Help me debug this code.",
                "images": [],
            },
        },
        # Turn context (should be skipped)
        {
            "timestamp": "2026-01-22T15:52:34.922Z",
            "type": "turn_context",
            "payload": {
                "cwd": "/home/user/project",
                "approval_policy": "never",
                "model": "gpt-5.1-codex-mini",
            },
        },
        # Token count event (should be skipped)
        {
            "timestamp": "2026-01-22T15:52:35.178Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": None,
            },
        },
        # Agent reasoning (should be skipped)
        {
            "timestamp": "2026-01-22T15:52:38.745Z",
            "type": "event_msg",
            "payload": {
                "type": "agent_reasoning",
                "text": "**Thinking about the problem**",
            },
        },
        # Reasoning response_item (should be skipped - no role)
        {
            "timestamp": "2026-01-22T15:52:38.745Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "**Thinking**"}],
            },
        },
        # Agent message via event_msg
        {
            "timestamp": "2026-01-22T15:52:38.915Z",
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "message": "I found the bug. The issue is in line 42.",
            },
        },
        # Assistant message via response_item
        {
            "timestamp": "2026-01-22T15:52:38.915Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "I found the bug. The issue is in line 42.",
                    }
                ],
            },
        },
        # Developer message (system context)
        {
            "timestamp": "2026-01-22T15:52:33.737Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You are running in sandbox mode.",
                    }
                ],
            },
        },
    ]

    with open(file_path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")

    return file_path


class TestCodexParserBasics:
    """Tests for basic parser functionality."""

    def test_source_name(self, parser: CodexParser) -> None:
        """Parser should have correct source name."""
        assert parser.source_name == "codex"

    def test_registered_in_registry(self) -> None:
        """Parser should be registered in ParserRegistry."""
        # Re-register since other tests may clear the registry
        ParserRegistry.register(CodexParser())
        retrieved = ParserRegistry.get("codex")
        assert retrieved is not None
        assert isinstance(retrieved, CodexParser)


class TestCodexParserParse:
    """Tests for parse method."""

    def test_parses_messages(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should parse user and assistant messages from JSONL."""
        messages, offset = parser.parse(sample_jsonl_file, "machine-001")

        # Should have messages (response_item messages + event_msg messages + developer)
        # response_item user, event_msg user, event_msg agent, response_item assistant, developer
        assert len(messages) == 5

    def test_extracts_session_id_from_payload(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should extract session_id from session_meta payload."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        for msg in messages:
            assert msg.conversation_id == "019be668-4c23-7792-8b9c-7995e5bfdeee"

    def test_extracts_project_from_session_meta(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should extract project from session_meta cwd field."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        for msg in messages:
            assert msg.project == "/home/user/project"

    def test_sets_machine_id(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should set machine_id from argument."""
        messages, _ = parser.parse(sample_jsonl_file, "my-laptop")

        for msg in messages:
            assert msg.machine_id == "my-laptop"

    def test_parses_timestamp(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should parse ISO 8601 timestamp to Unix timestamp."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        # All messages should have timestamps
        for msg in messages:
            assert msg.ts > 0
            assert isinstance(msg.ts, int)

    def test_extracts_input_text_content(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should extract content from input_text blocks."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        user_messages = [m for m in messages if m.role == "user"]
        assert any("Help me debug" in m.content for m in user_messages)

    def test_extracts_output_text_content(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should extract content from output_text blocks."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        assistant_messages = [m for m in messages if m.role == "assistant"]
        assert any("found the bug" in m.content for m in assistant_messages)

    def test_handles_event_msg_user_message(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should extract user_message from event_msg."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        user_messages = [m for m in messages if m.role == "user"]
        assert len(user_messages) >= 1

    def test_handles_event_msg_agent_message(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should extract agent_message from event_msg."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        assistant_messages = [m for m in messages if m.role == "assistant"]
        assert len(assistant_messages) >= 1

    def test_maps_developer_role_to_system(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should map developer role to system."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        system_messages = [m for m in messages if m.role == "system"]
        assert len(system_messages) >= 1
        assert any("sandbox mode" in m.content for m in system_messages)

    def test_sets_raw_path(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should set raw_path to file path."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        for msg in messages:
            assert msg.raw_path == str(sample_jsonl_file)

    def test_sets_raw_offset(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should set raw_offset for each message."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        # Each message should have an offset
        for msg in messages:
            assert msg.raw_offset is not None
            assert msg.raw_offset >= 0

    def test_returns_source_as_codex(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should set source to 'codex'."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        for msg in messages:
            assert msg.source == "codex"


class TestCodexParserIncremental:
    """Tests for incremental parsing."""

    def test_returns_new_offset(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should return new offset at end of file."""
        _, offset = parser.parse(sample_jsonl_file, "machine-001")

        # Offset should be at end of file
        file_size = sample_jsonl_file.stat().st_size
        assert offset == file_size

    def test_parses_from_offset(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should parse from given offset."""
        # First parse all messages
        all_messages, first_offset = parser.parse(sample_jsonl_file, "machine-001")

        # Parse again from offset - should get no new messages
        new_messages, second_offset = parser.parse(
            sample_jsonl_file, "machine-001", from_offset=first_offset
        )

        assert len(new_messages) == 0
        assert second_offset == first_offset

    def test_incremental_parse_with_new_content(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Should parse only new content when file is appended."""
        file_path = tmp_path / "rollout-test-session.jsonl"

        # Write initial content
        initial_lines = [
            {
                "timestamp": "2026-01-22T15:52:33.575Z",
                "type": "session_meta",
                "payload": {"id": "test-session", "cwd": "/project"},
            },
            {
                "timestamp": "2026-01-22T15:52:33.740Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "First message"},
            },
        ]
        with open(file_path, "w") as f:
            for line in initial_lines:
                f.write(json.dumps(line) + "\n")

        # First parse
        messages1, offset1 = parser.parse(file_path, "machine")
        assert len(messages1) == 1
        assert messages1[0].content == "First message"

        # Append new content
        new_line = {
            "timestamp": "2026-01-22T15:53:00.000Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Second message"},
        }
        with open(file_path, "a") as f:
            f.write(json.dumps(new_line) + "\n")

        # Parse from previous offset
        messages2, offset2 = parser.parse(file_path, "machine", from_offset=offset1)
        assert len(messages2) == 1
        assert messages2[0].content == "Second message"
        assert offset2 > offset1


class TestCodexParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_file(self, parser: CodexParser, tmp_path: Path) -> None:
        """Should handle empty file gracefully."""
        file_path = tmp_path / "empty.jsonl"
        file_path.touch()

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset == 0

    def test_skips_malformed_json(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Should skip lines with invalid JSON."""
        file_path = tmp_path / "malformed.jsonl"

        with open(file_path, "w") as f:
            f.write("not valid json\n")
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "Valid message"},
                    }
                )
                + "\n"
            )
            f.write("{broken json\n")

        messages, _ = parser.parse(file_path, "machine")

        # Should only get the valid message
        assert len(messages) == 1
        assert messages[0].content == "Valid message"

    def test_skips_empty_lines(self, parser: CodexParser, tmp_path: Path) -> None:
        """Should skip empty lines."""
        file_path = tmp_path / "with-blanks.jsonl"

        with open(file_path, "w") as f:
            f.write("\n")
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "Message"},
                    }
                )
                + "\n"
            )
            f.write("   \n")

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1

    def test_skips_response_item_without_role(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Should skip response_item entries without role."""
        file_path = tmp_path / "no-role.jsonl"

        with open(file_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "content": [{"type": "input_text", "text": "No role"}],
                        },
                    }
                )
                + "\n"
            )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 0

    def test_handles_missing_timestamp(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Should handle entries without timestamp."""
        file_path = tmp_path / "no-timestamp.jsonl"

        with open(file_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "Message"},
                    }
                )
                + "\n"
            )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].ts == 0

    def test_handles_empty_content(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Should skip entries with empty content."""
        file_path = tmp_path / "empty-content.jsonl"

        with open(file_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": ""},
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [],
                        },
                    }
                )
                + "\n"
            )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 0

    def test_returns_canonical_message_instances(
        self, parser: CodexParser, sample_jsonl_file: Path
    ) -> None:
        """Should return CanonicalMessage instances."""
        messages, _ = parser.parse(sample_jsonl_file, "machine-001")

        for msg in messages:
            assert isinstance(msg, CanonicalMessage)

    def test_handles_function_call_response_items(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Should skip function_call and function_call_output response items."""
        file_path = tmp_path / "function-calls.jsonl"

        with open(file_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "shell",
                            "arguments": '{"command":["ls"]}',
                            "call_id": "call_123",
                        },
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": "call_123",
                            "output": '{"output":"file.txt"}',
                        },
                    }
                )
                + "\n"
            )

        messages, _ = parser.parse(file_path, "machine")

        # Function calls should be skipped
        assert len(messages) == 0


class TestCodexParserSessionIdExtraction:
    """Tests for session ID extraction from filename."""

    def test_extracts_uuid_from_rollout_filename(self, parser: CodexParser) -> None:
        """Should extract UUID from standard rollout filename."""
        session_id = parser._extract_session_id(
            "rollout-2026-01-22T10-52-33-019be668-4c23-7792-8b9c-7995e5bfdeee"
        )
        assert session_id == "019be668-4c23-7792-8b9c-7995e5bfdeee"

    def test_handles_non_rollout_filename(self, parser: CodexParser) -> None:
        """Should return filename for non-rollout files."""
        session_id = parser._extract_session_id("custom-session-file")
        assert session_id == "custom-session-file"

    def test_session_id_from_payload_takes_precedence(
        self, parser: CodexParser, tmp_path: Path
    ) -> None:
        """Session ID from session_meta payload should override filename."""
        file_path = tmp_path / "rollout-wrong-id.jsonl"

        with open(file_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.575Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "correct-session-id",
                            "cwd": "/project",
                        },
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-01-22T15:52:33.740Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "Test"},
                    }
                )
                + "\n"
            )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].conversation_id == "correct-session-id"


class TestCodexParserWithRealFiles:
    """Tests using real Codex files (if available)."""

    @pytest.fixture
    def real_codex_file(self) -> Path | None:
        """Find a real Codex JSONL file for testing."""
        codex_dir = Path.home() / ".codex" / "sessions"
        if not codex_dir.exists():
            return None

        files = list(codex_dir.glob("**/rollout-*.jsonl"))
        return files[0] if files else None

    def test_parses_real_file_if_available(
        self, parser: CodexParser, real_codex_file: Path | None
    ) -> None:
        """Should successfully parse a real Codex file."""
        if real_codex_file is None:
            pytest.skip("No real Codex files found")

        messages, offset = parser.parse(real_codex_file, "test-machine")

        # Should parse without errors
        assert isinstance(messages, list)
        assert isinstance(offset, int)
        assert offset > 0

        # If there are messages, they should be valid
        if messages:
            for msg in messages:
                assert msg.source == "codex"
                assert msg.machine_id == "test-machine"
                assert msg.role in ("user", "assistant", "system")
                assert msg.content  # Should have content
