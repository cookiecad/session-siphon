"""Processor state tracking with SQLite persistence."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Self


@dataclass
class ProcessedFileState:
    """State information for a processed file."""

    path: str
    last_offset: int = 0
    last_processed: int | None = None


class ProcessorState:
    """Manages processor state persistence in SQLite database.

    Tracks processed files including the last offset for incremental
    processing of JSONL files.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize processor state with database path.

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
        """Create the processed_files table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                path TEXT PRIMARY KEY,
                last_offset INTEGER DEFAULT 0,
                last_processed INTEGER
            )
        """)
        self._conn.commit()

    def get_file_state(self, path: str) -> ProcessedFileState | None:
        """Get the state of a specific processed file.

        Args:
            path: File path

        Returns:
            ProcessedFileState if found, None otherwise
        """
        cursor = self._conn.execute(
            """
            SELECT path, last_offset, last_processed
            FROM processed_files
            WHERE path = ?
            """,
            (path,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ProcessedFileState(
            path=row["path"],
            last_offset=row["last_offset"] or 0,
            last_processed=row["last_processed"],
        )

    def get_last_offset(self, path: str) -> int:
        """Get the last processed offset for a file.

        Args:
            path: File path

        Returns:
            Last offset, or 0 if file not tracked
        """
        state = self.get_file_state(path)
        if state is None:
            return 0
        return state.last_offset

    def update_file_state(self, path: str, **attrs: int | None) -> None:
        """Update or insert processed file state.

        Args:
            path: File path
            **attrs: Attributes to update (last_offset, last_processed)
        """
        # Validate attrs
        valid_attrs = {"last_offset", "last_processed"}
        invalid = set(attrs.keys()) - valid_attrs
        if invalid:
            raise ValueError(f"Invalid attributes: {invalid}")

        # Get existing state or create new
        existing = self.get_file_state(path)

        if existing is None:
            # Insert new record
            last_offset = attrs.get("last_offset", 0)
            last_processed = attrs.get("last_processed")

            self._conn.execute(
                """
                INSERT INTO processed_files (path, last_offset, last_processed)
                VALUES (?, ?, ?)
                """,
                (path, last_offset, last_processed),
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

            values.append(path)
            self._conn.execute(
                f"""
                UPDATE processed_files
                SET {', '.join(set_clauses)}
                WHERE path = ?
                """,
                values,
            )

        self._conn.commit()

    def list_files(self) -> list[ProcessedFileState]:
        """List all tracked processed files.

        Returns:
            List of ProcessedFileState objects
        """
        cursor = self._conn.execute(
            """
            SELECT path, last_offset, last_processed
            FROM processed_files
            ORDER BY path
            """
        )

        return [
            ProcessedFileState(
                path=row["path"],
                last_offset=row["last_offset"] or 0,
                last_processed=row["last_processed"],
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
