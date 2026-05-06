"""
Fetch today's UPSC - relevant news.

Search strategy (priority order):
  1. Tavily Search API  — returns rich snippets with full content extracts;
                          no scraping needed when it works.
  2. DuckDuckGo (DDGS)  — free fallback; snippets only, scraper fills the rest.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date

from tavily import TavilyClient
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

UPSC_SEARCH_QUERIES = [
    "India government policy news today",
    "India economy RBI budget news today",
    "India environment climate news today",
    "India foreign affairs international relations today",
    "India science technology space news today",
    "India social issues governance news today",
]


@dataclass
class Article:
    title: str
    url: str
    snippet: str
    source: str = ""
    full_text: str = field(default="", repr=False)
    # Flag set to True when Tavily already returned full content —
    # the scraper will skip these to avoid redundant HTTP calls.
    content_ready: bool = False

# fetch news by tavily api
def _fetch_via_tavily(
        max_articles: int,
        today: str,
) -> list[Article]:
    """
    """
    API_KEY = os.getenv("TAVILY_API_KEY")
    if not API_KEY:
        logger.info("tavily api key not set")
        return []

    client = TavilyClient(api_key=API_KEY)
    seen_urls: str[str] = set()
    articles: list[Article] = []

    for query in UPSC_SEARCH_QUERIES:
        if len(articles) >= max_articles:
            break

        try:
            response = client.search(
                query=f"{query} {today}",
                search_depth="advanced",
                topic="news",
                days=1,
                max_results=3,
                include_raw_content=True
            )

            for r in response.get("results", []):
                url = r.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                full_text = (r.get("raw_content") or r.get("content") or "").strip()

                articles.append(Article(
                    title=r.get("title", ""),
                    url=url,
                    snippet=r.get("content", ""),
                    source=url.split("/")[2] if "/" in url else "",
                    full_text=full_text[:4_000],
                    content_ready=bool(full_text)
                ))
                if len(articles) >= max_articles:
                    break

        except Exception as exc:
            logger.warning("Tavily query failed (%s): %s", query, exc)

    logger.info("Tavily fetched %d articles.", len(articles))
    return articles

def _fetch_via_ddg(
        max_articles: int,
        today: str,
        seen_urls: set[str],
) -> list[Article]:
    """
    """
    articles: list[Article] = []

    with DDGS() as ddgs:
        for query in UPSC_SEARCH_QUERIES:
            if len(articles) >= max_articles:
                break
            try:
                results = ddgs.news(
                    f"{query} {today}",
                    max_results=4,
                    safesearch="moderate",
                )

                for r in results:
                    url = r.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    articles.append(Article(
                        title=r.get("title", ""),
                        url=url,
                        snippet=r.get("body",""),
                        source=r.get("source", "")
                    ))
                    if len(articles) >= max_articles:
                        break
            except Exception as exc:
                logger.warning("DDG query failed (%s): %s", query, exc)
        logger.info("DDG fetched %d articles.", len(articles))
    return articles

def fetch_news(max_articles: int | None = None) -> list[Article]:
    """
    Return a deduplicated list of UPSC-relevant :class:`Article` objects.
 
    Decision tree:
      • If TAVILY_API_KEY is set → use Tavily (richer, content_ready=True).
      • If Tavily returns < max_articles → top up with DDG.
      • If TAVILY_API_KEY is absent → use DDG only.
    """
    max_articles = max_articles or int(os.getenv("MAX_ARTICLES", "10"))
    today = date.today().strftime("%B %d, %Y")
 
    articles = _fetch_via_tavily(max_articles, today)
 
    # Top-up with DDG if Tavily didn't fill the quota (or isn't configured)
    if len(articles) < max_articles:
        seen = {a.url for a in articles}
        remaining = max_articles - len(articles)
        ddg_articles = _fetch_via_ddg(remaining, today, seen)
        articles.extend(ddg_articles)
 
    logger.info("Total articles fetched: %d", len(articles))
    return articles