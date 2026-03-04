"""
TransfPro Logging Configuration

This module sets up rotating file logging and console logging for the application.
Logs are stored in ~/.transfpro/logs/ directory.
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

from ..config.constants import APP_NAME


def setup_logger(name: str = APP_NAME) -> logging.Logger:
    """
    Set up and configure the application logger with file and console handlers.

    Creates a rotating file handler that logs to ~/.transfpro/logs/ directory
    and a console handler for immediate feedback.

    Args:
        name: Logger name (defaults to APP_NAME)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create logs directory if it doesn't exist
    log_dir = Path.home() / ".transfpro" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # Restrict log directory to owner only
    try:
        import os as _os
        _os.chmod(str(log_dir), 0o700)
    except OSError:
        pass

    # Create file handler with rotation
    log_file = log_dir / f"{APP_NAME.lower()}.log"

    # Rotating file handler: 5 MB per file, keep 10 backup files
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create formatter
    detailed_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    simple_formatter = logging.Formatter(
        fmt="%(levelname)s - %(message)s",
    )

    file_handler.setFormatter(detailed_formatter)
    console_handler.setFormatter(simple_formatter)

    # Add handlers to logger
    if not logger.handlers:  # Avoid duplicate handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.

    If the logger hasn't been set up yet, initializes it first.

    Args:
        name: Logger name (defaults to APP_NAME)

    Returns:
        logging.Logger: Logger instance
    """
    if name is None:
        name = APP_NAME

    logger = logging.getLogger(name)

    # If logger has no handlers, set it up
    if not logger.handlers:
        return setup_logger(name)

    return logger


def cleanup_old_logs(days: int = 30) -> None:
    """
    Clean up log files older than the specified number of days.

    Args:
        days: Number of days to keep (default: 30)
    """
    import time

    log_dir = Path.home() / ".transfpro" / "logs"

    if not log_dir.exists():
        return

    cutoff_time = time.time() - (days * 24 * 60 * 60)

    for log_file in log_dir.glob("*.log*"):
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
            except OSError:
                pass  # Silently ignore if unable to delete


# Module-level logger instance for convenience
logger = setup_logger()
