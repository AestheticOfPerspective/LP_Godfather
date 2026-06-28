"""Tool Runner — Executes fenced tool blocks from LLM responses.

The LLM can call tools by writing fenced code blocks in its response:
```tool_name
arguments
```

This module parses those blocks, executes the matching handler,
and replaces the block with the execution result.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from utils.storage import db
from utils.skill_store import create_skill, read_skill, list_active_skills

logger = logging.getLogger(__name__)

# ── Tool Block Pattern ──────────────────────────────────────────────
# Matches: ```tool_name\narguments\n``` (with optional language tag)
_TOOL_BLOCK_RE = re.compile(
    r"```(\w+)\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)

# Tool names that the LLM is allowed to call
TOOL_TAGS = frozenset({
    "memory", "recall", "forget",
    "knowledge", "search",
    "persona",
    "clip",
    "skill",
    "help",
    "antigravity",
})


def parse_tool_blocks(text: str) -> list[tuple[str, str, int, int]]:
    """Parse fenced tool blocks from LLM response text.

    Returns list of (tool_name, arguments, start_pos, end_pos).
    Positions are relative to the original text for replacement.
    """
    blocks = []
    for m in _TOOL_BLOCK_RE.finditer(text):
        tag = m.group(1).lower()
        if tag in TOOL_TAGS:
            args = m.group(2).strip()
            blocks.append((tag, args, m.start(), m.end()))
    return blocks


def strip_tool_blocks(text: str) -> str:
    """Remove all fenced tool blocks from text."""
    return _TOOL_BLOCK_RE.sub("", text).strip()


async def execute_tool(tool_name: str, args: str, user_id: int = 0) -> str:
    """Execute a tool and return a result message.

    All tools are sync (DB ops) except persona switch (needs state change).
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if not handler:
        return f"❌ Unbekanntes Tool: {tool_name}"
    try:
        return await handler(args, user_id)
    except Exception as e:
        logger.error("[tool-runner] %s failed: %s", tool_name, e)
        return f"❌ Tool {tool_name} Fehler: {e}"


async def _handle_memory(args: str, user_id: int) -> str:
    if not user_id:
        return "❌ Memory nur im Privatchat verfuegbar."
    if len(args) > 500:
        return "❌ Maximal 500 Zeichen."
    uid = str(user_id)
    count = db.count_user_facts(uid)
    if count >= 50:
        return "❌ Maximal 50 Fakten. Loesche alte mit /forget."
    fid = db.add_user_fact(uid, args)
    return f"🧠 Fakt #{fid} gespeichert: {args[:100]}"


async def _handle_recall(args: str, user_id: int) -> str:
    if not user_id or not args:
        return "❓ Wonach soll ich suchen?"
    uid = str(user_id)
    results = db.search_user_facts(uid, args)
    if not results:
        return f"🔍 Keine Fakten zu '{args}' gefunden."
    lines = [f"🧠 Gefundene Fakten zu '{args}':"]
    for fid, fact_text, _ in results[:5]:
        lines.append(f"  #{fid}  {fact_text}")
    return "\n".join(lines)


async def _handle_forget(args: str, user_id: int) -> str:
    if not user_id:
        return "❌ Nicht verfuegbar."
    try:
        fid = int(args.strip())
    except ValueError:
        return "❌ Bitte eine ID-Nummer angeben."
    uid = str(user_id)
    if db.delete_user_fact(fid, uid):
        return f"🧹 Fakt #{fid} geloescht."
    return "❌ Kein Fakt mit dieser ID gefunden."


async def _handle_knowledge(args: str, user_id: int) -> str:
    if not args:
        return "❓ Wonach soll ich suchen?"
    results = db.search_knowledge(args)
    if not results:
        return f"🔍 Kein Wissen zu '{args}' gefunden."
    lines = [f"📚 Wissen zu '{args}':"]
    for kid, topic, content, source, _ in results[:3]:
        lines.append(f"\n  Thema: {topic}\n  {content[:200]}")
    return "\n".join(lines)


async def _handle_search(args: str, user_id: int) -> str:
    return await _handle_knowledge(args, user_id)


async def _handle_persona(args: str, user_id: int) -> str:
    from handlers.ai import PERSONAS, set_user_persona
    name = args.strip().lower()
    # Try matching by key first, then by display name
    if name in PERSONAS:
        set_user_persona(user_id, name)
        return f"🔄 Persona gewechselt zu {PERSONAS[name]['name']}."
    for key, p in PERSONAS.items():
        if name in p["name"].lower():
            set_user_persona(user_id, key)
            return f"🔄 Persona gewechselt zu {p['name']}."
    available = ", ".join(PERSONAS.keys())
    return f"❌ Persona '{name}' nicht gefunden. Verfuegbar: {available}"


async def _handle_clip(args: str, user_id: int) -> str:
    return f"🎬 Clip-Vorschlag notiert: {args[:100]}"


async def _handle_skill(args: str, user_id: int) -> str:
    if not args:
        return "❓ Zweck des Skills fehlt."
    safe_name = re.sub(r"[^a-z0-9-]", "", args.lower().replace(" ", "-"))[:30]
    content = (
        f"# {safe_name} Skill\n\n"
        f"## Description\n{args}\n\n"
        f"## Signals\n{safe_name}\n\n"
        f"## Procedure\nnot-yet-defined\n"
    )
    if create_skill(safe_name, content, args[:100]):
        return f"✅ Skill '{safe_name}' erstellt (Draft). Admin muss aktivieren."
    return "❌ Konnte Skill nicht erstellen."


async def _handle_help(args: str, user_id: int) -> str:
    if not args:
        return ("Folgende Tools sind verfuegbar:\n"
                "- memory: Fakten speichern\n"
                "- recall: Fakten suchen\n"
                "- forget: Fakten loeschen\n"
                "- knowledge: Wissen abfragen\n"
                "- persona: Persona wechseln\n"
                "- clip: Clip einreichen\n"
                "- skill: Skill erstellen")
    topic = args.strip().lower()
    tool_descriptions = {
        "memory": "Speichert einen Fakt ueber dich. Beispiel: memory\nIch mag Kaffee",
        "recall": "Durchsucht deine Fakten. Beispiel: recall\nKaffee",
        "forget": "Loescht einen Fakt nach ID. Beispiel: forget\n3",
        "knowledge": "Durchsucht die Wissensdatenbank. Beispiel: knowledge\nPython",
        "persona": "Wechselt die aktive Persona. Beispiel: persona\nnyx",
    }
    info = tool_descriptions.get(topic)
    if info:
        return info
    return f"❌ Kein Hilfeeintrag zu '{topic}'."


async def _handle_antigravity(args: str, user_id: int) -> str:
    if not args:
        return "❓ Was soll der Antigravity Agent machen?"
    try:
        proc = await asyncio.create_subprocess_exec(
            "agy", "--prompt", args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode == 0:
            result = stdout.decode().strip()[:2000]
            return result or "✅ Antigravity erledigt."
        error = stderr.decode().strip()[:500]
        if "auth" in error.lower() or "sign" in error.lower():
            return "🔑 Antigravity nicht authentifiziert. Admin: `/antigravity setup`"
        return f"❌ Antigravity Fehler ({proc.returncode}): {error}"
    except asyncio.TimeoutError:
        return "⏱️ Antigravity hat zu lange gebraucht (Limit 120s)."
    except FileNotFoundError:
        return "❌ `agy` nicht installiert. Admin muss Container neu bauen."
    except Exception as e:
        logger.error("[tool-runner] antigravity error: %s", e)
        return f"❌ Antigravity Fehler: {e}"


_TOOL_HANDLERS = {
    "memory": _handle_memory,
    "recall": _handle_recall,
    "forget": _handle_forget,
    "knowledge": _handle_knowledge,
    "search": _handle_search,
    "persona": _handle_persona,
    "clip": _handle_clip,
    "skill": _handle_skill,
    "help": _handle_help,
    "antigravity": _handle_antigravity,
}
