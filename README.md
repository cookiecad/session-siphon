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

## Usage

### Prerequisites

- Python 3.11+
- Docker (for Typesense)
- Node.js (for UI)

### Setup

1.  **Start Typesense**:
    ```bash
    docker-compose up -d
    ```

2.  **Install Python Dependencies**:
    ```bash
    pip install .
    ```

3.  **Configure**:
    Edit `config.yaml` to match your paths and desired sources.

4.  **Run Collector** (on dev machine):
    ```bash
    siphon-collector
    ```

5.  **Run Processor** (on server):
    ```bash
    siphon-processor
    ```

6.  **Run UI**:
    ```bash
    cd ui
    npm install
    npm run dev
    ```
