# session-siphon

Centralized logging and search system for AI coding assistant conversations.

## Overview

Session Siphon aggregates conversation history from various AI coding tools scattered across development machines. It normalizes these logs into a single format and indexes them for search.

## Features

- **Unified History**: Collects logs from multiple AI assistants into one place.
- **Supported Sources**:
    - Claude Code
    - Codex (CLI & VS Code)
    - VS Code Copilot Chat (Standard & Insiders)
    - Gemini CLI
    - OpenCode
    - Google Antigravity (Task metadata)
- **Search**: Full-text search over all conversations using Typesense.
- **Web Interface**: Next.js application to browse and filter conversation history.
- **Distributed Collection**: Runs as a daemon on developer machines to sync logs to a central server.

## Architecture

The system consists of three main components:

1.  **Collector**: Runs on the developer's machine. Watches specific directories for changes and copies new log data to a local "outbox".
2.  **Processor**: Runs on the server. Monitors an "inbox", parses incoming logs, normalizes the data structure, deduplicates entries, and indexes them into Typesense.
3.  **UI**: A web interface for searching and viewing the indexed conversations.

---

## Deployment

### Server Installation (Docker)

The server components (Typesense, Processor, UI) run together via Docker Compose.

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/cookiecad/session-siphon.git
    cd session-siphon
    ```

2.  **Configure environment**:
    ```bash
    cp .env.example .env
    # Edit .env and set:
    # - TYPESENSE_API_KEY: A secure random string
    # - NEXT_PUBLIC_TYPESENSE_HOST: Your server's hostname (accessible to browsers)
    # - UI_PORT: Port for the web UI (default: 3000)
    ```

3.  **Start all services**:
    ```bash
    docker compose up -d
    ```

4.  **Verify**:
    - Typesense health: `curl http://localhost:8108/health`
    - UI: Open `http://your-server:3000` in a browser

The processor will automatically watch `/data/session-siphon/inbox` for incoming files.

---

### Client Installation (Collector)

The collector runs on each developer machine to gather AI assistant logs.

#### Option A: From Source (Python 3.11+)

1.  **Create virtual environment**:
    ```bash
    python3 -m venv ~/.local/share/session-siphon-venv
    ~/.local/share/session-siphon-venv/bin/pip install git+https://github.com/cookiecad/session-siphon.git
    ```

2.  **Create config file** at `~/.config/session-siphon/config.yaml`:
    ```yaml
    machine_id: "your-machine-name"

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
        opencode:
          enabled: true
          paths:
            - "~/.opencode/project/*/session/*/*.json"
        antigravity:
          enabled: true
          paths:
            - "~/.gemini/antigravity/conversations/*.json"
    ```

3.  **Run the collector**:
    ```bash
    ~/.local/share/session-siphon-venv/bin/siphon-collector
    ```

#### Option B: Pre-built Binary (GitHub Releases)

Download the latest release for your platform from [GitHub Releases](https://github.com/cookiecad/session-siphon/releases).

```bash
# Linux x86_64
curl -L https://github.com/cookiecad/session-siphon/releases/latest/download/siphon-collector-linux-x86_64 -o siphon-collector
chmod +x siphon-collector
./siphon-collector
```

---

### Syncing Data to Server

The collector writes files to the outbox. You need to sync this to the server's inbox.

#### Using rsync + cron/systemd

Create a systemd user service for periodic sync:

**`~/.config/systemd/user/siphon-sync.service`**:
```ini
[Unit]
Description=Session Siphon Outbox Sync

[Service]
Type=oneshot
ExecStart=/usr/bin/rsync -avz --remove-source-files %h/session-siphon/outbox/ user@server:docker/session-siphon/data/session-siphon/inbox/
```

**`~/.config/systemd/user/siphon-sync.timer`**:
```ini
[Unit]
Description=Sync Session Siphon outbox every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
```

Enable:
```bash
systemctl --user daemon-reload
systemctl --user enable --now siphon-sync.timer
```

---

### Running Collector as a Service

**`~/.config/systemd/user/siphon-collector.service`**:
```ini
[Unit]
Description=Session Siphon Collector
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/share/session-siphon-venv/bin/siphon-collector
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Enable:
```bash
systemctl --user daemon-reload
systemctl --user enable --now siphon-collector.service

# Enable linger so services run even when logged out
loginctl enable-linger $USER
```

---

## Development

### Prerequisites

- Python 3.11+
- Docker (for Typesense)
- Node.js 20+ (for UI)

### Setup

1.  **Start Typesense**:
    ```bash
    docker compose up -d typesense
    ```

2.  **Install Python Dependencies**:
    ```bash
    pip install -e ".[dev]"
    ```

3.  **Run tests**:
    ```bash
    pytest
    ```

4.  **Run UI in dev mode**:
    ```bash
    cd ui
    npm install
    npm run dev
    ```

