from __future__ import annotations

import os
import sys
import logging

logger = logging.getLogger(__name__)


# LLM
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-8b-8192")


# News
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
MAX_ARTICLES: int = int(os.getenv("MAX_ARTICLES", "10"))
MAX_SUMMARY_ARTICLES: int = int(os.getenv("MAX_SUMMARY_ARTICLES", "6"))


# Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")


# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


def validate() -> None:
    missing: list[str] = []

    if not GEMINI_API_KEY and not GROQ_API_KEY:
        missing.append("GEMINI_API_KEY or GROQ_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        for var in missing:
            logger.critical("Missing required environment variable: %s", var)
        sys.exit("Startup aborted. Check your environment variables.")