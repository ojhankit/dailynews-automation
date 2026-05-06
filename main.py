"""
main.py — UPSC Daily News Agent orchestrator.

Pipeline:
  1. Fetch news (DuckDuckGo)
  2. Scrape full article text
  3. Summarise with LLM (Gemini → Groq fallback)
  4. Classify into GS Papers
  5. Deliver via Telegram
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv

from src.agents.classifier import classify
from src.agents.summariser import summarise_all
from src.news_fetcher import fetch_news
from src.scraper import enrich_articles
from src.telegram_sender import deliver
from src.logger import setup_logger
from src import config

load_dotenv()
logger = setup_logger("upsc_agent")
config.validate()  # fail fast if required env vars are missing


def run() -> None:
    logger.info("=" * 50)
    logger.info("  UPSC Daily News Agent — starting run")
    logger.info("=" * 50)

    # ── Step 1: Fetch ─────────────────────────────────
    logger.info("[1/5] Fetching news …")
    articles = fetch_news()
    if not articles:
        logger.error("No articles fetched — aborting.")
        sys.exit(1)

    # ── Step 2: Scrape ────────────────────────────────
    logger.info("[2/5] Scraping article content …")
    articles = enrich_articles(articles)

    # ── Step 3: Summarise ─────────────────────────────
    logger.info("[3/5] Summarising with LLM …")
    summaries = summarise_all(articles)
    if not summaries:
        logger.error("No summaries generated — aborting.")
        sys.exit(1)

    # ── Step 4: Classify ──────────────────────────────
    logger.info("[4/5] Classifying into GS Papers …")
    classified = classify(summaries)
    for gs, arts in classified.items():
        logger.info("  %s: %d article(s)", gs, len(arts))

    # ── Step 5: Deliver ───────────────────────────────
    logger.info("[5/5] Delivering to Telegram …")
    deliver(classified)

    logger.info("=" * 50)
    logger.info("  Run complete ✓")
    logger.info("=" * 50)


if __name__ == "__main__":
    run()