"""Configuration loading and management."""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceConfig:
    enabled: bool = True
    paths: list[str] = field(default_factory=list)


@dataclass
class CollectorConfig:
    interval_seconds: int = 30
    outbox_path: Path = field(default_factory=lambda: Path.home() / "session-siphon" / "outbox")
    state_db: Path = field(default_factory=lambda: Path.home() / "session-siphon" / "state" / "collector.db")
    sources: dict[str, SourceConfig] = field(default_factory=dict)


@dataclass
class ServerConfig:
    inbox_path: Path = field(default_factory=lambda: Path("/data/session-siphon/inbox"))
    archive_path: Path = field(default_factory=lambda: Path("/data/session-siphon/archive"))
    state_db: Path = field(default_factory=lambda: Path("/data/session-siphon/state/processor.db"))


@dataclass
class TypesenseConfig:
    host: str = "localhost"
    port: int = 8108
    protocol: str = "http"
    api_key: str = "dev-api-key"


@dataclass
class Config:
    machine_id: str = "unknown"
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    typesense: TypesenseConfig = field(default_factory=TypesenseConfig)


def expand_env_var(value: str) -> str:
    """Expand environment variables in string (e.g. ${VAR})."""
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.environ.get(env_var, value)
    return value


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        # Look for config in standard locations
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.home() / ".config" / "session-siphon" / "config.yaml",
            Path("/etc/session-siphon/config.yaml"),
        ]
        for path in search_paths:
            if path.exists():
                config_path = path
                break

    if config_path is None or not config_path.exists():
        return Config()

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    # Parse collector config
    collector_data = data.get("collector", {})
    sources = {}
    for name, src_data in collector_data.get("sources", {}).items():
        sources[name] = SourceConfig(
            enabled=src_data.get("enabled", True),
            paths=src_data.get("paths", []),
        )

    collector = CollectorConfig(
        interval_seconds=collector_data.get("interval_seconds", 30),
        outbox_path=expand_path(collector_data.get("outbox_path", "~/session-siphon/outbox")),
        state_db=expand_path(collector_data.get("state_db", "~/session-siphon/state/collector.db")),
        sources=sources,
    )

    # Parse server config
    server_data = data.get("server", {})
    server = ServerConfig(
        inbox_path=expand_path(server_data.get("inbox_path", "/data/session-siphon/inbox")),
        archive_path=expand_path(server_data.get("archive_path", "/data/session-siphon/archive")),
        state_db=expand_path(server_data.get("state_db", "/data/session-siphon/state/processor.db")),
    )

    # Parse typesense config
    ts_data = data.get("typesense", {})
    api_key = expand_env_var(ts_data.get("api_key", "dev-api-key"))

    typesense = TypesenseConfig(
        host=ts_data.get("host", "localhost"),
        port=ts_data.get("port", 8108),
        protocol=ts_data.get("protocol", "http"),
        api_key=api_key,
    )

    # Determine machine_id
    machine_id = expand_env_var(data.get("machine_id", "unknown"))
    if machine_id == "unknown" or not machine_id:
        machine_id = platform.node()

    return Config(
        machine_id=machine_id,
        collector=collector,
        server=server,
        typesense=typesense,
    )
