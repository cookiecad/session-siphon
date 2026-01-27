"""End-to-end integration tests for the full session-siphon pipeline.

Tests the complete flow: collector -> sync -> processor -> indexing
for multiple sources (Claude Code, Codex, VS Code Copilot).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_siphon.collector.daemon import run_collector_cycle
from session_siphon.collector.state import CollectorState
from session_siphon.config import TypesenseConfig
from session_siphon.models import CanonicalMessage, Conversation
from session_siphon.processor.daemon import run_processor_cycle
from session_siphon.processor.indexer import TypesenseIndexer
from session_siphon.processor.state import ProcessorState


class TestEndToEndPipeline:
    """Tests the full collector -> sync -> processor -> index pipeline."""

    @pytest.fixture
    def e2e_paths(self, tmp_path: Path) -> dict[str, Path]:
        """Create all paths needed for E2E test."""
        paths = {
            "sources": tmp_path / "sources",
            "outbox": tmp_path / "outbox",
            "inbox": tmp_path / "inbox",
            "archive": tmp_path / "archive",
            "collector_state": tmp_path / "state" / "collector.db",
            "processor_state": tmp_path / "state" / "processor.db",
        }
        # Create source subdirectories
        paths["claude_source"] = paths["sources"] / ".claude" / "projects" / "myproject"
        paths["codex_source"] = (
            paths["sources"] / ".codex" / "sessions" / "2026" / "01" / "22"
        )
        paths["vscode_source"] = (
            paths["sources"]
            / ".config"
            / "Code"
            / "User"
            / "workspaceStorage"
            / "abc123"
            / "chatSessions"
        )

        for key, path in paths.items():
            if key.endswith("_source"):
                path.mkdir(parents=True)

        return paths

    @pytest.fixture
    def mock_typesense_client(self) -> MagicMock:
        """Create a mock Typesense client that tracks indexed documents."""
        client = MagicMock()

        # Store indexed documents for verification
        indexed_messages: list[dict] = []
        indexed_conversations: list[dict] = []

        def mock_import(docs, options):
            """Track imported documents."""
            if isinstance(docs, list):
                indexed_messages.extend(docs)
            return [{"success": True} for _ in docs]

        def mock_upsert(doc):
            """Track upserted conversation."""
            indexed_conversations.append(doc)
            return {"success": True}

        # Configure mock
        client.collections.__getitem__.return_value.documents.import_ = mock_import
        client.collections.__getitem__.return_value.documents.upsert = mock_upsert

        # Attach storage for verification
        client._indexed_messages = indexed_messages
        client._indexed_conversations = indexed_conversations

        return client

    @pytest.fixture
    def test_indexer(
        self, mock_typesense_client: MagicMock
    ) -> TypesenseIndexer:
        """Create an indexer with mock client."""
        config = TypesenseConfig(
            host="localhost",
            port=8108,
            api_key="test-key",
        )
        with patch(
            "session_siphon.processor.indexer.typesense.Client",
            return_value=mock_typesense_client,
        ):
            indexer = TypesenseIndexer(config)
            indexer._mock_client = mock_typesense_client
            return indexer

    def _create_claude_code_file(self, path: Path, session_id: str, project: str) -> None:
        """Create a Claude Code JSONL file with test messages."""
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Help me write a Python function"},
                "timestamp": "2026-01-22T10:00:00.000Z",
                "uuid": f"{session_id}-msg1",
                "sessionId": session_id,
                "cwd": project,
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": (
                        "Here's a Python function that does what you need:\n\n"
                        "```python\ndef hello():\n    return 'Hello, World!'\n```"
                    ),
                },
                "timestamp": "2026-01-22T10:00:05.000Z",
                "uuid": f"{session_id}-msg2",
                "sessionId": session_id,
                "cwd": project,
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Can you add type hints?"},
                "timestamp": "2026-01-22T10:00:10.000Z",
                "uuid": f"{session_id}-msg3",
                "sessionId": session_id,
                "cwd": project,
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": (
                        "Sure! Here's the function with type hints:\n\n"
                        "```python\ndef hello() -> str:\n    return 'Hello, World!'\n```"
                    ),
                },
                "timestamp": "2026-01-22T10:00:15.000Z",
                "uuid": f"{session_id}-msg4",
                "sessionId": session_id,
                "cwd": project,
            },
        ]

        with open(path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

    def _create_codex_file(self, path: Path, session_id: str, project: str) -> None:
        """Create a Codex JSONL file with test messages."""
        lines = [
            {
                "timestamp": "2026-01-22T11:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "cwd": project,
                    "originator": "codex_vscode",
                },
            },
            {
                "timestamp": "2026-01-22T11:00:01.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "Debug this code for me",
                },
            },
            {
                "timestamp": "2026-01-22T11:00:05.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": (
                        "I'll analyze the code. "
                        "The issue is on line 42 where you have a null reference."
                    ),
                },
            },
            {
                "timestamp": "2026-01-22T11:00:10.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "How do I fix it?",
                },
            },
            {
                "timestamp": "2026-01-22T11:00:15.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "Add a null check before accessing the property.",
                },
            },
        ]

        with open(path, "w") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")

    def _create_vscode_file(self, path: Path, session_id: str, project: str) -> None:
        """Create a VS Code Copilot JSON session file."""
        # Also create workspace.json in parent's parent directory
        workspace_dir = path.parent.parent
        workspace_json = workspace_dir / "workspace.json"
        workspace_json.write_text(json.dumps({"folder": f"file://{project}"}))

        session_data = {
            "version": 3,
            "sessionId": session_id,
            "creationDate": 1737543600000,  # 2026-01-22T12:00:00
            "lastMessageDate": 1737543660000,
            "requests": [
                {
                    "requestId": "req_001",
                    "message": {"text": "Explain this React component"},
                    "timestamp": 1737543600000,
                    "response": [],
                    "result": {
                        "metadata": {
                            "toolCallRounds": [
                                {
                                    "response": (
                                        "This is a functional React component "
                                        "that uses hooks."
                                    ),
                                    "toolCalls": [],
                                }
                            ]
                        }
                    },
                },
                {
                    "requestId": "req_002",
                    "message": {"text": "How can I optimize it?"},
                    "timestamp": 1737543630000,
                    "response": [
                        {
                            "kind": "thinking",
                            "value": "Analyzing for optimization opportunities...",
                        }
                    ],
                    "result": {
                        "metadata": {
                            "toolCallRounds": [
                                {
                                    "response": (
                                        "You can use useMemo to memoize "
                                        "expensive calculations."
                                    ),
                                    "toolCalls": [],
                                }
                            ]
                        }
                    },
                },
            ],
        }

        with open(path, "w") as f:
            json.dump(session_data, f)

    def test_full_pipeline_claude_code(
        self,
        e2e_paths: dict[str, Path],
        test_indexer: TypesenseIndexer,
    ) -> None:
        """Test full pipeline with Claude Code source."""
        # Create source file (filename IS the session ID for Claude Code)
        session_id = "980dc406-0dbf-49b5-86fa-675e1e6e1998"
        claude_file = e2e_paths["claude_source"] / f"{session_id}.jsonl"
        self._create_claude_code_file(
            claude_file,
            session_id=session_id,
            project="/home/user/myproject",
        )

        # Step 1: Collector syncs file to outbox
        with CollectorState(e2e_paths["collector_state"]) as collector_state:
            sources = {"claude_code": [claude_file]}
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                synced = run_collector_cycle(
                    collector_state,
                    "test-machine",
                    e2e_paths["outbox"],
                )

        assert synced == 1, "Should sync one file"

        # Verify file is in outbox
        outbox_files = list(e2e_paths["outbox"].glob("**/*.jsonl"))
        assert len(outbox_files) == 1

        # Step 2: Simulate sync by copying outbox to inbox
        # (In production, rsync would do this)
        inbox_path = e2e_paths["inbox"] / "test-machine" / "claude_code"
        inbox_path.mkdir(parents=True)
        # Keep the same filename (which contains the session_id)
        inbox_file = inbox_path / f"{session_id}.jsonl"

        # Copy content
        outbox_content = outbox_files[0].read_bytes()
        inbox_file.write_bytes(outbox_content)

        # Step 3: Processor parses and indexes
        with ProcessorState(e2e_paths["processor_state"]) as processor_state:
            totals = run_processor_cycle(
                e2e_paths["inbox"],
                e2e_paths["archive"],
                processor_state,
                test_indexer,
                stability_seconds=0,  # Archive immediately for test
            )

        # Verify processing results
        assert totals["files"] == 1
        assert totals["messages"] >= 4  # User + assistant messages
        assert totals["indexed"] >= 4
        assert totals["archived"] == 1

        # Step 4: Verify indexed messages
        mock_client = test_indexer._mock_client
        indexed_messages = mock_client._indexed_messages

        assert len(indexed_messages) >= 4

        # Check message fields
        for msg in indexed_messages:
            assert msg["source"] == "claude_code"
            assert msg["machine_id"] == "test-machine"
            assert msg["conversation_id"] == session_id
            assert msg["role"] in ("user", "assistant")
            assert msg["content"]

        # Verify specific content was indexed
        contents = [m["content"] for m in indexed_messages]
        assert any("Python function" in c for c in contents)
        assert any("type hints" in c for c in contents)

    def test_full_pipeline_codex(
        self,
        e2e_paths: dict[str, Path],
        test_indexer: TypesenseIndexer,
    ) -> None:
        """Test full pipeline with Codex source."""
        # Create source file
        codex_file = e2e_paths["codex_source"] / "rollout-2026-01-22T11-00-00-session123.jsonl"
        e2e_paths["codex_source"].mkdir(parents=True, exist_ok=True)
        self._create_codex_file(
            codex_file,
            session_id="codex-session-001",
            project="/home/user/codex-project",
        )

        # Step 1: Collector
        with CollectorState(e2e_paths["collector_state"]) as collector_state:
            sources = {"codex": [codex_file]}
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                synced = run_collector_cycle(
                    collector_state,
                    "test-machine",
                    e2e_paths["outbox"],
                )

        assert synced == 1

        # Step 2: Sync to inbox
        outbox_files = list(e2e_paths["outbox"].glob("**/*.jsonl"))
        inbox_path = e2e_paths["inbox"] / "test-machine" / "codex"
        inbox_path.mkdir(parents=True)
        inbox_file = inbox_path / codex_file.name
        inbox_file.write_bytes(outbox_files[0].read_bytes())

        # Step 3: Process
        with ProcessorState(e2e_paths["processor_state"]) as processor_state:
            totals = run_processor_cycle(
                e2e_paths["inbox"],
                e2e_paths["archive"],
                processor_state,
                test_indexer,
                stability_seconds=0,
            )

        # Verify
        assert totals["messages"] >= 4  # 4 messages (2 user, 2 assistant)
        assert totals["indexed"] >= 4

        mock_client = test_indexer._mock_client
        indexed_messages = mock_client._indexed_messages

        # Check Codex messages were indexed with correct source
        codex_messages = [m for m in indexed_messages if m["source"] == "codex"]
        assert len(codex_messages) >= 4

        contents = [m["content"] for m in codex_messages]
        assert any("Debug this code" in c for c in contents)
        assert any("null reference" in c for c in contents)

    def test_full_pipeline_vscode_copilot(
        self,
        e2e_paths: dict[str, Path],
        test_indexer: TypesenseIndexer,
    ) -> None:
        """Test full pipeline with VS Code Copilot source."""
        # Create source file
        vscode_file = e2e_paths["vscode_source"] / "vscode-session-001.json"
        e2e_paths["vscode_source"].mkdir(parents=True, exist_ok=True)
        self._create_vscode_file(
            vscode_file,
            session_id="vscode-session-001",
            project="/home/user/react-app",
        )

        # Step 1: Collector
        with CollectorState(e2e_paths["collector_state"]) as collector_state:
            sources = {"vscode_copilot": [vscode_file]}
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                synced = run_collector_cycle(
                    collector_state,
                    "test-machine",
                    e2e_paths["outbox"],
                )

        assert synced == 1

        # Step 2: Sync to inbox
        outbox_files = list(e2e_paths["outbox"].glob("**/*.json"))
        inbox_path = e2e_paths["inbox"] / "test-machine" / "vscode_copilot"
        inbox_path.mkdir(parents=True)

        # Need to recreate directory structure for workspace.json lookup
        workspace_inbox = inbox_path / "workspaceStorage" / "abc123" / "chatSessions"
        workspace_inbox.mkdir(parents=True)
        inbox_file = workspace_inbox / "vscode-session-001.json"
        inbox_file.write_bytes(outbox_files[0].read_bytes())

        # Also copy workspace.json
        workspace_json_dest = workspace_inbox.parent / "workspace.json"
        workspace_json_src = vscode_file.parent.parent / "workspace.json"
        workspace_json_dest.write_bytes(workspace_json_src.read_bytes())

        # Step 3: Process
        with ProcessorState(e2e_paths["processor_state"]) as processor_state:
            totals = run_processor_cycle(
                e2e_paths["inbox"],
                e2e_paths["archive"],
                processor_state,
                test_indexer,
                stability_seconds=0,
            )

        # Verify
        assert totals["messages"] >= 4  # 2 user + 2 assistant

        mock_client = test_indexer._mock_client
        indexed_messages = mock_client._indexed_messages

        vscode_messages = [m for m in indexed_messages if m["source"] == "vscode_copilot"]
        assert len(vscode_messages) >= 4

        contents = [m["content"] for m in vscode_messages]
        assert any("React component" in c for c in contents)
        assert any("useMemo" in c for c in contents)

    def test_incremental_sync_appends_new_messages(
        self,
        e2e_paths: dict[str, Path],
        test_indexer: TypesenseIndexer,
    ) -> None:
        """Test that new messages appear after subsequent collector/processor runs."""
        claude_file = e2e_paths["claude_source"] / "incremental.jsonl"

        # Initial messages
        initial_messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Initial question"},
                "timestamp": "2026-01-22T10:00:00.000Z",
                "uuid": "msg1",
                "sessionId": "session-incr",
                "cwd": "/project",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Initial answer"},
                "timestamp": "2026-01-22T10:00:05.000Z",
                "uuid": "msg2",
                "sessionId": "session-incr",
                "cwd": "/project",
            },
        ]

        with open(claude_file, "w") as f:
            for msg in initial_messages:
                f.write(json.dumps(msg) + "\n")

        # First sync cycle
        with CollectorState(e2e_paths["collector_state"]) as collector_state:
            sources = {"claude_code": [claude_file]}
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                run_collector_cycle(collector_state, "test-machine", e2e_paths["outbox"])

        # Copy to inbox
        outbox_files = list(e2e_paths["outbox"].glob("**/*.jsonl"))
        inbox_path = e2e_paths["inbox"] / "test-machine" / "claude_code"
        inbox_path.mkdir(parents=True)
        inbox_file = inbox_path / "incremental.jsonl"
        inbox_file.write_bytes(outbox_files[0].read_bytes())

        # First process cycle
        with ProcessorState(e2e_paths["processor_state"]) as processor_state:
            totals1 = run_processor_cycle(
                e2e_paths["inbox"],
                e2e_paths["archive"],
                processor_state,
                test_indexer,
                stability_seconds=999999,  # Don't archive yet
            )

        initial_count = totals1["indexed"]
        assert initial_count == 2

        # Append new messages to source file
        new_messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Follow-up question"},
                "timestamp": "2026-01-22T10:00:10.000Z",
                "uuid": "msg3",
                "sessionId": "session-incr",
                "cwd": "/project",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Follow-up answer"},
                "timestamp": "2026-01-22T10:00:15.000Z",
                "uuid": "msg4",
                "sessionId": "session-incr",
                "cwd": "/project",
            },
        ]

        with open(claude_file, "a") as f:
            for msg in new_messages:
                f.write(json.dumps(msg) + "\n")

        # Second sync cycle (incremental)
        with CollectorState(e2e_paths["collector_state"]) as collector_state:
            sources = {"claude_code": [claude_file]}
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                synced = run_collector_cycle(collector_state, "test-machine", e2e_paths["outbox"])

        assert synced == 1  # File was updated

        # Update inbox with new content
        outbox_files = list(e2e_paths["outbox"].glob("**/*.jsonl"))
        inbox_file.write_bytes(outbox_files[0].read_bytes())

        # Second process cycle
        with ProcessorState(e2e_paths["processor_state"]) as processor_state:
            totals2 = run_processor_cycle(
                e2e_paths["inbox"],
                e2e_paths["archive"],
                processor_state,
                test_indexer,
                stability_seconds=999999,
            )

        # Should have indexed the new messages
        assert totals2["indexed"] == 2  # Only the new messages

        # Verify total indexed messages
        mock_client = test_indexer._mock_client
        all_messages = mock_client._indexed_messages
        assert len(all_messages) == 4

        contents = [m["content"] for m in all_messages]
        assert "Initial question" in contents
        assert "Follow-up question" in contents

    def test_multiple_sources_in_single_cycle(
        self,
        e2e_paths: dict[str, Path],
        test_indexer: TypesenseIndexer,
    ) -> None:
        """Test processing multiple sources in a single pipeline run."""
        # Create files for all sources
        claude_file = e2e_paths["claude_source"] / "multi-conv.jsonl"
        self._create_claude_code_file(
            claude_file,
            session_id="multi-claude-001",
            project="/home/user/project1",
        )

        codex_file = e2e_paths["codex_source"] / "rollout-multi-session.jsonl"
        e2e_paths["codex_source"].mkdir(parents=True, exist_ok=True)
        self._create_codex_file(
            codex_file,
            session_id="multi-codex-001",
            project="/home/user/project2",
        )

        # Collector with multiple sources
        with CollectorState(e2e_paths["collector_state"]) as collector_state:
            sources = {
                "claude_code": [claude_file],
                "codex": [codex_file],
            }
            with patch(
                "session_siphon.collector.daemon.discover_all_sources",
                return_value=sources,
            ):
                synced = run_collector_cycle(
                    collector_state,
                    "test-machine",
                    e2e_paths["outbox"],
                )

        assert synced == 2

        # Sync to inbox
        for outbox_file in e2e_paths["outbox"].glob("**/*.jsonl"):
            relative = outbox_file.relative_to(e2e_paths["outbox"])
            inbox_file = e2e_paths["inbox"] / relative
            inbox_file.parent.mkdir(parents=True, exist_ok=True)
            inbox_file.write_bytes(outbox_file.read_bytes())

        # Process
        with ProcessorState(e2e_paths["processor_state"]) as processor_state:
            totals = run_processor_cycle(
                e2e_paths["inbox"],
                e2e_paths["archive"],
                processor_state,
                test_indexer,
                stability_seconds=0,
            )

        assert totals["files"] == 2
        assert totals["messages"] >= 8  # 4 from each source

        # Verify both sources were indexed
        mock_client = test_indexer._mock_client
        indexed_messages = mock_client._indexed_messages

        sources_indexed = set(m["source"] for m in indexed_messages)
        assert "claude_code" in sources_indexed
        assert "codex" in sources_indexed


class TestSearchCapabilities:
    """Tests for search functionality over indexed messages."""

    @pytest.fixture
    def search_mock_client(self) -> MagicMock:
        """Create a mock Typesense client that supports search."""
        client = MagicMock()

        # Store documents
        stored_messages: list[dict] = []

        def mock_import(docs, options):
            if isinstance(docs, list):
                stored_messages.extend(docs)
            return [{"success": True} for _ in docs]

        def mock_search(params):
            """Simple search mock that filters stored messages."""
            query = params.get("q", "*")
            filter_by = params.get("filter_by", "")

            results = []
            for msg in stored_messages:
                # Simple content match
                if query != "*" and query.lower() not in msg.get("content", "").lower():
                    continue

                # Simple filter parsing
                if filter_by:
                    # Parse "source:=claude_code" style filters
                    filters = filter_by.split(" && ")
                    match = True
                    for f in filters:
                        if ":=" in f:
                            key, value = f.split(":=")
                            if msg.get(key) != value:
                                match = False
                                break
                    if not match:
                        continue

                results.append({"document": msg, "highlights": []})

            return {
                "hits": results,
                "found": len(results),
                "page": 1,
            }

        client.collections.__getitem__.return_value.documents.import_ = mock_import
        client.collections.__getitem__.return_value.documents.search = mock_search
        client._stored_messages = stored_messages

        return client

    @pytest.fixture
    def searchable_indexer(self, search_mock_client: MagicMock) -> TypesenseIndexer:
        """Create an indexer that supports search."""
        config = TypesenseConfig(
            host="localhost",
            port=8108,
            api_key="test-key",
        )
        with patch(
            "session_siphon.processor.indexer.typesense.Client",
            return_value=search_mock_client,
        ):
            indexer = TypesenseIndexer(config)
            indexer._mock_client = search_mock_client
            return indexer

    def test_search_messages_by_content(
        self,
        searchable_indexer: TypesenseIndexer,
    ) -> None:
        """Test searching indexed messages by content."""
        # Index test messages
        messages = [
            CanonicalMessage(
                source="claude_code",
                machine_id="test-machine",
                project="/project",
                conversation_id="conv1",
                ts=1737543600,
                role="user",
                content="How do I write a Python decorator?",
                raw_path="/archive/file.jsonl",
            ),
            CanonicalMessage(
                source="claude_code",
                machine_id="test-machine",
                project="/project",
                conversation_id="conv1",
                ts=1737543605,
                role="assistant",
                content="Here's how to write a Python decorator: use @functools.wraps",
                raw_path="/archive/file.jsonl",
            ),
            CanonicalMessage(
                source="codex",
                machine_id="test-machine",
                project="/project2",
                conversation_id="conv2",
                ts=1737543700,
                role="user",
                content="Explain JavaScript promises",
                raw_path="/archive/file2.jsonl",
            ),
        ]

        searchable_indexer.upsert_messages(messages)

        # Search for Python content
        mock_client = searchable_indexer._mock_client
        results = mock_client.collections["messages"].documents.search({
            "q": "Python",
            "query_by": "content",
        })

        assert results["found"] == 2  # User question and assistant answer about Python

        # Verify results contain Python
        for hit in results["hits"]:
            assert "python" in hit["document"]["content"].lower()

    def test_filter_messages_by_source(
        self,
        searchable_indexer: TypesenseIndexer,
    ) -> None:
        """Test filtering indexed messages by source."""
        messages = [
            CanonicalMessage(
                source="claude_code",
                machine_id="m1",
                project="/p1",
                conversation_id="c1",
                ts=1737543600,
                role="user",
                content="Claude Code message",
                raw_path="/f1.jsonl",
            ),
            CanonicalMessage(
                source="codex",
                machine_id="m1",
                project="/p2",
                conversation_id="c2",
                ts=1737543700,
                role="user",
                content="Codex message",
                raw_path="/f2.jsonl",
            ),
            CanonicalMessage(
                source="vscode_copilot",
                machine_id="m1",
                project="/p3",
                conversation_id="c3",
                ts=1737543800,
                role="user",
                content="VS Code Copilot message",
                raw_path="/f3.json",
            ),
        ]

        searchable_indexer.upsert_messages(messages)

        mock_client = searchable_indexer._mock_client

        # Filter by source
        results = mock_client.collections["messages"].documents.search({
            "q": "*",
            "filter_by": "source:=claude_code",
        })

        assert results["found"] == 1
        assert results["hits"][0]["document"]["source"] == "claude_code"

    def test_search_claude_code_sessions(
        self,
        searchable_indexer: TypesenseIndexer,
    ) -> None:
        """Specifically test searching Claude Code sessions."""
        messages = [
            CanonicalMessage(
                source="claude_code",
                machine_id="laptop-01",
                project="/home/user/myproject",
                conversation_id="session-abc123",
                ts=1737543600,
                role="user",
                content="Help me refactor this database query",
                raw_path="/archive/conv.jsonl",
            ),
            CanonicalMessage(
                source="claude_code",
                machine_id="laptop-01",
                project="/home/user/myproject",
                conversation_id="session-abc123",
                ts=1737543605,
                role="assistant",
                content="I'll help optimize the database query using JOINs instead of subqueries",
                raw_path="/archive/conv.jsonl",
            ),
        ]

        searchable_indexer.upsert_messages(messages)

        mock_client = searchable_indexer._mock_client

        # Search for database-related content in Claude Code
        results = mock_client.collections["messages"].documents.search({
            "q": "database",
            "filter_by": "source:=claude_code",
        })

        assert results["found"] == 2

        # Verify all results are from Claude Code
        for hit in results["hits"]:
            assert hit["document"]["source"] == "claude_code"
            assert "database" in hit["document"]["content"].lower()


class TestConversationAggregation:
    """Tests for conversation metadata aggregation and indexing."""

    @pytest.fixture
    def conversation_mock_client(self) -> MagicMock:
        """Create a mock that tracks conversation upserts."""
        client = MagicMock()

        indexed_conversations: list[dict] = []

        def mock_upsert(doc):
            indexed_conversations.append(doc)
            return {"success": True}

        client.collections.__getitem__.return_value.documents.upsert = mock_upsert
        client._indexed_conversations = indexed_conversations

        return client

    @pytest.fixture
    def conv_indexer(
        self, conversation_mock_client: MagicMock
    ) -> TypesenseIndexer:
        """Create indexer for conversation tests."""
        config = TypesenseConfig(host="localhost", port=8108, api_key="key")
        with patch(
            "session_siphon.processor.indexer.typesense.Client",
            return_value=conversation_mock_client,
        ):
            indexer = TypesenseIndexer(config)
            indexer._mock_client = conversation_mock_client
            return indexer

    def test_update_conversation_metadata(
        self,
        conv_indexer: TypesenseIndexer,
    ) -> None:
        """Test updating conversation metadata."""
        conversation = Conversation(
            source="claude_code",
            machine_id="laptop-01",
            project="/home/user/project",
            conversation_id="conv-001",
            first_ts=1737543600,
            last_ts=1737544600,
            message_count=15,
            title="Refactoring database queries",
            preview="Help me refactor this database query",
        )

        result = conv_indexer.update_conversation(conversation)

        assert result is True

        mock_client = conv_indexer._mock_client
        indexed = mock_client._indexed_conversations

        assert len(indexed) == 1
        assert indexed[0]["source"] == "claude_code"
        assert indexed[0]["conversation_id"] == "conv-001"
        assert indexed[0]["message_count"] == 15
        assert indexed[0]["title"] == "Refactoring database queries"


class TestErrorRecovery:
    """Tests for error handling and recovery in the pipeline."""

    def test_continues_on_parse_error(self, tmp_path: Path) -> None:
        """Pipeline should continue processing even if one file fails to parse."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        state_db = tmp_path / "state" / "processor.db"

        # Create one valid and one invalid file
        (inbox / "m1" / "claude_code").mkdir(parents=True)

        valid_file = inbox / "m1" / "claude_code" / "valid.jsonl"
        valid_file.write_bytes(
            b'{"type":"user","message":{"role":"user","content":"valid"},"timestamp":"2026-01-22T10:00:00Z","uuid":"abc"}\n'
        )

        invalid_file = inbox / "m1" / "claude_code" / "invalid.jsonl"
        invalid_file.write_bytes(b"not valid json at all\n")

        with ProcessorState(state_db) as state:
            totals = run_processor_cycle(
                inbox,
                archive,
                state,
                indexer=None,
                stability_seconds=0,
            )

        # Should process both files, one succeeds
        assert totals["files"] == 2
        assert totals["messages"] >= 1  # At least the valid message

    def test_handles_typesense_connection_failure(self, tmp_path: Path) -> None:
        """Pipeline should handle Typesense connection failures gracefully."""
        inbox = tmp_path / "inbox"
        archive = tmp_path / "archive"
        state_db = tmp_path / "state" / "processor.db"

        (inbox / "m1" / "claude_code").mkdir(parents=True)
        valid_file = inbox / "m1" / "claude_code" / "test.jsonl"
        valid_file.write_bytes(
            b'{"type":"user","message":{"role":"user","content":"test"},"timestamp":"2026-01-22T10:00:00Z","uuid":"abc"}\n'
        )

        # Create indexer that raises connection error
        mock_client = MagicMock()
        mock_client.collections.__getitem__.return_value.documents.import_.side_effect = Exception(
            "Connection refused"
        )

        config = TypesenseConfig(host="localhost", port=8108, api_key="key")
        with patch(
            "session_siphon.processor.indexer.typesense.Client",
            return_value=mock_client,
        ):
            indexer = TypesenseIndexer(config)

        with ProcessorState(state_db) as state:
            totals = run_processor_cycle(
                inbox,
                archive,
                state,
                indexer,
                stability_seconds=0,
            )

        # Should still process and archive, just fail indexing
        assert totals["files"] == 1
        assert totals["messages"] >= 1
        assert totals["indexed"] == 0  # Failed to index
        assert totals["archived"] == 1  # Still archived
