# Session Siphon - Phase 1 Goals

Build a centralized logging and search system for AI coding assistant conversations.

## Project Description

Session Siphon collects conversation transcripts from multiple AI coding tools (Claude Code, Codex, VS Code Copilot, Gemini CLI), normalizes them into a unified format, and indexes them in Typesense for full-text search with filters.

## Phase 1 Scope

Single-machine implementation:
- Collector daemon to monitor and gather conversations
- Local processing pipeline
- Typesense indexing
- Basic Next.js UI for browsing and search

## Requirements

1. Collector daemon monitors source directories for new/changed files
2. Support Claude Code, Codex, VS Code Copilot, and Gemini CLI sources
3. Incremental extraction for JSONL files (tail from offset)
4. Snapshot extraction for JSON files (detect changes via hash/mtime)
5. Processor normalizes all formats into canonical message schema
6. Messages indexed in Typesense with faceted search
7. Conversations collection for browsing by date/project/source
8. Basic Next.js UI with conversation list, search, and viewer

## Technical Stack

- Python for collector and processor (watchdog, sqlite3, typesense)
- Typesense 27.1 in Docker for search
- Next.js + TypeScript for UI
- SQLite for state tracking

## Acceptance Criteria

- [ ] Collector daemon runs and syncs Claude Code conversations to outbox
- [ ] Processor indexes messages into Typesense
- [ ] Conversations are searchable and browsable in UI
- [ ] New messages in active sessions are picked up on subsequent runs
- [ ] At least one other source (Codex or VS Code) also works

## Verification

```bash
# Start services
docker compose up -d
python -m collector
python -m processor

# Verify indexing
curl http://localhost:8108/collections/messages/documents/search?q=test

# Start UI
cd ui && npm run dev
# Open http://localhost:3000
```
