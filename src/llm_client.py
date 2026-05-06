"""
llm_client.py — LLM wrapper.

Primary model : Gemini (google-generativeai via langchain-google-genai)
Fallback model: Groq   (llama3 via langchain-groq)

All configuration is sourced from src.config so there is a single place
to adjust keys, model names, temperature, and token limits.
"""

from __future__ import annotations
 
import logging
import os
 
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
 
logger = logging.getLogger(__name__)
 
 
def _gemini() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",        
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=0.3,
        max_output_tokens=2048,
    )
 
 
def _groq() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0.3,
        max_tokens=2048,
    )
 
 
def call_llm(prompt: str) -> str:
    """
    Send *prompt* to the primary LLM (Gemini).
    Automatically falls back to Groq on any exception.
 
    Returns the model's text response as a plain string.
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
 
    raise RuntimeError("All LLM providers failed. Check API keys and quotas.")