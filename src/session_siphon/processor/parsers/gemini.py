"""Parser for Gemini CLI conversation transcripts.

Gemini CLI stores conversations as JSON files at:
    ~/.gemini/tmp/<project_hash>/chats/session-*.json

Each file is a JSON object with:
- sessionId: UUID session identifier
- projectHash: Hash of the project path
- startTime: ISO 8601 timestamp
- lastUpdated: ISO 8601 timestamp
- messages: Array of message objects
  - id: Message UUID
  - timestamp: ISO 8601 timestamp
  - type: "user", "gemini", or "info"
  - content: String content
  - toolCalls: Optional array of tool call objects (for gemini messages)
  - thoughts: Optional array of thinking process objects
"""

import json
from datetime import datetime
from pathlib import Path

from session_siphon.processor.parsers.base import CanonicalMessage, Parser


class GeminiParser(Parser):
    """Parser for Gemini CLI JSON session files."""

    source_name = "gemini_cli"

    def parse(
        self,
        path: Path,
        machine_id: str,
        from_offset: int = 0,
    ) -> tuple[list[CanonicalMessage], int]:
        """Parse a Gemini CLI JSON file into canonical messages.

        Note: Gemini CLI uses JSON (not JSONL), so incremental parsing is not
        supported. The from_offset parameter is ignored and the entire file is
        reparsed on each call. The returned offset is always the file size.

        Args:
            path: Path to the JSON file
            machine_id: Machine identifier
            from_offset: Ignored (full reparse always performed)

        Returns:
            Tuple of (list of messages, file size as offset)
        """
        messages: list[CanonicalMessage] = []

        # Extract project hash from path structure
        # Path format: ~/.gemini/tmp/<project_hash>/chats/session-*.json
        project = self._extract_project_from_path(path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Return empty list for unreadable files
            return [], path.stat().st_size if path.exists() else 0

        session_id = data.get("sessionId", path.stem)

        for msg_data in data.get("messages", []):
            msg_type = msg_data.get("type")

            # Map Gemini message types to canonical roles
            role = self._map_role(msg_type)
            if role is None:
                # Skip non-conversation messages (like "info")
                continue

            # Extract content
            content = self._extract_content(msg_data)
            if not content:
                continue

            # Parse timestamp
            timestamp_str = msg_data.get("timestamp")
            ts = self._parse_timestamp(timestamp_str)

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
                    raw_offset=None,  # JSON files don't have meaningful offsets
                )
            )

        # Return file size as offset (signals we've processed the whole file)
        file_size = path.stat().st_size if path.exists() else 0
        return messages, file_size

    def _extract_project_from_path(self, path: Path) -> str:
        """Extract project identifier from file path.

        The path format is: ~/.gemini/tmp/<project_hash>/chats/session-*.json
        We extract the project_hash which serves as the project identifier.

        Args:
            path: Path to the session file

        Returns:
            Project hash string, or empty string if not extractable
        """
        parts = path.parts
        # Look for "chats" directory and get the parent (project_hash)
        try:
            chats_idx = parts.index("chats")
            if chats_idx > 0:
                return parts[chats_idx - 1]
        except ValueError:
            pass
        return ""

    def _map_role(self, msg_type: str | None) -> str | None:
        """Map Gemini message type to canonical role.

        Args:
            msg_type: Gemini message type ("user", "gemini", "info", etc.)

        Returns:
            Canonical role string, or None if the message should be skipped
        """
        if msg_type == "user":
            return "user"
        elif msg_type == "gemini":
            return "assistant"
        else:
            # Skip "info" and other non-conversation message types
            return None

    def _extract_content(self, msg_data: dict) -> str:
        """Extract text content from message data.

        Combines the main content with tool call information if present.

        Args:
            msg_data: Message dictionary

        Returns:
            Extracted text content as a string
        """
        parts: list[str] = []

        # Main content
        content = msg_data.get("content", "")
        if content:
            parts.append(content)

        # Include tool calls as descriptive text
        tool_calls = msg_data.get("toolCalls", [])
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "unknown")
            display_name = tool_call.get("displayName", tool_name)
            parts.append(f"[Tool: {display_name}]")

            # Include brief result info if available
            results = tool_call.get("result", [])
            for result in results:
                func_response = result.get("functionResponse", {})
                response = func_response.get("response", {})
                output = response.get("output", "")
                if output:
                    # Truncate long outputs
                    truncated = output[:200] + "..." if len(output) > 200 else output
                    parts.append(f"[Tool Result: {truncated}]")

        return "\n".join(parts)

    def _parse_timestamp(self, timestamp_str: str | None) -> int:
        """Parse ISO 8601 timestamp to Unix timestamp.

        Args:
            timestamp_str: ISO 8601 timestamp string (e.g., "2025-12-28T04:21:49.812Z")

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
