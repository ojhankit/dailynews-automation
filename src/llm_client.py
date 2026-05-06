"""
llm_client.py — LLM wrapper.

Primary model : Gemini (google-generativeai via langchain-google-genai)
Fallback model: Groq   (llama3 via langchain-groq)

All configuration is sourced from src.config so there is a single place
to adjust keys, model names, temperature, and token limits.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from src.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

logger = logging.getLogger(__name__)


def _gemini() -> ChatGoogleGenerativeAI:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=LLM_TEMPERATURE,
        max_output_tokens=LLM_MAX_TOKENS,
    )


def _groq() -> ChatGroq:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set.")
    return ChatGroq(
        model=GROQ_MODEL,
        groq_api_key=GROQ_API_KEY,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )


def call_llm(prompt: str) -> str:
    """
    Send *prompt* to the primary LLM; fall back to the secondary on any exception.

    Returns the model's text response as a plain string.
    Raises RuntimeError if every provider fails.
    """
    for name, build_client in [("Gemini", _gemini), ("Groq", _groq)]:
        try:
            logger.info("Calling %s …", name)
            llm = build_client()
            response = llm.invoke([HumanMessage(content=prompt)])
            text = response.content.strip()
            logger.info("%s responded (%d chars).", name, len(text))
            return text
        except Exception as exc:
            logger.warning("%s failed: %s — trying next provider.", name, exc)

    raise RuntimeError(
        "All LLM providers failed. Check API keys and quotas in your .env file."
    )