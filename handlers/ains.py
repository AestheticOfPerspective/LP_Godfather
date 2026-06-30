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
from handlers.mastering import _user_key as _mastering_key
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

    # Gruppen: NUR bei @Bot-Erwähnung triggern (kein Reply-to-Self mehr — verhindert Bot-Kaskaden).
    if chat.type in ("group", "supergroup"):
        is_mentioned = f"@{bot_username}" in text.lower()

        if not is_mentioned:
            return

        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE).strip()
        if not text:
            return

    if await handle_natural_intent(update, context, text):
        return

    if context.user_data.get(_mastering_key(user.id)):
        return

    user_id = user.id
    persona_key = get_user_persona(user_id)
    persona_name = PERSONAS[persona_key]["name"]
    is_group = chat.type in ("group", "supergroup")

    db.increment_stat("ai_requests")
    maturity = chat_maturity_level(chat)

    msg = None
    if is_group:
        msg = await update.message.reply_text(f"⏳ {persona_name} denkt nach...")

    response = await ask_ai(
        text,
        user_id=user_id,
        extra_context=build_chat_context_text(chat, user),
        is_group=is_group,
        fsk_level=maturity,
    )

    suggestion = suggest_persona(text, persona_key)
    hint = ""
    if suggestion and not _is_critical_or_corrective(text):
        s_name = PERSONAS[suggestion]["name"]
        hint = f"\n\n💡 <i>Tipp: {s_name} passt besser → /persona</i>"

    reply_text = f"{persona_name}:\n\n{telegram_safe_response(response)}{hint}"

    if is_group:
        await msg.edit_text(reply_text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
