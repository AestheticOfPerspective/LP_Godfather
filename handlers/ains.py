import re

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.ai import (
    ask_ai,
    PERSONAS,
    get_user_persona,
    suggest_persona,
    telegram_safe_response,
)
from handlers.chat_context import build_chat_context_text, chat_maturity_level
from handlers.feedback import log_text_reply_feedback
from handlers.intents import handle_natural_intent
from utils.storage import db


_CRITICAL_PATTERNS = re.compile(
    r"(bullshit|mist|fehler|falsch|kaputt|nicht richtig|nicht funktionier|"
    r"blöd|dumm|hör auf|lass es|nerv|scheiß|scheiss|was soll das|"
    r"copycat|kalt erwischt|rauswinden|und jetzt dieser|"
    r"du spinnst|das stimmt nicht|schwachsinn)",
    re.IGNORECASE,
)


def _is_critical_or_corrective(text: str) -> bool:
    """Prüft ob die User-Nachricht kritisch/korrigierend gegenüber dem Bot ist.

    In solchen Fällen keine Persona-Empfehlung — das wirkt taub.
    """
    return bool(_CRITICAL_PATTERNS.search(text))


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Normaler Text -> KI-Antwort.

    Privatchat: immer antworten.
    Gruppe: nur bei @Bot-Erwaehnung oder Reply auf Bot-Nachricht (wie @Magiebot).
    """
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat = update.effective_chat
    if not user or user.is_bot or not chat:
        return

    text = update.message.text
    bot_username = context.bot.username.lower()
    reply = update.message.reply_to_message

    # Gruppen: nur triggern bei Mention oder Reply auf DICH (nicht auf andere Bots).
    if chat.type in ("group", "supergroup"):
        is_reply_to_self = (
            update.message.reply_to_message
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.is_bot
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = f"@{bot_username}" in text.lower()

        if not is_reply_to_self and not is_mentioned:
            return

        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE).strip()
        if not text and reply:
            text = "Bitte reagiere auf die zitierte Nachricht."
        if not text:
            return

    if await handle_natural_intent(update, context, text):
        return

    if reply:
        log_text_reply_feedback(update, text)
        reply_text = reply.text or reply.caption or ""
        if reply_text:
            author = reply.from_user.first_name if reply.from_user else "Unbekannt"
            text = (
                "Kontext: Der User bezieht sich auf diese Telegram-Nachricht:\n"
                f"Von: {author}\n"
                f"---\n{reply_text[:1800]}\n---\n\n"
                f"Aktuelle Frage/Auftrag: {text}\n\n"
                "Antworte explizit auf diese zitierte Nachricht, nicht auf alte Chat-History."
            )

    user_id = user.id
    persona_key = get_user_persona(user_id)
    persona_name = PERSONAS[persona_key]["name"]

    msg = await update.message.reply_text(f"⏳ {persona_name} denkt nach...")

    db.increment_stat("ai_requests")
    maturity = chat_maturity_level(chat)
    response = await ask_ai(
        text,
        user_id=user_id,
        extra_context=build_chat_context_text(chat, user),
        is_group=chat.type in ("group", "supergroup"),
        fsk_level=maturity,
    )

    suggestion = suggest_persona(text, persona_key)
    hint = ""
    if suggestion and not _is_critical_or_corrective(text):
        s_name = PERSONAS[suggestion]["name"]
        hint = f"\n\n💡 <i>Tipp: {s_name} passt besser → /persona</i>"

    await msg.edit_text(
        f"{persona_name}:\n\n{telegram_safe_response(response)}{hint}",
        parse_mode=ParseMode.HTML,
    )
