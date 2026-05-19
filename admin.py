"""
handlers/admin.py — Moderations-Commands für Gruppen-Admins
"""

import logging
from datetime import timedelta, datetime

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import MAX_WARNS
from utils.decorators import admin_only, group_only
from utils.storage import db

logger = logging.getLogger(__name__)


def _get_target(update: Update, context) -> tuple | None:
    """Hilfsfunktion: Ziel-User aus Reply oder @mention extrahieren."""
    msg = update.message

    if msg.reply_to_message:
        user = msg.reply_to_message.from_user
        return user, msg.reply_to_message.message_id

    if context.args:
        # @username oder User-ID
        target = context.args[0].lstrip("@")
        try:
            uid = int(target)
            return type("User", (), {"id": uid, "mention_html": lambda: str(uid), "first_name": str(uid)})(), None
        except ValueError:
            pass

    return None, None


@group_only
@admin_only
async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target, _ = _get_target(update, context)
    if not target:
        await update.message.reply_text("❓ Reply auf eine Nachricht oder /warn @user [Grund]")
        return

    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "Kein Grund angegeben"
    chat_id = str(update.effective_chat.id)

    warns = db.add_warn(chat_id, str(target.id), reason)

    text = (
        f"⚠️ <b>Verwarnung {warns}/{MAX_WARNS}</b>\n"
        f"User: {target.mention_html()}\n"
        f"Grund: {reason}"
    )

    if warns >= MAX_WARNS:
        try:
            await context.bot.ban_chat_member(
                update.effective_chat.id,
                target.id,
                until_date=timedelta(days=1)
            )
            text += f"\n\n💀 Auto-Ban nach {MAX_WARNS} Verwarnungen."
            db.clear_warns(chat_id, str(target.id))
        except Exception as e:
            logger.error(f"Auto-Ban fehlgeschlagen: {e}")

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@group_only
@admin_only
async def cmd_warns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target, _ = _get_target(update, context)
    if not target:
        await update.message.reply_text("❓ Reply auf eine Nachricht oder /warns @user")
        return

    chat_id = str(update.effective_chat.id)
    warns_list = db.get_warns(chat_id, str(target.id))

    if not warns_list:
        await update.message.reply_text(
            f"✅ {target.mention_html()} hat keine Verwarnungen.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [f"📋 <b>Verwarnungen für {target.mention_html()}:</b>\n"]
    for i, (reason, ts) in enumerate(warns_list, 1):
        lines.append(f"{i}. {reason} <i>({ts})</i>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@group_only
@admin_only
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target, _ = _get_target(update, context)
    if not target:
        await update.message.reply_text("❓ /mute @user [Minuten]")
        return

    minutes = 30  # Default
    if context.args and len(context.args) > 1:
        try:
            minutes = int(context.args[1])
        except ValueError:
            pass

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=timedelta(minutes=minutes)
        )
        await update.message.reply_text(
            f"🔇 {target.mention_html()} für {minutes} Minuten gemutet.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


@group_only
@admin_only
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target, _ = _get_target(update, context)
    if not target:
        await update.message.reply_text("❓ Reply oder /unmute @user")
        return

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await update.message.reply_text(
            f"🔊 {target.mention_html()} wurde entmutet.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


@group_only
@admin_only
async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target, _ = _get_target(update, context)
    if not target:
        await update.message.reply_text("❓ Reply oder /kick @user [Grund]")
        return

    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "Kein Grund"

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(
            f"👟 {target.mention_html()} wurde gekickt.\nGrund: {reason}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


@group_only
@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target, _ = _get_target(update, context)
    if not target:
        await update.message.reply_text("❓ Reply oder /ban @user [Grund]")
        return

    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "Kein Grund"

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(
            f"💀 {target.mention_html()} wurde gebannt.\nGrund: {reason}",
            parse_mode=ParseMode.HTML
        )
        db.clear_warns(str(update.effective_chat.id), str(target.id))
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


@group_only
@admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = db.get_stats()
    text = (
        "📊 <b>GodFather Stats</b>\n\n"
        f"💬 Verarbeitete Nachrichten: {stats.get('messages', 0)}\n"
        f"👋 Neue Member begrüßt: {stats.get('joins', 0)}\n"
        f"⚠️ Verwarnungen gesamt: {stats.get('warns', 0)}\n"
        f"🤖 KI-Anfragen: {stats.get('ai_requests', 0)}\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
