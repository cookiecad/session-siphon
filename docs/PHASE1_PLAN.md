# Phase 1 Implementation Plan

**Goal:** Set up a daemon to monitor and gather conversations from one machine, consolidate them in a working folder, and index into Typesense for search.

## Scope

- Single machine (this one: Linux)
- All four sources: Claude Code, Codex, VS Code Copilot, Gemini CLI
- Local rsync (outbox → server inbox on same machine for now)
- Processor: archive, normalize, index to Typesense
- Basic Next.js UI for browsing and search

## Directory Structure to Create

```
~/session-siphon/
├── outbox/                    # Collector output
│   └── <machine_id>/
├── state/
│   └── collector.db           # Collector state

/data/session-siphon/          # Or ~/session-siphon-server/
├── inbox/                     # rsync target
├── archive/                   # Processed raw files
├── state/
│   └── processor.db           # Processor state
```

## Tasks

### 1. Project Setup

- [ ] Initialize Python project with dependencies
- [ ] Create directory structure
- [ ] Set up configuration (paths, machine_id, API keys)

**Files:**
- `pyproject.toml` - Python project config
- `config.yaml` - Runtime configuration
- `src/config.py` - Config loading

**Dependencies:**
- `watchdog` - File system monitoring
- `typesense` - Typesense client
- `pyyaml` - Config parsing
- `click` - CLI interface

---

### 2. Collector Daemon

Monitor source directories and copy new/changed files to outbox.

#### 2.1 Source Discovery Module
Detect and enumerate source paths for each tool.

**Files:**
- `src/collector/sources.py`

**Functions:**
```python
def get_claude_code_paths() -> list[Path]:
    """Return all Claude Code session files (~/.claude/projects/**/*.jsonl)"""

def get_codex_paths() -> list[Path]:
    """Return all Codex session files (~/.codex/sessions/*/*/*/*.jsonl)"""

def get_vscode_paths() -> list[Path]:
    """Return all VS Code chat session files (all workspaceStorage)"""

def get_gemini_paths() -> list[Path]:
    """Return all Gemini CLI session files (~/.gemini/tmp/*/chats/*.json)"""

def discover_all_sources() -> dict[str, list[Path]]:
    """Return {source_name: [paths]} for all sources"""
```

#### 2.2 State Tracking Module
SQLite database for tracking file state.

**Files:**
- `src/collector/state.py`

**Schema:**
```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    mtime REAL,
    size INTEGER,
    sha256 TEXT,
    last_offset INTEGER DEFAULT 0,
    last_synced REAL,
    UNIQUE(source, path)
);
```

**Functions:**
```python
class CollectorState:
    def get_file_state(source: str, path: str) -> FileState | None
    def update_file_state(source: str, path: str, state: FileState)
    def get_files_needing_sync(source: str) -> list[FileState]
```

#### 2.3 File Copier Module
Copy files from source to outbox with proper path mapping.

**Files:**
- `src/collector/copier.py`

**Functions:**
```python
def map_source_to_outbox(source: str, src_path: Path, machine_id: str) -> Path:
    """Map source file path to outbox destination path"""

def copy_jsonl_incremental(src: Path, dst: Path, from_offset: int) -> int:
    """Append new bytes from src to dst, return new offset"""

def copy_json_snapshot(src: Path, dst: Path) -> str:
    """Copy entire JSON file, return sha256"""

def sync_file(source: str, path: Path, state: CollectorState, outbox: Path, machine_id: str):
    """Sync a single file to outbox, update state"""
```

#### 2.4 Daemon Main Loop
Watch and sync on interval.

**Files:**
- `src/collector/daemon.py`
- `src/collector/__main__.py`

**Logic:**
```python
def run_collector():
    while True:
        sources = discover_all_sources()
        for source, paths in sources.items():
            for path in paths:
                sync_file(source, path, state, outbox, machine_id)
        sleep(interval)  # e.g., 30 seconds
```

---

### 3. Rsync Transport

Simple script/cron to rsync outbox to server inbox.

**Files:**
- `scripts/sync-to-server.sh`

**Script:**
```bash
#!/bin/bash
rsync -avz --partial --inplace \
    ~/session-siphon/outbox/ \
    /data/session-siphon/inbox/
```

For Phase 1 (same machine), this is just a local directory copy. Structure it so swapping to remote rsync later is trivial.

---

### 4. Processor Service

Watch inbox, parse files, normalize, index to Typesense.

#### 4.1 Parser Modules
Parse each source format into canonical messages.

**Files:**
- `src/processor/parsers/base.py`
- `src/processor/parsers/claude_code.py`
- `src/processor/parsers/codex.py`
- `src/processor/parsers/vscode.py`
- `src/processor/parsers/gemini.py`

**Base interface:**
```python
@dataclass
class CanonicalMessage:
    source: str
    machine_id: str
    project: str
    conversation_id: str
    ts: int  # Unix timestamp
    role: str  # user, assistant, tool, system
    content: str
    content_hash: str
    raw_path: str
    raw_offset: int | None = None

class Parser(ABC):
    @abstractmethod
    def parse(self, path: Path, from_offset: int = 0) -> tuple[list[CanonicalMessage], int]:
        """Parse file from offset, return (messages, new_offset)"""
```

**Claude Code parser (high priority):**
- JSONL format with message objects
- Extract: timestamp, role, content, session ID from path
- Project path: parent directory of session file

**Codex parser:**
- JSONL with event types (`turn.completed`, `item.*`, etc.)
- Extract messages from relevant event types

**VS Code parser:**
- JSON with conversation structure
- Full reparse on change, dedup by content hash + timestamp

**Gemini parser:**
- JSON session format
- Full reparse on change

#### 4.2 State Tracking
Track which files/offsets have been processed.

**Files:**
- `src/processor/state.py`

**Schema:**
```sql
CREATE TABLE processed_files (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    path TEXT NOT NULL,
    last_offset INTEGER DEFAULT 0,
    last_processed REAL,
    UNIQUE(source, machine_id, path)
);
```

#### 4.3 Typesense Indexer
Index canonical messages and update conversation docs.

**Files:**
- `src/processor/indexer.py`

**Functions:**
```python
class TypesenseIndexer:
    def __init__(self, client: typesense.Client)

    def ensure_collections(self):
        """Create messages and conversations collections if not exist"""

    def upsert_messages(self, messages: list[CanonicalMessage]):
        """Upsert messages to Typesense"""

    def update_conversation(self, conversation_id: str, messages: list[CanonicalMessage]):
        """Update conversation metadata (last_ts, count, preview)"""

    def generate_message_id(self, msg: CanonicalMessage) -> str:
        """Generate stable ID: source:machine:conversation:ts:hash"""
```

#### 4.4 Archiver
Move processed files from inbox to archive.

**Files:**
- `src/processor/archiver.py`

**Functions:**
```python
def archive_file(inbox_path: Path, archive_root: Path) -> Path:
    """Move file to archive with date-based structure, return archive path"""
    # /data/session-siphon/archive/<machine>/<source>/YYYY/MM/DD/<filename>
```

#### 4.5 Processor Main Loop

**Files:**
- `src/processor/daemon.py`
- `src/processor/__main__.py`

**Logic:**
```python
def run_processor():
    indexer = TypesenseIndexer(client)
    indexer.ensure_collections()

    while True:
        for path in scan_inbox():
            source, machine_id = parse_inbox_path(path)
            parser = get_parser(source)

            last_offset = state.get_offset(source, machine_id, path)
            messages, new_offset = parser.parse(path, last_offset)

            if messages:
                indexer.upsert_messages(messages)
                indexer.update_conversation(messages[0].conversation_id, messages)
                state.update_offset(source, machine_id, path, new_offset)

            # Only archive if file hasn't changed recently (not active)
            if is_stable(path):
                archive_file(path, archive_root)

        sleep(interval)
```

---

### 5. Typesense Docker Setup

**Files:**
- `docker-compose.yml`

**Content:**
```yaml
services:
  typesense:
    image: typesense/typesense:27.1
    restart: unless-stopped
    ports:
      - "127.0.0.1:8108:8108"
    volumes:
      - ./data/typesense:/data
    command: >
      --data-dir=/data
      --api-key=${TYPESENSE_API_KEY:-dev-api-key}
      --enable-cors
    environment:
      - TYPESENSE_API_KEY=${TYPESENSE_API_KEY:-dev-api-key}
```

**Setup script:**
- `scripts/setup-typesense.sh` - Start container, create collections

---

### 6. Next.js UI (Basic)

Minimal UI for browsing and searching.

**Files:**
```
ui/
├── package.json
├── next.config.js
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              # Conversation list
│   │   ├── search/page.tsx       # Search page
│   │   └── conversation/[id]/page.tsx
│   ├── lib/
│   │   └── typesense.ts          # Typesense client
│   └── components/
│       ├── ConversationList.tsx
│       ├── ConversationView.tsx
│       ├── SearchBar.tsx
│       └── MessageBubble.tsx
```

**Features:**
- List conversations sorted by date
- Filter by source, project
- Full-text search
- View conversation messages

---

## Implementation Order

### Week 1: Foundation

1. **Project setup**
   - Initialize Python project
   - Create config structure
   - Set up Docker Compose for Typesense

2. **Collector - Source discovery**
   - Implement `sources.py` with all four source finders
   - Test on local machine, verify paths exist

3. **Collector - State tracking**
   - Implement SQLite state module
   - Test CRUD operations

### Week 2: Collector Complete

4. **Collector - File copier**
   - Implement JSONL incremental copy
   - Implement JSON snapshot copy
   - Test with real Claude Code files

5. **Collector - Daemon**
   - Implement main loop
   - Add CLI with click
   - Test end-to-end: source → outbox

6. **Rsync script**
   - Create sync script
   - Test local sync

### Week 3: Processor

7. **Parsers - Claude Code (priority)**
   - Parse JSONL format
   - Extract all required fields
   - Handle edge cases

8. **Parsers - Other sources**
   - Codex parser
   - VS Code parser
   - Gemini parser

9. **Processor - Indexer**
   - Typesense client setup
   - Collection creation
   - Message upsert
   - Conversation update

### Week 4: Integration & UI

10. **Processor - Full loop**
    - Integrate all components
    - Add archiver
    - Test full pipeline

11. **Next.js UI**
    - Basic conversation list
    - Search page
    - Conversation viewer

12. **Testing & polish**
    - End-to-end testing
    - Error handling
    - Logging

---

## Configuration File

**`config.yaml`:**
```yaml
machine_id: "my-machine"

collector:
  interval_seconds: 30
  outbox_path: "~/session-siphon/outbox"
  state_db: "~/session-siphon/state/collector.db"

  sources:
    claude_code:
      enabled: true
      paths:
        - "~/.claude/projects/**/*.jsonl"
    codex:
      enabled: true
      paths:
        - "~/.codex/sessions/*/*/*/*.jsonl"
    vscode:
      enabled: true
      paths:
        - "~/.config/Code/User/workspaceStorage/*/chatSessions/*.json"
        - "~/.config/Code - Insiders/User/workspaceStorage/*/chatSessions/*.json"
    gemini:
      enabled: true
      paths:
        - "~/.gemini/tmp/*/chats/session-*.json"

server:
  inbox_path: "/data/session-siphon/inbox"
  archive_path: "/data/session-siphon/archive"
  state_db: "/data/session-siphon/state/processor.db"

typesense:
  host: "localhost"
  port: 8108
  protocol: "http"
  api_key: "${TYPESENSE_API_KEY}"
```

---

## Success Criteria

Phase 1 is complete when:

1. ✅ Collector daemon runs and syncs Claude Code conversations to outbox
2. ✅ Processor indexes messages into Typesense
3. ✅ Conversations are searchable and browsable in UI
4. ✅ New messages in active sessions are picked up on subsequent runs
5. ✅ At least one other source (Codex or VS Code) also works

---

## Notes

- Start with Claude Code parser since that's most actively used
- Keep parsers simple initially; can enhance field extraction later
- Don't over-engineer error handling in v1; focus on happy path
- Log extensively for debugging
