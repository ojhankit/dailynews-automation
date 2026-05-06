from __future__ import annotations
 
import logging
from dataclasses import dataclass
 
from src.news_fetcher import Article
from src.llm_client import call_llm
from src.config import MAX_SUMMARY_ARTICLES
 
logger = logging.getLogger(__name__)
 
SUMMARY_PROMPT = """\
You are an expert UPSC mentor. Summarise the following news article for a UPSC Civil Services aspirant.
 
Article Title : {title}
Article Text  :
{text}
 
Respond STRICTLY in this format (no extra text, no markdown headers outside the labels):
 
WHAT HAPPENED:
<2-3 sentences describing the key event or development>
 
WHY IT MATTERS:
<2-3 sentences on the broader significance — policy, society, economy, or geopolitics>
 
UPSC RELEVANCE:
<1-2 sentences on how this may appear in Prelims/Mains and which GS Paper it relates to>
 
GS PAPER: <one of: GS1 | GS2 | GS3 | GS4>
 
KEYWORDS: <comma-separated list of 4-6 important keywords/phrases for revision>
"""
 
 
@dataclass
class SummarisedArticle:
    article: Article
    what_happened: str = ""
    why_it_matters: str = ""
    upsc_relevance: str = ""
    gs_paper: str = ""
    keywords: list[str] = None  # type: ignore[assignment]
 
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
 
 
def _parse_response(raw: str) -> dict:
    """Extract labelled fields from the LLM's structured response."""
    fields = {
        "what_happened": "",
        "why_it_matters": "",
        "upsc_relevance": "",
        "gs_paper": "GS3",
        "keywords": [],
    }
    current_key = None
    buffer: list[str] = []
 
    label_map = {
        "WHAT HAPPENED:": "what_happened",
        "WHY IT MATTERS:": "why_it_matters",
        "UPSC RELEVANCE:": "upsc_relevance",
        "GS PAPER:": "gs_paper",
        "KEYWORDS:": "keywords",
    }
 
    for line in raw.splitlines():
        stripped = line.strip()
        matched = False
        for label, key in label_map.items():
            if stripped.upper().startswith(label):
                if current_key and buffer:
                    _flush(fields, current_key, buffer)
                current_key = key
                rest = stripped[len(label):].strip()
                buffer = [rest] if rest else []
                matched = True
                break
        if not matched and current_key:
            buffer.append(stripped)
 
    if current_key and buffer:
        _flush(fields, current_key, buffer)
 
    return fields
 
 
def _flush(fields: dict, key: str, buffer: list[str]) -> None:
    text = " ".join(b for b in buffer if b)
    if key == "keywords":
        fields[key] = [k.strip() for k in text.split(",") if k.strip()]
    elif key == "gs_paper":
        # Normalise to "GS1" … "GS4"
        for gs in ("GS1", "GS2", "GS3", "GS4"):
            if gs in text.upper():
                fields[key] = gs
                return
        fields[key] = "GS3"
    else:
        fields[key] = text
 
 
def summarise_article(article: Article) -> SummarisedArticle:
    """Call the LLM and return a :class:`SummarisedArticle`."""
    text = article.full_text or article.snippet
    prompt = SUMMARY_PROMPT.format(title=article.title, text=text[:3500])
    try:
        raw = call_llm(prompt)
        parsed = _parse_response(raw)
        return SummarisedArticle(article=article, **parsed)
    except Exception as exc:
        logger.error("Summarisation failed for '%s': %s", article.title, exc)
        return SummarisedArticle(
            article=article,
            what_happened=article.snippet,
            why_it_matters="Could not generate summary.",
            upsc_relevance="Please read the article directly.",
            gs_paper="GS3",
            keywords=[],
        )
 
 
def summarise_all(
    articles: list[Article], max_summaries: int | None = None
) -> list[SummarisedArticle]:
    """Summarise up to *max_summaries* articles."""
    limit = max_summaries or MAX_SUMMARY_ARTICLES
    results = []
    for art in articles[:limit]:
        logger.info("Summarising: %s", art.title)
        results.append(summarise_article(art))
    return results