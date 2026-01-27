"""Parser for Google Antigravity conversation transcripts.

Google Antigravity stores conversations in:
    ~/.gemini/antigravity/conversations/*.json (conversation history)
    ~/.gemini/antigravity/brain/<session-id>/session.json (brain session data)

Antigravity is Google's agentic IDE released in November 2025, using Gemini 3
models for AI-assisted development.

Conversation files typically contain:
- id: Conversation/session identifier
- title: User-defined objective title
- createdAt/modifiedAt: ISO 8601 timestamps
- messages: Array of message objects
  - role: "user" or "assistant" (or "model" for Gemini-style)
  - content: Message text
  - timestamp: ISO 8601 timestamp

Brain session files contain:
- sessionId: Session identifier
- workspaceUri: Project workspace path
- messages: Conversation history
- context: Accumulated context/memory
"""

import json
from datetime import datetime
from pathlib import Path

from session_siphon.processor.parsers.base import CanonicalMessage, Parser


class AntigravityParser(Parser):
    """Parser for Google Antigravity JSON conversation files.

    This parser handles both conversation files and brain session files
    from Google Antigravity. It performs full re-parse on each call since
    the JSON format doesn't support incremental reading.
    """

    source_name = "antigravity"

    def parse(
        self,
        path: Path,
        machine_id: str,
        from_offset: int = 0,
    ) -> tuple[list[CanonicalMessage], int]:
        """Parse an Antigravity JSON file into canonical messages.

        Since JSON files must be parsed in full, from_offset is ignored.
        Content hashing is used for deduplication instead.

        Args:
            path: Path to the JSON file
            machine_id: Machine identifier
            from_offset: Ignored for JSON files (full reparse required)

        Returns:
            Tuple of (list of messages, file size as new offset)
        """
        messages: list[CanonicalMessage] = []

        try:
            with open(path, "rb") as f:
                content = f.read()
                file_size = len(content)
        except OSError:
            return [], 0

        try:
            data = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return [], 0

        # Handle different Antigravity file formats
        if self._is_conversation_file(data):
            messages = self._parse_conversation(data, path, machine_id)
        elif self._is_brain_session(data):
            messages = self._parse_brain_session(data, path, machine_id)
        else:
            # Try to parse as generic message array
            messages = self._parse_generic(data, path, machine_id)

        return messages, file_size

    def _is_conversation_file(self, data: dict) -> bool:
        """Check if data is a conversation file format."""
        return (
            isinstance(data, dict)
            and "messages" in data
            and ("id" in data or "conversationId" in data)
        )

    def _is_brain_session(self, data: dict) -> bool:
        """Check if data is a brain session file format."""
        return (
            isinstance(data, dict)
            and "sessionId" in data
            and ("workspaceUri" in data or "workspace" in data)
        )

    def _parse_conversation(
        self,
        data: dict,
        path: Path,
        machine_id: str,
    ) -> list[CanonicalMessage]:
        """Parse a conversation file format.

        Args:
            data: Parsed JSON data
            path: Path to the source file
            machine_id: Machine identifier

        Returns:
            List of CanonicalMessage instances
        """
        messages: list[CanonicalMessage] = []

        # Extract conversation ID
        conversation_id = data.get("id") or data.get("conversationId") or path.stem

        # Extract project/workspace
        project = data.get("workspaceUri", "")
        if project.startswith("file://"):
            project = project[7:]

        # Process messages
        for msg_data in data.get("messages", []):
            msg = self._extract_message(
                msg_data,
                conversation_id,
                machine_id,
                project,
                str(path),
            )
            if msg:
                messages.append(msg)

        return messages

    def _parse_brain_session(
        self,
        data: dict,
        path: Path,
        machine_id: str,
    ) -> list[CanonicalMessage]:
        """Parse a brain session file format.

        Args:
            data: Parsed JSON data
            path: Path to the source file
            machine_id: Machine identifier

        Returns:
            List of CanonicalMessage instances
        """
        messages: list[CanonicalMessage] = []

        # Extract session ID
        session_id = data.get("sessionId") or path.parent.name

        # Extract workspace
        project = data.get("workspaceUri") or data.get("workspace", "")
        if isinstance(project, dict):
            project = project.get("uri", "")
        if project.startswith("file://"):
            project = project[7:]

        # Process messages from various possible locations
        msg_arrays = [
            data.get("messages", []),
            data.get("history", []),
            data.get("conversation", []),
        ]

        for msg_array in msg_arrays:
            if not isinstance(msg_array, list):
                continue
            for msg_data in msg_array:
                msg = self._extract_message(
                    msg_data,
                    session_id,
                    machine_id,
                    project,
                    str(path),
                )
                if msg:
                    messages.append(msg)

        return messages

    def _parse_generic(
        self,
        data: dict | list,
        path: Path,
        machine_id: str,
    ) -> list[CanonicalMessage]:
        """Parse generic JSON that might contain messages.

        Args:
            data: Parsed JSON data (dict or list)
            path: Path to the source file
            machine_id: Machine identifier

        Returns:
            List of CanonicalMessage instances
        """
        messages: list[CanonicalMessage] = []
        session_id = path.stem

        # Extract project from path structure
        # Path might be: ~/.gemini/antigravity/brain/<session-id>/session.json
        project = self._extract_project_from_path(path)

        # If data is a list, treat it as messages
        if isinstance(data, list):
            for msg_data in data:
                if isinstance(msg_data, dict):
                    msg = self._extract_message(
                        msg_data,
                        session_id,
                        machine_id,
                        project,
                        str(path),
                    )
                    if msg:
                        messages.append(msg)
        elif isinstance(data, dict):
            # Look for any array that might contain messages
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0:
                    if isinstance(value[0], dict) and self._looks_like_message(value[0]):
                        for msg_data in value:
                            msg = self._extract_message(
                                msg_data,
                                session_id,
                                machine_id,
                                project,
                                str(path),
                            )
                            if msg:
                                messages.append(msg)

        return messages

    def _looks_like_message(self, data: dict) -> bool:
        """Check if a dict looks like a message object."""
        message_keys = {"role", "content", "text", "message", "type"}
        return bool(set(data.keys()) & message_keys)

    def _extract_message(
        self,
        msg_data: dict,
        conversation_id: str,
        machine_id: str,
        project: str,
        raw_path: str,
    ) -> CanonicalMessage | None:
        """Extract a canonical message from message data.

        Args:
            msg_data: Message dictionary
            conversation_id: Conversation/session ID
            machine_id: Machine identifier
            project: Project path
            raw_path: Path to source file

        Returns:
            CanonicalMessage or None if invalid
        """
        if not isinstance(msg_data, dict):
            return None

        # Extract role - handle various formats
        role = msg_data.get("role") or msg_data.get("type") or msg_data.get("author")
        role = self._normalize_role(role)
        if not role:
            return None

        # Extract content - handle various formats
        content = self._extract_content(msg_data)
        if not content:
            return None

        # Extract timestamp
        ts = self._extract_timestamp(msg_data)

        return CanonicalMessage(
            source=self.source_name,
            machine_id=machine_id,
            project=project,
            conversation_id=conversation_id,
            ts=ts,
            role=role,
            content=content,
            raw_path=raw_path,
            raw_offset=None,
        )

    def _normalize_role(self, role: str | None) -> str | None:
        """Normalize role to canonical format.

        Args:
            role: Raw role string

        Returns:
            Canonical role or None if invalid
        """
        if not role:
            return None

        role = role.lower()

        role_mapping = {
            "user": "user",
            "human": "user",
            "assistant": "assistant",
            "model": "assistant",
            "ai": "assistant",
            "gemini": "assistant",
            "system": "system",
            "tool": "tool",
            "function": "tool",
        }

        return role_mapping.get(role)

    def _extract_content(self, msg_data: dict) -> str:
        """Extract text content from message data.

        Args:
            msg_data: Message dictionary

        Returns:
            Extracted content string
        """
        # Try various content field names
        content = (
            msg_data.get("content")
            or msg_data.get("text")
            or msg_data.get("message")
            or msg_data.get("value")
        )

        if content is None:
            return ""

        # Handle string content
        if isinstance(content, str):
            return content

        # Handle array content (parts)
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    # Handle structured parts
                    part_text = part.get("text") or part.get("content") or ""
                    if part_text:
                        parts.append(part_text)

                    # Handle tool calls
                    if part.get("type") == "tool_use" or "toolCall" in part:
                        tool_name = part.get("name") or part.get("toolCall", {}).get("name", "tool")
                        parts.append(f"[Tool: {tool_name}]")

                    # Handle tool results
                    if part.get("type") == "tool_result" or "toolResult" in part:
                        result = part.get("content") or part.get("toolResult", {}).get("output", "")
                        if result:
                            preview = result[:200] + "..." if len(str(result)) > 200 else str(result)
                            parts.append(f"[Tool Result: {preview}]")

            return "\n".join(parts)

        return ""

    def _extract_timestamp(self, msg_data: dict) -> int:
        """Extract timestamp from message data.

        Args:
            msg_data: Message dictionary

        Returns:
            Unix timestamp in seconds
        """
        # Try various timestamp field names
        ts_value = (
            msg_data.get("timestamp")
            or msg_data.get("createdAt")
            or msg_data.get("created_at")
            or msg_data.get("time")
        )

        if ts_value is None:
            return 0

        # Handle numeric timestamps
        if isinstance(ts_value, (int, float)):
            # If it looks like milliseconds, convert to seconds
            if ts_value > 1e12:
                return int(ts_value / 1000)
            return int(ts_value)

        # Handle ISO 8601 strings
        if isinstance(ts_value, str):
            return self._parse_iso_timestamp(ts_value)

        return 0

    def _parse_iso_timestamp(self, timestamp_str: str) -> int:
        """Parse ISO 8601 timestamp to Unix timestamp.

        Args:
            timestamp_str: ISO 8601 timestamp string

        Returns:
            Unix timestamp in seconds
        """
        if not timestamp_str:
            return 0

        try:
            # Handle Z suffix
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(timestamp_str)
            return int(dt.timestamp())
        except (ValueError, AttributeError):
            return 0

    def _extract_project_from_path(self, path: Path) -> str:
        """Extract project identifier from file path.

        Args:
            path: Path to the file

        Returns:
            Project identifier or empty string
        """
        # Path might be: ~/.gemini/antigravity/brain/<session-id>/session.json
        # Or: ~/.gemini/antigravity/conversations/<id>.json
        parts = path.parts

        try:
            if "brain" in parts:
                brain_idx = parts.index("brain")
                if brain_idx + 1 < len(parts):
                    return parts[brain_idx + 1]  # Return session ID as project
        except ValueError:
            pass

        return ""
