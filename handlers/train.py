"""Training handler — Knowledge Base verwalten.

Admins können Wissen speichern, das der Bot bei allen Antworten
berücksichtigt — ideal für Stream-Lore, Community-Wissen, FAQ.

Commands:
  /teach <topic> | <content>       – Wissen speichern (Admin)
  /knowledge <topic>                – Wissen abrufen
  /trainings                        – Alle Themen auflisten (Admin)
  /forget_training <id>             – Wissen löschen (Admin)
"""

from html import escape

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS
from utils.storage import db


async def cmd_teach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Nur Admins können mich trainieren, Choom.")
        return

    if not context.args or "|" not in " ".join(context.args):
        await update.message.reply_text(
            "❓ Nutzung: <code>/teach Thema | Wissensinhalt</code>\n\n"
            "Beispiele:\n"
            "<code>/teach JutsuGaming | Ist ein deutscher Gaming-Streamer, spielt Cyberpunk, Horror, Retro.</code>\n"
            "<code>/teach Live.Play | Premium-Hub für Creator & KI-Entwickler. FOSS trifft Commercial.</code>\n"
            "<code>/teach Night City Sessions | Jeden Mi 19:30 auf Twitch. Cyberpunk 2077, Lore-Dives, Challengeruns.</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = " ".join(context.args)
    parts = raw.split("|", 1)
    topic = parts[0].strip()
    content = parts[1].strip() if len(parts) > 1 else ""

    if not topic or not content:
        await update.message.reply_text("❌ Thema und Inhalt dürfen nicht leer sein.")
        return

    if len(topic) > 200:
        await update.message.reply_text("❌ Thema maximal 200 Zeichen.")
        return
    if len(content) > 2000:
        await update.message.reply_text("❌ Inhalt maximal 2000 Zeichen.")
        return

    kid = db.add_knowledge(
        topic=topic,
        content=content,
        source="telegram",
        added_by=str(user.id),
    )

    await update.message.reply_text(
        f"📚 <b>Wissen gespeichert!</b> (ID #{kid})\n"
        f"Thema: {escape(topic)}\n"
        f"Inhalt: {escape(content[:200])}{'…' if len(content) > 200 else ''}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/knowledge Suchbegriff oder Thema</code>\n\n"
            "Durchsucht die Wissensdatenbank nach passenden Einträgen.",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args).strip()
    results = db.search_knowledge(query)

    if not results:
        await update.message.reply_text(
            f"📚 Kein Wissen zu „{escape(query)}“ gefunden.\n"
            "Admins können mit <code>/teach</code> neues Wissen hinzufügen.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"📚 <b>Wissen zu „{escape(query)}“</b>\n"]
    for kid, topic, content, source, created_at in results[:5]:
        lines.append(f"\n<b>{escape(topic)}</b> (ID #{kid})")
        lines.append(f"{escape(content[:300])}{'…' if len(content) > 300 else ''}")

    if len(results) > 5:
        lines.append(f"\n… und {len(results) - 5} weitere Treffer.")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_trainings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Nur für Admins.")
        return

    topics = db.list_knowledge_topics()

    if not topics:
        await update.message.reply_text(
            "📚 Wissensdatenbank ist leer.\n"
            "Nutze <code>/teach</code> um den Bot zu trainieren.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Hole Details pro Thema
    lines = ["📚 <b>Wissensdatenbank – Themenübersicht</b>\n"]
    for topic in topics:
        entries = db.get_knowledge_by_topic(topic)
        lines.append(f"  • {escape(topic)} ({len(entries)} Einträge)")

    lines.append(
        "\nEinen Eintrag löschen: <code>/forget_training &lt;ID&gt;</code>\n"
        "Inhalt ansehen: <code>/knowledge &lt;Thema&gt;</code>"
    )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_forget_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Nur für Admins.")
        return

    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/forget_training 42</code>\n\n"
            "ID mit <code>/trainings</code> oder <code>/knowledge</code> finden.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        kid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Bitte eine gültige ID-Nummer angeben.")
        return

    if db.delete_knowledge(kid):
        await update.message.reply_text(f"📚 Wissenseintrag #{kid} gelöscht.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ Kein Eintrag mit ID #{kid} gefunden.", parse_mode=ParseMode.HTML)
