"""
utils/decorators.py — Permission Decorators
"""

import logging
from functools import wraps

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from config import ADMIN_IDS

logger = logging.getLogger(__name__)

ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


def admin_only(func):
    """Nur für Gruppen-Admins oder Bot-Owner."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        chat = update.effective_chat

        # Bot-Owner immer erlaubt
        if user.id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)

        # In Gruppen: Telegram-Admin-Status prüfen
        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status in ADMIN_STATUSES:
                return await func(update, context, *args, **kwargs)

        await update.message.reply_text("🚫 Nur für Admins.")

    return wrapper


def group_only(func):
    """Nur in Gruppen/Supergruppen erlaubt."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await update.message.reply_text("❌ Dieser Command funktioniert nur in Gruppen.")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper
