"""Collector state tracking with SQLite persistence."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Self


@dataclass
class FileState:
    """State information for a tracked file."""

    source: str
    path: str
    mtime: int | None = None
    size: int | None = None
    sha256: str | None = None
    last_offset: int = 0
    last_synced: int | None = None


class CollectorState:
    """Manages collector state persistence in SQLite database.

    Tracks file states including modification time, size, hash,
    and sync progress for incremental collection.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize collector state with database path.

        Args:
            db_path: Path to SQLite database file. Parent directories
                     will be created if they don't exist.
        """
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create the files table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                source TEXT NOT NULL,
                path TEXT NOT NULL,
                mtime INTEGER,
                size INTEGER,
                sha256 TEXT,
                last_offset INTEGER DEFAULT 0,
                last_synced INTEGER,
                PRIMARY KEY (source, path)
            )
        """)
        self._conn.commit()

    def get_file_state(self, source: str, path: str) -> FileState | None:
        """Get the state of a specific file.

        Args:
            source: Source identifier (e.g., 'claude', 'chatgpt')
            path: File path within the source

        Returns:
            FileState if found, None otherwise
        """
        cursor = self._conn.execute(
            """
            SELECT source, path, mtime, size, sha256, last_offset, last_synced
            FROM files
            WHERE source = ? AND path = ?
            """,
            (source, path),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return FileState(
            source=row["source"],
            path=row["path"],
            mtime=row["mtime"],
            size=row["size"],
            sha256=row["sha256"],
            last_offset=row["last_offset"] or 0,
            last_synced=row["last_synced"],
        )

    def update_file_state(self, source: str, path: str, **attrs: int | str | None) -> None:
        """Update or insert file state.

        Args:
            source: Source identifier
            path: File path within the source
            **attrs: Attributes to update (mtime, size, sha256, last_offset, last_synced)
        """
        # Validate attrs
        valid_attrs = {"mtime", "size", "sha256", "last_offset", "last_synced"}
        invalid = set(attrs.keys()) - valid_attrs
        if invalid:
            raise ValueError(f"Invalid attributes: {invalid}")

        # Get existing state or create new
        existing = self.get_file_state(source, path)

        if existing is None:
            # Insert new record
            mtime = attrs.get("mtime")
            size = attrs.get("size")
            sha256 = attrs.get("sha256")
            last_offset = attrs.get("last_offset", 0)
            last_synced = attrs.get("last_synced")

            self._conn.execute(
                """
                INSERT INTO files (source, path, mtime, size, sha256, last_offset, last_synced)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source, path, mtime, size, sha256, last_offset, last_synced),
            )
        else:
            # Update existing record
            if not attrs:
                return  # Nothing to update

            set_clauses = []
            values = []
            for key, value in attrs.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            values.extend([source, path])
            self._conn.execute(
                f"""
                UPDATE files
                SET {', '.join(set_clauses)}
                WHERE source = ? AND path = ?
                """,
                values,
            )

        self._conn.commit()

    def list_files(self, source: str | None = None) -> list[FileState]:
        """List all tracked files, optionally filtered by source.

        Args:
            source: Optional source to filter by

        Returns:
            List of FileState objects
        """
        if source is None:
            cursor = self._conn.execute(
                """
                SELECT source, path, mtime, size, sha256, last_offset, last_synced
                FROM files
                ORDER BY source, path
                """
            )
        else:
            cursor = self._conn.execute(
                """
                SELECT source, path, mtime, size, sha256, last_offset, last_synced
                FROM files
                WHERE source = ?
                ORDER BY path
                """,
                (source,),
            )

        return [
            FileState(
                source=row["source"],
                path=row["path"],
                mtime=row["mtime"],
                size=row["size"],
                sha256=row["sha256"],
                last_offset=row["last_offset"] or 0,
                last_synced=row["last_synced"],
            )
            for row in cursor
        ]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> Self:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Exit context manager, closing database connection."""
        self.close()
