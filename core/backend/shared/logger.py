"""Centralized logging configuration for VisionArk backend.

Call ``setup_logging()`` once at process startup (main.py / worker.py)
before any application code runs.  All modules that do
``logger = logging.getLogger(__name__)`` will automatically pick up
the configured handlers and level.
"""

from __future__ import annotations

import logging
import os
import sys


_INITIALISED = False


def setup_logging(*, level: str | None = None) -> None:
    """Configure the root logger for the entire process.

    Parameters
    ----------
    level:
        Override log level.  Accepted values: DEBUG, INFO, WARNING, ERROR.
        If *None*, reads ``LOG_LEVEL`` env-var, defaulting to ``INFO``
        (or ``DEBUG`` when ``ATMOS_ENV=dev``).
    """
    global _INITIALISED
    if _INITIALISED:
        return
    _INITIALISED = True

    if level is None:
        env = os.getenv("ATMOS_ENV", "dev")
        level = os.getenv("LOG_LEVEL", "DEBUG" if env == "dev" else "INFO")

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # ── Format ──────────────────────────────────────────────────────
    fmt = "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s"
    datefmt = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.addHandler(handler)

    # Quiet down noisy third-party loggers
    for noisy in ("httpcore", "httpx", "urllib3", "google", "grpc"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).debug(
        "Logging initialised (level=%s)", level.upper()
    )
