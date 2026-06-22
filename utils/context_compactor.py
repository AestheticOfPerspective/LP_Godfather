"""
Context Compactor — compresses chat history when it exceeds token limits.
Inspired by odysseus pattern: keep recent context, summarize old.

Two-phase strategy:
  Phase 1 — Drop oldest pairs until under limit (lossy, zero cost)
  Phase 2 — LLM-summarize remaining overflow (lossy, one Ollama call)
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3.5
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
MAX_CONTEXT_TOKENS = 6144
RESERVE_PAIRS = 2


def estimate_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN) + 1


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content", "")) + 4
    return total


async def compact_context(
    history: list[dict],
    sys_prompt: str,
    user_message: str,
    ollama_host: str = OLLAMA_HOST,
) -> list[dict]:
    if not history:
        return history

    total = (
        estimate_tokens(sys_prompt)
        + estimate_messages_tokens(history)
        + estimate_tokens(user_message)
    )

    if total <= MAX_CONTEXT_TOKENS:
        return history

    logger.info(
        "[compactor] Total ~%d tokens (limit %d), compacting...",
        total, MAX_CONTEXT_TOKENS,
    )

    # Phase 1: drop oldest pairs until reserve or under limit
    reserve = RESERVE_PAIRS * 2
    while len(history) > reserve:
        history = history[2:]
        total = (
            estimate_tokens(sys_prompt)
            + estimate_messages_tokens(history)
            + estimate_tokens(user_message)
        )
        if total <= MAX_CONTEXT_TOKENS:
            logger.info("[compactor] Dropped oldest pairs, now ~%d tokens", total)
            return history

    # Phase 2: summarize the oldest portion
    compressible = history[:-reserve] if len(history) > reserve else []
    if compressible and total > MAX_CONTEXT_TOKENS:
        summary = await _summarize_segment(compressible, ollama_host)
        if summary:
            history = (
                [{"role": "system", "content": f"[Verlauf]: {summary}"}]
                + history[-reserve:]
            )
            logger.info("[compactor] Summarized %d messages, now ~%d tokens",
                        len(compressible),
                        estimate_tokens(sys_prompt)
                        + estimate_messages_tokens(history)
                        + estimate_tokens(user_message))

    return history


async def _summarize_segment(messages: list[dict], ollama_host: str) -> str:
    text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    prompt = (
        "Fasse die folgende Konversation in 2-3 Sätzen auf Deutsch zusammen. "
        "Behalte wichtige Fakten, Entscheidungen und User-Infos.\n\n"
        f"{text}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": 256},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{ollama_host}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"].strip()
    except Exception as e:
        logger.warning("[compactor] Summarization failed: %s", e)
        return ""
