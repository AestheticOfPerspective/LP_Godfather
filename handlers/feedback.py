"""Feedback sensors for Telegram replies, reactions, and stickers.

This captures learning signals without blindly changing bot behavior. Stored
events can later become golden examples, prompt patches, or regression tests.
"""

from __future__ import annotations

import json
import logging
from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from handlers.chat_context import chat_title
from utils.storage import db

logger = logging.getLogger(__name__)

POSITIVE_EMOJIS = {
    "👍", "❤", "❤️", "🔥", "🥰", "👏", "😁", "🤩", "👌", "💯", "🏆", "⚡", "✅",
    "😂", "🤣", "😄", "😆",
}
NEGATIVE_EMOJIS = {
    "👎", "💩", "🤮", "😡", "🤬", "😢", "😭", "😐", "😕", "🙄", "❌", "🚫",
}

POSITIVE_TEXT = (
    "gut", "sehr gut", "passt", "nice", "preem", "geil", "stark", "perfekt",
    "lachen", "musste lachen", "besser", "genau", "richtig", "feier", "feiere",
    "hilfreich", "top", "stimmig", "resoniert",
)
NEGATIVE_TEXT = (
    "hm", "komisch", "falsch", "passt nicht", "zu generisch", "cringe", "schlecht",
    "funktionierst nicht", "funktionierst gerade nicht", "bug", "kaputt", "fail",
    "nicht so", "zu ernst", "zu trocken", "zu viel", "nervt", "unbrauchbar",
)


def classify_signal(payload: str) -> tuple[str, float]:
    lower = payload.lower()
    if any(token in payload for token in POSITIVE_EMOJIS):
        return "positive", 0.9
    if any(token in payload for token in NEGATIVE_EMOJIS):
        return "negative", 0.9
    positive_hits = sum(1 for token in POSITIVE_TEXT if token in lower)
    negative_hits = sum(1 for token in NEGATIVE_TEXT if token in lower)
    if positive_hits > negative_hits:
        return "positive", min(0.9, 0.45 + 0.15 * positive_hits)
    if negative_hits > positive_hits:
        return "negative", min(0.9, 0.45 + 0.15 * negative_hits)
    return "neutral", 0.2


def _user_label(user) -> str:
    if not user:
        return "unknown"
    return user.username or user.first_name or str(user.id)


def _base_event(update: Update) -> dict:
    chat = update.effective_chat
    user = update.effective_user
    return {
        "chat_id": str(chat.id if chat else "unknown"),
        "chat_type": str(chat.type if chat else "unknown"),
        "chat_title": chat_title(chat, user),
        "user_id": str(user.id if user else "unknown"),
        "username": _user_label(user),
    }


def log_text_reply_feedback(update: Update, text: str) -> int | None:
    msg = update.message
    if not msg or not msg.reply_to_message:
        return None
    reply_from = msg.reply_to_message.from_user
    if not reply_from or not reply_from.is_bot:
        return None
    polarity, confidence = classify_signal(text)
    base = _base_event(update)
    return db.add_feedback_event(
        source="telegram",
        event_kind="text_reply",
        target_message_id=str(msg.reply_to_message.message_id),
        payload=text[:2000],
        polarity=polarity,
        confidence=confidence,
        **base,
    )


async def handle_sticker_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.sticker:
        return
    reply = msg.reply_to_message
    if not reply or not reply.from_user or not reply.from_user.is_bot:
        return

    sticker = msg.sticker
    payload = {
        "emoji": sticker.emoji or "",
        "set_name": sticker.set_name or "",
        "file_unique_id": sticker.file_unique_id,
        "is_animated": bool(sticker.is_animated),
        "is_video": bool(sticker.is_video),
    }
    polarity, confidence = classify_signal(payload["emoji"])
    base = _base_event(update)
    db.add_feedback_event(
        source="telegram",
        event_kind="sticker_reply",
        target_message_id=str(reply.message_id),
        payload=json.dumps(payload, ensure_ascii=False),
        polarity=polarity,
        confidence=confidence,
        **base,
    )


def _reaction_to_emoji(reaction) -> str:
    emoji = getattr(reaction, "emoji", None)
    if emoji:
        return str(emoji)
    return str(reaction)


async def handle_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reaction = update.message_reaction
    if not reaction:
        return
    try:
        new_reactions = getattr(reaction, "new_reaction", []) or []
        old_reactions = getattr(reaction, "old_reaction", []) or []
        emojis = [_reaction_to_emoji(item) for item in new_reactions]
        old_emojis = [_reaction_to_emoji(item) for item in old_reactions]
        payload = json.dumps({"new": emojis, "old": old_emojis}, ensure_ascii=False)
        polarity, confidence = classify_signal(" ".join(emojis))
        chat = reaction.chat
        user = getattr(reaction, "user", None)
        db.add_feedback_event(
            source="telegram",
            chat_id=str(chat.id),
            chat_type=str(chat.type),
            chat_title=chat_title(chat, user),
            user_id=str(user.id if user else "unknown"),
            username=_user_label(user),
            target_message_id=str(reaction.message_id),
            event_kind="message_reaction",
            payload=payload,
            polarity=polarity,
            confidence=confidence,
        )
    except Exception as exc:
        logger.warning("Failed to log message reaction feedback: %s", exc)


def format_feedback_summary(chat_id: str | None = None) -> str:
    summary = db.feedback_summary(chat_id)
    total = sum(summary.values())
    if not total:
        return "📈 Noch keine Feedback-Signale gespeichert."
    return (
        "📈 Feedback-Signale\n\n"
        f"Gesamt: {total}\n"
        f"Positiv: {summary.get('positive', 0)}\n"
        f"Neutral: {summary.get('neutral', 0)}\n"
        f"Negativ: {summary.get('negative', 0)}"
    )
