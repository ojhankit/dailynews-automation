"""
logger.py — Structured logging for UPSC News Agent.

Produces TWO outputs simultaneously on every run:

  1. stdout          — human-readable coloured text (for live GitHub Actions console)
  2. logs/run_<timestamp>.jsonl — newline-delimited JSON, one object per log record

The .jsonl file is uploaded as a GitHub Actions artifact after every run
(success OR failure), so you can download and inspect the full structured
log history.

JSONL format — each line is a valid JSON object:
{
  "ts":        "2026-05-06T09:20:12.345678",   // ISO-8601 UTC timestamp
  "ts_epoch":  1746523212.345,                 // float seconds since epoch
  "level":     "INFO",                         // DEBUG / INFO / WARNING / ERROR / CRITICAL
  "logger":    "src.agents.summariser",        // dotted logger name
  "message":   "Summarising: Cabinet approves …",
  "module":    "summariser",                   // filename without .py
  "func":      "summarise_article",            // function name
  "line":      78,                             // line number
  "run_id":    "20260506_092012",              // same for every record in one run
  "exc":       null                            // exception traceback string or null
}
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

LOGS_DIR = Path("logs")
_RUN_ID: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
_LOG_FILE: Path = LOGS_DIR / f"run_{_RUN_ID}.jsonl"

# ── ANSI colours for stdout (disabled on non-TTY / CI without colour support) ─
_COLOURS = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}
_RESET = "\033[0m"
_USE_COLOUR = sys.stdout.isatty() or os.getenv("FORCE_COLOR", "") == "1"


# ── JSONL handler ─────────────────────────────────────────────────────────────

class _JsonlHandler(logging.Handler):
    """Appends one JSON object per log record to the run's .jsonl file."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        exc_text: str | None = None
        if record.exc_info:
            exc_text = "".join(traceback.format_exception(*record.exc_info)).strip()

        obj = {
            "ts":       datetime.fromtimestamp(record.created, tz=timezone.utc)
                        .isoformat(timespec="microseconds"),
            "ts_epoch": round(record.created, 3),
            "level":    record.levelname,
            "logger":   record.name,
            "message":  record.getMessage(),
            "module":   record.module,
            "func":     record.funcName,
            "line":     record.lineno,
            "run_id":   _RUN_ID,
            "exc":      exc_text,
        }
        try:
            self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._fh.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        super().close()
        try:
            self._fh.close()
        except Exception:
            pass


# ── Pretty stdout handler ─────────────────────────────────────────────────────

class _PrettyHandler(logging.StreamHandler):
    """Human-readable coloured output for the GitHub Actions console."""

    _FMT = "[{ts}] {colour}{level:<8}{reset} {name} — {msg}"

    def emit(self, record: logging.LogRecord) -> None:
        colour = _COLOURS.get(record.levelname, "") if _USE_COLOUR else ""
        reset  = _RESET if _USE_COLOUR else ""
        ts     = datetime.fromtimestamp(record.created, tz=timezone.utc) \
                         .strftime("%Y-%m-%d %H:%M:%S")
        line   = self._FMT.format(
            ts=ts,
            colour=colour,
            level=record.levelname,
            reset=reset,
            name=record.name,
            msg=record.getMessage(),
        )
        if record.exc_info:
            line += "\n" + logging.Formatter().formatException(record.exc_info)
        try:
            self.stream.write(line + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)


# ── Public API ────────────────────────────────────────────────────────────────

def setup_logger(name: str = "upsc_agent") -> logging.Logger:
    """
    Configure and return the named logger.

    Safe to call multiple times — handlers are only attached once.
    All child loggers (src.*, langchain, httpx, …) inherit the root-level
    JSONL handler so every library log is captured in the run file.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level      = getattr(logging, level_name, logging.INFO)

    # ── Root logger: capture everything into JSONL ────────────────────────────
    root = logging.getLogger()
    if not any(isinstance(h, _JsonlHandler) for h in root.handlers):
        jsonl_handler = _JsonlHandler(_LOG_FILE)
        jsonl_handler.setLevel(logging.DEBUG)   # capture all levels in file
        root.addHandler(jsonl_handler)
        root.setLevel(logging.DEBUG)

        # Suppress noisy third-party loggers in the file (still captured, just quieter)
        for noisy in ("httpx", "httpcore", "urllib3", "google", "hpack"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── Named logger: pretty stdout ───────────────────────────────────────────
    logger = logging.getLogger(name)
    if not any(isinstance(h, _PrettyHandler) for h in logger.handlers):
        pretty = _PrettyHandler(sys.stdout)
        pretty.setLevel(level)
        logger.addHandler(pretty)
        logger.setLevel(level)
        logger.propagate = True   # also flows to root → JSONL

    # Log the file path once so it's easy to find in the Actions console
    logger.info("📝 Structured log → %s  (run_id: %s)", _LOG_FILE, _RUN_ID)
    return logger


def get_run_log_path() -> Path:
    """Return the path of the current run's .jsonl file."""
    return _LOG_FILE


def get_run_id() -> str:
    return _RUN_ID