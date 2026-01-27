"""Parser for Claude Code conversation transcripts.

Claude Code stores conversations as JSONL files at:
    ~/.claude/projects/<encoded-project-path>/<session-id>.jsonl

Each line is a JSON object with:
- type: "user", "assistant", or "queue-operation"
- message.role: "user" or "assistant"
- message.content: string or array of content blocks
- timestamp: ISO 8601 timestamp
- sessionId: UUID session identifier
- cwd: Working directory (project path)
"""

import json
from datetime import datetime
from pathlib import Path

from session_siphon.processor.parsers.base import CanonicalMessage, Parser


class ClaudeCodeParser(Parser):
    """Parser for Claude Code JSONL transcript files."""

    source_name = "claude_code"

    def parse(
        self,
        path: Path,
        machine_id: str,
        from_offset: int = 0,
    ) -> tuple[list[CanonicalMessage], int]:
        """Parse a Claude Code JSONL file into canonical messages.

        Args:
            path: Path to the JSONL file
            machine_id: Machine identifier
            from_offset: Byte offset to start parsing from

        Returns:
            Tuple of (list of messages, new offset for next parse)
        """
        messages: list[CanonicalMessage] = []

        # Extract session_id from filename (e.g., "980dc406-0dbf-49b5-86fa-675e1e6e1998.jsonl")
        session_id = path.stem

        with open(path, "rb") as f:
            # Seek to the starting offset for incremental parsing
            f.seek(from_offset)

            for line in f:
                line_offset = f.tell() - len(line)  # Offset of this line
                line_text = line.decode("utf-8").strip()

                if not line_text:
                    continue

                try:
                    entry = json.loads(line_text)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

                # Only process user and assistant messages
                entry_type = entry.get("type")
                if entry_type not in ("user", "assistant"):
                    continue

                message = entry.get("message", {})
                role = message.get("role")
                if not role:
                    continue

                # Extract content
                content = self._extract_content(message.get("content"))
                if not content:
                    continue

                # Parse timestamp
                timestamp_str = entry.get("timestamp")
                ts = self._parse_timestamp(timestamp_str)

                # Extract project from cwd field
                project = entry.get("cwd", "")

                messages.append(
                    CanonicalMessage(
                        source=self.source_name,
                        machine_id=machine_id,
                        project=project,
                        conversation_id=session_id,
                        ts=ts,
                        role=role,
                        content=content,
                        raw_path=str(path),
                        raw_offset=line_offset,
                    )
                )

            # Return current file position as the new offset
            new_offset = f.tell()

        return messages, new_offset

    def _extract_content(self, content: str | list | None) -> str:
        """Extract text content from message content field.

        Args:
            content: Either a string or array of content blocks

        Returns:
            Extracted text content as a string
        """
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif block_type == "tool_use":
                        # Include tool use as descriptive text
                        tool_name = block.get("name", "unknown")
                        text_parts.append(f"[Tool: {tool_name}]")
                    elif block_type == "tool_result":
                        # Include tool result content if present
                        result_content = block.get("content", "")
                        if result_content:
                            text_parts.append(f"[Tool Result: {result_content[:200]}...]")
                elif isinstance(block, str):
                    text_parts.append(block)
            return "\n".join(text_parts)

        return ""

    def _parse_timestamp(self, timestamp_str: str | None) -> int:
        """Parse ISO 8601 timestamp to Unix timestamp.

        Args:
            timestamp_str: ISO 8601 timestamp string (e.g., "2026-01-26T00:38:34.590Z")

        Returns:
            Unix timestamp in seconds
        """
        if not timestamp_str:
            return 0

        try:
            # Handle ISO 8601 with optional microseconds and Z suffix
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(timestamp_str)
            return int(dt.timestamp())
        except (ValueError, AttributeError):
            return 0
