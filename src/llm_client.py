"""
LLM wrapper
Primary model: Gemini
Fallback:      Groq
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
        model="gemini-1.5-flash",
        google_api_key=os.environ("GEMINI_API_KEY"),
        temperature=0.3, # declare var inside env
        max_output_tokens=2048 # can declare var inside env
    )

def _groq() -> ChatGroq:
    return ChatGroq(
        model='llama3-8b-8192',
        groq_api_key=os.environ("GROQ_API_KEY"),
        temperature=0.3,
        max_tokens=2048,
    )

def call_llm(prompt: str) -> str:
    """
    Send prompt to primary llm, fallback to secondary llm in case of any exception

    returns the model's text as response
    """

    for name, build_client in [("Gemini", _gemini), ("Groq", _groq)]:
        try:
            logger.info("Calling %s - ", name)
            llm = build_client()
            response = llm.invoke([HumanMessage(content=prompt)])
            text = response.content.strip()
            logger.info("%s responded (%d chars).", name, len(text))
            return text
        except Exception as exc:
            logger.warning("%s failed: %s - trying next provider.", name, exc)
    
    raise RuntimeError("All LLM providers failed. Check API keys and quotes.")