"""Tests for Gemini CLI parser."""

import json
from pathlib import Path

import pytest

from session_siphon.processor.parsers import GeminiParser, ParserRegistry
from session_siphon.processor.parsers.base import CanonicalMessage


@pytest.fixture
def parser() -> GeminiParser:
    """Create a fresh parser instance."""
    return GeminiParser()


@pytest.fixture
def sample_json_file(tmp_path: Path) -> Path:
    """Create a sample Gemini CLI JSON file with realistic path structure."""
    # Create path structure: tmp/<project_hash>/chats/session-*.json
    project_hash = "4df5bbda56593e2b61fbf92b04c67f7ea84fbceceb9c601e09c297849a1a6801"
    chats_dir = tmp_path / project_hash / "chats"
    chats_dir.mkdir(parents=True)
    file_path = chats_dir / "session-2025-12-28T04-25-fc357040.json"

    data = {
        "sessionId": "fc357040-1b15-4db4-9163-78167dd99496",
        "projectHash": project_hash,
        "startTime": "2025-12-28T04:25:36.602Z",
        "lastUpdated": "2025-12-28T04:25:38.439Z",
        "messages": [
            {
                "id": "a491b2b7-8735-41b9-a0b5-e40ad99935f9",
                "timestamp": "2025-12-28T04:25:36.602Z",
                "type": "user",
                "content": "Hello, how can you help me?",
            },
            {
                "id": "0dd44dd4-58b7-4b4b-b613-93cda73ceebf",
                "timestamp": "2025-12-28T04:25:38.439Z",
                "type": "gemini",
                "content": "I can help you with coding tasks!",
                "thoughts": [
                    {
                        "subject": "Seeking User Input",
                        "description": "Preparing to help the user.",
                        "timestamp": "2025-12-28T04:25:38.383Z",
                    }
                ],
                "tokens": {"input": 100, "output": 20, "total": 120},
                "model": "gemini-2.5-flash",
            },
        ],
    }

    with open(file_path, "w") as f:
        json.dump(data, f)

    return file_path


@pytest.fixture
def sample_json_with_tools(tmp_path: Path) -> Path:
    """Create a sample Gemini CLI JSON file with tool calls."""
    project_hash = "abc123def456"
    chats_dir = tmp_path / project_hash / "chats"
    chats_dir.mkdir(parents=True)
    file_path = chats_dir / "session-2025-12-28T04-36-test.json"

    data = {
        "sessionId": "test-session-id",
        "projectHash": project_hash,
        "startTime": "2025-12-28T04:36:00.000Z",
        "lastUpdated": "2025-12-28T04:36:30.000Z",
        "messages": [
            {
                "id": "msg-1",
                "timestamp": "2025-12-28T04:36:00.000Z",
                "type": "user",
                "content": "Create a hello.py file",
            },
            {
                "id": "msg-2",
                "timestamp": "2025-12-28T04:36:10.000Z",
                "type": "gemini",
                "content": "",
                "toolCalls": [
                    {
                        "id": "tool-1",
                        "name": "write_file",
                        "displayName": "WriteFile",
                        "args": {"file_path": "hello.py", "content": "print('hello')"},
                        "result": [
                            {
                                "functionResponse": {
                                    "id": "tool-1",
                                    "name": "write_file",
                                    "response": {
                                        "output": "Successfully created hello.py"
                                    },
                                }
                            }
                        ],
                        "status": "success",
                    }
                ],
            },
            {
                "id": "msg-3",
                "timestamp": "2025-12-28T04:36:20.000Z",
                "type": "gemini",
                "content": "I've created the hello.py file for you.",
            },
        ],
    }

    with open(file_path, "w") as f:
        json.dump(data, f)

    return file_path


class TestGeminiParserBasics:
    """Tests for basic parser functionality."""

    def test_source_name(self, parser: GeminiParser) -> None:
        """Parser should have correct source name."""
        assert parser.source_name == "gemini_cli"

    def test_registered_in_registry(self) -> None:
        """Parser should be registered in ParserRegistry."""
        # Re-register since other tests may affect the registry
        ParserRegistry.register(GeminiParser())
        retrieved = ParserRegistry.get("gemini_cli")
        assert retrieved is not None
        assert isinstance(retrieved, GeminiParser)


class TestGeminiParserParse:
    """Tests for parse method."""

    def test_parses_user_and_gemini_messages(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should parse user and gemini messages from JSON."""
        messages, offset = parser.parse(sample_json_file, "machine-001")

        # Should have 2 messages
        assert len(messages) == 2

        # Check roles
        roles = [m.role for m in messages]
        assert roles == ["user", "assistant"]

    def test_extracts_session_id(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should extract sessionId as conversation_id."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        for msg in messages:
            assert msg.conversation_id == "fc357040-1b15-4db4-9163-78167dd99496"

    def test_extracts_project_from_path(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should extract project hash from file path."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        expected_project = "4df5bbda56593e2b61fbf92b04c67f7ea84fbceceb9c601e09c297849a1a6801"
        for msg in messages:
            assert msg.project == expected_project

    def test_sets_machine_id(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should set machine_id from argument."""
        messages, _ = parser.parse(sample_json_file, "my-laptop")

        for msg in messages:
            assert msg.machine_id == "my-laptop"

    def test_parses_timestamp(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should parse ISO 8601 timestamp to Unix timestamp."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        # Timestamps should be positive integers
        assert messages[0].ts > 0
        assert isinstance(messages[0].ts, int)

    def test_extracts_content(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should extract content correctly."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        assert messages[0].content == "Hello, how can you help me?"
        assert messages[1].content == "I can help you with coding tasks!"

    def test_sets_raw_path(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should set raw_path to file path."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        for msg in messages:
            assert msg.raw_path == str(sample_json_file)

    def test_returns_source_as_gemini_cli(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should set source to 'gemini_cli'."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        for msg in messages:
            assert msg.source == "gemini_cli"


class TestGeminiParserToolCalls:
    """Tests for tool call handling."""

    def test_includes_tool_calls_in_content(
        self, parser: GeminiParser, sample_json_with_tools: Path
    ) -> None:
        """Should include tool calls as descriptive text."""
        messages, _ = parser.parse(sample_json_with_tools, "machine-001")

        # Second message has tool calls
        assert "[Tool: WriteFile]" in messages[1].content

    def test_includes_tool_results(
        self, parser: GeminiParser, sample_json_with_tools: Path
    ) -> None:
        """Should include tool results in content."""
        messages, _ = parser.parse(sample_json_with_tools, "machine-001")

        assert "[Tool Result:" in messages[1].content
        assert "Successfully created hello.py" in messages[1].content

    def test_handles_empty_content_with_tools(
        self, parser: GeminiParser, sample_json_with_tools: Path
    ) -> None:
        """Should handle messages with empty content but tool calls."""
        messages, _ = parser.parse(sample_json_with_tools, "machine-001")

        # Second message has empty content but tool calls
        assert len(messages[1].content) > 0  # Should have tool info


class TestGeminiParserFullReparse:
    """Tests for full reparse behavior."""

    def test_returns_file_size_as_offset(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should return file size as offset."""
        _, offset = parser.parse(sample_json_file, "machine-001")

        file_size = sample_json_file.stat().st_size
        assert offset == file_size

    def test_ignores_from_offset_parameter(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should ignore from_offset and always reparse full file."""
        # First parse
        messages1, offset1 = parser.parse(sample_json_file, "machine-001")

        # Parse again with offset - should still return all messages
        messages2, offset2 = parser.parse(
            sample_json_file, "machine-001", from_offset=offset1
        )

        # Should get same messages (full reparse)
        assert len(messages2) == len(messages1)
        assert offset2 == offset1

    def test_reparse_detects_new_messages(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should detect new messages on reparse."""
        project_hash = "test-project"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-test.json"

        # Initial data
        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "startTime": "2025-12-28T00:00:00.000Z",
            "lastUpdated": "2025-12-28T00:00:00.000Z",
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "user",
                    "content": "First message",
                }
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        # First parse
        messages1, _ = parser.parse(file_path, "machine")
        assert len(messages1) == 1

        # Add new message
        data["messages"].append(
            {
                "id": "msg-2",
                "timestamp": "2025-12-28T00:01:00.000Z",
                "type": "gemini",
                "content": "Second message",
            }
        )

        with open(file_path, "w") as f:
            json.dump(data, f)

        # Reparse - should get both messages
        messages2, _ = parser.parse(file_path, "machine")
        assert len(messages2) == 2


class TestGeminiParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_file(self, parser: GeminiParser, tmp_path: Path) -> None:
        """Should handle empty file gracefully."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-empty.json"
        file_path.touch()

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset == 0

    def test_handles_invalid_json(self, parser: GeminiParser, tmp_path: Path) -> None:
        """Should handle invalid JSON gracefully."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-invalid.json"

        with open(file_path, "w") as f:
            f.write("not valid json{")

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset > 0  # File size

    def test_skips_info_messages(self, parser: GeminiParser, tmp_path: Path) -> None:
        """Should skip info-type messages."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-info.json"

        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "startTime": "2025-12-28T00:00:00.000Z",
            "lastUpdated": "2025-12-28T00:00:00.000Z",
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "info",
                    "content": "Installing IDE companion...",
                },
                {
                    "id": "msg-2",
                    "timestamp": "2025-12-28T00:00:01.000Z",
                    "type": "user",
                    "content": "Hello",
                },
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_skips_empty_content(self, parser: GeminiParser, tmp_path: Path) -> None:
        """Should skip messages with empty content and no tool calls."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-empty-content.json"

        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "startTime": "2025-12-28T00:00:00.000Z",
            "lastUpdated": "2025-12-28T00:00:00.000Z",
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "user",
                    "content": "",
                },
                {
                    "id": "msg-2",
                    "timestamp": "2025-12-28T00:00:01.000Z",
                    "type": "user",
                    "content": "Valid message",
                },
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].content == "Valid message"

    def test_handles_missing_session_id(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should use filename stem when sessionId is missing."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-fallback.json"

        data = {
            "projectHash": project_hash,
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "user",
                    "content": "Hello",
                }
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].conversation_id == "session-fallback"

    def test_handles_missing_timestamp(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should handle messages without timestamp."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-no-ts.json"

        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "messages": [
                {
                    "id": "msg-1",
                    "type": "user",
                    "content": "Hello",
                }
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].ts == 0

    def test_handles_path_without_chats_dir(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should handle paths without standard chats directory structure."""
        file_path = tmp_path / "random-session.json"

        data = {
            "sessionId": "test-session",
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "user",
                    "content": "Hello",
                }
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].project == ""  # Empty project when path doesn't match

    def test_returns_canonical_message_instances(
        self, parser: GeminiParser, sample_json_file: Path
    ) -> None:
        """Should return CanonicalMessage instances."""
        messages, _ = parser.parse(sample_json_file, "machine-001")

        for msg in messages:
            assert isinstance(msg, CanonicalMessage)

    def test_handles_empty_messages_array(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should handle JSON with empty messages array."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-empty-messages.json"

        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "messages": [],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset > 0


class TestGeminiParserContentExtraction:
    """Tests for content extraction edge cases."""

    def test_truncates_long_tool_results(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should truncate long tool result content."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-long-result.json"

        long_output = "x" * 500

        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "gemini",
                    "content": "Running command",
                    "toolCalls": [
                        {
                            "id": "tool-1",
                            "name": "run_shell_command",
                            "displayName": "Shell",
                            "result": [
                                {
                                    "functionResponse": {
                                        "response": {"output": long_output}
                                    }
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        # Should be truncated
        assert len(messages[0].content) < len(long_output) + 100
        assert "..." in messages[0].content

    def test_uses_name_when_displayname_missing(
        self, parser: GeminiParser, tmp_path: Path
    ) -> None:
        """Should fall back to name when displayName is missing."""
        project_hash = "test"
        chats_dir = tmp_path / project_hash / "chats"
        chats_dir.mkdir(parents=True)
        file_path = chats_dir / "session-no-displayname.json"

        data = {
            "sessionId": "test-session",
            "projectHash": project_hash,
            "messages": [
                {
                    "id": "msg-1",
                    "timestamp": "2025-12-28T00:00:00.000Z",
                    "type": "gemini",
                    "content": "",
                    "toolCalls": [
                        {
                            "id": "tool-1",
                            "name": "write_file",
                            "result": [],
                        }
                    ],
                }
            ],
        }

        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert "[Tool: write_file]" in messages[0].content


class TestGeminiParserWithRealFiles:
    """Tests using real Gemini CLI files (if available)."""

    @pytest.fixture
    def real_gemini_file(self) -> Path | None:
        """Find a real Gemini CLI JSON file for testing."""
        gemini_dir = Path.home() / ".gemini" / "tmp"
        if not gemini_dir.exists():
            return None

        files = list(gemini_dir.glob("*/chats/session-*.json"))
        return files[0] if files else None

    def test_parses_real_file_if_available(
        self, parser: GeminiParser, real_gemini_file: Path | None
    ) -> None:
        """Should successfully parse a real Gemini CLI file."""
        if real_gemini_file is None:
            pytest.skip("No real Gemini CLI files found")

        messages, offset = parser.parse(real_gemini_file, "test-machine")

        # Should parse without errors
        assert isinstance(messages, list)
        assert isinstance(offset, int)
        assert offset > 0

        # If there are messages, they should be valid
        if messages:
            for msg in messages:
                assert msg.source == "gemini_cli"
                assert msg.machine_id == "test-machine"
                assert msg.role in ("user", "assistant")
                assert msg.content  # Should have content
