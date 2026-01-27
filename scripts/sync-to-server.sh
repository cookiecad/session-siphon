#!/bin/bash
# Sync outbox to server inbox
# For Phase 1 (same machine), this is a local copy
# Later: change destination to remote server

set -euo pipefail

OUTBOX="${HOME}/session-siphon/outbox"
INBOX="${HOME}/session-siphon/inbox"

# Ensure directories exist
mkdir -p "$OUTBOX"
mkdir -p "$INBOX"

# Rsync with options suitable for incremental JSONL files
rsync -avz --partial --inplace \
    "$OUTBOX/" \
    "$INBOX/"

echo "Sync complete: $OUTBOX -> $INBOX"
