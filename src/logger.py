"""
logger.py — Centralised logging setup.

Call setup_logger(name) once per entry-point (main.py) to configure
the root logger. All child loggers (logging.getLogger(__name__)) in
other modules automatically inherit the handler and level.
"""
from __future__ import annotations

import logging
import os
import sys


def setup_logger(name: str) -> logging.Logger:
    """
    Configure and return a named logger.

    - Log level is driven by the LOG_LEVEL env var (default: INFO).
    - Output goes to stdout so it plays nicely with systemd / Docker / GitHub Actions.
    - If the root logger already has handlers (e.g. during tests), no duplicate
      handlers are added.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        fmt = logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        root.addHandler(handler)

    root.setLevel(level)
    return logging.getLogger(name)
