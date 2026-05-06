from __future__ import annotations

from collections import defaultdict

from src.agents.summariser import SummarisedArticle

GS_DESCRIPTIONS = {
    "GS1": "History, Geography & Society",
    "GS2": "Polity, Governance & International Relations",
    "GS3": "Economy, Environment & Science-Technology",
    "GS4": "Ethics, Integrity & Aptitude",
}

GS_ORDER = ["GS1", "GS2", "GS3", "GS4"]


def classify(
    summaries: list[SummarisedArticle],
) -> dict[str, list[SummarisedArticle]]:
    """
    Return an ordered dict mapping GS paper label → list of articles.
    Only papers with ≥1 article are included.
    """
    grouped: dict[str, list[SummarisedArticle]] = defaultdict(list)
    for s in summaries:
        gs = s.gs_paper if s.gs_paper in GS_ORDER else "GS3"
        grouped[gs].append(s)

    # Return in canonical GS order
    return {gs: grouped[gs] for gs in GS_ORDER if grouped[gs]}