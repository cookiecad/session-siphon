"""Parser for OpenCode (SST) conversation transcripts.

OpenCode stores conversations in a hierarchical structure at:
    ~/.local/share/opencode/storage/

Directory layout:
    session/<projectHash>/ses_<id>.json    - Session metadata
    message/<sessionID>/msg_<id>.json      - Message metadata
    part/<messageID>/prt_<id>.json         - Content parts

Session file contains:
- id: Session identifier (e.g., "ses_419ccecd4ffe0HogypcacqYZnm")
- projectID: Project hash
- directory: Working directory path
- title: Display title
- time.created: Creation timestamp (milliseconds)
- time.updated: Last modification timestamp

Message file contains:
- id: Message identifier (e.g., "msg_be6331331001IbdWP1cz6buxkc")
- sessionID: Parent session reference
- role: "user" or "assistant"
- time.created: Creation timestamp (milliseconds)
- time.completed: Completion timestamp

Part file contains various types:
- TextPart: {type: "text", text: string}
- ReasoningPart: {type: "reasoning", text: string}
- ToolPart: {type: "tool", tool: string, state: {input, output, status}}
- FilePart: {type: "file", url: string, mime: string, filename: string}
- StepFinish: {type: "step-finish", ...}

This parser reads session files and reconstructs conversations
from the associated message and part files.
"""

import json
from pathlib import Path

from session_siphon.processor.parsers.base import CanonicalMessage, Parser


class OpenCodeParser(Parser):
    """Parser for OpenCode JSON session files.

    OpenCode uses a hierarchical file structure with separate files for
    sessions, messages, and parts. This parser reconstructs conversations
    by reading the session file and then loading associated messages and parts.
    """

    source_name = "opencode"

    def parse(
        self,
        path: Path,
        machine_id: str,
        from_offset: int = 0,
    ) -> tuple[list[CanonicalMessage], int]:
        """Parse an OpenCode session into canonical messages.

        This parser expects to receive a session file path. It will then
        discover and parse all associated messages and parts.

        Since OpenCode uses JSON files (not JSONL), incremental parsing is
        not supported. The from_offset parameter is ignored.

        Args:
            path: Path to the session JSON file (ses_*.json)
            machine_id: Machine identifier
            from_offset: Ignored for JSON files (full reparse required)

        Returns:
            Tuple of (list of messages, file size as new offset)
        """
        messages: list[CanonicalMessage] = []

        # Read session file
        try:
            with open(path, "r", encoding="utf-8") as f:
                session_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return [], path.stat().st_size if path.exists() else 0

        session_id = session_data.get("id", path.stem)
        project_dir = session_data.get("directory", "")

        # Find storage root
        # Path structure: .../storage/session/<projectHash>/ses_*.json
        storage_root = self._find_storage_root(path)

        if storage_root:
            # Find message directory: .../storage/message/<sessionID>/
            message_dir = storage_root / "message" / session_id

            if message_dir.exists():
                # Load all messages for this session
                message_files = sorted(message_dir.glob("msg_*.json"))

                for msg_file in message_files:
                    msg = self._parse_message_file(
                        msg_file,
                        storage_root,
                        session_id,
                        machine_id,
                        project_dir,
                        str(path),
                    )
                    if msg:
                        messages.append(msg)

        # Sort messages by timestamp
        messages.sort(key=lambda m: m.ts)

        # Return file size as offset
        file_size = path.stat().st_size if path.exists() else 0
        return messages, file_size

    def _find_storage_root(self, session_path: Path) -> Path | None:
        """Find the storage root directory from a session file path.

        Args:
            session_path: Path to the session JSON file

        Returns:
            Path to storage root (.../opencode/storage/), or None if not found
        """
        # Navigate from session file to storage root
        # session_path: .../storage/session/<projectHash>/ses_*.json
        # storage_root: .../storage/

        try:
            parts = session_path.parts
            # Find "session" in path and go to parent storage dir
            if "session" in parts:
                session_idx = parts.index("session")
                if session_idx > 0:
                    return Path(*parts[:session_idx])
        except (ValueError, IndexError):
            pass

        # Fallback: try parent directories
        # session_path.parent = <projectHash>
        # session_path.parent.parent = session
        # session_path.parent.parent.parent = storage
        return session_path.parent.parent.parent

    def _parse_message_file(
        self,
        msg_path: Path,
        storage_root: Path,
        session_id: str,
        machine_id: str,
        project_dir: str,
        raw_path: str,
    ) -> CanonicalMessage | None:
        """Parse a message file and its parts into a CanonicalMessage.

        Args:
            msg_path: Path to the message JSON file
            storage_root: Root storage directory
            session_id: Session identifier
            machine_id: Machine identifier
            project_dir: Project directory path
            raw_path: Path to the original session file

        Returns:
            CanonicalMessage or None if parsing failed
        """
        try:
            with open(msg_path, "r", encoding="utf-8") as f:
                msg_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        role = msg_data.get("role")
        if role not in ("user", "assistant"):
            return None

        message_id = msg_data.get("id", msg_path.stem)

        # Extract timestamp (milliseconds to seconds)
        time_data = msg_data.get("time", {})
        ts_ms = time_data.get("created", 0)
        ts = ts_ms // 1000 if ts_ms else 0

        # Load parts for this message
        content = self._load_message_parts(storage_root, message_id)

        if not content:
            return None

        return CanonicalMessage(
            source=self.source_name,
            machine_id=machine_id,
            project=project_dir,
            conversation_id=session_id,
            ts=ts,
            role=role,
            content=content,
            raw_path=raw_path,
            raw_offset=None,
        )

    def _load_message_parts(self, storage_root: Path, message_id: str) -> str:
        """Load and combine parts for a message.

        Args:
            storage_root: Root storage directory
            message_id: Message identifier

        Returns:
            Combined content from all parts
        """
        # Parts directory: .../storage/part/<messageID>/
        parts_dir = storage_root / "part" / message_id

        if not parts_dir.exists():
            return ""

        content_parts: list[str] = []

        # Load all parts
        part_files = sorted(parts_dir.glob("prt_*.json"))
        for part_file in part_files:
            part_content = self._parse_part_file(part_file)
            if part_content:
                content_parts.append(part_content)

        return "\n\n".join(content_parts)

    def _parse_part_file(self, part_path: Path) -> str:
        """Parse a part file and extract its content.

        Args:
            part_path: Path to the part JSON file

        Returns:
            Extracted content string
        """
        try:
            with open(part_path, "r", encoding="utf-8") as f:
                part_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return ""

        part_type = part_data.get("type", "")

        if part_type == "text":
            return part_data.get("text", "")

        elif part_type == "reasoning":
            text = part_data.get("text", "")
            if text:
                return f"[Reasoning]\n{text}"
            return ""

        elif part_type == "tool":
            return self._format_tool_part(part_data)

        elif part_type == "file":
            filename = part_data.get("filename", "unknown")
            mime = part_data.get("mime", "")
            return f"[File: {filename} ({mime})]"

        elif part_type == "patch":
            # File modification patch
            return self._format_patch_part(part_data)

        elif part_type == "snapshot":
            # Compacted conversation state
            return "[Snapshot: conversation state compacted]"

        elif part_type == "compaction":
            return "[Context compacted]"

        elif part_type == "step-finish":
            # End of a step - no visible content
            return ""

        return ""

    def _format_tool_part(self, part_data: dict) -> str:
        """Format a tool part into readable text.

        Args:
            part_data: Tool part data

        Returns:
            Formatted tool call string
        """
        tool_name = part_data.get("tool", "unknown")
        state = part_data.get("state", {})

        parts: list[str] = [f"[Tool: {tool_name}]"]

        # Include tool input if available
        tool_input = state.get("input")
        if tool_input:
            if isinstance(tool_input, str):
                input_preview = tool_input[:200] + "..." if len(tool_input) > 200 else tool_input
                parts.append(f"Input: {input_preview}")
            elif isinstance(tool_input, dict):
                input_str = json.dumps(tool_input, indent=2)
                input_preview = input_str[:200] + "..." if len(input_str) > 200 else input_str
                parts.append(f"Input: {input_preview}")

        # Include tool output if available
        tool_output = state.get("output")
        if tool_output:
            if isinstance(tool_output, str):
                output_preview = tool_output[:200] + "..." if len(tool_output) > 200 else tool_output
                parts.append(f"Output: {output_preview}")
            elif isinstance(tool_output, dict):
                output_str = json.dumps(tool_output, indent=2)
                output_preview = output_str[:200] + "..." if len(output_str) > 200 else output_str
                parts.append(f"Output: {output_preview}")

        status = state.get("status", "")
        if status:
            parts.append(f"Status: {status}")

        return "\n".join(parts)

    def _format_patch_part(self, part_data: dict) -> str:
        """Format a patch part into readable text.

        Args:
            part_data: Patch part data

        Returns:
            Formatted patch string
        """
        path = part_data.get("path", "unknown")
        operation = part_data.get("operation", "modify")

        parts: list[str] = [f"[Patch: {operation} {path}]"]

        # Include diff preview if available
        diff = part_data.get("diff", "")
        if diff:
            diff_preview = diff[:500] + "..." if len(diff) > 500 else diff
            parts.append(diff_preview)

        return "\n".join(parts)
