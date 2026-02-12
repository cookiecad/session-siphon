"""Parser for VS Code Copilot chat session transcripts.

VS Code Copilot stores chat sessions as JSON files at:
    ~/.config/Code/User/workspaceStorage/<hash>/chatSessions/<session-id>.json (Linux)
    ~/Library/Application Support/Code/User/workspaceStorage/<hash>/*.json (macOS)

Each file is a JSON object with:
- sessionId: UUID session identifier
- creationDate: Timestamp in milliseconds
- requests: Array of request/response pairs
- Each request contains:
  - message.text: User's message text
  - timestamp: Timestamp in milliseconds
  - response: Array of response items (thinking, toolInvocationSerialized, etc.)
  - result.metadata.toolCallRounds: Contains assistant response text

The workspace path is extracted from workspace.json in the parent directory.
"""

import json
from pathlib import Path

from session_siphon.processor.git_utils import get_git_repo_info
from session_siphon.processor.parsers.base import CanonicalMessage, Parser


class VSCodeCopilotParser(Parser):
    """Parser for VS Code Copilot JSON chat session files.

    This parser performs full re-parse on each call since the JSON format
    doesn't support incremental reading. Deduplication is handled by
    content hash.
    """

    source_name = "vscode_copilot"

    def parse(
        self,
        path: Path,
        machine_id: str,
        from_offset: int = 0,
    ) -> tuple[list[CanonicalMessage], int]:
        """Parse a VS Code Copilot JSON file into canonical messages.

        Since JSON files must be parsed in full, from_offset is ignored.
        Content hashing is used for deduplication instead.

        Args:
            path: Path to the JSON session file
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

        # Extract session ID
        session_id = data.get("sessionId", path.stem)

        # Extract workspace/project path
        project = self._extract_workspace(path)

        # Extract git repository info
        git_repo = get_git_repo_info(project)

        # Process each request in the session
        requests = data.get("requests", [])
        for request in requests:
            # Extract user message
            user_msg = self._extract_user_message(
                request, session_id, machine_id, project, str(path), git_repo
            )
            if user_msg:
                messages.append(user_msg)

            # Extract assistant response(s)
            assistant_msgs = self._extract_assistant_messages(
                request, session_id, machine_id, project, str(path), git_repo
            )
            messages.extend(assistant_msgs)

        return messages, file_size

    def _extract_workspace(self, session_path: Path) -> str:
        """Extract workspace path from workspace.json in parent directory.

        Args:
            session_path: Path to the chat session JSON file

        Returns:
            Workspace folder path, or empty string if not found
        """
        # Navigate from chatSessions/<id>.json to workspace.json
        # Path structure: .../workspaceStorage/<hash>/chatSessions/<session>.json
        workspace_json = session_path.parent.parent / "workspace.json"

        if not workspace_json.exists():
            # Fallback to the hash directory name so at least we group by workspace
            # structure is workspaceStorage/<hash>/chatSessions/<session>.json
            # session_path.parent is chatSessions
            # session_path.parent.parent is <hash>
            return session_path.parent.parent.name

        try:
            with open(workspace_json) as f:
                workspace_data = json.load(f)

            folder = workspace_data.get("folder", "")
            # folder is typically "file:///path/to/workspace"
            if folder.startswith("file://"):
                return folder[7:]  # Strip "file://" prefix
            return folder
        except (OSError, json.JSONDecodeError):
            return ""

    def _extract_user_message(
        self,
        request: dict,
        session_id: str,
        machine_id: str,
        project: str,
        raw_path: str,
        git_repo: str | None,
    ) -> CanonicalMessage | None:
        """Extract user message from a request.

        Args:
            request: The request object from the session
            session_id: Session identifier
            machine_id: Machine identifier
            project: Project/workspace path
            raw_path: Path to source file
            git_repo: Git repository identifier

        Returns:
            CanonicalMessage for user, or None if no valid message
        """
        message = request.get("message", {})
        text = message.get("text", "")

        if not text:
            return None

        # Timestamp is in milliseconds
        timestamp_ms = request.get("timestamp", 0)
        ts = timestamp_ms // 1000 if timestamp_ms else 0

        return CanonicalMessage(
            source=self.source_name,
            machine_id=machine_id,
            project=project,
            conversation_id=session_id,
            ts=ts,
            role="user",
            content=text,
            raw_path=raw_path,
            raw_offset=None,
            git_repo=git_repo,
        )

    def _extract_assistant_messages(
        self,
        request: dict,
        session_id: str,
        machine_id: str,
        project: str,
        raw_path: str,
        git_repo: str | None,
    ) -> list[CanonicalMessage]:
        """Extract assistant messages from a request's response.

        Args:
            request: The request object from the session
            session_id: Session identifier
            machine_id: Machine identifier
            project: Project/workspace path
            raw_path: Path to source file
            git_repo: Git repository identifier

        Returns:
            List of CanonicalMessage instances for assistant responses
        """
        messages: list[CanonicalMessage] = []

        # Timestamp is in milliseconds
        timestamp_ms = request.get("timestamp", 0)
        ts = timestamp_ms // 1000 if timestamp_ms else 0

        # Collect all assistant content from different sources
        content_parts: list[str] = []

        # 1. Extract thinking content from response array
        for resp_item in request.get("response", []):
            kind = resp_item.get("kind", "")
            if kind == "thinking":
                thinking_text = resp_item.get("value", "")
                if thinking_text:
                    content_parts.append(f"[Thinking]\n{thinking_text}")

        # 2. Extract response text from toolCallRounds in result.metadata
        result = request.get("result", {})
        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        tool_call_rounds = metadata.get("toolCallRounds", [])

        for round_data in tool_call_rounds:
            # Response text from the round
            response_text = round_data.get("response", "")
            if response_text:
                content_parts.append(response_text)

            # Thinking text embedded in rounds
            thinking = round_data.get("thinking", {})
            if isinstance(thinking, dict):
                thinking_text = thinking.get("text", "")
                if thinking_text and thinking_text not in str(content_parts):
                    content_parts.append(f"[Thinking]\n{thinking_text}")

        # Combine all content
        combined_content = "\n\n".join(content_parts)

        if combined_content:
            messages.append(
                CanonicalMessage(
                    source=self.source_name,
                    machine_id=machine_id,
                    project=project,
                    conversation_id=session_id,
                    ts=ts,
                    role="assistant",
                    content=combined_content,
                    git_repo=git_repo,
                    raw_path=raw_path,
                    raw_offset=None,
                )
            )

        return messages
