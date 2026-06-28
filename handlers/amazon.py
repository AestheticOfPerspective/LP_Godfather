"""Amazon PartnerNet — /deals Command + Affiliate Link Builder.

Commands:
  /deals          — Alle Kategorien & Produkte
  /deals setup    — Fossnomade's persönliches Stream-Equipment
  /deals <keyword> — Produkt-Suche
"""

from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import AMAZON_PARTNER_TAG

PERSONAL_GEAR = [
    ("🔊 Anker SoundCore 2", "B01MTB55WH", "~30€"),
    ("🕷️ Spider-Man Premium Maske", "B0FG7JPX4L", "~80€"),
    ("🎤 Mikrofon", "", "Platzhalter"),
    ("🎧 Kopfhörer", "", "Platzhalter"),
    ("🖱️ Maus", "", "Platzhalter"),
    ("⌨️ Tastatur", "", "Platzhalter"),
]

DEALS = [
    {
        "name": "🔥 Mein Stream-Setup",
        "items": PERSONAL_GEAR,
    },
    {
        "name": "Streaming Setup",
        "items": [
            ("Logitech C920 Webcam", "B08J8K3W1Q", "49€"),
            ("Rode NT-USB Mikrofon", "B00N1YPXW2", "129€"),
            ("Elgato Stream Deck MK.2", "B09738CV2G", "139€"),
            ("Elgato Key Light", "B07N3DHN6L", "179€"),
        ],
    },
    {
        "name": "Gaming Peripherals",
        "items": [
            ("Razer DeathAdder V3", "B0B7X6Y9YZ", "89€"),
            ("SteelSeries Arctis 7+", "B09H6ZQ6JG", "149€"),
            ("Corsair K70 RGB Pro", "B0B7X6Y9YZ", "169€"),
        ],
    },
    {
        "name": "Retro & Tech",
        "items": [
            ("Raspberry Pi 5 (8GB)", "B0CK3Y7K2G", "89€"),
            ("SanDisk Extreme 1TB", "B08R2XGQ8Q", "89€"),
            ("Anker PowerCore 26800", "B01JIWQPMW", "55€"),
        ],
    },
    {
        "name": "🕷️ Cosplay / Masken",
        "items": [
            ("Spider-Man Premium Helm (LED + bewegliche Augen)", "B0FG7JPX4L", "~80€"),
        ],
    },
]


def amazon_url(asin: str) -> str:
    if not asin:
        return ""
    base = "https://www.amazon.de/dp/"
    if AMAZON_PARTNER_TAG:
        return f"{base}{asin}?tag={AMAZON_PARTNER_TAG}"
    return base + asin


def _format_section(name: str, items: list) -> str:
    lines = [f"<b>── {name} ──</b>"]
    for entry in items:
        title, asin, price = entry[0], entry[1], entry[2]
        url = amazon_url(asin)
        if url:
            lines.append(f"  • <a href='{url}'>{escape(title)}</a> — {price}")
        else:
            lines.append(f"  • {escape(title)} — {price}")
    lines.append("")
    return "\n".join(lines)


def format_deals() -> str:
    tag_status = f"Tag: <code>{escape(AMAZON_PARTNER_TAG)}</code>" if AMAZON_PARTNER_TAG else "⚠️ Kein Partner-Tag gesetzt!"

    lines = [
        "🛒 <b>Amazon Deals — JutsuGaming Empfehlungen</b>",
        f"{tag_status}\n",
        "💡 <code>/deals setup</code> — Mein persönliches Equipment",
        "💡 <code>/deals maus</code> — Produkt-Suche\n",
    ]

    for cat in DEALS:
        lines.append(_format_section(cat["name"], cat["items"]))

    lines.append(
        "💡 <i>Als Amazon-Partner verdiene ich an qualifizierten Verkäufen. "
        "Dir entstehen keine Mehrkosten.</i>"
    )

    return "\n".join(lines)


def format_personal_setup() -> str:
    lines = [
        "🛒 <b>Mein Stream-Setup — Fossnomade</b>\n"
        "Alles was ich zum streamen, zocken und produzieren nutze.\n"
        "<i>Platzhalter — ich update sobald ich mein genaues Equipment gecheckt habe!</i>\n",
    ]
    lines.append(_format_section("Mein Equipment", PERSONAL_GEAR))

    lines.append(
        "📝 <i>Du nutzt auch Stream-Zeug? Schreib mir — ich such dir den Amazon-Link raus!</i>"
    )
    return "\n".join(lines)


async def cmd_deals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    if args:
        keyword = " ".join(args).lower()

        if keyword == "setup":
            await update.message.reply_text(format_personal_setup(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return

        results = []
        for cat in DEALS:
            for entry in cat["items"]:
                if keyword in entry[0].lower():
                    results.append(entry)

        if results:
            lines = [f"🛒 <b>Suche: {escape(keyword)}</b>\n"]
            for title, asin, price in results:
                url = amazon_url(asin)
                if url:
                    lines.append(f"  • <a href='{url}'>{escape(title)}</a> — {price}")
                else:
                    lines.append(f"  • {escape(title)} — {price}")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return
        else:
            await update.message.reply_text(
                f"❌ Nix zu „{escape(keyword)}“ gefunden.\n"
                "Tipp: <code>/deals</code> für alle Kategorien.",
                parse_mode=ParseMode.HTML,
            )
            return

    await update.message.reply_text(format_deals(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
