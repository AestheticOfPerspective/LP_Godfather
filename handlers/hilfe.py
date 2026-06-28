"""Enhanced Help System — kategorisches /hilfe mit Inline-Navigation.

Commands:
  /hilfe              – Kategorie-Menü mit Buttons
  /hilfe <kategorie>  – Detail-Hilfe für eine Kategorie

Kategorien: general, ai, stream, memory, training, moderation, hermes
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import CLIP_INTAKE_URL, TWITCH_CHANNEL_URL, YOUTUBE_URL

HELP_CATEGORIES = {
    "general": {
        "title": "Allgemein",
        "emoji": "📋",
        "desc": "Basis-Commands & Navigation",
        "commands": [
            ("/start", "Intro & Hauptmenü mit Buttons"),
            ("/help", "Diese klassische Command-Liste"),
            ("/hilfe", "Kategorische Hilfe (das hier)"),
            ("/about", "Über Life.Play"),
            ("/products", "Produkte & Preise ansehen"),
            ("/personas", "Life.Play KI-Persona-Übersicht"),
        ],
    },
    "ai": {
        "title": "KI & Chat",
        "emoji": "🤖",
        "desc": "Alle KI-Funktionen & Persona-System",
        "commands": [
            ("/ask [Frage]", "KI mit aktueller Persona befragen"),
            ("/persona", "KI-Persona wechseln (7 verfügbar)"),
            ("/prompt [Text]", "Prompt-Engineering-Analyse"),
            ("/orchestrate [Frage]", "Multi-Persona Perspektiven"),
            ("/tarot", "Nyx.exe Tarot-Orakel"),
            ("/comedy_test [Idee]", "Clip-Idee gegen Comedy Gates prüfen"),
            ("/vibe [preset]", "DJ-Agent Playlist erstellen"),
            ("/clear", "Gesprächsverlauf löschen"),
            ("🎙️ Sprachnachricht", "Wird transkribiert + KI antwortet"),
        ],
        "note": "Der Bot merkt sich die letzten 5 Nachrichten pro User. Nutzt Smart Routing: einfache Fragen → schnell (Gemini), komplexe → lokal (Ollama).",
    },
    "stream": {
        "title": "Stream & Community",
        "emoji": "📺",
        "desc": "JutsuGaming Stream-Utility & Community-Tools",
        "commands": [
            ("/wann", "Wochenplan der Streams"),
            ("/heute", "Stream-Status heute"),
            ("/follow", "Twitch/YouTube Follow-Links"),
            ("/clip [Text]", "Clip-Moment einreichen"),
            ("/recap [add Text]", "Letzten Recap zeigen oder neuen setzen (add=Admin)"),
            ("/promo", "Edgerunner Cross-Promotion: alle Channels & Vorlagen"),
            ("/deals [Produkt]", "Amazon Deals — Gaming/Streaming Tech (Partnerlinks)"),
            ("/mastering", "Mixing & Mastering — Track einreichen"),
        ],
        "note": "Du kannst auch natürlich schreiben: „wann stream?“, „heute live?“, „clip das“, „recap: Kurzfassung“. Commands sind nur Fallback.",
        "links": [
            ("Twitch", TWITCH_CHANNEL_URL),
            ("YouTube", YOUTUBE_URL),
        ],
    },
    "memory": {
        "title": "Memory",
        "emoji": "🧠",
        "desc": "Der Bot merkt sich Fakten über dich",
        "commands": [
            ("/remember [Fakt]", "Speichert einen Fakt über dich"),
            ("/recall [Begriff]", "Durchsucht deine gespeicherten Fakten"),
            ("/mymemories", "Listet alle deine Fakten auf"),
            ("/forget [ID]", "Löscht einen bestimmten Fakt"),
        ],
        "note": "Sag natürlich: „merk dir ich programmiere seit 10 Jahren TypeScript @meinGodFatherBot“ oder „was weißt du über mich @meinGodFatherBot?“. In Gruppen: Text zuerst, Mention danach irgendwo mittendrin oder am Ende. Sensible Fakten speichert GodFather nicht automatisch.",
    },
    "training": {
        "title": "Training",
        "emoji": "📚",
        "desc": "Wissensdatenbank (Admins)",
        "commands": [
            ("/teach Thema | Inhalt", "Wissen speichern (Admin)"),
            ("/knowledge [Begriff]", "Wissen abrufen"),
            ("/trainings", "Alle Themen auflisten (Admin)"),
            ("/forget_training [ID]", "Wissen löschen (Admin)"),
        ],
        "note": "Admins können natürlich schreiben: „lern: Night City Sessions | Mittwoch 19:30 Cyberpunk“. Der Bot nutzt passende Einträge automatisch im Kontext.",
    },
    "moderation": {
        "title": "Moderation",
        "emoji": "🛡️",
        "desc": "Admin-Tools für Gruppen",
        "commands": [
            ("/warn @User [Grund]", "Verwarnung aussprechen"),
            ("/warns @User", "Verwarnungen anzeigen"),
            ("/mute @User [Min]", "Stummschalten"),
            ("/unmute @User", "Stummschaltung aufheben"),
            ("/kick @User [Grund]", "Kicken"),
            ("/ban @User [Grund]", "Bannen"),
            ("/stats", "Gruppen-Statistiken"),
            ("/revive [Tage] [--dm]", "Inaktive Member pingen (Default 14d, --dm für DM)"),
            ("/activity [Tage]", "Community-Aktivität anzeigen"),
        ],
    },
    "sales": {
        "title": "SUPERNOVA Sales",
        "emoji": "💫",
        "desc": "Live.Play SUPERNOVA Campaign & Deal Tracker",
        "commands": [
            ("/supernova", "SUPERNOVA Campaign Status + Countdown"),
        ],
        "note": "Sales-Channels: ExtremeAlex27 auf Facebook, Instagram, LinkedIn & Meta Ads. Der Countdown läuft — check den Fortschritt!",
    },
    "hermes": {
        "title": "Hermes Router",
        "emoji": "🔀",
        "desc": "Telegram Control Plane & Orchestration",
        "commands": [
            ("/live [sub]", "Stream State & Orchestration"),
            ("/dj [sub]", "DJ Actions & Mode"),
            ("/ops [sub]", "Runtime/Ops Status"),
            ("/chronik [sub]", "Recap & Learnings"),
        ],
        "subs": "sub: preflight | go | checkpoint | brb | panic | outro | state | mode | drop | switch | lock | recover | status | diag | log | recap",
    },
}

CATEGORY_ORDER = ["general", "ai", "stream", "sales", "memory", "training", "moderation", "hermes"]


def format_help_menu() -> str:
    text = (
        "❓ <b>GodFather Hilfe-Menü</b>\n\n"
        "Du musst dir keine Commands merken. Sag es natürlich:\n"
        "• merk dir ich streame freitags Horror @meinGodFatherBot\n"
        "• lern diese Gruppe: Bot-Ecke | Bot-Tests, Feedback, Automatisierung @meinGodFatherBot\n"
        "• lern: Night City Sessions | Mittwoch 19:30 Cyberpunk @meinGodFatherBot\n"
        "• clip das @meinGodFatherBot\n"
        "• Nyx, push mich kurz @meinGodFatherBot\n"
        "• wann stream? @meinGodFatherBot\n\n"
        "Telegram-Gruppen-Tipp: Text zuerst, Bot-Mention danach mittendrin oder am Ende.\n"
        "Grundregel: Read the room, read the person, then text.\n\n"
        "Kategorien für Details:\n\n"
    )
    for key in CATEGORY_ORDER:
        cat = HELP_CATEGORIES[key]
        text += f"{cat['emoji']} <code>/hilfe {key}</code>  – {cat['desc']}\n"
    return text + "\nButtons unten gehen auch, Choom. 💀"


def format_help_category(key: str) -> str:
    return _format_category(key)


def _build_category_keyboard(back_to_menu: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    for key in CATEGORY_ORDER:
        cat = HELP_CATEGORIES[key]
        buttons.append([
            InlineKeyboardButton(
                f"{cat['emoji']} {cat['title']}", callback_data=f"hilfe_{key}"
            ),
        ])
    if back_to_menu:
        buttons.append([InlineKeyboardButton("⬅️ Zurück zum Menü", callback_data="hilfe_menu")])
    return InlineKeyboardMarkup(buttons)


def _format_category(key: str) -> str:
    cat = HELP_CATEGORIES[key]
    lines = [f"{cat['emoji']} <b>{cat['title']}</b> — {cat['desc']}\n"]

    for cmd, desc in cat["commands"]:
        lines.append(f"  <code>{cmd}</code>  — {desc}")

    if "links" in cat:
        lines.append("")
        for name, url in cat["links"]:
            if url:
                lines.append(f"  🔗 {name}: {url}")

    if "note" in cat:
        lines.append(f"\n💡 <i>{cat['note']}</i>")

    if "subs" in cat:
        lines.append(f"\n🔸 Verfügbare Sub-Commands: <code>{cat['subs']}</code>")

    return "\n".join(lines)


async def cmd_hilfe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        key = context.args[0].lower()
        if key in HELP_CATEGORIES:
            text = _format_category(key)
            keyboard = _build_category_keyboard(back_to_menu=True)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        # Fuzzy match
        matches = [k for k in CATEGORY_ORDER if k.startswith(key)]
        if matches:
            text = _format_category(matches[0])
            keyboard = _build_category_keyboard(back_to_menu=True)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        await update.message.reply_text(
            f"❌ Unbekannte Kategorie: „{key}“\n"
            f"Verfügbar: {', '.join(HELP_CATEGORIES.keys())}",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        format_help_menu(), parse_mode=ParseMode.HTML, reply_markup=_build_category_keyboard()
    )


async def handle_hilfe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "hilfe_menu":
        await query.edit_message_text(
            format_help_menu(), parse_mode=ParseMode.HTML, reply_markup=_build_category_keyboard()
        )
        return

    if data.startswith("hilfe_"):
        key = data[len("hilfe_"):]
        if key in HELP_CATEGORIES:
            text = _format_category(key)
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=_build_category_keyboard(back_to_menu=True),
            )
