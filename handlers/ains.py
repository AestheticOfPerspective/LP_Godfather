from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.ai import ask_ai, PERSONAS, get_user_persona, suggest_persona
from utils.storage import db


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Normaler Text → direkt an die KI. Kein /ask nötig."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text
    persona_key = get_user_persona(user_id)
    persona_name = PERSONAS[persona_key]["name"]

    msg = await update.message.reply_text(f"⏳ {persona_name} denkt nach...")

    db.increment_stat("ai_requests")
    response = await ask_ai(text, user_id=user_id)

    suggestion = suggest_persona(text, persona_key)
    hint = ""
    if suggestion:
        s_name = PERSONAS[suggestion]["name"]
        hint = f"\n\n💡 <i>Tipp: {s_name} passt besser → /persona</i>"

    await msg.edit_text(
        f"{persona_name}:\n\n{response}{hint}",
        parse_mode=ParseMode.HTML,
    )
