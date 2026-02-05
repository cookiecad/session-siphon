"""Canonical data models."""

from dataclasses import dataclass
import hashlib


@dataclass
class CanonicalMessage:
    """A normalized message from any AI conversation source."""

    source: str  # claude_code, codex, vscode_copilot, gemini_cli
    machine_id: str
    project: str  # Project/workspace directory path
    conversation_id: str
    ts: int  # Unix timestamp (seconds)
    role: str  # user, assistant, tool, system
    content: str
    raw_path: str  # Path to source file in archive
    git_repo: str | None = None  # Git repository identifier (owner/repo)
    raw_offset: int | None = None  # Byte offset for JSONL files

    @property
    def content_hash(self) -> str:
        """SHA256 hash of content for deduplication."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    @property
    def id(self) -> str:
        """Stable unique ID for this message."""
        return f"{self.source}:{self.machine_id}:{self.conversation_id}:{self.ts}:{self.content_hash}"

    def to_typesense_doc(self) -> dict:
        """Convert to Typesense document format."""
        return {
            "id": self.id,
            "source": self.source,
            "machine_id": self.machine_id,
            "project": self.project,
            "conversation_id": self.conversation_id,
            "ts": self.ts,
            "role": self.role,
            "content": self.content,
            "content_hash": self.content_hash,
            "raw_path": self.raw_path,
            "git_repo": self.git_repo,
            "raw_offset": self.raw_offset or 0,
        }


@dataclass
class Conversation:
    """Aggregated conversation metadata."""

    source: str
    machine_id: str
    project: str
    conversation_id: str
    first_ts: int
    last_ts: int
    message_count: int
    title: str
    preview: str
    git_repo: str | None = None

    @property
    def id(self) -> str:
        """Stable unique ID for this conversation."""
        return f"{self.source}:{self.machine_id}:{self.conversation_id}"

    def to_typesense_doc(self) -> dict:
        """Convert to Typesense document format."""
        return {
            "id": self.id,
            "source": self.source,
            "machine_id": self.machine_id,
            "project": self.project,
            "conversation_id": self.conversation_id,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "message_count": self.message_count,
            "title": self.title,
            "git_repo": self.git_repo,
            "preview": self.preview,
        }
