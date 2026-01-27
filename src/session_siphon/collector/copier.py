"""File copying utilities for the collector.

Implements incremental JSONL copying and hash-based JSON snapshot copying.
"""

import hashlib
import shutil
from pathlib import Path

from session_siphon.collector.state import FileState
from session_siphon.logging import get_logger

logger = get_logger("copier")


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        path: Path to file to hash

    Returns:
        Hex-encoded SHA-256 hash string
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        # Read in chunks for memory efficiency with large files
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def map_source_to_outbox(
    source: str,
    source_path: Path,
    machine_id: str,
    outbox_path: Path,
) -> Path:
    """Map a source file path to its outbox destination path.

    Creates path structure: outbox/<machine_id>/<source>/<path_structure>

    Args:
        source: Source identifier (e.g., 'claude_code', 'vscode_copilot')
        source_path: Original file path
        machine_id: Machine identifier
        outbox_path: Base outbox directory path

    Returns:
        Full destination path in outbox
    """
    # Get relative path from home directory for consistent structure
    try:
        relative_path = source_path.relative_to(Path.home())
    except ValueError:
        # If not under home directory, use the full path structure
        # Remove leading slash to make it relative
        relative_path = Path(str(source_path).lstrip("/"))

    return outbox_path / machine_id / source / relative_path


def copy_jsonl_incremental(
    source_path: Path,
    dest_path: Path,
    from_offset: int,
) -> int:
    """Copy new bytes from a JSONL file incrementally.

    Appends only bytes after from_offset to the destination file.
    Creates destination file and parent directories if they don't exist.

    Args:
        source_path: Source JSONL file path
        dest_path: Destination file path
        from_offset: Byte offset to start reading from

    Returns:
        New offset (end of file position after copy)
    """
    # Get current file size
    file_size = source_path.stat().st_size

    # If no new bytes, return current offset
    if file_size <= from_offset:
        return from_offset

    # Ensure destination directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Read new bytes and append to destination
    with open(source_path, "rb") as src:
        src.seek(from_offset)
        new_bytes = src.read()

    # Append to destination (or create if doesn't exist)
    with open(dest_path, "ab") as dst:
        dst.write(new_bytes)

    bytes_copied = file_size - from_offset
    logger.debug(
        "Incremental copy: source=%s dest=%s bytes=%d",
        source_path.name,
        dest_path.name,
        bytes_copied,
    )

    return file_size


def copy_json_snapshot(source_path: Path, dest_path: Path) -> None:
    """Copy entire JSON file to destination.

    Overwrites destination if it exists. Creates parent directories if needed.

    Args:
        source_path: Source JSON file path
        dest_path: Destination file path
    """
    # Ensure destination directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy entire file
    shutil.copy2(source_path, dest_path)

    logger.debug("Snapshot copy: source=%s dest=%s", source_path.name, dest_path.name)


def needs_sync(
    source_path: Path,
    state: FileState | None,
) -> tuple[bool, str, str]:
    """Check if a file needs to be synced.

    For JSONL files, checks if file has grown (new bytes to copy).
    For JSON files, checks if hash has changed.

    Args:
        source_path: Path to source file
        state: Current file state (None if never synced)

    Returns:
        Tuple of (needs_sync, reason, current_hash)
        - needs_sync: True if file should be synced
        - reason: Description of why sync is needed (or "up_to_date")
        - current_hash: Current SHA-256 hash of the file
    """
    # Check if file exists
    if not source_path.exists():
        return False, "file_not_found", ""

    # Get current file stats
    stat = source_path.stat()
    current_size = stat.st_size
    current_mtime = int(stat.st_mtime)

    # Determine file type based on extension
    is_jsonl = source_path.suffix.lower() == ".jsonl"

    # Compute current hash
    current_hash = compute_sha256(source_path)

    # Never synced before
    if state is None:
        reason = "new_file"
        return True, reason, current_hash

    # For JSONL files, check if there are new bytes to copy
    if is_jsonl:
        if current_size > state.last_offset:
            return True, "new_bytes", current_hash
        # File might have been truncated/rewritten
        if current_size < state.last_offset:
            return True, "file_reset", current_hash
        # Size unchanged but hash might differ (file rewritten with same size)
        if current_hash != state.sha256:
            return True, "content_changed", current_hash
        return False, "up_to_date", current_hash

    # For JSON files, check if hash changed
    if current_hash != state.sha256:
        return True, "hash_changed", current_hash

    return False, "up_to_date", current_hash
