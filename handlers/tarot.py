"""Cyberpunk tarot command for Telegram."""

from __future__ import annotations

import random
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "tarot"

CARDS: list[tuple[str, str, str]] = [
    ("00_der_narr.png", "Der Narr", "Neustart, Risiko, erster Schritt. Spring, aber mit offenen Augen."),
    ("01_der_magier.png", "Der Magier", "Tools sind geladen. Jetzt baust du Realitaet statt Ausreden."),
    ("02_die_hohepriesterin.png", "Die Hohepriesterin", "Dein Bauchgefuehl hat Root-Zugriff. Hoer genauer hin."),
    ("03_die_herrscherin.png", "Die Herrscherin", "Kreation, Pflege, Wachstum. Was du naehrst, wird groesser."),
    ("04_der_kaiser.png", "Der Kaiser", "Struktur, Grenzen, Fuehrung. Chaos braucht ein Command-Center."),
    ("05_der_hierophant.png", "Der Hierophant", "Tradition, Lehre, Systemwissen. Lerne die Regeln, dann hack sie."),
    ("06_die_liebenden.png", "Die Liebenden", "Entscheidung mit Herz. Alignment ist staerker als reine Logik."),
    ("07_der_wagen.png", "Der Wagen", "Momentum. Greif ans Steuer, sonst faehrt die City dich."),
    ("08_die_kraft.png", "Die Kraft", "Sanfte Macht. Nicht lauter werden, stabiler werden."),
    ("09_der_eremit.png", "Der Eremit", "Rueckzug ist kein Fehler. Im Dunkeln sieht man manche Signale besser."),
    ("10_rad_des_schicksals.png", "Rad des Schicksals", "Der Zyklus dreht. Nutze den Spin, statt gegen ihn zu kaempfen."),
    ("11_die_gerechtigkeit.png", "Die Gerechtigkeit", "Klarheit, Konsequenz, Ausgleich. Der Log zeigt alles."),
    ("12_der_gehaengte.png", "Der Gehaengte", "Perspektivwechsel. Stillstand kann ein anderer Blickwinkel sein."),
    ("13_der_tod.png", "Der Tod", "Transformation. Etwas endet, damit der Phoenix Platz hat."),
    ("14_die_maessigkeit.png", "Die Maessigkeit", "Balance. Feuer und Wasser werden Alchemie, wenn du sie fuehrst."),
    ("15_der_teufel.png", "Der Teufel", "Bindungen, Muster, Versuchung. Frag: was besitzt mich gerade?"),
    ("16_der_turm.png", "Der Turm", "Reset durch Wahrheit. Was faellt, war nicht stabil genug."),
    ("17_der_stern.png", "Der Stern", "Hoffnung, Heilung, Signal am Horizont. Folge dem kleinen Licht."),
    ("18_der_mond.png", "Der Mond", "Nebel, Traum, Projektion. Nicht alles ist, wie es leuchtet."),
    ("19_die_sonne.png", "Die Sonne", "Klarheit, Erfolg, Energie. Geh sichtbar, Choom."),
    ("20_das_gericht.png", "Das Gericht", "Ruf, Erwachen, Entscheidung. Der naechste Level fragt nach dir."),
    ("21_die_welt.png", "Die Welt", "Completion. Ein Kreis schliesst sich, ein groesserer startet."),
]


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎭 Tageskarte", callback_data="tarot_single")],
        [InlineKeyboardButton("🎵 Pick-a-Card", callback_data="tarot_pick")],
        [InlineKeyboardButton("✨ 3er Legung", callback_data="tarot_three")],
        [InlineKeyboardButton("❌ Schliessen", callback_data="tarot_close")],
    ])


def _pick_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💜 Frequenz Alpha", callback_data="tarot_pile_0")],
        [InlineKeyboardButton("💙 Frequenz Beta", callback_data="tarot_pile_1")],
        [InlineKeyboardButton("💛 Frequenz Gamma", callback_data="tarot_pile_2")],
        [InlineKeyboardButton("↩️ Zurueck", callback_data="tarot_menu")],
    ])


def _format_card(card: tuple[str, str, str], prefix: str = "Deine Karte") -> str:
    _, name, meaning = card
    return (
        f"🎭 <b>{prefix}: {name}</b>\n\n"
        f"{meaning}\n\n"
        "<i>Nyx.exe fluestert: Die Karte ist kein Urteil. Sie ist ein Spiegel.</i>"
    )


async def _send_card(update: Update, context: ContextTypes.DEFAULT_TYPE, card: tuple[str, str, str], prefix: str) -> None:
    filename, _, _ = card
    image_path = ASSETS_DIR / filename
    chat = update.effective_chat
    if not chat:
        return
    caption = _format_card(card, prefix)

    if image_path.exists():
        with open(image_path, "rb") as image:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=InputFile(image),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
    else:
        await context.bot.send_message(chat_id=chat.id, text=caption, parse_mode=ParseMode.HTML)


async def cmd_tarot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "🎭 <b>Nyx.exe — Tarot-Orakel</b>\n\n"
        "Waehle dein Legesystem. Cyberpunk-Vibe, klare Spiegelung, kein Hokuspokus-Spam.",
        parse_mode=ParseMode.HTML,
        reply_markup=_menu_keyboard(),
    )


async def handle_tarot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    if data == "tarot_close":
        await query.edit_message_text("❌ Tarot-Orakel geschlossen. Die Karten warten im Neon-Nebel.")
        return

    if data == "tarot_menu":
        await query.edit_message_text(
            "🎭 <b>Nyx.exe — Tarot-Orakel</b>\n\nWaehle dein Legesystem.",
            parse_mode=ParseMode.HTML,
            reply_markup=_menu_keyboard(),
        )
        return

    if data == "tarot_pick":
        user_data = context.user_data
        if user_data is not None:
            user_data["tarot_piles"] = random.sample(CARDS, 3)
        await query.edit_message_text(
            "🎵 <b>Pick-a-Card</b>\n\nDrei Frequenzen liegen bereit. Welche zieht dich?",
            parse_mode=ParseMode.HTML,
            reply_markup=_pick_keyboard(),
        )
        return

    if data.startswith("tarot_pile_"):
        user_data = context.user_data or {}
        piles = user_data.get("tarot_piles") or random.sample(CARDS, 3)
        idx = int(data.rsplit("_", 1)[1])
        if idx < len(piles):
            await query.edit_message_text("✨ Karte aufgedeckt. Schau in den Spiegel.")
            await _send_card(update, context, piles[idx], "Deine Frequenz")
        return

    if data == "tarot_single":
        card = random.choice(CARDS)
        await query.edit_message_text("🎭 Tageskarte gezogen. Nyx legt sie vor dich.")
        await _send_card(update, context, card, "Tageskarte")
        return

    if data == "tarot_three":
        cards = random.sample(CARDS, 3)
        labels = ["Vergangenheit", "Gegenwart", "Zukunft"]
        text = "✨ <b>3er Legung — dein Pfad</b>\n\n"
        text += "\n\n".join(_format_card(card, label) for label, card in zip(labels, cards))
        await query.edit_message_text(text[:3900], parse_mode=ParseMode.HTML, reply_markup=_menu_keyboard())
