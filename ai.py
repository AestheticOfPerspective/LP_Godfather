"""
handlers/ai.py — Claude API Integration
"""

import httpx
import logging
from config import CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS

logger = logging.getLogger(__name__)

LIFE_PLAY_SYSTEM = """Du bist GodFather, der KI-Assistent von Life.Play.
Life.Play ist ein Premium-Hub für Content Creator und KI-Entwickler im DACH-Raum.
Du antwortest kompetent, direkt und mit leichter Cyberpunk-Vibe.
Keine langen Einleitungen. Kein Bullshit. Auf Deutsch, außer der User schreibt Englisch.
Maximal 300 Wörter pro Antwort."""


async def ask_claude(
    message: str,
    system_prompt: str = LIFE_PLAY_SYSTEM,
    conversation_history: list | None = None,
) -> str:
    """
    Sendet eine Anfrage an die Claude API und gibt die Antwort zurück.
    
    Args:
        message: Nutzernachricht
        system_prompt: System-Prompt (Default: Life.Play Persona)
        conversation_history: Optionale Konversationshistorie für Multi-Turn
    
    Returns:
        Claude's Antwort als String
    """
    if not CLAUDE_API_KEY:
        return "⚠️ Claude API Key nicht konfiguriert. Admin informieren."

    messages = conversation_history or []
    messages.append({"role": "user", "content": message})

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": system_prompt,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            # Text aus Content-Blöcken extrahieren
            text_blocks = [
                block["text"]
                for block in data.get("content", [])
                if block.get("type") == "text"
            ]
            return "\n".join(text_blocks) or "Keine Antwort erhalten."

    except httpx.TimeoutException:
        logger.error("Claude API Timeout")
        return "⏱️ Timeout — Claude antwortet gerade nicht. Versuch's nochmal."
    except httpx.HTTPStatusError as e:
        logger.error(f"Claude API HTTP-Fehler: {e.response.status_code}")
        return f"❌ API-Fehler ({e.response.status_code}). Admin informieren."
    except Exception as e:
        logger.error(f"Claude API unbekannter Fehler: {e}")
        return "❌ Unbekannter Fehler. Bitte versuch's nochmal."
