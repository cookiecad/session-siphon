#!/bin/bash
# Set up Typesense: start container and create collections

set -euo pipefail

cd "$(dirname "$0")/.."

# Default API key for development
TYPESENSE_API_KEY="${TYPESENSE_API_KEY:-dev-api-key}"
TYPESENSE_HOST="${TYPESENSE_HOST:-localhost}"
TYPESENSE_PORT="${TYPESENSE_PORT:-8108}"

echo "Starting Typesense..."
docker compose up -d typesense

echo "Waiting for Typesense to be ready..."
for i in {1..60}; do
    if curl -s "http://${TYPESENSE_HOST}:${TYPESENSE_PORT}/health" | grep -q "ok"; then
        echo "Health check passed, waiting for full initialization..."
        sleep 3
        break
    fi
    sleep 1
done

# Wait until we can actually list collections (proves Typesense is fully ready)
echo "Verifying Typesense is accepting requests..."
for i in {1..30}; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://${TYPESENSE_HOST}:${TYPESENSE_PORT}/collections" \
        -H "X-TYPESENSE-API-KEY: ${TYPESENSE_API_KEY}")
    if [ "$RESPONSE" = "200" ]; then
        echo "Typesense is fully ready"
        break
    fi
    echo "Waiting for Typesense to be fully ready... (attempt $i)"
    sleep 2
done

echo "Creating collections..."

# Create messages collection
curl -s -X POST "http://${TYPESENSE_HOST}:${TYPESENSE_PORT}/collections" \
    -H "X-TYPESENSE-API-KEY: ${TYPESENSE_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "messages",
        "fields": [
            {"name": "source", "type": "string", "facet": true},
            {"name": "machine_id", "type": "string", "facet": true},
            {"name": "project", "type": "string", "facet": true},
            {"name": "conversation_id", "type": "string"},
            {"name": "ts", "type": "int64", "sort": true},
            {"name": "role", "type": "string", "facet": true},
            {"name": "content", "type": "string"},
            {"name": "content_hash", "type": "string"},
            {"name": "raw_path", "type": "string"},
            {"name": "raw_offset", "type": "int64"}
        ],
        "default_sorting_field": "ts"
    }'
echo ""

# Verify messages collection was created
for i in {1..10}; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://${TYPESENSE_HOST}:${TYPESENSE_PORT}/collections/messages" \
        -H "X-TYPESENSE-API-KEY: ${TYPESENSE_API_KEY}")
    if [ "$RESPONSE" = "200" ]; then
        echo "Messages collection ready"
        break
    fi
    sleep 1
done

# Create conversations collection
curl -s -X POST "http://${TYPESENSE_HOST}:${TYPESENSE_PORT}/collections" \
    -H "X-TYPESENSE-API-KEY: ${TYPESENSE_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "conversations",
        "fields": [
            {"name": "source", "type": "string", "facet": true},
            {"name": "machine_id", "type": "string", "facet": true},
            {"name": "project", "type": "string", "facet": true},
            {"name": "conversation_id", "type": "string"},
            {"name": "first_ts", "type": "int64"},
            {"name": "last_ts", "type": "int64", "sort": true},
            {"name": "message_count", "type": "int32"},
            {"name": "title", "type": "string"},
            {"name": "preview", "type": "string"}
        ],
        "default_sorting_field": "last_ts"
    }'
echo ""

# Verify conversations collection was created
for i in {1..10}; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://${TYPESENSE_HOST}:${TYPESENSE_PORT}/collections/conversations" \
        -H "X-TYPESENSE-API-KEY: ${TYPESENSE_API_KEY}")
    if [ "$RESPONSE" = "200" ]; then
        echo "Conversations collection ready"
        break
    fi
    sleep 1
done

echo ""
echo "Setup complete! Collections are ready."
