"""SUPERNOVA — Live.Play Sales Campaign Tracker.

Tracks deals, countdowns, and KPIs for the SUPERNOVA campaign.
Channels: ExtremeAlex27 on Facebook, Instagram, LinkedIn, Meta Ads.
"""

from __future__ import annotations

from datetime import datetime, date
from html import escape
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.storage import db

CAMPAIGN_NAME = "SUPERNOVA"
CAMPAIGN_EMOJI = "💫"
CAMPAIGN_ACCOUNT = "ExtremeAlex27"
CAMPAIGN_END = date(2026, 12, 31)

CHANNELS = {
    "facebook": {"emoji": "📘", "name": "Facebook", "account": CAMPAIGN_ACCOUNT},
    "instagram": {"emoji": "📸", "name": "Instagram", "account": CAMPAIGN_ACCOUNT},
    "linkedin": {"emoji": "💼", "name": "LinkedIn", "account": CAMPAIGN_ACCOUNT},
    "meta_ads": {"emoji": "📢", "name": "Meta Ads", "account": CAMPAIGN_ACCOUNT},
}


def _tz() -> ZoneInfo:
    return ZoneInfo("Europe/Berlin")


def _countdown(target: date) -> str:
    remaining = (target - datetime.now(_tz()).date()).days
    if remaining < 0:
        return "🚀 ABGESCHLOSSEN"
    if remaining == 0:
        return "🔥 HEUTE IST DEADLINE!"
    if remaining == 1:
        return "⚠️ Morgen ist Deadline!"
    if remaining <= 7:
        return f"⚡ {remaining} Tage (letzte Woche!)"
    if remaining <= 30:
        return f"🔥 {remaining} Tage"
    return f"📅 {remaining} Tage"


def _progress_bar(pct: float, width: int = 12) -> str:
    filled = int(pct * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def format_supernova() -> str:
    now = datetime.now(_tz())
    total_days = (CAMPAIGN_END - date(2026, 1, 1)).days
    elapsed = (now.date() - date(2026, 1, 1)).days
    progress = min(max(elapsed / total_days, 0.0), 1.0)

    lines = [
        f"{CAMPAIGN_EMOJI} <b>SUPERNOVA — Live.Play Sales Campaign</b>",
        f"Account: <code>{CAMPAIGN_ACCOUNT}</code>",
        "",
        f"<b>── Countdown ──</b>",
        f"  Ende: {CAMPAIGN_END.strftime('%d.%m.%Y')}",
        f"  {_countdown(CAMPAIGN_END)}",
        "",
        f"<b>── Channels ──</b>",
    ]

    for key, ch in CHANNELS.items():
        lines.append(f"  {ch['emoji']} {ch['name']} — @{ch['account']}")

    lines += [
        "",
        f"<b>── Gesamt-Fortschritt ──</b>",
        f"  {_progress_bar(progress)} {progress:.0%}",
        f"  Tag {elapsed} von {total_days}",
        "",
        f"<i>Letzte Aktualisierung: {now.strftime('%d.%m.%Y %H:%M')}</i>",
        "",
        "💀 <b>Built different. Pay for Value, not Access.</b>",
    ]

    return "\n".join(lines)


async def cmd_supernova(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        format_supernova(), parse_mode=ParseMode.HTML
    )
