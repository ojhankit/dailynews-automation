"""
telegram_sender.py — Format and deliver the daily digest to Telegram.

Telegram message limit: 4096 chars per message.
We split long digests into multiple messages automatically.
"""
from __future__ import annotations

import logging
import os
from datetime import date

import httpx

from src.agents.classifier import GS_DESCRIPTIONS, GS_ORDER
from src.agents.summariser import SummarisedArticle

logger = logging.getLogger(__name__)

MAX_MSG_LEN = 4000  # stay safely below Telegram's 4096 limit


# ── Formatting helpers ────────────────────────────────────────────────────────

# Every character in this set must be preceded by \ in MarkdownV2 text spans.
_MDV2_SPECIAL = r"\_*[]()~`>#+-=|{}.!"


def _escape(text: str) -> str:
    """Escape all MarkdownV2 reserved characters in a plain-text span."""
    return "".join(f"\\{c}" if c in _MDV2_SPECIAL else c for c in str(text))


def _escape_url(url: str) -> str:
    """
    Escape a URL for use inside a MarkdownV2 inline link: [label](url).
    Inside the () only ')' and '\\' need escaping per the Telegram spec.
    """
    return url.replace("\\", "\\\\").replace(")", "\\)")


def _format_article(idx: int, s: SummarisedArticle) -> str:
    kw = ", ".join(s.keywords) if s.keywords else "—"
    title_escaped = _escape(s.article.title)
    url_escaped   = _escape_url(s.article.url)

    lines = [
        # Bold title as a clickable link — avoids raw URL in text span
        f"*{idx}\\. [{title_escaped}]({url_escaped})*",
        "",
        f"📌 *What Happened:* {_escape(s.what_happened)}",
        f"💡 *Why It Matters:* {_escape(s.why_it_matters)}",
        f"🎯 *UPSC Relevance:* {_escape(s.upsc_relevance)}",
        f"🏷 *Keywords:* {_escape(kw)}",
    ]
    return "\n".join(lines)


def build_messages(
    classified: dict[str, list[SummarisedArticle]],
) -> list[str]:
    """
    Build a list of Telegram-ready MarkdownV2 strings, each ≤ MAX_MSG_LEN chars.
    """
    today = _escape(date.today().strftime("%A, %d %B %Y"))
    header = (
        f"📰 *UPSC Daily News Digest*\n"
        f"📅 {today}\n"
        f"{'─' * 30}\n"
    )

    messages: list[str] = []
    current = header
    article_idx = 1

    for gs in GS_ORDER:
        articles = classified.get(gs)
        if not articles:
            continue

        desc = _escape(GS_DESCRIPTIONS[gs])
        section_header = f"\n\n📚 *{gs} \\— {desc}*\n{'─' * 28}\n"

        if len(current) + len(section_header) > MAX_MSG_LEN:
            messages.append(current)
            current = section_header
        else:
            current += section_header

        for s in articles:
            block = "\n\n" + _format_article(article_idx, s)
            article_idx += 1

            if len(current) + len(block) > MAX_MSG_LEN:
                messages.append(current)
                current = block
            else:
                current += block

    if current.strip():
        messages.append(current)

    return messages


# ── Sender ────────────────────────────────────────────────────────────────────

def send_to_telegram(messages: list[str]) -> None:
    """POST each message chunk to the Telegram Bot API."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for i, text in enumerate(messages, 1):
        logger.info("Sending Telegram message %d/%d …", i, len(messages))
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        try:
            resp = httpx.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Message %d sent ✓", i)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Telegram API error (msg %d): %s — %s", i, exc.response.status_code, exc.response.text
            )
            raise
        except Exception as exc:
            logger.error("Failed to send message %d: %s", i, exc)
            raise


def deliver(classified: dict[str, list[SummarisedArticle]]) -> None:
    """High-level entry point: format + send."""
    msgs = build_messages(classified)
    logger.info("Delivering %d Telegram message(s) …", len(msgs))
    send_to_telegram(msgs)
    logger.info("Delivery complete.")