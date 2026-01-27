"""CLI entry point for the collector daemon.

Allows running the collector as a module:
    python -m session_siphon.collector
"""

import signal
import sys
from types import FrameType

from session_siphon.collector.daemon import request_shutdown, run_collector
from session_siphon.config import load_config
from session_siphon.logging import get_logger

logger = get_logger("collector")


def signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully."""
    sig_name = signal.Signals(signum).name
    logger.info("Received signal %s, shutting down", sig_name)
    request_shutdown()


def main() -> None:
    """Main entry point for the collector daemon."""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load configuration
    config = load_config()

    # Run the collector daemon
    try:
        run_collector(config)
    except KeyboardInterrupt:
        # Handle case where signal handler didn't catch it
        logger.info("Interrupted, shutting down")
        request_shutdown()

    sys.exit(0)


if __name__ == "__main__":
    main()
