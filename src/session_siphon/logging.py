"""Logging configuration for session-siphon.

Provides centralized logging setup with file output to ~/session-siphon/logs/.
"""

import logging
import sys
from pathlib import Path

# Default log directory
DEFAULT_LOG_DIR = Path.home() / "session-siphon" / "logs"


def setup_logging(
    name: str,
    log_dir: Path | None = None,
    level: int = logging.INFO,
    console: bool = True,
) -> logging.Logger:
    """Configure logging for a session-siphon component.

    Creates a logger with both file and optional console handlers.
    Log files are written to ~/session-siphon/logs/<name>.log.

    Args:
        name: Logger name (used for log filename)
        log_dir: Directory for log files (defaults to ~/session-siphon/logs/)
        level: Logging level (defaults to INFO)
        console: Whether to also log to console (defaults to True)

    Returns:
        Configured logger instance
    """
    if log_dir is None:
        log_dir = DEFAULT_LOG_DIR

    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger(f"session_siphon.{name}")
    logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if logger.handlers:
        return logger

    # Log format with timestamp, level, and context
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    log_file = log_dir / f"{name}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler (optional)
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a session-siphon component.

    This function returns an existing logger or creates a basic one.
    For full configuration with file output, use setup_logging().

    Args:
        name: Logger name (will be prefixed with 'session_siphon.')

    Returns:
        Logger instance
    """
    return logging.getLogger(f"session_siphon.{name}")
