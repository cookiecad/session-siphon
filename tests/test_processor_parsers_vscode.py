"""Tests for VS Code Copilot parser."""

import json
from pathlib import Path

import pytest

from session_siphon.processor.parsers import ParserRegistry, VSCodeCopilotParser
from session_siphon.processor.parsers.base import CanonicalMessage


@pytest.fixture
def parser() -> VSCodeCopilotParser:
    """Create a fresh parser instance."""
    return VSCodeCopilotParser()


@pytest.fixture
def sample_session_file(tmp_path: Path) -> Path:
    """Create a sample VS Code Copilot session file with workspace.json."""
    # Create workspace structure
    workspace_hash = "abc123def456"
    workspace_dir = tmp_path / "workspaceStorage" / workspace_hash
    chat_sessions_dir = workspace_dir / "chatSessions"
    chat_sessions_dir.mkdir(parents=True)

    # Create workspace.json
    workspace_json = workspace_dir / "workspace.json"
    workspace_json.write_text(json.dumps({"folder": "file:///home/user/myproject"}))

    # Create session file
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    file_path = chat_sessions_dir / f"{session_id}.json"

    session_data = {
        "version": 3,
        "sessionId": session_id,
        "creationDate": 1700000000000,
        "lastMessageDate": 1700000060000,
        "requests": [
            {
                "requestId": "request_001",
                "message": {
                    "text": "How do I create a Python class?",
                    "parts": [
                        {"kind": "text", "text": "How do I create a Python class?"}
                    ],
                },
                "timestamp": 1700000000000,
                "response": [],
                "result": {
                    "timings": {"totalElapsed": 2000},
                    "metadata": {
                        "toolCallRounds": [
                            {
                                "response": (
                                    "Here's how to create a Python class:\n\n"
                                    "```python\nclass MyClass:\n"
                                    "    def __init__(self):\n        pass\n```"
                                ),
                                "toolCalls": [],
                            }
                        ]
                    },
                },
            },
            {
                "requestId": "request_002",
                "message": {
                    "text": "Can you add a method to it?",
                    "parts": [{"kind": "text", "text": "Can you add a method to it?"}],
                },
                "timestamp": 1700000030000,
                "response": [
                    {
                        "kind": "thinking",
                        "value": "The user wants to add a method to the Python class.",
                    }
                ],
                "result": {
                    "timings": {"totalElapsed": 1500},
                    "metadata": {
                        "toolCallRounds": [
                            {
                                "response": (
                                    "Sure! Here's the class with a method:\n\n"
                                    "```python\nclass MyClass:\n"
                                    "    def __init__(self):\n        pass\n\n"
                                    "    def my_method(self):\n"
                                    "        return 'Hello!'\n```"
                                ),
                                "toolCalls": [],
                            }
                        ]
                    },
                },
            },
        ],
    }

    file_path.write_text(json.dumps(session_data))
    return file_path


class TestVSCodeCopilotParserBasics:
    """Tests for basic parser functionality."""

    def test_source_name(self, parser: VSCodeCopilotParser) -> None:
        """Parser should have correct source name."""
        assert parser.source_name == "vscode_copilot"

    def test_registered_in_registry(self) -> None:
        """Parser should be registered in ParserRegistry."""
        ParserRegistry.register(VSCodeCopilotParser())
        retrieved = ParserRegistry.get("vscode_copilot")
        assert retrieved is not None
        assert isinstance(retrieved, VSCodeCopilotParser)


class TestVSCodeCopilotParserParse:
    """Tests for parse method."""

    def test_parses_user_and_assistant_messages(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should parse user and assistant messages from JSON."""
        messages, offset = parser.parse(sample_session_file, "machine-001")

        # Should have 4 messages: 2 user + 2 assistant
        assert len(messages) == 4

        # Check roles alternate
        roles = [m.role for m in messages]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_extracts_session_id(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should extract sessionId as conversation_id."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.conversation_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_extracts_workspace_from_workspace_json(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should extract project from workspace.json folder field."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.project == "/home/user/myproject"

    def test_sets_machine_id(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should set machine_id from argument."""
        messages, _ = parser.parse(sample_session_file, "my-laptop")

        for msg in messages:
            assert msg.machine_id == "my-laptop"

    def test_parses_timestamp_from_milliseconds(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should parse timestamp from milliseconds to seconds."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        # First message timestamp: 1700000000000ms = 1700000000s
        assert messages[0].ts == 1700000000
        assert isinstance(messages[0].ts, int)

    def test_extracts_user_message_text(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should extract user message text."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        user_messages = [m for m in messages if m.role == "user"]
        assert user_messages[0].content == "How do I create a Python class?"
        assert user_messages[1].content == "Can you add a method to it?"

    def test_extracts_assistant_response_from_toolcallrounds(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should extract assistant response from toolCallRounds."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        assistant_messages = [m for m in messages if m.role == "assistant"]
        assert "class MyClass:" in assistant_messages[0].content
        assert "__init__" in assistant_messages[0].content

    def test_includes_thinking_in_assistant_response(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should include thinking content in assistant response."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        assistant_messages = [m for m in messages if m.role == "assistant"]
        # Second assistant message should have thinking
        assert "[Thinking]" in assistant_messages[1].content
        assert "user wants to add a method" in assistant_messages[1].content

    def test_sets_raw_path(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should set raw_path to file path."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.raw_path == str(sample_session_file)

    def test_returns_source_as_vscode_copilot(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should set source to 'vscode_copilot'."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert msg.source == "vscode_copilot"

    def test_returns_file_size_as_offset(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should return file size as the new offset."""
        messages, offset = parser.parse(sample_session_file, "machine-001")

        file_size = sample_session_file.stat().st_size
        assert offset == file_size


class TestVSCodeCopilotParserFullReparse:
    """Tests for full reparse behavior (dedup by content hash)."""

    def test_ignores_from_offset_parameter(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should ignore from_offset and always parse full file."""
        # Parse with offset 0
        messages1, _ = parser.parse(sample_session_file, "machine-001", from_offset=0)

        # Parse with non-zero offset (should still get all messages)
        messages2, _ = parser.parse(
            sample_session_file, "machine-001", from_offset=1000
        )

        assert len(messages1) == len(messages2)
        assert [m.content for m in messages1] == [m.content for m in messages2]

    def test_content_hash_provides_dedup(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Content hash should be stable for deduplication."""
        messages1, _ = parser.parse(sample_session_file, "machine-001")
        messages2, _ = parser.parse(sample_session_file, "machine-001")

        # Same content should produce same hash
        for m1, m2 in zip(messages1, messages2, strict=False):
            assert m1.content_hash == m2.content_hash
            assert m1.id == m2.id


class TestVSCodeCopilotParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_file(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle empty file gracefully."""
        file_path = tmp_path / "empty.json"
        file_path.write_text("")

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset == 0

    def test_handles_invalid_json(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle invalid JSON gracefully."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("not valid json {{{")

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset == 0

    def test_handles_missing_file(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle missing file gracefully."""
        file_path = tmp_path / "nonexistent.json"

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset == 0

    def test_handles_empty_requests_array(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle session with empty requests array."""
        file_path = tmp_path / "empty-requests.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "creationDate": 1700000000000,
                    "requests": [],
                }
            )
        )

        messages, offset = parser.parse(file_path, "machine")

        assert messages == []
        assert offset > 0  # File has content

    def test_handles_missing_workspace_json(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should use hash as fallback project when workspace.json missing."""
        # Create proper directory structure without workspace.json
        workspace_hash = "abc123hash"
        workspace_dir = tmp_path / "workspaceStorage" / workspace_hash
        chat_sessions_dir = workspace_dir / "chatSessions"
        chat_sessions_dir.mkdir(parents=True)

        # Create session file without workspace.json
        file_path = chat_sessions_dir / "session.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "creationDate": 1700000000000,
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Hello"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        # Falls back to using the workspace hash as project identifier
        assert messages[0].project == workspace_hash

    def test_handles_request_without_message_text(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should skip requests without message text."""
        file_path = tmp_path / "no-text.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {},  # No text
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 0

    def test_handles_request_without_response(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle requests with no assistant response."""
        file_path = tmp_path / "no-response.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Hello"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        # Should have user message but no assistant message
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_handles_missing_timestamp(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle requests without timestamp."""
        file_path = tmp_path / "no-timestamp.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Hello"},
                            # No timestamp
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].ts == 0

    def test_handles_workspace_json_without_folder(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle workspace.json without folder field."""
        # Create directory structure
        workspace_dir = tmp_path / "workspaceStorage" / "hash123"
        chat_dir = workspace_dir / "chatSessions"
        chat_dir.mkdir(parents=True)

        # Create workspace.json without folder
        workspace_json = workspace_dir / "workspace.json"
        workspace_json.write_text(json.dumps({"some": "other_data"}))

        # Create session file
        file_path = chat_dir / "session.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Hello"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].project == ""

    def test_handles_folder_without_file_prefix(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should handle folder field without file:// prefix."""
        # Create directory structure
        workspace_dir = tmp_path / "workspaceStorage" / "hash123"
        chat_dir = workspace_dir / "chatSessions"
        chat_dir.mkdir(parents=True)

        # Create workspace.json with plain path
        workspace_json = workspace_dir / "workspace.json"
        workspace_json.write_text(json.dumps({"folder": "/plain/path/project"}))

        # Create session file
        file_path = chat_dir / "session.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Hello"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assert len(messages) == 1
        assert messages[0].project == "/plain/path/project"

    def test_returns_canonical_message_instances(
        self, parser: VSCodeCopilotParser, sample_session_file: Path
    ) -> None:
        """Should return CanonicalMessage instances."""
        messages, _ = parser.parse(sample_session_file, "machine-001")

        for msg in messages:
            assert isinstance(msg, CanonicalMessage)

    def test_uses_filename_stem_if_no_session_id(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should use filename stem if sessionId is missing."""
        file_path = tmp_path / "my-session-id.json"
        file_path.write_text(
            json.dumps(
                {
                    # No sessionId
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Hello"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {},
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assert messages[0].conversation_id == "my-session-id"


class TestVSCodeCopilotParserMultipleRounds:
    """Tests for sessions with multiple tool call rounds."""

    def test_combines_multiple_response_rounds(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should combine responses from multiple toolCallRounds."""
        file_path = tmp_path / "multi-round.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "Help me refactor this code"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {
                                "metadata": {
                                    "toolCallRounds": [
                                        {
                                            "response": "First, let me analyze the code.",
                                            "toolCalls": [],
                                        },
                                        {
                                            "response": "Here's the refactored version.",
                                            "toolCalls": [],
                                        },
                                    ]
                                }
                            },
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert "First, let me analyze" in assistant_msgs[0].content
        assert "refactored version" in assistant_msgs[0].content

    def test_includes_thinking_from_rounds(
        self, parser: VSCodeCopilotParser, tmp_path: Path
    ) -> None:
        """Should include thinking content embedded in rounds."""
        file_path = tmp_path / "thinking-rounds.json"
        file_path.write_text(
            json.dumps(
                {
                    "sessionId": "test-session",
                    "requests": [
                        {
                            "requestId": "req1",
                            "message": {"text": "What's wrong with this code?"},
                            "timestamp": 1700000000000,
                            "response": [],
                            "result": {
                                "metadata": {
                                    "toolCallRounds": [
                                        {
                                            "response": "I found the issue.",
                                            "thinking": {
                                                "text": "Analyzing the code structure...",
                                                "id": "think-123",
                                            },
                                            "toolCalls": [],
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                }
            )
        )

        messages, _ = parser.parse(file_path, "machine")

        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert "[Thinking]" in assistant_msgs[0].content
        assert "Analyzing the code structure" in assistant_msgs[0].content


class TestVSCodeCopilotParserWithRealFiles:
    """Tests using real VS Code Copilot files (if available)."""

    @pytest.fixture
    def real_vscode_copilot_file(self) -> Path | None:
        """Find a real VS Code Copilot session file for testing."""
        import platform

        system = platform.system()

        if system == "Linux":
            base_paths = [
                Path.home() / ".config" / "Code" / "User" / "workspaceStorage",
                Path.home()
                / ".config"
                / "Code - Insiders"
                / "User"
                / "workspaceStorage",
            ]
        elif system == "Darwin":
            base_paths = [
                Path.home()
                / "Library"
                / "Application Support"
                / "Code"
                / "User"
                / "workspaceStorage",
            ]
        else:
            return None

        for base_path in base_paths:
            if not base_path.exists():
                continue
            files = list(base_path.glob("*/chatSessions/*.json"))
            if files:
                # Find a file with actual requests
                for f in files:
                    try:
                        data = json.loads(f.read_text())
                        if data.get("requests"):
                            return f
                    except (json.JSONDecodeError, OSError):
                        continue
        return None

    def test_parses_real_file_if_available(
        self, parser: VSCodeCopilotParser, real_vscode_copilot_file: Path | None
    ) -> None:
        """Should successfully parse a real VS Code Copilot file."""
        if real_vscode_copilot_file is None:
            pytest.skip("No real VS Code Copilot files found")

        messages, offset = parser.parse(real_vscode_copilot_file, "test-machine")

        # Should parse without errors
        assert isinstance(messages, list)
        assert isinstance(offset, int)
        assert offset > 0

        # If there are messages, they should be valid
        if messages:
            for msg in messages:
                assert msg.source == "vscode_copilot"
                assert msg.machine_id == "test-machine"
                assert msg.role in ("user", "assistant")
