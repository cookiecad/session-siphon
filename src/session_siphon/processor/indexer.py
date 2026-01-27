"""Typesense indexer for session-siphon messages and conversations."""

from typing import Any

import typesense
from typesense.exceptions import ObjectNotFound

from session_siphon.config import TypesenseConfig
from session_siphon.logging import get_logger
from session_siphon.models import CanonicalMessage, Conversation

logger = get_logger("indexer")

MESSAGES_SCHEMA: dict[str, Any] = {
    "name": "messages",
    "fields": [
        {"name": "id", "type": "string"},
        {"name": "source", "type": "string", "facet": True},
        {"name": "machine_id", "type": "string", "facet": True},
        {"name": "project", "type": "string", "facet": True},
        {"name": "conversation_id", "type": "string", "facet": True},
        {"name": "ts", "type": "int64", "sort": True},
        {"name": "role", "type": "string", "facet": True},
        {"name": "content", "type": "string"},
        {"name": "content_hash", "type": "string"},
        {"name": "raw_path", "type": "string"},
        {"name": "raw_offset", "type": "int32"},
    ],
    "default_sorting_field": "ts",
}

CONVERSATIONS_SCHEMA: dict[str, Any] = {
    "name": "conversations",
    "fields": [
        {"name": "id", "type": "string"},
        {"name": "source", "type": "string", "facet": True},
        {"name": "machine_id", "type": "string", "facet": True},
        {"name": "project", "type": "string", "facet": True},
        {"name": "conversation_id", "type": "string", "facet": True},
        {"name": "first_ts", "type": "int64", "sort": True},
        {"name": "last_ts", "type": "int64", "sort": True},
        {"name": "message_count", "type": "int32"},
        {"name": "title", "type": "string"},
        {"name": "preview", "type": "string"},
    ],
    "default_sorting_field": "last_ts",
}


class TypesenseIndexer:
    """Indexes messages and conversations in Typesense.

    Handles collection creation/verification and document upserts.
    """

    def __init__(self, config: TypesenseConfig) -> None:
        """Initialize indexer with Typesense configuration.

        Args:
            config: TypesenseConfig with connection details
        """
        self._config = config
        self._client = typesense.Client({
            "nodes": [{
                "host": config.host,
                "port": str(config.port),
                "protocol": config.protocol,
            }],
            "api_key": config.api_key,
            "connection_timeout_seconds": 5,
        })

    @property
    def client(self) -> typesense.Client:
        """Access the underlying Typesense client."""
        return self._client

    def ensure_collections(self) -> None:
        """Create or verify that required collections exist.

        Creates 'messages' and 'conversations' collections if they
        don't exist. If they exist, verifies basic structure.
        """
        self._ensure_collection(MESSAGES_SCHEMA)
        self._ensure_collection(CONVERSATIONS_SCHEMA)

    def _ensure_collection(self, schema: dict[str, Any]) -> None:
        """Create a collection if it doesn't exist.

        Args:
            schema: Collection schema definition
        """
        name = schema["name"]
        try:
            self._client.collections[name].retrieve()
            logger.debug("Collection already exists: collection=%s", name)
        except ObjectNotFound:
            self._client.collections.create(schema)
            logger.info("Created collection: collection=%s", name)

    def upsert_messages(self, messages: list[CanonicalMessage]) -> dict[str, int]:
        """Index messages into Typesense.

        Uses upsert semantics - creates new documents or updates existing
        ones based on the document ID.

        Args:
            messages: List of CanonicalMessage objects to index

        Returns:
            Dict with counts: {"success": N, "failed": M}
        """
        if not messages:
            return {"success": 0, "failed": 0}

        documents = [msg.to_typesense_doc() for msg in messages]

        results = self._client.collections["messages"].documents.import_(
            documents,
            {"action": "upsert"},
        )

        success = 0
        failed = 0
        for result in results:
            if result.get("success", False):
                success += 1
            else:
                failed += 1
                logger.debug("Failed to index message: error=%s", result.get("error", "unknown"))

        if failed > 0:
            logger.warning("Some messages failed to index: success=%d failed=%d", success, failed)

        return {"success": success, "failed": failed}

    def update_conversation(self, conversation: Conversation) -> bool:
        """Update or create a conversation document.

        Args:
            conversation: Conversation metadata to index

        Returns:
            True if successful, False otherwise
        """
        doc = conversation.to_typesense_doc()

        try:
            self._client.collections["conversations"].documents.upsert(doc)
            return True
        except Exception:
            logger.exception("Failed to update conversation: id=%s", doc.get("id", "unknown"))
            return False
