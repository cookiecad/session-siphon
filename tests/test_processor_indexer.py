"""Tests for Typesense indexer."""

from unittest.mock import MagicMock, patch

import pytest
from typesense.exceptions import ObjectNotFound

from session_siphon.config import TypesenseConfig
from session_siphon.models import CanonicalMessage, Conversation
from session_siphon.processor.indexer import (
    CONVERSATIONS_SCHEMA,
    MESSAGES_SCHEMA,
    TypesenseIndexer,
)


@pytest.fixture
def config() -> TypesenseConfig:
    """Provide a test TypesenseConfig."""
    return TypesenseConfig(
        host="localhost",
        port=8108,
        protocol="http",
        api_key="test-api-key",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """Provide a mock Typesense client."""
    return MagicMock()


@pytest.fixture
def indexer(config: TypesenseConfig, mock_client: MagicMock) -> TypesenseIndexer:
    """Provide a TypesenseIndexer with mocked client."""
    with patch("session_siphon.processor.indexer.typesense.Client", return_value=mock_client):
        return TypesenseIndexer(config)


class TestTypesenseIndexerInit:
    """Tests for TypesenseIndexer initialization."""

    def test_creates_client_with_config(self, config: TypesenseConfig) -> None:
        """TypesenseIndexer should create client with correct config."""
        with patch("session_siphon.processor.indexer.typesense.Client") as mock_client_class:
            TypesenseIndexer(config)

            mock_client_class.assert_called_once_with({
                "nodes": [{
                    "host": "localhost",
                    "port": "8108",
                    "protocol": "http",
                }],
                "api_key": "test-api-key",
                "connection_timeout_seconds": 5,
            })

    def test_client_property(self, indexer: TypesenseIndexer, mock_client: MagicMock) -> None:
        """TypesenseIndexer should expose client via property."""
        assert indexer.client is mock_client


class TestEnsureCollections:
    """Tests for ensure_collections method."""

    def test_creates_messages_collection_when_missing(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """ensure_collections should create messages collection if not found."""
        mock_client.collections.__getitem__.return_value.retrieve.side_effect = [
            ObjectNotFound("messages"),  # messages collection
            {"name": "conversations"},  # conversations exists
        ]

        indexer.ensure_collections()

        mock_client.collections.create.assert_any_call(MESSAGES_SCHEMA)

    def test_creates_conversations_collection_when_missing(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """ensure_collections should create conversations collection if not found."""
        mock_client.collections.__getitem__.return_value.retrieve.side_effect = [
            {"name": "messages"},  # messages exists
            ObjectNotFound("conversations"),  # conversations missing
        ]

        indexer.ensure_collections()

        mock_client.collections.create.assert_any_call(CONVERSATIONS_SCHEMA)

    def test_creates_both_collections_when_missing(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """ensure_collections should create both collections if neither exist."""
        mock_client.collections.__getitem__.return_value.retrieve.side_effect = ObjectNotFound(
            "collection"
        )

        indexer.ensure_collections()

        assert mock_client.collections.create.call_count == 2

    def test_no_create_when_collections_exist(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """ensure_collections should not create if collections exist."""
        mock_client.collections.__getitem__.return_value.retrieve.return_value = {"name": "test"}

        indexer.ensure_collections()

        mock_client.collections.create.assert_not_called()


class TestUpsertMessages:
    """Tests for upsert_messages method."""

    def test_upserts_single_message(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """upsert_messages should index a single message."""
        message = CanonicalMessage(
            source="claude_code",
            machine_id="machine1",
            project="/home/user/project",
            conversation_id="conv123",
            ts=1706000000,
            role="user",
            content="Hello world",
            raw_path="/archive/file.jsonl",
            raw_offset=0,
        )

        mock_client.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True}
        ]

        result = indexer.upsert_messages([message])

        assert result == {"success": 1, "failed": 0}
        mock_client.collections["messages"].documents.import_.assert_called_once()

    def test_upserts_multiple_messages(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """upsert_messages should index multiple messages."""
        messages = [
            CanonicalMessage(
                source="claude_code",
                machine_id="machine1",
                project="/project",
                conversation_id="conv1",
                ts=1706000000 + i,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                raw_path="/archive/file.jsonl",
                raw_offset=i * 100,
            )
            for i in range(5)
        ]

        mock_client.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True} for _ in range(5)
        ]

        result = indexer.upsert_messages(messages)

        assert result == {"success": 5, "failed": 0}

    def test_reports_failed_messages(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """upsert_messages should report failed imports."""
        message = CanonicalMessage(
            source="claude_code",
            machine_id="machine1",
            project="/project",
            conversation_id="conv1",
            ts=1706000000,
            role="user",
            content="Test",
            raw_path="/archive/file.jsonl",
        )

        mock_client.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": False, "error": "Some error"}
        ]

        result = indexer.upsert_messages([message])

        assert result == {"success": 0, "failed": 1}

    def test_handles_mixed_success_failure(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """upsert_messages should correctly count mixed results."""
        messages = [
            CanonicalMessage(
                source="claude_code",
                machine_id="m1",
                project="/p",
                conversation_id="c1",
                ts=1706000000 + i,
                role="user",
                content=f"Msg {i}",
                raw_path="/f.jsonl",
            )
            for i in range(4)
        ]

        mock_client.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True},
            {"success": False, "error": "err"},
            {"success": True},
            {"success": False, "error": "err"},
        ]

        result = indexer.upsert_messages(messages)

        assert result == {"success": 2, "failed": 2}

    def test_empty_messages_list(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """upsert_messages should handle empty list."""
        result = indexer.upsert_messages([])

        assert result == {"success": 0, "failed": 0}
        mock_client.collections.__getitem__.return_value.documents.import_.assert_not_called()

    def test_uses_upsert_action(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """upsert_messages should use upsert action for import."""
        message = CanonicalMessage(
            source="claude_code",
            machine_id="m1",
            project="/p",
            conversation_id="c1",
            ts=1706000000,
            role="user",
            content="Test",
            raw_path="/f.jsonl",
        )

        mock_client.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True}
        ]

        indexer.upsert_messages([message])

        call_args = mock_client.collections["messages"].documents.import_.call_args
        assert call_args[0][1] == {"action": "upsert"}


class TestUpdateConversation:
    """Tests for update_conversation method."""

    def test_updates_conversation(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """update_conversation should upsert conversation document."""
        conversation = Conversation(
            source="claude_code",
            machine_id="machine1",
            project="/project",
            conversation_id="conv123",
            first_ts=1706000000,
            last_ts=1706001000,
            message_count=10,
            title="Test Conversation",
            preview="Hello world...",
        )

        result = indexer.update_conversation(conversation)

        assert result is True
        mock_client.collections["conversations"].documents.upsert.assert_called_once()

    def test_passes_correct_document(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """update_conversation should pass correctly formatted document."""
        conversation = Conversation(
            source="codex",
            machine_id="m1",
            project="/home/user/work",
            conversation_id="abc123",
            first_ts=1706000000,
            last_ts=1706002000,
            message_count=25,
            title="Coding Session",
            preview="Let me help you...",
        )

        indexer.update_conversation(conversation)

        call_args = mock_client.collections["conversations"].documents.upsert.call_args
        doc = call_args[0][0]

        assert doc["id"] == "codex:m1:abc123"
        assert doc["source"] == "codex"
        assert doc["machine_id"] == "m1"
        assert doc["project"] == "/home/user/work"
        assert doc["conversation_id"] == "abc123"
        assert doc["first_ts"] == 1706000000
        assert doc["last_ts"] == 1706002000
        assert doc["message_count"] == 25
        assert doc["title"] == "Coding Session"
        assert doc["preview"] == "Let me help you..."

    def test_returns_false_on_error(
        self, indexer: TypesenseIndexer, mock_client: MagicMock
    ) -> None:
        """update_conversation should return False on error."""
        conversation = Conversation(
            source="claude_code",
            machine_id="m1",
            project="/p",
            conversation_id="c1",
            first_ts=1706000000,
            last_ts=1706001000,
            message_count=5,
            title="Test",
            preview="Preview",
        )

        mock_client.collections.__getitem__.return_value.documents.upsert.side_effect = Exception(
            "Connection error"
        )

        result = indexer.update_conversation(conversation)

        assert result is False


class TestSchemaDefinitions:
    """Tests for collection schema definitions."""

    def test_messages_schema_has_required_fields(self) -> None:
        """Messages schema should have all required fields."""
        field_names = {f["name"] for f in MESSAGES_SCHEMA["fields"]}

        expected_fields = {
            "id",
            "source",
            "machine_id",
            "project",
            "conversation_id",
            "ts",
            "role",
            "content",
            "content_hash",
            "raw_path",
            "raw_offset",
        }

        assert field_names == expected_fields

    def test_messages_schema_sorting(self) -> None:
        """Messages schema should sort by timestamp."""
        assert MESSAGES_SCHEMA["default_sorting_field"] == "ts"

    def test_conversations_schema_has_required_fields(self) -> None:
        """Conversations schema should have all required fields."""
        field_names = {f["name"] for f in CONVERSATIONS_SCHEMA["fields"]}

        expected_fields = {
            "id",
            "source",
            "machine_id",
            "project",
            "conversation_id",
            "first_ts",
            "last_ts",
            "message_count",
            "title",
            "preview",
        }

        assert field_names == expected_fields

    def test_conversations_schema_sorting(self) -> None:
        """Conversations schema should sort by last_ts."""
        assert CONVERSATIONS_SCHEMA["default_sorting_field"] == "last_ts"

    def test_facet_fields_for_filtering(self) -> None:
        """Schemas should have facet fields for filtering."""
        messages_facets = {
            f["name"] for f in MESSAGES_SCHEMA["fields"] if f.get("facet", False)
        }
        conversations_facets = {
            f["name"] for f in CONVERSATIONS_SCHEMA["fields"] if f.get("facet", False)
        }

        # Both should have common facets
        assert "source" in messages_facets
        assert "machine_id" in messages_facets
        assert "project" in messages_facets
        assert "conversation_id" in messages_facets
        assert "role" in messages_facets

        assert "source" in conversations_facets
        assert "machine_id" in conversations_facets
        assert "project" in conversations_facets
        assert "conversation_id" in conversations_facets
