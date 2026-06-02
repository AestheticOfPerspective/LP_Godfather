"""handlers/maintenance.py — GodFather Maintenance Session

Reviews feedback signals, generates actionable suggestions for:
- Golden Examples candidates from positive signals
- Intent patches from negative signals
- Skill improvements

Command:
  /maintenance         — Full maintenance report
  /maintenance quick   — Short summary (polarity counts + top signals)
"""

from __future__ import annotations

import logging
from html import escape
from datetime import datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from utils.storage import db

logger = logging.getLogger(__name__)


def _format_signal_row(signal_type: str, payload: str, count: int) -> str:
    truncated = payload[:120].replace("\n", " ")
    return f"  {signal_type} x{count}: {escape(truncated)}"


def build_maintenance_report(scope_chat_id: str | None = None) -> str:
    """Build a structured maintenance report from feedback_events.

    scope_chat_id: None = global, otherwise chat-specific.
    """
    summary = db.feedback_summary(scope_chat_id)
    total = sum(summary.values())
    if not total:
        return "📈 Noch keine Feedback-Signale gespeichert. Starte Sammlung durch Interaktion in Gruppen."

    recent = db.recent_feedback_events(limit=50)
    recent = [
        e for e in recent
        if not scope_chat_id or e[2] == scope_chat_id
    ]

    # Count signal types
    positive_signals: dict[str, int] = {}
    negative_signals: dict[str, int] = {}
    neutral_signals: dict[str, int] = {}

    for event in recent:
        _id, source, chat_title, username, event_kind, payload, polarity, confidence, created_at = event
        key = payload[:60]
        if polarity == "positive":
            positive_signals[key] = positive_signals.get(key, 0) + 1
        elif polarity == "negative":
            negative_signals[key] = negative_signals.get(key, 0) + 1
        else:
            neutral_signals[key] = neutral_signals.get(key, 0) + 1

    top_positive = sorted(positive_signals.items(), key=lambda x: -x[1])[:5]
    top_negative = sorted(negative_signals.items(), key=lambda x: -x[1])[:5]

    lines = [
        "🛠️ <b>GodFather Maintenance Report</b>\n",
        f"📊 <b>Feedback-Signale</b>",
        f"  Gesamt: {total}",
        f"  Positiv: {summary.get('positive', 0)}",
        f"  Neutral: {summary.get('neutral', 0)}",
        f"  Negativ: {summary.get('negative', 0)}",
    ]

    if top_positive:
        lines.append("\n✅ <b>Top Positive Signals</b>  (Golden Example Kandidaten)")
        for payload, count in top_positive:
            lines.append(_format_signal_row("✅", payload, count))

    if top_negative:
        lines.append("\n❌ <b>Top Negative Signals</b>  (Intent Patch Kandidaten)")
        for payload, count in top_negative:
            lines.append(_format_signal_row("❌", payload, count))

    # Recent high-confidence events
    high_conf = [e for e in recent if e[6] in ("positive", "negative") and float(e[7]) >= 0.7][:4]
    if high_conf:
        lines.append("\n🎯 <b>High-Confidence Events</b>")
        for event in high_conf:
            _id, source, chat_title, username, event_kind, payload, polarity, confidence, created_at = event
            truncated = payload[:100].replace("\n", " ")
            lines.append(
                f"  [{polarity}] ({event_kind}) {escape(username)}: "
                f"{escape(truncated)}"
            )

    # Suggestions
    suggestions = []

    if top_positive:
        suggestions.append(
            "📝 <b>Golden Example Vorschlag:</b> "
            "Die positiven Signale zeigen, was gut ankommt. "
            "Extrahiere das Muster und schreib es als Golden Example in GOLDEN_EXAMPLES.md."
        )

    if top_negative:
        suggestions.append(
            "🔧 <b>Intent Patch Vorschlag:</b> "
            "Negative Signale zeigen, wo GodFather falsch liegt oder falsch verstanden wird. "
            "Pruefe ob ein neues Intent-Signal oder eine Prompt-Anpassung noetig ist."
        )

    if total > 10 and summary.get("negative", 0) > summary.get("positive", 0) * 0.5:
        suggestions.append(
            "⚠️ <b>Verhaeltnis-Warnung:</b> "
            "Negativ-Signale sind im Vergleich zu Positiv-Signalen hoch (>50%). "
            "Empfehle eine Team-Session zur Ursachenanalyse."
        )

    if suggestions:
        lines.append(f"\n💡 <b>Aktionsvorschlaege</b>")
        lines.extend(suggestions)

    lines.append(
        "\n<i>Maintenance-Rhythmus: Feedback sammeln, reflektieren, "
        "Golden Examples pflegen, Intents patchen. Keine blinde Auto-Mutation.</i>"
    )

    return "\n".join(lines)


async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Maintenance nur fuer Admins.")
        return

    args = context.args or []
    scope = str(chat.id) if chat and args and args[0].lower() == "hier" else None

    report = build_maintenance_report(scope)
    await update.message.reply_text(report, parse_mode=ParseMode.HTML)
