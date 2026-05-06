from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from scraperapi import ScraperAPIClient

from src.news_fetcher import Article
from src.config import SCRAPER_API_KEY

logger = logging.getLogger(__name__)

client = ScraperAPIClient(SCRAPER_API_KEY)

MAX_CHARS = 4000


def _clean(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _parse(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()

    container = soup.find("article") or soup.find("main") or soup.body
    if not container:
        return ""

    return _clean(container.get_text(separator="\n"))


def scrape_article(article: Article) -> str:
    try:
        response = client.get(
            article.url,
            params={
                "render": "false",  # set true for JS-heavy sites
                "country_code": "in",  # better for Indian news
            },
        )

        html = response.text
        text = _parse(html)

        if text:
            return text[:MAX_CHARS]

    except Exception as e:
        logger.warning("ScraperAPI failed (%s): %s", article.url, e)

    return article.snippet


def enrich_articles(articles: list[Article]) -> list[Article]:
    for art in articles:
        if not art.content_ready:
            art.full_text = scrape_article(art)
    return articles