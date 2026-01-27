"""File archiver for processed transcript files.

Moves files from inbox to archive with date-based organization
while preserving the source/machine hierarchy.
"""

import shutil
from datetime import datetime
from pathlib import Path

from session_siphon.logging import get_logger

logger = get_logger("archiver")


def archive_file(
    source_path: Path,
    inbox_path: Path,
    archive_path: Path,
    archive_date: datetime | None = None,
) -> Path:
    """Move a file from inbox to archive with date-based structure.

    Creates archive path structure: archive/<date>/<machine_id>/<source>/<path_structure>
    where <date> is in YYYY-MM-DD format.

    Args:
        source_path: Path to the file in inbox to archive
        inbox_path: Base inbox directory path
        archive_path: Base archive directory path
        archive_date: Date for archive directory (defaults to today)

    Returns:
        Path to the archived file

    Raises:
        ValueError: If source_path is not under inbox_path
        FileNotFoundError: If source_path does not exist
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")

    # Ensure source is under inbox
    try:
        relative_path = source_path.relative_to(inbox_path)
    except ValueError:
        raise ValueError(f"Source path {source_path} is not under inbox {inbox_path}")

    # Use provided date or current date
    if archive_date is None:
        archive_date = datetime.now()

    date_str = archive_date.strftime("%Y-%m-%d")

    # Build archive destination: archive/<date>/<relative_from_inbox>
    dest_path = archive_path / date_str / relative_path

    # Ensure destination directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Move file to archive
    shutil.move(str(source_path), str(dest_path))

    logger.info("Archived file: source=%s dest=%s", source_path, dest_path)

    return dest_path
