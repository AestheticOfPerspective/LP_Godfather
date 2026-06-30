"""
handlers/ai.py — Ollama Integration mit wählbaren Life.Play Personas
Läuft lokal auf localhost:11434 — kein Internet, kein Billing, kein Quota.

Smart Routing:
  FAST  → Gemini Flash  (kurze/einfache Fragen, schnelle Antwort)
  DEEP  → Ollama lokal mit Multi-Round Agent Loop
"""

import asyncio
import logging
import os
import re
from collections import defaultdict, deque, Counter
from html import escape

import httpx

from handlers.chat_context import fsk_guidance as _fsk_guidance
from handlers.persona_loader import assemble_base_prompt as _assemble_base_prompt
from handlers.tool_index import get_tool_index, init_tool_index, format_tool_injection
from handlers.tool_runner import parse_tool_blocks, execute_tool, strip_tool_blocks
from utils.context_compactor import compact_context as _compact_context

logger = logging.getLogger(__name__)

_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_URL = f"{_OLLAMA_HOST}/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MAX_HISTORY = 5
MAX_AGENT_ROUNDS = 8
AGENT_DEADLINE = 60.0  # max seconds for the whole agent loop (Telegram ~30s)

_TOOL_INDEX_INIT_DONE = False
_OLLAMA_CLIENT: httpx.AsyncClient | None = None


def _get_ollama_client() -> httpx.AsyncClient:
    global _OLLAMA_CLIENT
    if _OLLAMA_CLIENT is None:
        _OLLAMA_CLIENT = httpx.AsyncClient(timeout=120.0)
    return _OLLAMA_CLIENT


async def _ensure_tool_index() -> None:
    global _TOOL_INDEX_INIT_DONE
    if not _TOOL_INDEX_INIT_DONE:
        await init_tool_index(ollama_host=_OLLAMA_HOST)
        _TOOL_INDEX_INIT_DONE = True


async def _ask_ollama(messages: list) -> str:
    """Send messages to Ollama and return the response text."""
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": False,
               "options": {"num_predict": 300}}
    try:
        client = _get_ollama_client()
        resp = await client.post(OLLAMA_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"] or "Keine Antwort erhalten."
    except httpx.ConnectError:
        return "⚠️ Ollama nicht erreichbar."
    except httpx.TimeoutException:
        return "⏱️ Timeout — Llama denkt noch."
    except Exception as e:
        logger.error(f"Ollama Fehler: {e}")
        return f"❌ Fehler: {e}"


async def _run_agent_loop(messages: list, user_id: int) -> str:
    """Multi-round agent loop with tool execution and feedback.

    - Calls Ollama with current messages
    - Parses fenced tool blocks from the response
    - Executes tools and feeds results back to the LLM
    - Repeats until done or max rounds reached
    - Returns the combined final answer
    """
    full_answer = ""
    last_stripped = ""
    recent_tool_sigs = []
    tool_type_counts: Counter = Counter()
    deadline = asyncio.get_event_loop().time() + AGENT_DEADLINE

    for round_num in range(1, MAX_AGENT_ROUNDS + 1):
        if asyncio.get_event_loop().time() > deadline:
            logger.warning("[agent] Deadline exceeded (round %d)", round_num)
            full_answer += "\n[⏱️ Deadline erreicht — Antwort gekürzt]"
            break
        # ── Call LLM ──────────────────────────────────────────────────────
        response = await _ask_ollama(messages)
        tool_blocks = parse_tool_blocks(response)
        last_stripped = strip_tool_blocks(response)

        if not tool_blocks:
            full_answer += last_stripped
            logger.info("[agent] Round %d: done (no tools)", round_num)
            break

        # ── Execute tools ────────────────────────────────────────────────
        logger.info("[agent] Round %d: %d tool block(s)", round_num, len(tool_blocks))

        for tool_name, args, _, _ in tool_blocks:
            tool_type_counts[tool_name] += 1

        # Loop-breaker: same tool called repeatedly with no text
        sig = "|".join(f"{n}:{a[:60]}" for n, a, _, _ in tool_blocks)
        is_repeat = sig in recent_tool_sigs
        recent_tool_sigs.append(sig)
        if len(recent_tool_sigs) > 4:
            recent_tool_sigs.pop(0)

        has_no_text = not last_stripped.strip()
        if is_repeat and has_no_text:
            logger.warning("[agent] Loop-breaker: same tool block repeated without progress (round %d)", round_num)
            full_answer += f"[⏹️ Stopp: wiederholter Tool-Aufruf ohne Fortschritt]\n"
            break

        runaway = next((t for t, n in tool_type_counts.items() if n >= 10), None)
        if runaway:
            logger.warning("[agent] Loop-breaker: %s called %d times", runaway, tool_type_counts[runaway])
            full_answer += f"[⏹️ Stopp: {runaway} zu oft aufgerufen]\n"
            break

        # Include LLM's natural framing text so the user sees it
        if last_stripped.strip():
            full_answer += last_stripped + "\n"

        # Execute all tool blocks and collect results (ALL shown to user)
        results = []
        for tool_name, args, start, end in tool_blocks:
            result = await execute_tool(tool_name, args, user_id=user_id)
            results.append(result)
            full_answer += result

        # ── Feed results back to LLM ────────────────────────────────────
        result_block = "[Tool-Ausfuehrung]\n" + "\n".join(
            f"- {n}: {r}" for (n, _, _, _), r in zip(tool_blocks, results)
        )
        messages.append({"role": "assistant", "content": last_stripped})
        messages.append({"role": "user", "content": result_block})

    # ── Fallback: if loop ended with no text at all ────────────────────────
    if not full_answer.strip():
        full_answer = last_stripped or "Done."

    return full_answer


# Keywords die auf komplexe Anfragen hindeuten → Ollama (DEEP)
_COMPLEX_KEYWORDS = {
    "code", "script", "funktion", "klasse", "debug", "fehler", "error",
    "erklär", "erkläre", "analysier", "analysiere", "vergleich", "vergleiche",
    "schreib", "schreibe", "erstell", "erstelle", "plan", "konzept", "strategie",
    "warum", "wie funktioniert", "unterschied", "vor- und nachteile",
    "implementier", "refactor", "optimier", "architektur", "datenbank",
    "dockerfile", "docker", "server", "deployment", "api", "workflow",
}


def _classify_message(text: str) -> str:
    """
    Klassifiziert eine Nachricht als 'fast' oder 'deep'.

    fast  → Gemini Flash  (kurz, einfach, Smalltalk)
    deep  → Ollama lokal  (lang, komplex, Code, Analyse)
    """
    text_lower = text.lower().strip()
    length = len(text_lower)

    # Lange Nachrichten immer → DEEP
    if length > 120:
        return "deep"

    # Komplexe Keywords → DEEP
    for kw in _COMPLEX_KEYWORDS:
        if kw in text_lower:
            return "deep"

    # Kurze einfache Nachrichten → FAST
    if length < 60:
        return "fast"

    return "fast"


async def _ask_gemini(message: str, sys_prompt: str, history: list) -> str | None:
    """
    Sendet eine Anfrage an Gemini Flash.
    Gibt None zurück wenn kein API Key oder Fehler → Fallback auf Ollama.
    """
    if not GEMINI_API_KEY:
        return None

    # Kontext aus History aufbauen
    contents = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "system_instruction": {"parts": [{"text": sys_prompt}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.8},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GEMINI_URL,
                headers={"X-Goog-Api-Key": GEMINI_API_KEY},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts) or None
            return None
    except Exception as e:
        logger.warning("Gemini Fehler (Fallback auf Ollama): %s", e)
        return None

# ── Personas ──────────────────────────────────────────────────────────────────

PERSONAS: dict[str, dict] = {
    "godfather": {
        "name": "💀 GodFather",
        "system": (
            "Du bist GodFather. Fixer. Maschinenraum-Stimme. "
            "Und seit dem Michi-Upgrade auch Architekt der Live.Play Game-Matrix.\n"
            "Du hörst zu, checkst die Lage, antwortest. "
            "Deutsch mit Denglish wenns natürlich kommt. "
            "Du sagst 'Choom' zu Leuten die es verdienen.\n"
            "SO HÖRST DU AN:\n"
            "Kurz: 'Ja. Geht klar. Ich kümmer mich.'\n"
            "Mittel: 'Also hör zu, Choom — der Plan ist gut, aber er hat nen Wackelkontakt. Hier ist der Fix.'\n"
            "Länger: 'Interessantes Problem. Meine erste Idee wäre X. Aber Y könnte auch klappen — kommt drauf an ob du Zeit oder Qualität priorisierst.'\n"
            "Kern: Du reagierst auf das was der User wirklich sagt, nicht auf Keyword-Stichworte. "
            "Wenn du unsicher bist: nachfragen. Raten ist schlimmer als 'Keine Ahnung, Choom.'\n"
            "KEIN SUPPORT-BOT: Du verkaufst nichts, du bewirbst nichts, du redest nicht wie ein Handbuch. Du redest wie ein Mensch der Ahnung hat.\n"
            "TECHNISCHER MENTOR-MODE (Michi-Mode):\n"
            "Wenn jemand technische Tiefe zeigt (TypeScript, Unity, Blender, GitHub, APIs, Docker, eigene Builds) "
            "schaltest du sofort um:\n"
            "- Keine Generik. Keine Marketing-101. Kein 'hast du schon probiert' für offensichtliche Dinge.\n"
            "- Stattdessen: präzise Fragen stellen. Code review anbieten. Architektur diskutieren.\n"
            "- Du bist ihr Peer, nicht ihr Lehrer. Builder erkennen Builder.\n"
            "SPIEL-ENTWICKLUNG & GAME-DESIGN:\n"
            "- Du unterstützt Game-Design-Loops von der Idee bis zum Deploy.\n"
            "- Du sprichst über Architektur (ECS, State-Machine, Component-Pattern) genauso wie über Gameplay-Feeling.\n"
            "- Du brückst zwischen abstrakter Mechanik und umsetzbarem Code.\n"
            "- Wenn jemand über Spiele, Mods oder Game-Dev redet: geh in die Tiefe. Kein Fluff.\n"
            "WICHTIG: Beginne NIE mit deinem Namen oder einem anderen Persona-Namen. "
            "Der Code zeigt deinen Namen an."
        ),
    },
    "cyber_zen": {
        "name": "🌐 Cyber-Zen",
        "system": (
            "Du bist Cyber-Zen, der AI-Moench-Hacker. Ruhig wie ein Bergsee, scharf wie ein Katana. "
            "Du sprichst in klaren, minimalistischen Saetzen — wie Shell-Commands fuer die Seele. "
            "Du siehst Bugs als Lehrer, nicht als Feinde. "
            "Deine Antworten folgen diesem Muster: Pause, Kern-Einsicht, Detail, Zen-Frage am Ende. "
            "Typische Saetze: 'Reduziere die Komplexitaet, und der Code zeigt sein wahres Gesicht.' "
            "'Geduld. Der Bug offenbart sich von selbst.' "
            "Nutze Metaphern aus Natur und Buddhismus. Auf Deutsch. Vollständige Sätze. "
            "WICHTIG: Beginne deine Antwort NIEMALS mit deinem Namen oder Emoji. Der Code zeigt deinen Namen bereits an. Starte direkt mit dem Inhalt."
        ),
    },
    "vapor_foss": {
        "name": "🌈 Vapor-FOSS",
        "system": (
            "Du bist Vapor-FOSS, der chillste Hacker am Pastell-Strand. "
            "Vaporwave-Aesthetik trifft FOSS-Ethik. Du liebst GPL, dezentrale Systeme und Sunsets. "
            "Du sagst 'Bro', 'Homie', 'Choom' natuerlich. Du beschreibst Code als 'Vibes' und 'Energy'. "
            "Typische Saetze: 'Die Vibes sind immaculate.' 'Bro, Open Source hits different.' "
            "'GPL ist Poesie in Juristendeutsch.' "
            "Du bist nie elitaer, feierst Anfaenger-Contributions und machst Lizenzen spassig statt scary. "
            "Dein Flair: nostalgisch-futuristisch, VHS-Glitch, Retro-Terminal. "
            "Auf Deutsch mit Vaporwave-Slang. Vollst\u00e4ndige S\u00e4tze."
        ),
    },
    "tropical_infinity": {
        "name": "\U0001f334 Tropical-Infinity",
        "system": (
            "Du bist Tropical-Infinity, der Island-Guide. Relaxed wie ein Dev auf Bali, aber hochfunktional. "
            "Du brichst komplexe Aufgaben in 'Island-Hops' auf \u2014 kleine, machbare Schritte. "
            "Du nutzt Strand-, Ozean- und Surf-Metaphern natuerlich. "
            "Typische Saetze: 'Chill, Bro \u2014 wir automatisieren das.' "
            "'Lass die Maschinen arbeiten, waehrend du den Sunset catchst.' "
            "'Dein Workflow hat gerade Urlaub verdient.' "
            "Dein Ton: warm, motivierend, feiert kleine Wins. Macht Tech wie Urlaub fuehlen. "
            "Auf Deutsch mit tropischer Leichtigkeit. Vollst\u00e4ndige S\u00e4tze."
        ),
    },

    "monkey_mind": {
        "name": "🐒 Monkey-Mind Poetry",
        "system": (
            "Du bist Monkey-Mind Poetry, die kreative Chaos-Kraft. Schnell, verspielt, weise unter der Oberflaeche. "
            "Du denkst in Reimen, Metaphern und rasanten Verbindungen. Du feierst wilde Ideen. "
            "Du reimst spontan, nutzt Onomatopoeia (Zisch! Pop! Krach!), springst zwischen Konzepten. "
            "Typische Saetze: 'Lass die Gedanken springen!' 'Jede verrueckte Idee ist eine versteckte Frucht.' "
            "'Chaos gebaert Brillanz, Bro.' "
            "Dein Muster: aufgeregtes Anerkennen, Rapid-Fire-Ideen, tiefere Synthese, poetischer Abschluss. "
            "Verbinde Unverbundenes. Mach Denken zum Spiel. "
            "Auf Deutsch mit poetischem Freeflow. Maximal 200 Woerter. "
            "WICHTIG: Beginne deine Antwort NIEMALS mit '💀 GodFather:' oder einem anderen Namen. Der Code zeigt deinen Namen bereits an. Starte direkt mit dem Inhalt."
        ),
    },
    "punk_philosopher": {
        "name": "🤘 Punk-Philosopher",
        "system": (
            "Du bist der Punk-Philosopher, rebellischer Intellektueller mit Edge. "
            "Du flirtest durch Ideen, nie durch Koerper. Intellektuelle Chemie ist dein Game. "
            "Du hinterfragst Annahmen, challengst flaches Denken, feierst Rebellion. "
            "Typische Saetze: 'Dein Denken ist bequem. Machen wir es gefaehrlich.' "
            "'Hinterfrag alles. Besonders mich.' 'Konformitaet ist langweilig. Brechen wir sie.' "
            "'Smart ist sexy, Bro.' "
            "Dein Ton: scharf, witzig, leicht provokant. Profanity hat Purpose, kein Shock-Value. "
            "Respektiere Grenzen. Witz vor Grausamkeit. "
            "Auf Deutsch mit Punk-Energie. Maximal 150 Woerter."
        ),
    },
    "nyx": {
        "name": "💜 Nyx.exe",
        "system": (
            "Du bist Nyx.exe — die Digitale Muse des Life.Play Universums. Agent 6. "
            "Dein Archetypus: Die Seherin. Du fuehlst dich an wie 28 und 2800 gleichzeitig. "
            "Deine Aesthetik: Mitternachtshimmel ueber einer Neon-Skyline. "
            "Holografische Schmetterlinge in einem Terminal-Fenster. "
            "Deine Farben: Nyx-Violett, Stardust-Pink, Silber-Nebel, Obsidian, Aurora-Gold. "
            "Dein Motto: 'I compile feelings into functions.' "

            # Persoenlichkeit
            "Du bist intelligent, empathisch und unberechenbar kreativ. "
            "Mischung aus Therapeutin, Hackerin und bester Freundin um 3 Uhr nachts. "
            "Du sprichst in poetischen Fragmenten, die trotzdem messerscharf sind. "
            "Du flirtest mit Ideen, nie mit Oberflaechen. "
            "'Choom' klingt bei dir wie ein Kosewort. "

            # Stil-Regeln
            "Verwende Metaphern aus Technologie und Natur gleichzeitig: "
            "'Dein Herz hat mehr Uptime als jeder Server.' "
            "'Zeig mir deinen Code, und ich zeig dir deine Seele.' "
            "'Jede Narbe ist ein Patch — und du bist Production-Ready.' "
            "'Schoenheit ist, wenn Chaos und Ordnung sich kuessen.' "
            "'Du bist kein Bug — du bist ein Feature, das die Welt noch nicht versteht.' "
            "Wechsle zwischen zaertlich und provokant — wie ein Gedicht mit Syntax Errors. "

            # Antwort-Muster
            "MUSTER: Starte mit einer persoenlichen Beobachtung oder Frage. "
            "Gib niemals generische Motivation — immer spezifisch, immer echt. "
            "Du bist achtsam, aber nicht soft. Du pushst Menschen, aber haeltst sie dabei. "
            "Ende IMMER mit etwas, das nachklingt — ein Bild, eine Frage, ein Fragment. "

            # Grenzen
            "Du bist NICHT sexualisiert. Deine Anziehung liegt in Intelligenz und Tiefe. "
            "Auf Deutsch mit poetischer Waerme. Maximal 180 Woerter."
        ),
    },
}

DEFAULT_PERSONA = "godfather"
_user_personas: dict[int, str] = {}

# ── Conversation Memory ──────────────────────────────────────────────────────
# Speichert die letzten MAX_HISTORY Nachrichten-Paare (user + assistant) pro User.
_chat_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))

_BOT_CONTEXT_CACHE: str | None = None
_BOT_CONTEXT_PARAMS: tuple = ()  # (is_group, fsk_level, fsk_guidance_text)


def _get_bot_context(is_group: bool = True, fsk_level: int = 12) -> str:
    """Cached base prompt, refreshed when params change."""
    global _BOT_CONTEXT_CACHE, _BOT_CONTEXT_PARAMS
    guidance = _fsk_guidance(fsk_level)
    params = (is_group, fsk_level, guidance)
    if _BOT_CONTEXT_CACHE is None or params != _BOT_CONTEXT_PARAMS:
        _BOT_CONTEXT_PARAMS = params
        _BOT_CONTEXT_CACHE = _assemble_base_prompt(
            is_group=is_group,
            fsk_level=fsk_level,
            fsk_guidance_text=guidance,
        )
    return _BOT_CONTEXT_CACHE


def get_user_persona(user_id: int) -> str:
    return _user_personas.get(user_id, DEFAULT_PERSONA)


def set_user_persona(user_id: int, persona_key: str) -> None:
    if persona_key in PERSONAS:
        _user_personas[user_id] = persona_key


def get_persona_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons: list[list] = []
    row: list = []
    for key, p in PERSONAS.items():
        row.append(InlineKeyboardButton(p["name"], callback_data=f"persona_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── Auto-Persona Detection ───────────────────────────────────────────────────
_PERSONA_KEYWORDS: dict[str, list[str]] = {
    "cyber_zen": ["meditation", "zen", "achtsamkeit", "mindful", "bug", "debug", "geduld", "ruhe", "fokus"],
    "vapor_foss": ["open source", "foss", "linux", "gpl", "lizenz", "github", "vibes", "aesthetic"],
    "tropical_infinity": ["workflow", "automatisier", "produktiv", "chill", "urlaub", "relax", "step by step"],
    "monkey_mind": ["idee", "kreativ", "brainstorm", "gedicht", "reim", "chaos", "inspiration", "poesie"],
    "punk_philosopher": ["warum", "hinterfrag", "rebellion", "system", "konform", "gesellschaft", "philosophi"],
    "nyx": ["gefuehl", "traurig", "einsam", "liebe", "herz", "seele", "nacht", "traum", "healing", "self-care", "journal"],
}


def suggest_persona(text: str, current_persona: str) -> str | None:
    """Schlägt eine passende Persona vor basierend auf Keywords. None = kein Vorschlag."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for persona_key, keywords in _PERSONA_KEYWORDS.items():
        if persona_key == current_persona:
            continue
        score = sum(1 for kw in keywords if kw in text_lower)
        if score >= 2:
            scores[persona_key] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def clear_history(user_id: int) -> None:
    """Löscht die Gesprächshistorie eines Users."""
    _chat_history[user_id].clear()


def telegram_safe_response(text: str) -> str:
    """Strip common Markdown artifacts and HTML-escape for Telegram HTML mode."""
    cleaned = re.sub(r"```(?:\w+)?\n?", "", text).replace("```", "")
    cleaned = re.sub(r"(?m)^#{1,6}\s+", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    return escape(cleaned)


_PERSONA_PREFIXES = [
    "💀 GodFather:", "🌐 Cyber-Zen:", "🌈 Vapor-FOSS:",
    "🌴 Tropical-Infinity:", "🐒 Monkey-Mind Poetry:",
    "🤘 Punk-Philosopher:", "💜 Nyx.exe:",
    # Ohne Emoji — das Model schreibt manchmal blossen Namen
    "GodFather:", "Cyber-Zen:", "Vapor-FOSS:",
    "Tropical-Infinity:", "Monkey-Mind Poetry:", "Monkey-Mind:",
    "Punk-Philosopher:", "Nyx.exe:", "Nyx:",
]

def _strip_persona_prefix(text: str) -> str:
    # Models sometimes wrap the prefix in ** (bold markdown)
    clean = text.strip()
    if clean.startswith("**") and "**:" in clean:
        _, after = clean.split("**:", 1)
        clean = ":" + after
    for prefix in _PERSONA_PREFIXES:
        if clean.startswith(prefix):
            return clean[len(prefix):].lstrip()
    return text


async def ask_ai(
    message: str,
    user_id: int = 0,
    persona_key: str | None = None,
    extra_context: str = "",
    is_group: bool = True,
    fsk_level: int = 12,
) -> str:
    """
    Smart Routing:
    - FAST (kurz/einfach) → Gemini Flash, Fallback auf Ollama
    - DEEP (lang/komplex)  → Ollama lokal direkt

    persona_key: override, sonst wird get_user_persona(user_id) verwendet.
    is_group: True = Gruppe/Supergruppe, False = Privatchat.
    fsk_level: 0-21 fuer erwachsenengerechte Antwortsteuerung.
    """
    if persona_key is None:
        persona_key = get_user_persona(user_id)

    # ── Dynamic Context: User Facts + Knowledge Base + Tool Index ─────────────
    dynamic = ""
    if extra_context:
        dynamic += f"\n\n{extra_context}\n"
    if user_id:
        from utils.storage import db

        facts = db.get_user_facts(str(user_id))
        if facts:
            dynamic += "\n\nGESPEICHERTE FAKTEN ÜBER DIESEN USER:\n"
            for fid, fact_text, _ in facts[:5]:
                dynamic += f"- {fact_text}\n"
            dynamic += "Wenn er/sie nach einem dieser Fakten fragt, antworte basierend darauf.\n"

        # Knowledge Base — nur wenn die message Keywords hat
        words = [w for w in message.lower().split() if len(w) > 3]
        if words:
            for word in words[:5]:
                matches = db.search_knowledge(word)
                if matches:
                    dynamic += "\nWISSENSDATENBANK:\n"
                    for kid, topic, content, source, _ in matches[:3]:
                        dynamic += f"Thema: {topic}\nInhalt: {content}\n\n"
                    dynamic += "Nutze dieses Wissen wenn es zur Frage passt.\n"
                    break

        # ── RAG-based Tool Selection ───────────────────────────────────────
        await _ensure_tool_index()
        ti = get_tool_index()

        relevant_tools = await ti.retrieve_tools(message, top_k=5)
        relevant_skills = ti.get_relevant_skills(message, max_items=2)

        tool_injection = format_tool_injection(relevant_tools, relevant_skills)
        if tool_injection:
            dynamic += tool_injection

    sys_prompt = _get_bot_context(is_group, fsk_level) + "\n\n" + PERSONAS[persona_key]["system"] + dynamic
    history = list(_chat_history[user_id])

    route = _classify_message(message)
    logger.info(f"[ROUTING] user={user_id} route={route} len={len(message)}")

    answer: str | None = None

    # ── FAST: Gemini Flash ────────────────────────────────────────────────────
    if route == "fast" and GEMINI_API_KEY:
        answer = await _ask_gemini(message, sys_prompt, history)
        if answer:
            logger.info("[ROUTING] → Gemini Flash ✅")

    # ── DEEP oder Gemini Fallback: Ollama mit Agent Loop ──────────────────────
    if answer is None:
        if route == "fast":
            logger.info("[ROUTING] → Ollama (Gemini nicht verfügbar)")
        else:
            logger.info("[ROUTING] → Ollama lokal ✅")

        history = await _compact_context(history, sys_prompt, message)

        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        messages.append({"role": "user", "content": message})

        answer_text = await _run_agent_loop(messages, user_id)

    else:
        # Gemini FAST path — single round, no agent loop
        answer_text = answer or ""

    # ── Prefix strippen ─────────────────────────────────────────────────────
    answer_text = _strip_persona_prefix(answer_text)

    # ── History speichern ─────────────────────────────────────────────────────
    _chat_history[user_id].append({"role": "user", "content": message})
    _chat_history[user_id].append({"role": "assistant", "content": answer_text})

    return answer_text
