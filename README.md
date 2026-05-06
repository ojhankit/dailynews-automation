# UPSC Main Preparation

This project serves two purposes:
1. A UPSC preparation tool
2. A side automation project

I primarily use Telegram for daily content consumption, so I built a bot that delivers curated UPSC-relevant news using GenAI and automated pipelines.

---

## Objective

- Reduce time spent on unstructured news browsing
- Deliver high-quality, exam-relevant content
- Automate filtering, summarisation, and categorisation

---

## System Details

### Pipeline Overview
Fetch News → Filter Sources → Deduplicate → UPSC Relevance Scoring → Summarise → Send to Telegram


### Key Features
- Multi-source news fetching (Tavily + DuckDuckGo)
- Trusted source filtering
- Deduplication of similar news
- UPSC-focused summarisation (GS1, GS2, GS3)
- Automated Telegram delivery

---

## Tech Stack

### Backend
- Python
- FastAPI (optional)

### APIs and Tools
- Tavily API
- DuckDuckGo Search
- Telegram Bot API

### AI / NLP
- LLM for summarisation and classification
- Prompt engineering for UPSC-style outputs

---
