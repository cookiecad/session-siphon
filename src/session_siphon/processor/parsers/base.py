"""Base parser interface and registry."""

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from session_siphon.models import CanonicalMessage

# Re-export CanonicalMessage for convenient access from parsers
__all__ = ["CanonicalMessage", "Parser", "ParserRegistry", "generate_message_id", "content_hash"]


def content_hash(content: str) -> str:
    """Compute SHA256 hash of content for deduplication.

    Args:
        content: The message content to hash

    Returns:
        First 16 characters of the hex-encoded SHA256 hash
    """
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def generate_message_id(
    source: str,
    machine_id: str,
    conversation_id: str,
    ts: int,
    content: str,
) -> str:
    """Generate a stable unique ID for a message.

    The ID format is: {source}:{machine_id}:{conversation_id}:{ts}:{content_hash}

    This creates deterministic IDs that can be used for deduplication and
    stable references across systems.

    Args:
        source: Source identifier (e.g., 'claude_code', 'codex')
        machine_id: Machine identifier
        conversation_id: Conversation identifier
        ts: Unix timestamp (seconds)
        content: Message content

    Returns:
        Stable unique message ID string
    """
    hash_part = content_hash(content)
    return f"{source}:{machine_id}:{conversation_id}:{ts}:{hash_part}"


class Parser(ABC):
    """Base class for transcript parsers.

    Subclasses must set the `source_name` class attribute and implement
    the `parse()` method to convert source-specific formats into
    CanonicalMessage instances.
    """

    source_name: str

    @abstractmethod
    def parse(
        self,
        path: Path,
        machine_id: str,
        from_offset: int = 0,
    ) -> tuple[list[CanonicalMessage], int]:
        """Parse a transcript file into canonical messages.

        Args:
            path: Path to the transcript file
            machine_id: Machine identifier
            from_offset: Byte offset to start parsing from (for JSONL)

        Returns:
            Tuple of (list of messages, new offset for next parse)
        """


class ParserRegistry:
    """Registry of parsers by source name."""

    _parsers: dict[str, Parser] = {}

    @classmethod
    def register(cls, parser: Parser) -> None:
        """Register a parser."""
        cls._parsers[parser.source_name] = parser

    @classmethod
    def get(cls, source_name: str) -> Parser | None:
        """Get parser by source name."""
        return cls._parsers.get(source_name)

    @classmethod
    def all_sources(cls) -> list[str]:
        """List all registered source names."""
        return list(cls._parsers.keys())
