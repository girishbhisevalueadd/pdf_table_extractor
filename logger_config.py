"""
Shared logging configuration for PDF Table Extractor.

Provides rotating file + console handlers shared across app.py and pdf_table_extractor.py.
Log files are written to the `logs/` directory next to this file.

Log levels:
  DEBUG   - detailed internal steps (file only)
  INFO    - normal operation milestones (file + console)
  WARNING - recoverable issues (file + console)
  ERROR   - failures with tracebacks (file + console + errors.log)
"""

import logging
import logging.handlers
import os
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR  = Path(__file__).parent
LOG_DIR    = _BASE_DIR / "logs"
LOG_FILE   = LOG_DIR / "pdf_extractor.log"
ERROR_FILE = LOG_DIR / "pdf_extractor_errors.log"

# ── format ─────────────────────────────────────────────────────────────────────
LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── registry to avoid duplicate handlers on Streamlit reruns ───────────────────
_configured_loggers: set = set()


def setup_logging(logger_name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Set up and return a configured logger.

    Features:
    - Rotating main log  : logs/pdf_extractor.log       (5 MB × 5 backups, DEBUG+)
    - Rotating error log : logs/pdf_extractor_errors.log (2 MB × 3 backups, ERROR+)
    - Console handler    : INFO+ (visible in terminal / Streamlit logs)
    - Safe to call multiple times (idempotent via _configured_loggers registry)

    Args:
        logger_name : typically __name__ of the calling module
        level       : root level for this logger (default DEBUG)

    Returns:
        logging.Logger instance
    """
    global _configured_loggers

    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger(logger_name)

    # Idempotency: skip setup if already configured
    if logger_name in _configured_loggers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # ── 1. Main rotating file handler (DEBUG+) ────────────────────────────────
    try:
        main_fh = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,   # 5 MB
            backupCount=5,
            encoding="utf-8",
        )
        main_fh.setLevel(logging.DEBUG)
        main_fh.setFormatter(formatter)
        logger.addHandler(main_fh)
    except Exception as e:
        print(f"[logger_config] Could not create main file handler: {e}")

    # ── 2. Error-only rotating file handler ──────────────────────────────────
    try:
        err_fh = logging.handlers.RotatingFileHandler(
            ERROR_FILE,
            maxBytes=2 * 1024 * 1024,   # 2 MB
            backupCount=3,
            encoding="utf-8",
        )
        err_fh.setLevel(logging.ERROR)
        err_fh.setFormatter(formatter)
        logger.addHandler(err_fh)
    except Exception as e:
        print(f"[logger_config] Could not create error file handler: {e}")

    # ── 3. Console handler (INFO+) ────────────────────────────────────────────
    console_fh = logging.StreamHandler()
    console_fh.setLevel(logging.INFO)
    console_fh.setFormatter(formatter)
    logger.addHandler(console_fh)

    # Prevent double-printing via root logger
    logger.propagate = False

    _configured_loggers.add(logger_name)
    logger.debug(f"Logger '{logger_name}' initialized. Log dir: {LOG_DIR}")
    return logger


def get_logger(logger_name: str) -> logging.Logger:
    """Convenience alias for setup_logging."""
    return setup_logging(logger_name)
