from __future__ import annotations

import logging
import os
import html
from datetime import date

import httpx

from src.agents.classifier import GS_DESCRIPTIONS, GS_ORDER
from src.agents.summariser import SummarisedArticle
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

MAX_MSG_LEN = 4000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    return html.escape(str(text))


def _format_article(idx: int, s: SummarisedArticle) -> str:
    title = _escape(s.article.title)
    url = s.article.url

    what = _escape(s.what_happened)
    why = _escape(s.why_it_matters)
    rel = _escape(s.upsc_relevance)
    kw = _escape(", ".join(s.keywords) if s.keywords else "—")

    return f"""
<b>{idx}. <a href="{url}">{title}</a></b>

<b>What Happened:</b> {what}
<b>Why It Matters:</b> {why}
<b>UPSC Relevance:</b> {rel}
<b>Keywords:</b> {kw}
""".strip()


def _split_message(text: str) -> list[str]:
    return [text[i:i + MAX_MSG_LEN] for i in range(0, len(text), MAX_MSG_LEN)]


# ── Message Builder ───────────────────────────────────────────────────────────

def build_messages(
    classified: dict[str, list[SummarisedArticle]],
) -> list[str]:
    today = _escape(date.today().strftime("%A, %d %B %Y"))

    messages: list[str] = []

    for gs in GS_ORDER:
        articles = classified.get(gs)
        if not articles:
            continue

        desc = _escape(GS_DESCRIPTIONS[gs])

        header = f"""
<b>UPSC Daily News</b>
{today}

<b>{gs} — {desc}</b>
{"─" * 28}
""".strip()

        current = header
        article_idx = 1

        for s in articles:
            block = "\n\n" + _format_article(article_idx, s)
            article_idx += 1

            if len(current) + len(block) > MAX_MSG_LEN:
                messages.extend(_split_message(current))
                current = header + block
            else:
                current += block

        if current.strip():
            messages.extend(_split_message(current))

    return messages


# ── Sender ────────────────────────────────────────────────────────────────────

def send_to_telegram(messages: list[str]) -> None:
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for i, text in enumerate(messages, 1):
        logger.info("Sending message %d/%d", i, len(messages))

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Telegram error %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise
        except Exception as exc:
            logger.error("Failed to send message: %s", exc)
            raise


# ── Entry Point ───────────────────────────────────────────────────────────────

def deliver(classified: dict[str, list[SummarisedArticle]]) -> None:
    messages = build_messages(classified)
    logger.info("Delivering %d message(s) to Telegram", len(messages))
    send_to_telegram(messages)
    logger.info("Delivery complete.")