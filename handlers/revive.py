"""
handlers/revive.py — Community Revive: Ping inaktive Member
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.decorators import admin_only, group_only
from utils.storage import db

logger = logging.getLogger(__name__)


@group_only
@admin_only
async def cmd_revive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return

    days = 14
    send_dm = False
    if context.args:
        send_dm = "--dm" in context.args
        for arg in context.args:
            if arg == "--dm":
                continue
            try:
                days = max(1, int(arg))
            except ValueError:
                pass

    inactive = db.get_inactive_users(str(chat.id), days=days, limit=20)
    stats = db.get_activity_stats(str(chat.id))

    if not inactive:
        await update.message.reply_text(
            f"🌅 Alle aktiv! Keiner länger als {days} Tage inaktiv.\n"
            f"({stats['active_14d']}/{stats['total']} Member aktiv)",
            parse_mode=ParseMode.HTML,
        )
        return

    if send_dm:
        ok = 0
        fail = 0
        for uid, username, last_seen in inactive:
            try:
                name = username or f"User {uid[:6]}"
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"🌅 <b>Community Revival</b>\n\n"
                        f"Hey {name}, in <b>{chat.title}</b> warst du "
                        f"zuletzt am <i>{last_seen}</i> aktiv.\n\n"
                        f"💀 Komm mal wieder rein — die Chooms vermissen dich!"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                ok += 1
            except Exception as e:
                logger.warning("Revive DM failed for %s (%s): %s", uid, name, e)
                fail += 1

        await update.message.reply_text(
            f"📬 <b>Revive DMs</b>\n"
            f"✅ {ok} gesendet\n"
            f"❌ {fail} fehlgeschlagen\n"
            f"({stats['active_14d']}/{stats['total']} Member aktiv)",
            parse_mode=ParseMode.HTML,
        )
        return

    mentions = []
    for uid, username, last_seen in inactive:
        if username:
            mentions.append(f"@{username}")

    text = (
        f"🌅 <b>Community Revive</b>\n\n"
        f"{stats['active_14d']}/{stats['total']} Member sind die letzten 14 Tage aktiv.\n"
        f"{len(mentions)} Member waren länger als {days} Tage weg:\n\n"
    )

    if mentions:
        text += "👋 " + ", ".join(mentions[:10]) + "\n"
        if len(mentions) > 10:
            text += f"...und {len(mentions) - 10} weitere\n"

    text += "\n💀 Live.Play lebt — kommt mal wieder rein!"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@group_only
@admin_only
async def cmd_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return

    days = 7
    if context.args:
        try:
            days = max(1, int(context.args[0]))
        except ValueError:
            pass

    active = db.get_active_users(str(chat.id), days=days, limit=15)
    stats = db.get_activity_stats(str(chat.id))

    text = (
        f"📊 <b>Community Activity ({days}Tage)</b>\n\n"
        f"Gesamt Member: {stats['total']}\n"
        f"Aktiv ({days}d): {stats.get(f'active_{days}d', len(active))}\n"
        f"Inaktiv ({days}d): {stats['total'] - len(active)}\n\n"
    )

    if active:
        text += "📋 <b>Zuletzt aktiv:</b>\n"
        for uid, username, last_seen in active[:10]:
            name = username or uid[:8]
            text += f"  • {name} — {last_seen}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
