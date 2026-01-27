"""Tests for OpenCode (SST) parser."""

import json
from pathlib import Path

import pytest

from session_siphon.processor.parsers import OpenCodeParser, ParserRegistry
from session_siphon.processor.parsers.base import CanonicalMessage


@pytest.fixture
def parser() -> OpenCodeParser:
    """Create a fresh parser instance."""
    return OpenCodeParser()


def create_opencode_structure(
    tmp_path: Path,
    project_hash: str,
    session_id: str,
    messages: list[dict],
) -> Path:
    """Create OpenCode file structure with session, messages, and parts.

    The actual OpenCode storage structure is:
        ~/.local/share/opencode/storage/
            session/<projectHash>/ses_*.json
            message/<sessionID>/msg_*.json
            part/<messageID>/prt_*.json

    Args:
        tmp_path: Base temporary directory (simulates .../storage/)
        project_hash: Project hash identifier
        session_id: Session identifier (e.g., "ses_abc123")
        messages: List of message dicts with 'id', 'role', 'time', and 'parts' keys

    Returns:
        Path to the session file
    """
    # Create directory structure
    session_dir = tmp_path / "session" / project_hash
    message_dir = tmp_path / "message" / session_id
    part_base_dir = tmp_path / "part"

    session_dir.mkdir(parents=True)
    message_dir.mkdir(parents=True)

    # Create session file
    session_file = session_dir / f"{session_id}.json"
    session_data = {
        "id": session_id,
        "projectID": project_hash,
        "directory": "/home/user/projects/myapp",
        "title": "Test Session",
        "time": {
            "created": 1706745600000,  # milliseconds
            "updated": 1706749200000,
        },
    }
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    # Create message and part files
    for msg in messages:
        msg_id = msg["id"]
        msg_file = message_dir / f"{msg_id}.json"
        msg_data = {
            "id": msg_id,
            "sessionID": session_id,
            "role": msg["role"],
        }
        # Only add time if specified
        if "time" in msg:
            msg_data["time"] = msg["time"]
        with open(msg_file, "w") as f:
            json.dump(msg_data, f)

        # Create parts for this message
        if "parts" in msg:
            part_dir = part_base_dir / msg_id
            part_dir.mkdir(parents=True)

            for i, part in enumerate(msg["parts"]):
                part_file = part_dir / f"prt_{i:03d}.json"
                with open(part_file, "w") as f:
                    json.dump(part, f)

    return session_file


@pytest.fixture
def sample_session_file(tmp_path: Path) -> Path:
    """Create a sample OpenCode session with messages and parts."""
    return create_opencode_structure(
        tmp_path,
        project_hash="abc123def456",
        session_id="ses_def456",
        messages=[
            {
                "id": "msg_001",
                "role": "user",
                "time": {"created": 1706745600000},
                "parts": [
                    {"type": "text", "text": "Hello, can you help me with Python?"},
                ],
            },
            {
                "id": "msg_002",
                "role": "assistant",
                "time": {"created": 1706745610000},
                "parts": [
                    {"type": "text", "text": "Of course! I'd be happy to help with Python."},
                ],
            },
        ],
    )


@pytest.fixture
def sample_session_with_tools(tmp_path: Path) -> Path:
    """Create a session with tool calls and reasoning."""
    return create_opencode_structure(
        tmp_path,
        project_hash="toolshash123",
        session_id="ses_tools",
        messages=[
            {
                "id": "msg_001",
                "role": "user",
                "time": {"created": 1706745600000},
                "parts": [
                    {"type": "text", "text": "Create a hello.py file"},
                ],
            },
            {
                "id": "msg_002",
                "role": "assistant",
                "time": {"created": 1706745610000},
                "parts": [
                    {
                        "type": "reasoning",
                        "text": "I need to create a Python file with a hello world program.",
                    },
                    {
                        "type": "tool",
                        "tool": "write_file",
                        "state": {
                            "input": {"path": "hello.py", "content": "print('Hello!')"},
                            "output": "File created successfully",
                            "status": "success",
                        },
                    },
                    {"type": "text", "text": "I've created the hello.py file for you."},
                ],
            },
        ],
    )


class TestOpenCodeParserBasics:
    """Tests for basic parser functionality."""

    def test_source_name(self, parser: OpenCodeParser) -> None:
        """Parser should have correct source name."""
        assert parser.source_name == "opencode"

    def test_registered_in_registry(self) -> None:
        """Parser should be registered in ParserRegistry."""
        ParserRegistry.register(OpenCodeParser())
        retrieved = ParserRegistry.get("opencode")
        assert retrieved is not None
        assert isinstance(retrieved, OpenCodeParser)


class TestOpenCodeParserParse:
    """Tests for parse method."""

    def test_parses_user_and_assistant_messages(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should parse user and assistant messages."""
        messages, offset = parser.parse(sample_session_file, "machine-001")

        assert len(messages) == 2
        roles = [m.role for m in messages]
        assert roles == ["user", "assistant"]

    def test_extracts_session_id(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should extract session ID as conversation_id."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.conversation_id == "ses_def456"

    def test_extracts_project_directory(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should extract project directory from session."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.project == "/home/user/projects/myapp"

    def test_sets_machine_id(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should set machine_id from argument."""
        messages, _ = parser.parse(sample_session_file, "my-laptop")

        for msg in messages:
            assert msg.machine_id == "my-laptop"

    def test_parses_timestamp(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should convert milliseconds timestamp to Unix seconds."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        # 1706745600000 ms = 1706745600 seconds
        assert messages[0].ts == 1706745600
        assert isinstance(messages[0].ts, int)

    def test_extracts_text_content(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should extract text content from parts."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        assert messages[0].content == "Hello, can you help me with Python?"
        assert messages[1].content == "Of course! I'd be happy to help with Python."

    def test_sets_raw_path(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should set raw_path to session file path."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.raw_path == str(sample_session_file)

    def test_returns_source_as_opencode(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should set source to 'opencode'."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.source == "opencode"

    def test_returns_file_size_as_offset(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should return file size as offset."""
        _, offset = parser.parse(sample_session_file, "machine-001")

        file_size = sample_session_file.stat().st_size
        assert offset == file_size


class TestOpenCodeParserToolsAndReasoning:
    """Tests for tool call and reasoning handling."""

    def test_includes_reasoning_in_content(
        self, parser: OpenCodeParser, sample_session_with_tools: Path
    ) -> None:
        """Should include reasoning parts in content."""
        messages, _ = parser.parse(sample_session_with_tools, "machine-001")

        # Second message is assistant with reasoning
        assert "[Reasoning]" in messages[1].content
        assert "I need to create a Python file" in messages[1].content

    def test_includes_tool_calls_in_content(
        self, parser: OpenCodeParser, sample_session_with_tools: Path
    ) -> None:
        """Should include tool calls in content."""
        messages, _ = parser.parse(sample_session_with_tools, "machine-001")

        assert "[Tool: write_file]" in messages[1].content

    def test_includes_tool_output(
        self, parser: OpenCodeParser, sample_session_with_tools: Path
    ) -> None:
        """Should include tool output in content."""
        messages, _ = parser.parse(sample_session_with_tools, "machine-001")

        assert "Output:" in messages[1].content
        assert "File created successfully" in messages[1].content

    def test_includes_tool_status(
        self, parser: OpenCodeParser, sample_session_with_tools: Path
    ) -> None:
        """Should include tool status in content."""
        messages, _ = parser.parse(sample_session_with_tools, "machine-001")

        assert "Status: success" in messages[1].content

    def test_combines_multiple_parts(
        self, parser: OpenCodeParser, sample_session_with_tools: Path
    ) -> None:
        """Should combine multiple parts with separators."""
        messages, _ = parser.parse(sample_session_with_tools, "machine-001")

        # Should have reasoning, tool, and text parts
        assert "[Reasoning]" in messages[1].content
        assert "[Tool:" in messages[1].content
        assert "I've created the hello.py file" in messages[1].content


class TestOpenCodeParserPartTypes:
    """Tests for different part types."""

    def test_handles_file_part(self, parser: OpenCodeParser, tmp_path: Path) -> None:
        """Should format file parts correctly."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="filehash123",
            session_id="ses_file",
            messages=[
                {
                    "id": "msg_001",
                    "role": "user",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {
                            "type": "file",
                            "filename": "image.png",
                            "mime": "image/png",
                            "url": "data:image/png;base64,...",
                        },
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert "[File: image.png (image/png)]" in messages[0].content

    def test_handles_patch_part(self, parser: OpenCodeParser, tmp_path: Path) -> None:
        """Should format patch parts correctly."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="patchhash123",
            session_id="ses_patch",
            messages=[
                {
                    "id": "msg_001",
                    "role": "assistant",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {
                            "type": "patch",
                            "path": "src/main.py",
                            "operation": "modify",
                            "diff": "@@ -1,3 +1,4 @@\n+import os\n import sys",
                        },
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert "[Patch: modify src/main.py]" in messages[0].content
        assert "import os" in messages[0].content

    def test_handles_snapshot_part(self, parser: OpenCodeParser, tmp_path: Path) -> None:
        """Should format snapshot parts correctly."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="snaphash123",
            session_id="ses_snap",
            messages=[
                {
                    "id": "msg_001",
                    "role": "assistant",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {"type": "snapshot"},
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert "[Snapshot:" in messages[0].content

    def test_handles_compaction_part(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should format compaction parts correctly."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="compacthash123",
            session_id="ses_compact",
            messages=[
                {
                    "id": "msg_001",
                    "role": "assistant",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {"type": "compaction"},
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert "[Context compacted]" in messages[0].content

    def test_handles_step_finish_part(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should handle step-finish parts (no visible content)."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="stephash123",
            session_id="ses_step",
            messages=[
                {
                    "id": "msg_001",
                    "role": "assistant",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {"type": "text", "text": "Done!"},
                        {"type": "step-finish", "reason": "tool-calls"},
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        # step-finish should not add visible content
        assert messages[0].content == "Done!"


class TestOpenCodeParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_invalid_session_json(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should handle invalid session JSON gracefully."""
        session_dir = tmp_path / "session" / "hash123"
        session_dir.mkdir(parents=True)
        session_file = session_dir / "ses_123.json"

        with open(session_file, "w") as f:
            f.write("not valid json{")

        messages, offset = parser.parse(session_file, "machine")

        assert messages == []
        assert offset > 0

    def test_handles_empty_session_file(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should handle empty session file gracefully."""
        session_dir = tmp_path / "session" / "hash123"
        session_dir.mkdir(parents=True)
        session_file = session_dir / "ses_123.json"
        session_file.touch()

        messages, offset = parser.parse(session_file, "machine")

        assert messages == []
        assert offset == 0

    def test_handles_missing_message_directory(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should handle missing message directory gracefully."""
        session_dir = tmp_path / "session" / "hash123"
        session_dir.mkdir(parents=True)
        session_file = session_dir / "ses_123.json"

        session_data = {
            "id": "ses_123",
            "projectID": "hash123",
            "directory": "/test",
            "title": "Test",
            "time": {"created": 1706745600000},
        }
        with open(session_file, "w") as f:
            json.dump(session_data, f)

        messages, offset = parser.parse(session_file, "machine")

        assert messages == []
        assert offset > 0

    def test_handles_missing_parts_directory(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should handle missing parts directory gracefully."""
        session_dir = tmp_path / "session" / "hash123"
        message_dir = tmp_path / "message" / "ses_123"

        session_dir.mkdir(parents=True)
        message_dir.mkdir(parents=True)

        # Create session
        session_file = session_dir / "ses_123.json"
        session_data = {
            "id": "ses_123",
            "projectID": "hash123",
            "directory": "/test",
            "title": "Test",
            "time": {"created": 1706745600000},
        }
        with open(session_file, "w") as f:
            json.dump(session_data, f)

        # Create message without parts
        msg_file = message_dir / "msg_001.json"
        msg_data = {
            "id": "msg_001",
            "sessionID": "ses_123",
            "role": "user",
            "time": {"created": 1706745600000},
        }
        with open(msg_file, "w") as f:
            json.dump(msg_data, f)

        messages, _ = parser.parse(session_file, "machine")

        # Message should be skipped because it has no content
        assert messages == []

    def test_skips_invalid_role(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should skip messages with invalid roles."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="hash123",
            session_id="ses_123",
            messages=[
                {
                    "id": "msg_001",
                    "role": "system",  # Not user or assistant
                    "time": {"created": 1706745600000},
                    "parts": [{"type": "text", "text": "System message"}],
                },
                {
                    "id": "msg_002",
                    "role": "user",
                    "time": {"created": 1706745610000},
                    "parts": [{"type": "text", "text": "Hello"}],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_skips_empty_content_messages(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should skip messages with no content."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="hash123",
            session_id="ses_123",
            messages=[
                {
                    "id": "msg_001",
                    "role": "user",
                    "time": {"created": 1706745600000},
                    "parts": [{"type": "text", "text": ""}],  # Empty text
                },
                {
                    "id": "msg_002",
                    "role": "user",
                    "time": {"created": 1706745610000},
                    "parts": [{"type": "text", "text": "Hello"}],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_sorts_messages_by_timestamp(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should sort messages by timestamp."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="hash123",
            session_id="ses_123",
            messages=[
                {
                    "id": "msg_002",  # Later timestamp but created first
                    "role": "assistant",
                    "time": {"created": 1706745700000},
                    "parts": [{"type": "text", "text": "Response"}],
                },
                {
                    "id": "msg_001",
                    "role": "user",
                    "time": {"created": 1706745600000},
                    "parts": [{"type": "text", "text": "Question"}],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert len(messages) == 2
        assert messages[0].content == "Question"
        assert messages[1].content == "Response"

    def test_handles_missing_timestamp(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should handle messages without timestamp."""
        session_file = create_opencode_structure(
            tmp_path,
            project_hash="hash123",
            session_id="ses_123",
            messages=[
                {
                    "id": "msg_001",
                    "role": "user",
                    # No time field
                    "parts": [{"type": "text", "text": "Hello"}],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert len(messages) == 1
        assert messages[0].ts == 0

    def test_returns_canonical_message_instances(
        self, parser: OpenCodeParser, sample_session_file: Path
    ) -> None:
        """Should return CanonicalMessage instances."""
        messages, _ = parser.parse(sample_session_file, "machine")

        for msg in messages:
            assert isinstance(msg, CanonicalMessage)


class TestOpenCodeParserToolTruncation:
    """Tests for tool input/output truncation."""

    def test_truncates_long_tool_input(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should truncate long tool input."""
        long_input = "x" * 500

        session_file = create_opencode_structure(
            tmp_path,
            project_hash="hash123",
            session_id="ses_123",
            messages=[
                {
                    "id": "msg_001",
                    "role": "assistant",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "test_tool",
                            "state": {"input": long_input},
                        },
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert len(messages) == 1
        # Should be truncated to 200 chars + "..."
        assert "..." in messages[0].content
        assert len(messages[0].content) < len(long_input)

    def test_truncates_long_tool_output(
        self, parser: OpenCodeParser, tmp_path: Path
    ) -> None:
        """Should truncate long tool output."""
        long_output = "y" * 500

        session_file = create_opencode_structure(
            tmp_path,
            project_hash="hash123",
            session_id="ses_123",
            messages=[
                {
                    "id": "msg_001",
                    "role": "assistant",
                    "time": {"created": 1706745600000},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "test_tool",
                            "state": {"output": long_output},
                        },
                    ],
                },
            ],
        )

        messages, _ = parser.parse(session_file, "machine")

        assert len(messages) == 1
        assert "..." in messages[0].content


class TestOpenCodeParserWithRealFiles:
    """Tests using real OpenCode files (if available)."""

    @pytest.fixture
    def real_opencode_session(self) -> Path | None:
        """Find a real OpenCode session file for testing."""
        # New correct location
        opencode_dir = Path.home() / ".local" / "share" / "opencode" / "storage" / "session"
        if not opencode_dir.exists():
            return None

        files = list(opencode_dir.glob("*/ses_*.json"))
        return files[0] if files else None

    def test_parses_real_file_if_available(
        self, parser: OpenCodeParser, real_opencode_session: Path | None
    ) -> None:
        """Should successfully parse a real OpenCode session file."""
        if real_opencode_session is None:
            pytest.skip("No real OpenCode session files found")

        messages, offset = parser.parse(real_opencode_session, "test-machine")

        # Should parse without errors
        assert isinstance(messages, list)
        assert isinstance(offset, int)
        assert offset > 0

        # If there are messages, they should be valid
        if messages:
            for msg in messages:
                assert msg.source == "opencode"
                assert msg.machine_id == "test-machine"
                assert msg.role in ("user", "assistant")
