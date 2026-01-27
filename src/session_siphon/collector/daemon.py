"""Collector daemon main loop for syncing AI conversation files."""

import time
from pathlib import Path

from session_siphon.collector.copier import (
    copy_json_snapshot,
    copy_jsonl_incremental,
    map_source_to_outbox,
    needs_sync,
)
from session_siphon.collector.sources import discover_all_sources
from session_siphon.collector.state import CollectorState
from session_siphon.config import Config
from session_siphon.logging import get_logger, setup_logging

logger = get_logger("collector")

# Global flag for graceful shutdown
_shutdown_requested = False


def request_shutdown() -> None:
    """Request graceful shutdown of the collector daemon."""
    global _shutdown_requested
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    return _shutdown_requested


def reset_shutdown() -> None:
    """Reset shutdown flag (useful for testing)."""
    global _shutdown_requested
    _shutdown_requested = False


def sync_file(
    source: str,
    source_path: Path,
    state: CollectorState,
    machine_id: str,
    outbox_path: Path,
) -> bool:
    """Sync a single file if needed.

    Args:
        source: Source identifier (e.g., 'claude_code')
        source_path: Path to the source file
        state: CollectorState database
        machine_id: Machine identifier
        outbox_path: Base outbox directory

    Returns:
        True if file was synced, False if up-to-date or skipped
    """
    # Get current state for this file
    file_state = state.get_file_state(source, str(source_path))

    # Check if sync is needed
    sync_needed, reason, current_hash = needs_sync(source_path, file_state)

    if not sync_needed:
        return False

    # Map to destination path
    dest_path = map_source_to_outbox(source, source_path, machine_id, outbox_path)

    # Get file stats
    stat = source_path.stat()
    current_mtime = int(stat.st_mtime)
    current_size = stat.st_size
    current_time = int(time.time())

    # Determine copy method based on file extension
    is_jsonl = source_path.suffix.lower() == ".jsonl"

    if is_jsonl:
        # For file_reset or content_changed, we need to start fresh
        if reason in ("file_reset", "content_changed", "new_file"):
            # Remove existing destination to start clean
            if dest_path.exists():
                dest_path.unlink()
            from_offset = 0
        else:
            from_offset = file_state.last_offset if file_state else 0

        new_offset = copy_jsonl_incremental(source_path, dest_path, from_offset)

        # Update state with new offset
        state.update_file_state(
            source,
            str(source_path),
            mtime=current_mtime,
            size=current_size,
            sha256=current_hash,
            last_offset=new_offset,
            last_synced=current_time,
        )
    else:
        # JSON snapshot copy
        copy_json_snapshot(source_path, dest_path)

        # Update state
        state.update_file_state(
            source,
            str(source_path),
            mtime=current_mtime,
            size=current_size,
            sha256=current_hash,
            last_offset=current_size,
            last_synced=current_time,
        )

    logger.info("Synced file: source=%s path=%s reason=%s", source, source_path.name, reason)
    return True


def run_collector_cycle(
    state: CollectorState,
    machine_id: str,
    outbox_path: Path,
) -> int:
    """Run one collection cycle.

    Args:
        state: CollectorState database
        machine_id: Machine identifier
        outbox_path: Base outbox directory

    Returns:
        Number of files synced
    """
    # Discover all sources
    sources = discover_all_sources()

    synced_count = 0
    for source_name, paths in sources.items():
        for source_path in paths:
            if is_shutdown_requested():
                return synced_count

            try:
                if sync_file(source_name, source_path, state, machine_id, outbox_path):
                    synced_count += 1
            except Exception:
                logger.exception("Error syncing file: source=%s path=%s", source_name, source_path)

    return synced_count


def run_collector(config: Config) -> None:
    """Run the collector daemon main loop.

    Discovers AI conversation sources, syncs files to outbox,
    and repeats on configured interval until shutdown is requested.

    Args:
        config: Application configuration
    """
    reset_shutdown()

    # Set up logging for collector
    setup_logging("collector")

    machine_id = config.machine_id
    outbox_path = config.collector.outbox_path
    interval = config.collector.interval_seconds
    state_db = config.collector.state_db

    logger.info(
        "Starting collector daemon: machine_id=%s outbox=%s state_db=%s interval=%ds",
        machine_id,
        outbox_path,
        state_db,
        interval,
    )

    with CollectorState(state_db) as state:
        while not is_shutdown_requested():
            synced = run_collector_cycle(state, machine_id, outbox_path)

            if synced > 0:
                logger.info("Cycle complete: files_synced=%d", synced)
            else:
                logger.debug("Cycle complete: no changes detected")

            if is_shutdown_requested():
                break

            logger.debug("Waiting %ds until next cycle", interval)

            # Sleep in small increments to allow graceful shutdown
            sleep_remaining = interval
            while sleep_remaining > 0 and not is_shutdown_requested():
                sleep_time = min(1.0, sleep_remaining)
                time.sleep(sleep_time)
                sleep_remaining -= sleep_time

    logger.info("Collector daemon stopped")
