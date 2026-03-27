"""Cosplay — Safe configuration recovery utilities.

Provides backup and logging for corrupted JSON configuration files.
Every configuration manager MUST use these helpers during load() to
prevent silent data loss.

Added in v1.0.1 as a critical reliability patch.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("cosplay.config")


def backup_corrupted_file(filepath: Path) -> Path | None:
    """Create a timestamped .bak copy of a corrupted configuration file.

    Returns the backup path on success, or None if the source file
    does not exist or the backup itself fails.
    """
    if not filepath.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = filepath.with_suffix(f".{timestamp}.bak")

    try:
        shutil.copy2(str(filepath), str(backup_path))
        logger.info("Backup created: %s", backup_path)
        return backup_path
    except OSError as exc:
        logger.error("Failed to create backup of %s: %s", filepath, exc)
        return None


def log_corruption(filepath: Path, error: Exception) -> None:
    """Log a corruption event with full context."""
    logger.error(
        "Corrupted configuration detected: %s — %s: %s. "
        "Safe defaults will be loaded. The corrupted file has been preserved as a .bak backup.",
        filepath,
        type(error).__name__,
        error,
    )
