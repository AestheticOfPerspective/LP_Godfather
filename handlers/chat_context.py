"""Chat environment awareness for GodFather."""

from __future__ import annotations

from html import escape
import re

from telegram import Chat, User

from config import TELEGRAM_CHAT_FSK, TELEGRAM_DEFAULT_FSK
from utils.storage import db

FSK_LEVELS = (0, 6, 12, 16, 18, 21)


def chat_title(chat: Chat | None, user: User | None = None) -> str:
    if not chat:
        return "unbekannter Chat"
    if chat.title:
        return chat.title
    if chat.type == "private" and user:
        return user.username or user.first_name or str(user.id)
    return str(chat.id)


def chat_maturity_level(chat: Chat | None) -> int:
    if not chat or chat.type == "private":
        return TELEGRAM_DEFAULT_FSK
    title = (chat.title or "").lower()
    for marker, level in TELEGRAM_CHAT_FSK.items():
        if marker in title:
            return _valid_fsk(level)
    saved = db.get_chat_context(str(chat.id))
    if saved:
        _, _, saved_title, purpose, needs, _, _ = saved
        haystack = " ".join(str(part or "").lower() for part in (saved_title, purpose, needs))
        explicit = _extract_explicit_fsk(haystack)
        if explicit is not None:
            return explicit
        for marker, level in TELEGRAM_CHAT_FSK.items():
            if marker in haystack:
                return _valid_fsk(level)
    return _valid_fsk(TELEGRAM_DEFAULT_FSK)


def _valid_fsk(level: int) -> int:
    return level if level in FSK_LEVELS else 12


def _extract_explicit_fsk(text: str) -> int | None:
    match = re.search(r"\bfsk\s*(0|6|12|16|18|21)\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def fsk_guidance(level: int) -> str:
    if level <= 0:
        return "FSK 0: sehr freundlich, familienkompatibel, kein Fluchen, keine dunklen Witze."
    if level <= 6:
        return "FSK 6: leicht verspielt, harmlose Witze, keine harte Sprache."
    if level <= 12:
        return "FSK 12: normale Community-Leichtigkeit, milde Ironie, kein harter schwarzer Humor."
    if level <= 16:
        return "FSK 16: mehr Edge, trockene Ironie, leichte Profanity sparsam und ohne Zielscheibe."
    if level <= 18:
        return "FSK 18: erwachsener Ton, Denglish, schwarzer Humor und Profanity mit Purpose erlaubt, aber nicht creepy oder grausam."
    return "FSK 21: maximale Edgerunner-Freiheit fuer erwachsene Crew-Raeume, trotzdem keine Demuetigung, keine sensiblen Fakten als Punchline, keine Creepy-Schiene."


def build_chat_context_text(chat: Chat | None, user: User | None = None) -> str:
    if not chat:
        return "UMGEBUNG: unbekannt."

    if chat.type == "private":
        label = chat_title(chat, user)
        return (
            "UMGEBUNG: Privatchat mit einem einzelnen Nutzer. "
            f"Nutzer/Chat: {label}. "
            "Antworte persoenlicher, direkter und ohne Gruppen-Annahmen. "
            "Memory darf nur mit klarer Absicht gespeichert werden."
        )

    saved = db.get_chat_context(str(chat.id))
    title = chat_title(chat, user)
    maturity = chat_maturity_level(chat)
    if not saved:
        return (
            "UMGEBUNG: Telegram-Gruppe oder Supergruppe. "
            f"Gruppenname: {title}. "
            f"FSK-Level: {maturity}. {fsk_guidance(maturity)} "
            "Der konkrete Zweck dieser Gruppe wurde noch nicht gespeichert. "
            "Frage bei Bedarf kurz nach oder bleibe allgemein community-orientiert."
        )

    _, chat_type, saved_title, purpose, needs, _, updated_at = saved
    parts = [
        "UMGEBUNG: Telegram-Gruppe oder Supergruppe.",
        f"Gruppenname: {saved_title or title}.",
        f"FSK-Level: {maturity}.",
        fsk_guidance(maturity),
    ]
    if purpose:
        parts.append(f"Hoeherer Zweck: {purpose}.")
    if needs:
        parts.append(f"Typische Beduerfnisse: {needs}.")
    parts.append("Nutze diesen Kontext fuer relevante, gruppenspezifische Antworten.")
    return " ".join(parts)


def format_chat_context(chat: Chat | None, user: User | None = None) -> str:
    if not chat:
        return "🌐 Kontext unbekannt."
    title = chat_title(chat, user)
    if chat.type == "private":
        return (
            "🌐 <b>Chat-Kontext</b>\n\n"
            f"Typ: Privatchat\n"
            f"Mit: {escape(title)}\n\n"
            "Ich antworte hier persoenlicher und direkter als in Gruppen."
        )

    saved = db.get_chat_context(str(chat.id))
    maturity = chat_maturity_level(chat)
    if not saved:
        return (
            "🌐 <b>Chat-Kontext</b>\n\n"
            f"Typ: {escape(chat.type)}\n"
            f"Gruppe: {escape(title)}\n"
            f"FSK-Level: {maturity}\n"
            f"Ton: {escape(fsk_guidance(maturity))}\n\n"
            "Noch kein Gruppenzweck gespeichert. Admins koennen sagen:\n"
            "<code>lern diese gruppe: Zweck | typische Beduerfnisse</code>"
        )

    _, chat_type, saved_title, purpose, needs, updated_by, updated_at = saved
    return (
        "🌐 <b>Chat-Kontext</b>\n\n"
        f"Typ: {escape(chat_type)}\n"
        f"Gruppe: {escape(saved_title or title)}\n"
        f"FSK-Level: {maturity}\n"
        f"Ton: {escape(fsk_guidance(maturity))}\n"
        f"Zweck: {escape(purpose or 'nicht gesetzt')}\n"
        f"Beduerfnisse: {escape(needs or 'nicht gesetzt')}\n"
        f"Stand: {escape(updated_at)}"
    )
