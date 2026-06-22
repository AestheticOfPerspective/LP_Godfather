"""
handlers/comedy_test.py — Comedy Gate Checker fuer /comedy-test
Prueft Clip-Ideen gegen JutsuGaming Comedy Gates via lokales Ollama.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

COMEDY_SYSTEM_PROMPT = (
    "Du pruefst Clip-Ideen gegen die JutsuGaming Comedy Gates.\n\n"
    "Bewerte jede Idee nach diesen 4 Gates:\n\n"
    "1. SATIRE: Ist das Ziel klar erkennbar? Systemkritik oder Personenkritik?\n"
    "   - OK Ziel klar (System/Verhalten/Produkt)\n"
    "   - FAIL Ziel vage oder Personengerichtet\n\n"
    "2. IRONY: Ist der Kontrast ohne privates Kontext verstaendlich?\n"
    "   - OK Kontrast sofort klar fuer Aussenstehende\n"
    "   - FAIL Braucht Insiderwissen zum Verstaendnis\n\n"
    "3. DARK HUMOR: Trifft das System/Selbst, nicht Personen?\n"
    "   - OK System/Selbst ist Ziel\n"
    "   - FAIL Person/Trauma/Identitaet ist Ziel\n\n"
    "4. DE/EN/RU SAFE: Funktioniert der Humor in der Zielsprache ohne Target-Shift?\n"
    "   - OK Uebersetzbar ohne Ziel-Verschiebung\n"
    "   - FAIL Humor geht in Uebersetzung verloren oder trifft falsches Ziel\n\n"
    "Antworte NUR im folgenden Format - keine Einleitung, kein Kommentar:\n\n"
    "SATIRE: OK/FAIL - kurze Begruendung\n"
    "IRONY: OK/FAIL - kurze Begruendung\n"
    "DARK_HUMOR: OK/FAIL - kurze Begruendung\n"
    "SAFE: OK/FAIL - kurze Begruendung\n"
    "GESAMT: PASS/REVISE/BLOCK - kurze Begruendung"
)


async def check_clip(idea: str) -> str:
    if not idea:
        return (
            "SATIRE: FAIL - keine Idee zum Pruefen\n"
            "IRONY: FAIL - keine Idee zum Pruefen\n"
            "DARK_HUMOR: FAIL - keine Idee zum Pruefen\n"
            "SAFE: FAIL - keine Idee zum Pruefen\n"
            "GESAMT: BLOCK - Leereingabe ist kein Clip"
        )
    messages = [
        {"role": "system", "content": COMEDY_SYSTEM_PROMPT},
        {"role": "user", "content": f"Clip-Idee: {idea}"},
    ]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 300, "temperature": 0.3},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OLLAMA_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", str(data)).strip()
    except httpx.ConnectError:
        return "⚠️ Ollama nicht erreichbar. Starte den Container auf Beast."
    except httpx.TimeoutException:
        return "⏱️ Timeout — Comedy-Gate-Denk-Schleife zu lang."
    except Exception as e:
        logger.error(f"Comedy test error: {e}")
        return f"❌ Fehler: {e}"
