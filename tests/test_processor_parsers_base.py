"""Tests for the parser base module."""

import hashlib
from pathlib import Path

import pytest

from session_siphon.processor.parsers.base import (
    CanonicalMessage,
    Parser,
    ParserRegistry,
    content_hash,
    generate_message_id,
)


class TestContentHash:
    """Tests for content_hash function."""

    def test_returns_sha256_truncated_to_16_chars(self) -> None:
        """content_hash should return first 16 chars of SHA256 hex digest."""
        content = "Hello, world!"
        expected = hashlib.sha256(content.encode()).hexdigest()[:16]
        assert content_hash(content) == expected

    def test_consistent_for_same_content(self) -> None:
        """content_hash should return same hash for same content."""
        content = "Test message content"
        assert content_hash(content) == content_hash(content)

    def test_different_for_different_content(self) -> None:
        """content_hash should return different hash for different content."""
        assert content_hash("message1") != content_hash("message2")

    def test_handles_empty_string(self) -> None:
        """content_hash should handle empty string."""
        expected = hashlib.sha256(b"").hexdigest()[:16]
        assert content_hash("") == expected

    def test_handles_unicode(self) -> None:
        """content_hash should handle unicode content."""
        content = "Hello 世界 🌍"
        expected = hashlib.sha256(content.encode()).hexdigest()[:16]
        assert content_hash(content) == expected


class TestGenerateMessageId:
    """Tests for generate_message_id function."""

    def test_format_is_correct(self) -> None:
        """generate_message_id should return correctly formatted ID."""
        msg_id = generate_message_id(
            source="claude_code",
            machine_id="laptop-001",
            conversation_id="conv-123",
            ts=1706200000,
            content="Hello, assistant!",
        )
        parts = msg_id.split(":")
        assert len(parts) == 5
        assert parts[0] == "claude_code"
        assert parts[1] == "laptop-001"
        assert parts[2] == "conv-123"
        assert parts[3] == "1706200000"
        assert len(parts[4]) == 16  # content hash

    def test_stable_for_same_inputs(self) -> None:
        """generate_message_id should return same ID for same inputs."""
        kwargs = {
            "source": "codex",
            "machine_id": "server-01",
            "conversation_id": "session-456",
            "ts": 1706300000,
            "content": "Write a function",
        }
        assert generate_message_id(**kwargs) == generate_message_id(**kwargs)

    def test_different_for_different_content(self) -> None:
        """generate_message_id should differ when content differs."""
        base_kwargs = {
            "source": "claude_code",
            "machine_id": "machine",
            "conversation_id": "conv",
            "ts": 1706400000,
        }
        id1 = generate_message_id(**base_kwargs, content="content1")
        id2 = generate_message_id(**base_kwargs, content="content2")
        assert id1 != id2

    def test_different_for_different_timestamp(self) -> None:
        """generate_message_id should differ when timestamp differs."""
        base_kwargs = {
            "source": "claude_code",
            "machine_id": "machine",
            "conversation_id": "conv",
            "content": "same content",
        }
        id1 = generate_message_id(**base_kwargs, ts=1000)
        id2 = generate_message_id(**base_kwargs, ts=2000)
        assert id1 != id2

    def test_uses_content_hash(self) -> None:
        """generate_message_id should use content_hash for hash portion."""
        content = "Test message"
        msg_id = generate_message_id(
            source="source",
            machine_id="machine",
            conversation_id="conv",
            ts=1000,
            content=content,
        )
        expected_hash = content_hash(content)
        assert msg_id.endswith(expected_hash)


class TestCanonicalMessageReexport:
    """Tests for CanonicalMessage re-export from base module."""

    def test_canonical_message_importable_from_base(self) -> None:
        """CanonicalMessage should be importable from base module."""
        assert CanonicalMessage is not None

    def test_canonical_message_can_be_instantiated(self) -> None:
        """CanonicalMessage should be instantiatable."""
        msg = CanonicalMessage(
            source="claude_code",
            machine_id="laptop",
            project="/home/user/project",
            conversation_id="conv-123",
            ts=1706500000,
            role="user",
            content="Hello!",
            raw_path="/archive/file.jsonl",
        )
        assert msg.source == "claude_code"
        assert msg.role == "user"

    def test_canonical_message_content_hash_uses_sha256(self) -> None:
        """CanonicalMessage.content_hash should use SHA256."""
        content = "Test content for hash"
        msg = CanonicalMessage(
            source="test",
            machine_id="machine",
            project="/project",
            conversation_id="conv",
            ts=1000,
            role="user",
            content=content,
            raw_path="/path",
        )
        expected = hashlib.sha256(content.encode()).hexdigest()[:16]
        assert msg.content_hash == expected

    def test_canonical_message_id_matches_generate_message_id(self) -> None:
        """CanonicalMessage.id should match generate_message_id output."""
        msg = CanonicalMessage(
            source="claude_code",
            machine_id="laptop",
            project="/project",
            conversation_id="conv-123",
            ts=1706600000,
            role="assistant",
            content="Here is the answer",
            raw_path="/archive/file.jsonl",
        )
        expected_id = generate_message_id(
            source=msg.source,
            machine_id=msg.machine_id,
            conversation_id=msg.conversation_id,
            ts=msg.ts,
            content=msg.content,
        )
        assert msg.id == expected_id


class TestParserAbstractClass:
    """Tests for Parser abstract base class."""

    def test_parser_is_abstract(self) -> None:
        """Parser should not be directly instantiable."""
        with pytest.raises(TypeError):
            Parser()  # type: ignore[abstract]

    def test_parser_requires_parse_method(self) -> None:
        """Concrete Parser subclass must implement parse method."""

        class IncompleteParser(Parser):
            source_name = "incomplete"

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_concrete_parser_can_be_instantiated(self) -> None:
        """Properly implemented Parser subclass should work."""

        class ConcreteParser(Parser):
            source_name = "test_source"

            def parse(
                self,
                path: Path,
                machine_id: str,
                from_offset: int = 0,
            ) -> tuple[list[CanonicalMessage], int]:
                return [], 0

        parser = ConcreteParser()
        assert parser.source_name == "test_source"


class TestParserRegistry:
    """Tests for ParserRegistry."""

    def setup_method(self) -> None:
        """Clear registry before each test."""
        ParserRegistry._parsers = {}

    def test_register_and_get_parser(self) -> None:
        """Should register and retrieve a parser."""

        class TestParser(Parser):
            source_name = "test_parser"

            def parse(
                self,
                path: Path,
                machine_id: str,
                from_offset: int = 0,
            ) -> tuple[list[CanonicalMessage], int]:
                return [], 0

        parser = TestParser()
        ParserRegistry.register(parser)

        retrieved = ParserRegistry.get("test_parser")
        assert retrieved is parser

    def test_get_returns_none_for_unknown_source(self) -> None:
        """get should return None for unregistered source."""
        assert ParserRegistry.get("nonexistent") is None

    def test_all_sources_lists_registered_sources(self) -> None:
        """all_sources should list all registered source names."""

        class ParserA(Parser):
            source_name = "source_a"

            def parse(
                self,
                path: Path,
                machine_id: str,
                from_offset: int = 0,
            ) -> tuple[list[CanonicalMessage], int]:
                return [], 0

        class ParserB(Parser):
            source_name = "source_b"

            def parse(
                self,
                path: Path,
                machine_id: str,
                from_offset: int = 0,
            ) -> tuple[list[CanonicalMessage], int]:
                return [], 0

        ParserRegistry.register(ParserA())
        ParserRegistry.register(ParserB())

        sources = ParserRegistry.all_sources()
        assert "source_a" in sources
        assert "source_b" in sources
        assert len(sources) == 2
