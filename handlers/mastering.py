"""Mixing & Mastering — /mastering Command + Intake Workflow.

Track-Einreichung via Telegram. User sendet Audiodatei + Infos,
Bot speichert in Queue und benachrichtigt Admin.

Commands:
  /mastering        — Startet Intake (Package wählen → Beschreibung → File → Confirm)
  /queue            — Alle deine Tickets anzeigen
  /status <ticket>  — Status eines Tickets prüfen
  /cancel           — Aktuellen Intake abbrechen
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS

QUEUE_DIR = Path("data/mastering_queue")
QUEUE_DIR.mkdir(parents=True, exist_ok=True)

PACKAGES = {
    "bronze": {"name": "🥉 Bronze", "price": "19€", "desc": "Mix + Master (≤4 Min, 2 Rev)"},
    "silver": {"name": "🥈 Silver", "price": "39€", "desc": "Mix + Master + Beat optional"},
    "gold": {"name": "🥇 Gold", "price": "79€", "desc": "Full Production + Stream-Ready + DJ-Push"},
}

STATUS_LABELS = {
    "received": "📥 Received",
    "in_work": "🔧 In Work",
    "done": "✅ Done",
    "stream_ready": "🔥 Stream-Ready",
    "cancelled": "❌ Cancelled",
}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aac", ".ogg", ".wma", ".m4a"}


def _tz() -> ZoneInfo:
    return ZoneInfo("Europe/Berlin")


def _user_key(uid: int) -> str:
    return f"mastering_{uid}"


def _list_tickets(user_id: int | None = None) -> list[dict]:
    tickets = []
    for f in sorted(QUEUE_DIR.glob("MX*.json")):
        try:
            with open(f) as fh:
                t = json.load(fh)
            if user_id is None or t.get("user_id") == user_id:
                t["_ticket_id"] = f.stem
                tickets.append(t)
        except (json.JSONDecodeError, OSError):
            pass
    return tickets


def _get_ticket(ticket_id: str) -> dict | None:
    path = QUEUE_DIR / f"{ticket_id}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            t = json.load(f)
        t["_ticket_id"] = ticket_id
        return t
    except (json.JSONDecodeError, OSError):
        return None


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    tickets = _list_tickets(user_id=uid)

    if not tickets:
        await update.message.reply_text(
            "📭 Keine offenen Tickets gefunden.\n"
            "Schick mir <code>/mastering</code> um einen Track einzureichen!",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = ["<b>Deine Mastering-Tickets</b>\n"]
    for t in tickets[-10:]:
        pkg = PACKAGES.get(t.get("package", ""), {})
        pkg_name = pkg.get("name", t.get("package", "?"))
        status = STATUS_LABELS.get(t.get("status", "?"), t.get("status", "?"))
        ts = t.get("timestamp", "")[:16].replace("T", " ")
        lines.append(
            f"• <code>{t['_ticket_id']}</code> {pkg_name} — {status}\n"
            f"  {escape(t.get('file_name', '?'))} — {ts}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Ticket-ID fehlt.\n"
            "Beispiel: <code>/status MX1234567890</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    ticket = _get_ticket(args[0])
    if not ticket:
        await update.message.reply_text(
            f"❌ Ticket <code>{escape(args[0])}</code> nicht gefunden.",
            parse_mode=ParseMode.HTML,
        )
        return

    pkg = PACKAGES.get(ticket.get("package", ""), {})
    pkg_name = pkg.get("name", ticket.get("package", "?"))
    status = STATUS_LABELS.get(ticket.get("status", "?"), ticket.get("status", "?"))
    ts = ticket.get("timestamp", "")[:16].replace("T", " ")

    lines = [
        f"<b>Ticket {ticket['_ticket_id']}</b>\n",
        f"Package: {pkg_name}",
        f"Status: {status}",
        f"Track: {escape(ticket.get('file_name', '?'))}",
        f"Eingereicht: {ts}",
    ]

    desc = ticket.get("description")
    if desc:
        lines.append(f"Notiz: {escape(desc)}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_mastering(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    context.user_data[_user_key(uid)] = {"step": "package"}

    text = (
        "🎵 <b>Mixing & Mastering — Intake</b>\n\n"
        "Wähle dein Package:\n\n"
    )
    for key, pkg in PACKAGES.items():
        text += f"  <code>/{key}</code>  {pkg['name']} — {pkg['price']}\n"
        text += f"       <i>{pkg['desc']}</i>\n\n"

    text += (
        "Oder <code>/cancel</code> zum Abbrechen.\n\n"
        "⏱️ Stundensatz auch möglich: 20€/h"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def _handle_cancel(uid: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    key = _user_key(uid)
    if key in context.user_data:
        context.user_data.pop(key, None)
        await update.message.reply_text("❌ Abgebrochen. Komm gern später wieder 🎵")
        return True
    return False


async def _handle_package_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    text = update.message.text.strip().lower()
    uid = update.effective_user.id
    key = _user_key(uid)

    if text == "/cancel":
        return await _handle_cancel(uid, update, context)

    if text in PACKAGES:
        pkg = PACKAGES[text]
        context.user_data[key] = {"step": "desc", "package": text}
        await update.message.reply_text(
            f"{pkg['name']} — {pkg['price']}\n\n"
            f"<i>{pkg['desc']}</i>\n\n"
            "📝 Beschreib deinen Track kurz:\n"
            "Genre, BPM, gewünschter Vibe, Besonderheiten?\n\n"
            "Oder <code>/cancel</code>",
            parse_mode=ParseMode.HTML,
        )
        return True

    return False


async def _handle_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    key = _user_key(uid)
    data = context.user_data.get(key)
    if not data or data.get("step") != "desc":
        return False

    text = update.message.text.strip().lower()
    if text == "/cancel":
        return await _handle_cancel(uid, update, context)

    data["step"] = "file"
    data["description"] = update.message.text

    await update.message.reply_text(
        "🎵 Perfekt! Jetzt schick mir die Track-Datei:\n"
        "• MP3, WAV oder FLAC (bis ~50MB)\n"
        "• Als Audio-Datei hier im Chat\n\n"
        "Oder <code>/cancel</code>",
        parse_mode=ParseMode.HTML,
    )
    return True


def _is_audio_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in AUDIO_EXTENSIONS


async def _handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    key = _user_key(uid)
    data = context.user_data.get(key)
    if not data or data.get("step") != "file":
        return False

    audio = update.message.audio or update.message.voice
    doc = update.message.document
    file_id = None
    file_name = None
    file_size = 0

    if audio:
        file_id = audio.file_id
        file_name = audio.file_name or f"track_{uid}.ogg"
        file_size = getattr(audio, "file_size", 0)
    elif doc:
        file_id = doc.file_id
        file_name = doc.file_name or f"track_{uid}"
        file_size = getattr(doc, "file_size", 0)
    else:
        return False

    if file_size > 50 * 1024 * 1024:
        await update.message.reply_text(
            "❌ Datei zu groß (max 50MB).\n"
            "Komprimier den Track oder schick mir einen Link.\n"
            "Oder <code>/cancel</code>",
            parse_mode=ParseMode.HTML,
        )
        return True

    if not _is_audio_file(file_name):
        await update.message.reply_text(
            "❌ Das sieht nicht nach einer Audio-Datei aus.\n"
            "Bitte MP3, WAV oder FLAC.\n"
            "Oder <code>/cancel</code>",
            parse_mode=ParseMode.HTML,
        )
        return True

    data["step"] = "confirm"
    data["file_id"] = file_id
    data["file_name"] = file_name

    pkg = PACKAGES[data["package"]]
    summary = (
        f"<b>Zusammenfassung</b>\n\n"
        f"Package: {pkg['name']} — {pkg['price']}\n"
        f"Track: {escape(file_name)}\n"
        f"Größe: {file_size // 1024}KB\n"
        f"Beschreibung: {escape(data['description'])}\n\n"
        f"Alles korrekt? Dann schick ich's ab.\n"
        f"<code>/confirm</code> — Absenden\n"
        f"<code>/cancel</code> — Abbrechen"
    )
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)
    return True


async def _handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    key = _user_key(uid)
    data = context.user_data.get(key)
    if not data or data.get("step") != "confirm":
        return False

    text = update.message.text.strip().lower()
    if text == "/cancel":
        return await _handle_cancel(uid, update, context)
    if text != "/confirm":
        return False

    entry = {
        "user_id": uid,
        "username": update.effective_user.username or update.effective_user.first_name,
        "package": data["package"],
        "description": data["description"],
        "file_id": data["file_id"],
        "file_name": data["file_name"],
        "timestamp": datetime.now(_tz()).isoformat(),
        "status": "received",
    }

    ticket_id = f"MX{int(time.time())}"
    ticket_path = QUEUE_DIR / f"{ticket_id}.json"
    with open(ticket_path, "w") as f:
        json.dump(entry, f, indent=2)

    context.user_data.pop(key, None)

    await update.message.reply_text(
        f"✅ <b>Track eingereicht!</b>\n"
        f"Ticket: <code>{ticket_id}</code>\n\n"
        "Ich meld mich bei dir sobald ich dran bin 🎵🔥\n"
        "Status check: <code>/status " + ticket_id + "</code>",
        parse_mode=ParseMode.HTML,
    )

    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(
                aid,
                f"🎵 <b>Neuer Mastering-Auftrag</b>\n"
                f"Ticket: <code>{ticket_id}</code>\n"
                f"User: {entry['username']} (ID: {uid})\n"
                f"Package: {PACKAGES[data['package']]['name']} — {PACKAGES[data['package']]['price']}\n"
                f"Beschreibung: {escape(data['description'])}\n\n"
                f"Datei-ID: <code>{data['file_id']}</code>\n"
                f"Datei: {escape(data['file_name'])}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    return True


async def cmd_update_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: Ticket-Status updaten: /updatestatus MX1234567890 in_work"""
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("❌ Nur für Admins.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Syntax: <code>/updatestatus MX1234567890 status</code>\n\n"
            f"Verfügbar: {', '.join(STATUS_LABELS.keys())}",
            parse_mode=ParseMode.HTML,
        )
        return

    ticket = _get_ticket(args[0])
    if not ticket:
        await update.message.reply_text(f"❌ Ticket {escape(args[0])} nicht gefunden.", parse_mode=ParseMode.HTML)
        return

    new_status = args[1].lower()
    if new_status not in STATUS_LABELS:
        await update.message.reply_text(
            f"❌ Status '{escape(new_status)}' ungültig.\n"
            f"Verfügbar: {', '.join(STATUS_LABELS.keys())}",
            parse_mode=ParseMode.HTML,
        )
        return

    ticket["status"] = new_status
    ticket["updated_at"] = datetime.now(_tz()).isoformat()
    path = QUEUE_DIR / f"{args[0]}.json"
    with open(path, "w") as f:
        json.dump(ticket, f, indent=2)

    label = STATUS_LABELS[new_status]
    await update.message.reply_text(f"✅ Ticket {args[0]} → {label}")

    try:
        await context.bot.send_message(
            ticket["user_id"],
            f"🎵 <b>Status-Update: Mastering</b>\n"
            f"Ticket: <code>{args[0]}</code>\n"
            f"Status: {label}\n\n"
            f"<i>Dein Track ist auf dem Weg!</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def route_mastering(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    uid = update.effective_user.id
    key = _user_key(uid)
    data = context.user_data.get(key)
    if not data:
        return

    step = data.get("step")

    if step == "package":
        handled = await _handle_package_choice(update, context)
    elif step == "desc":
        handled = await _handle_desc(update, context)
    elif step == "file":
        handled = await _handle_file(update, context)
    elif step == "confirm":
        handled = await _handle_confirm(update, context)
    else:
        return

    if not handled:
        text = update.message.text
        if text and text.startswith("/"):
            return
        await update.message.reply_text(
            "Ich warte auf deine Eingabe für den Mastering-Intake.\n"
            "Schreib <code>/cancel</code> zum Abbrechen.",
            parse_mode=ParseMode.HTML,
        )
