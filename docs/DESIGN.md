# Session Siphon - Design Document

A centralized logging and search system for AI coding assistant conversations.

## Overview

Session Siphon collects conversation transcripts from multiple AI coding tools (Claude Code, Codex, VS Code Copilot, Gemini CLI, OpenCode, Google Antigravity), normalizes them into a unified format, and indexes them in Typesense for full-text search with filters.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Per-Machine Collector                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ Claude Code │    │   Codex     │    │ VS Code     │    ...          │
│  │ ~/.claude/  │    │ ~/.codex/   │    │ chatSessions│                 │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│         │                  │                  │                         │
│         └──────────────────┼──────────────────┘                         │
│                            ▼                                            │
│                    ┌───────────────┐                                    │
│                    │  Collector    │  (watches for changes,             │
│                    │  Daemon       │   copies to outbox)                │
│                    └───────┬───────┘                                    │
│                            ▼                                            │
│                    ┌───────────────┐                                    │
│                    │    Outbox     │  ~/session-siphon/outbox/          │
│                    │    (raw)      │  <machine>/<source>/...            │
│                    └───────┬───────┘                                    │
└────────────────────────────┼────────────────────────────────────────────┘
                             │ rsync
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Server                                      │
│                    ┌───────────────┐                                    │
│                    │    Inbox      │  /data/session-siphon/inbox/       │
│                    └───────┬───────┘                                    │
│                            ▼                                            │
│                    ┌───────────────┐                                    │
│                    │   Processor   │  (normalizes, dedupes,             │
│                    │   Service     │   indexes)                         │
│                    └───────┬───────┘                                    │
│                            │                                            │
│              ┌─────────────┼─────────────┐                              │
│              ▼             ▼             ▼                              │
│       ┌───────────┐ ┌───────────┐ ┌───────────┐                        │
│       │  Archive  │ │ Typesense │ │  Next.js  │                        │
│       │  (raw)    │ │  (search) │ │   UI      │                        │
│       └───────────┘ └───────────┘ └───────────┘                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Source Locations

### Claude Code
- **Path:** `~/.claude/projects/**/*.jsonl`
- **Format:** JSON Lines (append-only)
- **Extraction:** Tail from last offset

### Codex (CLI & VS Code)
- **Path:** `~/.codex/sessions/*/*/*/rollout-*.jsonl`
- **Format:** JSON Lines (append-only)
- **Extraction:** Tail from last offset

### VS Code Copilot Chat
- **Paths:**
  - Linux: `~/.config/Code/User/workspaceStorage/*/chatSessions/*.json`
  - macOS: `~/Library/Application Support/Code/User/workspaceStorage/*/chatSessions/*.json`
  - Windows: `%APPDATA%/Code/User/workspaceStorage/*/chatSessions/*.json`
  - Also scan Insiders: replace `Code` with `Code - Insiders`
- **Format:** JSON snapshot (full session per file)
- **Extraction:** Re-parse on hash/mtime change, dedup by message

### Gemini CLI
- **Path:** `~/.gemini/tmp/*/chats/session-*.json`
- **Format:** JSON snapshot
- **Extraction:** Re-parse on hash/mtime change

### OpenCode (SST)
- **Path:** `~/.local/share/opencode/storage/session/*/*.json`
- **Format:** JSON (hierarchical structure with separate message and part files)
- **Extraction:** Re-parse on hash/mtime change
- **Note:** Messages stored in `~/.local/share/opencode/storage/message/<sessionID>/*.json`
- **Note:** Parts stored in `~/.local/share/opencode/storage/part/<messageID>/*.json`

### Google Antigravity
- **Status:** Limited support - conversations are in encrypted protobuf format
- **Paths:**
  - `~/.gemini/antigravity/brain/*/*.metadata.json` (task metadata only)
- **Format:** JSON metadata files (conversations are `.pb` protobuf, not parseable)
- **Extraction:** Can only collect task metadata, not full conversations
- **Note:** Google's agentic IDE using Gemini 3 models (released November 2025)
- **Workaround:** Use `/export` command within Antigravity to manually export conversations to markdown

## Directory Structure

### Collector Machine
```
~/session-siphon/
├── outbox/                          # Staged for sync to server
│   └── <machine_id>/
│       ├── claude_code/
│       │   └── <project_hash>/
│       │       └── <session_id>.jsonl
│       ├── codex/
│       │   └── YYYY/MM/DD/
│       │       └── rollout-*.jsonl
│       ├── vscode_copilot/
│       │   └── <workspace_hash>/
│       │       └── <uuid>.json
│       └── gemini_cli/
│           └── <project_hash>/
│               └── session-*.json
└── state/
    └── collector.db                 # SQLite: tracks files, offsets, hashes
```

### Server
```
/data/session-siphon/
├── inbox/                           # Received from collectors (rsync target)
│   └── <machine_id>/...
├── archive/                         # Immutable raw file archive
│   └── <machine_id>/
│       └── <source>/
│           └── YYYY/MM/DD/
│               └── <filename>
├── normalized/                      # Canonical format (optional backup)
│   └── YYYY/MM/DD/
│       └── <batch>.jsonl.gz
└── state/
    └── processor.db                 # SQLite: tracks processing state
```

## Data Models

### Canonical Message Schema (Typesense `messages` collection)

```json
{
  "id": "claude_code:mbp14:proj123:sess456:1706745600000:abc123",
  "source": "claude_code",
  "machine_id": "my-laptop",
  "project": "/home/user/projects/myapp",
  "conversation_id": "sess456",
  "ts": 1706745600,
  "role": "user",
  "content": "How do I implement...",
  "content_hash": "abc123def456",
  "raw_path": "claude_code/proj123/sess456.jsonl",
  "raw_offset": 12345
}
```

**Field definitions:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable unique ID: `<source>:<machine>:<conversation>:<ts>:<content_hash>` |
| `source` | string | Origin tool: `claude_code`, `codex`, `vscode_copilot`, `gemini_cli`, `opencode`, `antigravity` |
| `machine_id` | string | Machine identifier |
| `project` | string | Project/workspace directory path |
| `conversation_id` | string | Session/conversation identifier |
| `ts` | int64 | Unix timestamp (seconds) |
| `role` | string | `user`, `assistant`, `tool`, `system` |
| `content` | string | Message text content |
| `content_hash` | string | SHA256 of content (for dedup) |
| `raw_path` | string | Path to source file in archive |
| `raw_offset` | int64 | Byte offset in JSONL files (for re-read) |

### Typesense `conversations` collection (for browsing)

```json
{
  "id": "claude_code:mbp14:sess456",
  "source": "claude_code",
  "machine_id": "my-laptop",
  "project": "/home/user/projects/myapp",
  "conversation_id": "sess456",
  "first_ts": 1706745600,
  "last_ts": 1706749200,
  "message_count": 42,
  "title": "Implement authentication",
  "preview": "How do I implement JWT..."
}
```

## Component Details

### 1. Collector Daemon

**Responsibilities:**
- Monitor source directories for new/changed files
- Incrementally extract new content (tail JSONL, detect JSON changes)
- Copy raw files to outbox with stable paths
- Track state in SQLite (offsets, hashes, mtimes)

**State tracking (SQLite):**
```sql
CREATE TABLE files (
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    mtime INTEGER,
    size INTEGER,
    sha256 TEXT,
    last_offset INTEGER DEFAULT 0,
    last_synced INTEGER,
    PRIMARY KEY (source, path)
);
```

**Sync strategy:**
- JSONL files: copy incrementally (append new bytes)
- JSON files: copy entire file when hash changes

### 2. Rsync Transport

**Collector → Server:**
```bash
rsync -avz --partial --inplace \
    ~/session-siphon/outbox/ \
    server:/data/session-siphon/inbox/
```

**Key flags:**
- `-a`: archive mode (preserve permissions, times)
- `-z`: compress during transfer
- `--partial`: keep partial files on interrupt
- `--inplace`: update files in place (better for JSONL appends)

### 3. Processor Service

**Responsibilities:**
- Watch inbox for new/changed files
- Parse source-specific formats into canonical schema
- Deduplicate messages (by stable ID)
- Index into Typesense
- Move processed files to archive

**Processing flow:**
1. Scan inbox for new/modified files
2. For each file:
   a. Parse according to source format
   b. Generate canonical message records
   c. Upsert messages to Typesense
   d. Update/create conversation doc
   e. Move file to archive
   f. Record processing state

**Handling active sessions:**
- Track `last_processed_offset` per file
- On re-process, only parse from offset
- Use stable message IDs for idempotent upserts

### 4. Typesense Configuration

**Docker setup:**
```yaml
services:
  typesense:
    image: typesense/typesense:27.1
    ports:
      - "8108:8108"
    volumes:
      - typesense-data:/data
    command: >
      --data-dir=/data
      --api-key=${TYPESENSE_API_KEY}
      --enable-cors
```

**Collections schema:**

```json
// messages collection
{
  "name": "messages",
  "fields": [
    {"name": "source", "type": "string", "facet": true},
    {"name": "machine_id", "type": "string", "facet": true},
    {"name": "project", "type": "string", "facet": true},
    {"name": "conversation_id", "type": "string"},
    {"name": "ts", "type": "int64", "sort": true},
    {"name": "role", "type": "string", "facet": true},
    {"name": "content", "type": "string"},
    {"name": "content_hash", "type": "string"}
  ],
  "default_sorting_field": "ts"
}

// conversations collection
{
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
}
```

### 5. Next.js UI

**Pages:**
- `/` - Conversation browser (sorted by date, filtered by project/source/machine)
- `/search` - Full-text search with filters
- `/conversation/[id]` - Conversation viewer

**API routes:**
- `GET /api/conversations` - List/filter conversations
- `GET /api/conversations/[id]` - Get conversation messages
- `GET /api/search` - Search messages

## Security Considerations

- **Sensitive data:** Transcripts may contain secrets, API keys, credentials
- **Access control:** Typesense API key required; bind to localhost or use Tailscale
- **No public exposure:** Never expose raw transcript endpoints publicly
- **Future:** Consider encryption at rest for archive

## Technology Stack

| Component | Technology |
|-----------|------------|
| Collector daemon | Python (watchdog, sqlite3) |
| Transport | rsync over SSH |
| Processor | Python |
| Search engine | Typesense (Docker) |
| UI | Next.js + TypeScript |
| State tracking | SQLite |

## Future Phases

1. **Phase 1:** Single-machine collection + local processing + Typesense + basic UI
2. **Phase 2:** Multi-machine collection (rsync to central server)
3. **Phase 3:** Enhanced UI (semantic search, conversation threads, export)
4. **Phase 4:** Encryption, retention policies, analytics
