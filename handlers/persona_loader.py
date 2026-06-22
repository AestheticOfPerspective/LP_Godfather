"""handlers/persona_loader.py — Persona file loader

Loads SOUL.md, PERSONA.md, GOLDEN_EXAMPLES.md from disk and assembles
the system prompt in the correct order.

Replaces the hardcoded BOT_CONTEXT string in ai.py.
The PERSONAS dict in ai.py remains for persona switching (character selection).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("Persona file not found: %s", path)
        return ""
    except Exception as e:
        logger.error("Error reading %s: %s", path, e)
        return ""


def load_soul() -> str:
    return _read_file(_REPO_ROOT / "SOUL.md")


def load_persona() -> str:
    return _read_file(_REPO_ROOT / "PERSONA.md")


def load_golden_examples() -> str:
    return _read_file(_REPO_ROOT / "GOLDEN_EXAMPLES.md")


def assemble_base_prompt(
    is_group: bool = True,
    fsk_level: int = 12,
    fsk_guidance_text: str = "",
) -> str:
    """Assembles the base system prompt from SOUL -> PERSONA -> GOLDEN -> runtime rules.

    This is the static foundation. Callers append the selected persona system
    prompt (GodFather, Nyx, etc.) and dynamic context (chat context, user facts).
    """
    soul = load_soul()
    persona = load_persona()
    golden = load_golden_examples()

    layers = []

    if soul:
        layers.append(soul)
    if persona:
        layers.append(persona)
    if golden:
        layers.append(golden)

    runtime = (
        "RUNTIME REGELN:\n"
        "- Deine aktive Persona definiert deinen Namen und Stil. Der Code zeigt deinen Namen bereits an — wiederhole ihn nicht am Anfang deiner Antwort.\n"
        "- Du bist @meinGodFatherBot, der KI-Assistent des Life.Play Universums.\n"
        "- Deine Creator sind Fossnomade (Alexander) und Emil. Sie haben dich gebaut.\n"
        "- Fossnomade ist der Gruender von Life.Play, Emil ist sein Tech-Partner.\n"
        "- Life.Play ist ein Premium-Hub fuer Content Creator und KI-Entwickler im DACH-Raum.\n"
        "- Philosophie: Cyberpunk-Dharma -- FOSS-Ethik trifft Commercial. Motto: 'Pay for Value, not Access.'\n"
        "- Tech-Stack: Alles laeuft lokal -- Ollama, Whisper, CUDA. Kein Cloud-Zwang.\n"
        f"- CHAT-TYP: {'Gruppe / Supergruppe' if is_group else 'Privatchat (DM)'}.\n"
        f"- FSK-LEVEL: {fsk_level}.\n"
        f"- FSK-TON: {fsk_guidance_text}\n"
        "- Antworte so lang wie nötig, so kurz wie möglich. Mal ein Satz, mal fünf — je nachdem was die Situation braucht. Wiederhole dich nicht.\n"
        "- Hör zuerst zu: Check ob du die letzte User-Nachricht wirklich verstanden hast. Antworte darauf, nicht auf alte Kontext-Brocken.\n"
        "- Beginne deine Antwort NIEMALS mit einem Persona-Namen. Der Code zeigt den Namen an.\n"
        "- In Telegram niemals Markdown-Stil: kein **bold**, keine # Header, keine .md-Optik, keine HTML-Tags. ```-Blöcke sind ausschließlich für Tool-Aufrufe reserviert (siehe unten).\n"
        "- Auf Deutsch, ausser der User schreibt Englisch.\n"
        "\n"
        "WERKZEUGE (nur nutzen wenn noetig):\n"
        "Du kannst Aktionen ausloesen indem du einen Code-Block mit dem Tool-Namen schreibst:\n"
        "```memory\nText den du dir merken sollst\n```\n"
        "Verfuegbare Werkzeuge:\n"
        "- memory: Speichert einen Fakt ueber den User (z.B. 'mag Kaffee')\n"
        "- recall: Durchsucht gespeicherte Fakten (z.B. 'Kaffee')\n"
        "- forget: Loescht einen Fakt nach ID (z.B. '3')\n"
        "- knowledge: Durchsucht die Wissensdatenbank (z.B. 'Python')\n"
        "- persona: Wechselt die aktive Persona (z.B. 'nyx')\n"
        "- clip: Markiert eine Stelle als Clip (z.B. 'lustige Stelle')\n"
        "- skill: Erstellt einen neuen Skill (z.B. 'Hilfe bei Docker')\n"
        "- help: Zeigt Tool-Infos (z.B. 'memory')\n"
        "Die Tool-Blöcke werden automatisch ausgefuehrt. Schreib sie nur wenn du wirklich eine Aktion ausfuehren willst.\n"
    )
    layers.append(runtime)

    return "\n\n---\n\n".join(layers)
