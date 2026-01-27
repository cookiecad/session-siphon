"""Tests for Google Antigravity parser."""

import json
from pathlib import Path

import pytest

from session_siphon.processor.parsers import AntigravityParser, ParserRegistry
from session_siphon.processor.parsers.base import CanonicalMessage


@pytest.fixture
def parser() -> AntigravityParser:
    """Create a fresh parser instance."""
    return AntigravityParser()


@pytest.fixture
def sample_conversation_file(tmp_path: Path) -> Path:
    """Create a sample Antigravity conversation file."""
    conversations_dir = tmp_path / "conversations"
    conversations_dir.mkdir(parents=True)
    file_path = conversations_dir / "conv-123.json"

    data = {
        "id": "conv-123",
        "title": "Help with Python",
        "workspaceUri": "file:///home/user/projects/myapp",
        "createdAt": "2025-12-01T10:00:00.000Z",
        "modifiedAt": "2025-12-01T10:05:00.000Z",
        "messages": [
            {
                "role": "user",
                "content": "How do I read a file in Python?",
                "timestamp": "2025-12-01T10:00:00.000Z",
            },
            {
                "role": "assistant",
                "content": "You can use the open() function to read files in Python.",
                "timestamp": "2025-12-01T10:00:05.000Z",
            },
        ],
    }

    with open(file_path, "w") as f:
        json.dump(data, f)

    return file_path


@pytest.fixture
def sample_brain_session(tmp_path: Path) -> Path:
    """Create a sample Antigravity brain session file."""
    brain_dir = tmp_path / "brain" / "session-abc123"
    brain_dir.mkdir(parents=True)
    file_path = brain_dir / "session.json"

    data = {
        "sessionId": "session-abc123",
        "workspaceUri": "file:///home/user/projects/webapp",
        "messages": [
            {
                "role": "user",
                "content": "Create a new React component",
                "timestamp": 1701432000000,  # milliseconds
            },
            {
                "role": "model",  # Gemini-style role
                "content": "I'll create a new React component for you.",
                "timestamp": 1701432010000,
            },
        ],
    }

    with open(file_path, "w") as f:
        json.dump(data, f)

    return file_path


@pytest.fixture
def sample_with_parts(tmp_path: Path) -> Path:
    """Create a conversation with array content parts."""
    conversations_dir = tmp_path / "conversations"
    conversations_dir.mkdir(parents=True)
    file_path = conversations_dir / "conv-parts.json"

    data = {
        "id": "conv-parts",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Can you help me?"},
                ],
                "timestamp": "2025-12-01T10:00:00.000Z",
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Of course!"},
                    {"type": "tool_use", "name": "read_file"},
                    {"type": "tool_result", "content": "File contents here"},
                ],
                "timestamp": "2025-12-01T10:00:05.000Z",
            },
        ],
    }

    with open(file_path, "w") as f:
        json.dump(data, f)

    return file_path


class TestAntigravityParserBasics:
    """Tests for basic parser functionality."""

    def test_source_name(self, parser: AntigravityParser) -> None:
        """Parser should have correct source name."""
        assert parser.source_name == "antigravity"

    def test_registered_in_registry(self) -> None:
        """Parser should be registered in ParserRegistry."""
        ParserRegistry.register(AntigravityParser())
        retrieved = ParserRegistry.get("antigravity")
        assert retrieved is not None
        assert isinstance(retrieved, AntigravityParser)


class TestAntigravityParserConversation:
    """Tests for conversation file parsing."""

    def test_parses_user_and_assistant_messages(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should parse user and assistant messages from conversation file."""
        messages, offset = parser.parse(sample_conversation_file, "machine-001")

        assert len(messages) == 2
        roles = [m.role for m in messages]
        assert roles == ["user", "assistant"]

    def test_extracts_conversation_id(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should extract conversation ID."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        for msg in messages:
            assert msg.conversation_id == "conv-123"

    def test_extracts_workspace_as_project(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should extract workspaceUri as project path."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        for msg in messages:
            assert msg.project == "/home/user/projects/myapp"

    def test_sets_machine_id(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should set machine_id from argument."""
        messages, _ = parser.parse(sample_conversation_file, "my-laptop")

        for msg in messages:
            assert msg.machine_id == "my-laptop"

    def test_parses_iso_timestamp(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should parse ISO 8601 timestamp to Unix seconds."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        assert messages[0].ts > 0
        assert isinstance(messages[0].ts, int)

    def test_extracts_content(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should extract message content."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        assert messages[0].content == "How do I read a file in Python?"
        assert "open() function" in messages[1].content

    def test_sets_raw_path(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should set raw_path to file path."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        for msg in messages:
            assert msg.raw_path == str(sample_conversation_file)

    def test_returns_source_as_antigravity(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should set source to 'antigravity'."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        for msg in messages:
            assert msg.source == "antigravity"


class TestAntigravityParserBrainSession:
    """Tests for brain session file parsing."""

    def test_parses_brain_session_messages(
        self, parser: AntigravityParser, sample_brain_session: Path
    ) -> None:
        """Should parse messages from brain session file."""
        messages, _ = parser.parse(sample_brain_session, "machine-001")

        assert len(messages) == 2

    def test_extracts_session_id(
        self, parser: AntigravityParser, sample_brain_session: Path
    ) -> None:
        """Should extract sessionId as conversation_id."""
        messages, _ = parser.parse(sample_brain_session, "machine-001")

        for msg in messages:
            assert msg.conversation_id == "session-abc123"

    def test_normalizes_model_role_to_assistant(
        self, parser: AntigravityParser, sample_brain_session: Path
    ) -> None:
        """Should normalize 'model' role to 'assistant'."""
        messages, _ = parser.parse(sample_brain_session, "machine-001")

        roles = [m.role for m in messages]
        assert roles == ["user", "assistant"]

    def test_handles_millisecond_timestamps(
        self, parser: AntigravityParser, sample_brain_session: Path
    ) -> None:
        """Should convert millisecond timestamps to seconds."""
        messages, _ = parser.parse(sample_brain_session, "machine-001")

        # 1701432000000 ms = 1701432000 seconds
        assert messages[0].ts == 1701432000


class TestAntigravityParserContentParts:
    """Tests for array content handling."""

    def test_extracts_text_from_parts(
        self, parser: AntigravityParser, sample_with_parts: Path
    ) -> None:
        """Should extract text from content parts array."""
        messages, _ = parser.parse(sample_with_parts, "machine-001")

        assert "Can you help me?" in messages[0].content

    def test_includes_tool_use_info(
        self, parser: AntigravityParser, sample_with_parts: Path
    ) -> None:
        """Should include tool use information."""
        messages, _ = parser.parse(sample_with_parts, "machine-001")

        assert "[Tool: read_file]" in messages[1].content

    def test_includes_tool_results(
        self, parser: AntigravityParser, sample_with_parts: Path
    ) -> None:
        """Should include tool results."""
        messages, _ = parser.parse(sample_with_parts, "machine-001")

        assert "[Tool Result:" in messages[1].content


class TestAntigravityParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_file(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should handle empty file gracefully."""
        file_path = tmp_path / "empty.json"
        file_path.touch()

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset == 0

    def test_handles_invalid_json(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should handle invalid JSON gracefully."""
        file_path = tmp_path / "invalid.json"
        with open(file_path, "w") as f:
            f.write("not valid json{")

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []

    def test_handles_missing_messages(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should handle file without messages array."""
        file_path = tmp_path / "no-messages.json"
        with open(file_path, "w") as f:
            json.dump({"id": "test", "title": "Test"}, f)

        messages, _ = parser.parse(file_path, "machine")

        assert messages == []

    def test_skips_messages_without_content(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should skip messages with no content."""
        file_path = tmp_path / "empty-content.json"
        data = {
            "id": "test",
            "messages": [
                {"role": "user", "content": ""},
                {"role": "user", "content": "Hello"},
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_skips_unknown_roles(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should skip messages with unknown roles."""
        file_path = tmp_path / "unknown-role.json"
        data = {
            "id": "test",
            "messages": [
                {"role": "unknown", "content": "Test"},
                {"role": "user", "content": "Hello"},
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_handles_missing_timestamp(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should handle messages without timestamp."""
        file_path = tmp_path / "no-timestamp.json"
        data = {
            "id": "test",
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].ts == 0

    def test_uses_filename_as_fallback_id(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should use filename stem when id is missing."""
        file_path = tmp_path / "my-conversation.json"
        data = {
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": "2025-12-01T10:00:00Z"},
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert messages[0].conversation_id == "my-conversation"

    def test_returns_file_size_as_offset(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should return file size as offset."""
        _, offset = parser.parse(sample_conversation_file, "machine-001")

        file_size = sample_conversation_file.stat().st_size
        assert offset == file_size

    def test_returns_canonical_message_instances(
        self, parser: AntigravityParser, sample_conversation_file: Path
    ) -> None:
        """Should return CanonicalMessage instances."""
        messages, _ = parser.parse(sample_conversation_file, "machine-001")

        for msg in messages:
            assert isinstance(msg, CanonicalMessage)


class TestAntigravityParserRoleNormalization:
    """Tests for role normalization."""

    @pytest.mark.parametrize(
        "input_role,expected_role",
        [
            ("user", "user"),
            ("human", "user"),
            ("assistant", "assistant"),
            ("model", "assistant"),
            ("ai", "assistant"),
            ("gemini", "assistant"),
            ("system", "system"),
            ("tool", "tool"),
            ("function", "tool"),
        ],
    )
    def test_normalizes_roles(
        self,
        parser: AntigravityParser,
        tmp_path: Path,
        input_role: str,
        expected_role: str,
    ) -> None:
        """Should normalize various role names to canonical roles."""
        file_path = tmp_path / "role-test.json"
        data = {
            "id": "test",
            "messages": [
                {"role": input_role, "content": "Test message", "timestamp": "2025-12-01T10:00:00Z"},
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].role == expected_role


class TestAntigravityParserGenericFormat:
    """Tests for generic/unknown format handling."""

    def test_parses_message_array_at_root(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should parse root-level message array."""
        file_path = tmp_path / "array.json"
        data = [
            {"role": "user", "content": "Hello", "timestamp": "2025-12-01T10:00:00Z"},
            {"role": "assistant", "content": "Hi!", "timestamp": "2025-12-01T10:00:05Z"},
        ]
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 2

    def test_finds_messages_in_nested_array(
        self, parser: AntigravityParser, tmp_path: Path
    ) -> None:
        """Should find messages in nested arrays."""
        file_path = tmp_path / "nested.json"
        data = {
            "metadata": {"version": 1},
            "history": [
                {"role": "user", "content": "Question", "timestamp": "2025-12-01T10:00:00Z"},
                {"role": "assistant", "content": "Answer", "timestamp": "2025-12-01T10:00:05Z"},
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 2


class TestAntigravityParserWithRealFiles:
    """Tests using real Antigravity files (if available)."""

    @pytest.fixture
    def real_antigravity_file(self) -> Path | None:
        """Find a real Antigravity conversation file for testing."""
        antigravity_dir = Path.home() / ".gemini" / "antigravity"
        if not antigravity_dir.exists():
            return None

        # Try conversations directory
        conversations = antigravity_dir / "conversations"
        if conversations.exists():
            files = list(conversations.glob("*.json"))
            if files:
                return files[0]

        # Try brain directory
        brain = antigravity_dir / "brain"
        if brain.exists():
            files = list(brain.glob("*/session.json"))
            if files:
                return files[0]

        return None

    def test_parses_real_file_if_available(
        self, parser: AntigravityParser, real_antigravity_file: Path | None
    ) -> None:
        """Should successfully parse a real Antigravity file."""
        if real_antigravity_file is None:
            pytest.skip("No real Antigravity files found")

        messages, offset = parser.parse(real_antigravity_file, "test-machine")

        # Should parse without errors
        assert isinstance(messages, list)
        assert isinstance(offset, int)
        assert offset > 0

        # If there are messages, they should be valid
        if messages:
            for msg in messages:
                assert msg.source == "antigravity"
                assert msg.machine_id == "test-machine"
                assert msg.role in ("user", "assistant", "system", "tool")
