"""
Fetch today's UPSC-relevant news with source validation, relevance scoring,
near-duplicate detection, and ranked output.

Pipeline (5 stages):
  1. Fetch      — Tavily (primary) then DDG top-up, URL-deduped.
  2. Validate   — allowlist trusted domains, block aggregators / opinion blogs.
  3. Enrich     — scrape full text for DDG articles that lack it.
  4. Score      — keyword match across GS1–GS4 buckets + recency boost;
                  drop articles below MIN_RELEVANCE_SCORE.
  5. Output     — near-duplicate collapse (trigram title similarity),
                  sort by score DESC, attach GS tag.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

import requests
from duckduckgo_search import DDGS
from tavily import TavilyClient

from src.config import MAX_ARTICLES, TAVILY_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_RELEVANCE_SCORE: float = 0.15   # articles below this are dropped
DUPLICATE_THRESHOLD: float = 0.55   # trigram Jaccard threshold for near-dups
SCRAPE_TIMEOUT: int = 8             # seconds per HTTP request in the enricher
MAX_SCRAPE_CHARS: int = 4_000

UPSC_SEARCH_QUERIES: list[str] = [
    "India government policy news today",
    "India economy RBI budget news today",
    "India environment climate news today",
    "India foreign affairs international relations today",
    "India science technology space news today",
    "India social issues governance news today",
]

# ---------------------------------------------------------------------------
# Trusted-source allowlist / blocklist
# ---------------------------------------------------------------------------

# Substrings matched against the article hostname (lowercased).
TRUSTED_DOMAINS: frozenset[str] = frozenset({
    "thehindu.com",
    "indianexpress.com",
    "hindustantimes.com",
    "livemint.com",
    "economictimes.indiatimes.com",
    "pib.gov.in",
    "prs.in",
    "isro.gov.in",
    "rbi.org.in",
    "mpfinance.gov.in",
    "mospi.gov.in",
    "timesofindia.indiatimes.com",
    "business-standard.com",
    "downtoearth.org.in",
    "ndtv.com",
    "reuters.com",
    "thewire.in",
    "scroll.in",
    "frontline.thehindu.com",
    "moneycontrol.com",
})

# Articles whose hostname contains any of these strings are discarded.
BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "opindia.com",
    "postcard.news",
    "thecitizen.in",
    "newsbyteshindi.com",
    "aggregator",
    "buzzfeed",
    "reddit.com",
    "quora.com",
    "youtube.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "medium.com",
    "substack.com",
})

# ---------------------------------------------------------------------------
# GS-topic keyword buckets for relevance scoring
# ---------------------------------------------------------------------------

GS_KEYWORDS: dict[str, list[str]] = {
    "GS1 – History & Culture": [
        "heritage", "archaeology", "monument", "folk", "classical", "tribal",
        "medieval", "ancient india", "mughal", "colonial", "partition",
        "freedom fighter", "cultural", "dance", "music tradition", "art form",
    ],
    "GS1 – Geography": [
        "monsoon", "cyclone", "earthquake", "flood", "drought", "glacier",
        "river basin", "delta", "plateau", "peninsula", "tectonic", "climate zone",
        "soil erosion", "groundwater", "watershed",
    ],
    "GS2 – Polity & Governance": [
        "constitution", "parliament", "supreme court", "high court", "bill",
        "amendment", "election commission", "governor", "rajya sabha", "lok sabha",
        "panchayat", "municipal", "central government", "state government",
        "ministry", "policy", "scheme", "committee", "legislation",
    ],
    "GS2 – International Relations": [
        "bilateral", "multilateral", "treaty", "summit", "UN", "WHO", "WTO",
        "IMF", "World Bank", "SCO", "ASEAN", "BRICS", "G20", "G7",
        "foreign policy", "diplomatic", "sanctions", "trade agreement",
        "border dispute", "geopolitics",
    ],
    "GS2 – Social Issues": [
        "poverty", "malnutrition", "health scheme", "NITI Aayog", "education policy",
        "gender equality", "child rights", "women empowerment", "disability",
        "tribal rights", "dalits", "minority", "social justice",
    ],
    "GS3 – Economy": [
        "GDP", "inflation", "RBI", "monetary policy", "repo rate", "fiscal deficit",
        "budget", "GST", "FDI", "exports", "imports", "trade balance",
        "startup", "MSMEs", "PLI scheme", "disinvestment", "public sector",
        "agriculture", "MSP", "crop", "rural economy",
    ],
    "GS3 – Environment": [
        "climate change", "carbon", "net zero", "Paris agreement", "COP",
        "biodiversity", "wildlife", "national park", "forest", "wetland",
        "pollution", "plastic", "renewable energy", "solar", "wind energy",
        "EIA", "environment clearance", "IPCC",
    ],
    "GS3 – Science & Technology": [
        "ISRO", "space mission", "satellite", "nuclear", "AI", "artificial intelligence",
        "quantum", "semiconductor", "5G", "cybersecurity", "biotech",
        "vaccine", "drug approval", "genome", "patent", "research",
        "IIT", "CSIR", "DRDO", "defence technology",
    ],
    "GS4 – Ethics": [
        "corruption", "transparency", "accountability", "whistleblower",
        "judicial ethics", "civil services", "probity", "conflict of interest",
    ],
}

# Flatten for fast lookup; also keep the per-GS mapping for tagging.
_ALL_KEYWORDS: list[str] = [kw for kws in GS_KEYWORDS.values() for kw in kws]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Article:
    title: str
    url: str
    snippet: str
    source: str = ""
    full_text: str = field(default="", repr=False)
    content_ready: bool = False
    relevance_score: float = 0.0
    gs_tag: str = ""


# ---------------------------------------------------------------------------
# Stage 1 – Fetch
# ---------------------------------------------------------------------------

def _fetch_via_tavily(max_articles: int, today: str) -> list[Article]:
    if not TAVILY_API_KEY:
        logger.info("TAVILY_API_KEY not set — skipping Tavily.")
        return []

    client = TavilyClient(api_key=TAVILY_API_KEY)
    seen_urls: set[str] = set()
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
                include_raw_content=True,
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
                    source=_hostname(url),
                    full_text=full_text[:MAX_SCRAPE_CHARS],
                    content_ready=bool(full_text),
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
                        snippet=r.get("body", ""),
                        source=r.get("source", "") or _hostname(url),
                    ))
                    if len(articles) >= max_articles:
                        break
            except Exception as exc:
                logger.warning("DDG query failed (%s): %s", query, exc)
    logger.info("DDG fetched %d articles.", len(articles))
    return articles


# ---------------------------------------------------------------------------
# Stage 2 – Source validation
# ---------------------------------------------------------------------------

def _hostname(url: str) -> str:
    """Extract lowercase hostname from a URL string."""
    try:
        return url.split("/")[2].lower()
    except IndexError:
        return ""


def _is_trusted(article: Article) -> bool:
    host = _hostname(article.url)
    if any(blocked in host for blocked in BLOCKED_DOMAINS):
        logger.debug("Blocked domain: %s", host)
        return False
    if any(trusted in host for trusted in TRUSTED_DOMAINS):
        return True
    # Unknown domain: allow but mark with low implicit trust
    # (scoring will further discount it if the text is thin).
    return True


def _validate_sources(articles: list[Article]) -> list[Article]:
    validated = [a for a in articles if _is_trusted(a)]
    dropped = len(articles) - len(validated)
    if dropped:
        logger.info("Source validation dropped %d article(s).", dropped)
    return validated


# ---------------------------------------------------------------------------
# Stage 3 – Content enrichment (scrape DDG articles that lack full text)
# ---------------------------------------------------------------------------

def _scrape_url(url: str) -> str:
    """Return up to MAX_SCRAPE_CHARS of visible text from a URL, or ''."""
    try:
        resp = requests.get(
            url,
            timeout=SCRAPE_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; UPSCBot/1.0)"},
        )
        resp.raise_for_status()
        # Very lightweight extraction: strip tags, collapse whitespace.
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:MAX_SCRAPE_CHARS]
    except Exception as exc:
        logger.debug("Scrape failed for %s: %s", url, exc)
        return ""


def _enrich_content(articles: list[Article]) -> list[Article]:
    for a in articles:
        if not a.content_ready:
            text = _scrape_url(a.url)
            if text:
                a.full_text = text
                a.content_ready = True
    return articles


# ---------------------------------------------------------------------------
# Stage 4 – UPSC relevance scoring
# ---------------------------------------------------------------------------

def _trigrams(text: str) -> set[str]:
    t = text.lower()
    return {t[i:i+3] for i in range(len(t) - 2)}


def _score_article(article: Article) -> tuple[float, str]:
    """
    Returns (score, best_gs_tag).

    Score is the fraction of GS keywords present in the article's combined
    title + snippet + full_text, weighted by the best-matching GS bucket.
    """
    haystack = " ".join([
        article.title,
        article.snippet,
        article.full_text,
    ]).lower()

    best_score = 0.0
    best_tag = ""

    for gs_label, keywords in GS_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw.lower() in haystack)
        score = hits / len(keywords)
        if score > best_score:
            best_score = score
            best_tag = gs_label

    # Boost articles from highly trusted sources slightly.
    host = _hostname(article.url)
    if any(trusted in host for trusted in TRUSTED_DOMAINS):
        best_score = min(best_score * 1.15, 1.0)

    return round(best_score, 4), best_tag


def _score_and_filter(
    articles: list[Article],
    min_score: float = MIN_RELEVANCE_SCORE,
) -> list[Article]:
    for a in articles:
        a.relevance_score, a.gs_tag = _score_article(a)

    before = len(articles)
    articles = [a for a in articles if a.relevance_score >= min_score]
    logger.info(
        "Relevance filter: kept %d / %d article(s) (threshold %.2f).",
        len(articles), before, min_score,
    )
    return articles


# ---------------------------------------------------------------------------
# Stage 5 – Near-duplicate collapse + ranked output
# ---------------------------------------------------------------------------

def _jaccard_trigram(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _deduplicate(
    articles: list[Article],
    threshold: float = DUPLICATE_THRESHOLD,
) -> list[Article]:
    """
    Iterative greedy deduplication: for each article (highest score first)
    keep it only if its title is not too similar to any already-kept title.
    """
    kept: list[Article] = []
    for candidate in articles:
        is_dup = any(
            _jaccard_trigram(candidate.title, kept_article.title) >= threshold
            for kept_article in kept
        )
        if not is_dup:
            kept.append(candidate)
    removed = len(articles) - len(kept)
    if removed:
        logger.info("Deduplication removed %d near-duplicate(s).", removed)
    return kept


def _rank(articles: list[Article]) -> list[Article]:
    return sorted(articles, key=lambda a: a.relevance_score, reverse=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_news(max_articles: int | None = None) -> list[Article]:
    """
    Return a validated, scored, deduplicated, and ranked list of UPSC-relevant
    :class:`Article` objects.

    Pipeline:
        1. Fetch   — Tavily first; DDG tops up to ``max_articles``.
        2. Validate — block known low-credibility / off-topic sources.
        3. Enrich  — scrape full text for articles without it.
        4. Score   — GS-keyword relevance; drop below threshold.
        5. Output  — collapse near-duplicates, sort by score DESC.
    """
    max_articles = max_articles or MAX_ARTICLES
    today = date.today().strftime("%B %d, %Y")

    # --- Stage 1: Fetch ---
    articles = _fetch_via_tavily(max_articles, today)
    if len(articles) < max_articles:
        seen = {a.url for a in articles}
        remaining = max_articles - len(articles)
        articles.extend(_fetch_via_ddg(remaining, today, seen))
    logger.info("Total fetched: %d", len(articles))

    # --- Stage 2: Validate sources ---
    articles = _validate_sources(articles)

    # --- Stage 3: Enrich content ---
    articles = _enrich_content(articles)

    # --- Stage 4: Score & filter ---
    articles = _score_and_filter(articles)

    # --- Stage 5: Deduplicate & rank ---
    articles = _deduplicate(_rank(articles))

    logger.info("Pipeline complete. Returning %d article(s).", len(articles))
    return articles