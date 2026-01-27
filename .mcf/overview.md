# Session Siphon - Overview

A centralized logging and search system for AI coding assistant conversations.

## Current Status

**Phase 1 Complete**

- **Phases:** 5/5 complete (foundation, collector, processor, ui, integration)
- **Tasks:** 25/25 complete
- **Tests:** 319 passing
- **Build:** UI builds successfully

### Verification Status
- All 319 tests pass
- Python modules import correctly (`from session_siphon.collector import daemon`)
- UI builds successfully (`npm run build`)
- All feature branches merged to main (latest: ab298ae)

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Per-Machine Collector                      │
│  [Claude Code] [Codex] [VS Code] [Gemini]                    │
│         │         │        │        │                         │
│         └─────────┴────────┴────────┘                         │
│                         │                                     │
│                    Collector Daemon                           │
│                         │                                     │
│                      Outbox                                   │
└─────────────────────────┼────────────────────────────────────┘
                          │ rsync
┌─────────────────────────┼────────────────────────────────────┐
│                      Server                                   │
│                      Inbox                                    │
│                         │                                     │
│                   Processor                                   │
│                         │                                     │
│         ┌───────────────┼───────────────┐                    │
│         │               │               │                    │
│      Archive       Typesense        Next.js                  │
│       (raw)        (search)           UI                     │
└──────────────────────────────────────────────────────────────┘
```

## Key Components

1. **Collector Daemon** - Monitors source directories, copies to outbox
2. **Rsync Transport** - Syncs outbox to server inbox
3. **Processor Service** - Parses, normalizes, indexes to Typesense
4. **Typesense** - Full-text search with faceted filtering
5. **Next.js UI** - Browse conversations and search messages

## Data Flow

1. AI tools write conversations to their storage locations
2. Collector detects changes, copies to outbox (incremental for JSONL)
3. Rsync syncs outbox to server inbox
4. Processor parses files into canonical message format
5. Messages indexed in Typesense, conversations updated
6. Processed files archived with date-based structure
7. UI queries Typesense for search and browsing

## Technology Stack

| Component | Technology |
|-----------|------------|
| Collector | Python (watchdog, sqlite3) |
| Transport | rsync |
| Processor | Python (typesense client) |
| Search | Typesense 27.1 (Docker) |
| UI | Next.js + TypeScript |
| State | SQLite |

## Usage

```bash
# Start Typesense
docker compose up -d

# Setup collections (first time)
./scripts/setup-typesense.sh

# Run collector daemon
siphon-collector  # or python -m session_siphon.collector

# Sync to server (local in Phase 1)
./scripts/sync-to-server.sh

# Run processor daemon
siphon-processor  # or python -m session_siphon.processor

# Start UI
cd ui && npm run dev
# Open http://localhost:3000
```
