"""Edgerunner Cross-Promotion — /promo command.

Returns all channel links, YouTube description template, and social cross-posts
for the full Edgerunner network: JutsuGaming, Aesthetic Of Perspective,
LivePlay, LivePlayTV.
"""

from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import TWITCH_CHANNEL_URL, YOUTUBE_URL

CHANNELS = [
    {
        "name": "JutsuGaming",
        "emoji": "🎮",
        "desc": "Retro runs, dry humor, clean focus",
        "links": [
            ("Twitch", TWITCH_CHANNEL_URL or "https://twitch.tv/jutsugaming"),
            ("YouTube", YOUTUBE_URL or "https://youtube.com/@jutsugaming"),
        ],
    },
    {
        "name": "Aesthetic Of Perspective",
        "emoji": "🎨",
        "desc": "Creative Direction · Illustration · Dev · Content",
        "links": [
            ("Web", "https://web.asfmedia.org"),
        ],
    },
    {
        "name": "LivePlay",
        "emoji": "🎙️",
        "desc": "Life.Play Talks, BBB Sessions & Community",
        "links": [
            ("Web", "https://liveplaytv.de"),
        ],
    },
    {
        "name": "LivePlayTV",
        "emoji": "📺",
        "desc": "Live.Play Video & Stream Archive",
        "links": [
            ("Web", "https://liveplaytv.de"),
        ],
    },
]


def _build_channel_block() -> list[str]:
    lines = []
    for ch in CHANNELS:
        lines.append(f"{ch['emoji']} <b>{ch['name']}</b>")
        lines.append(f"   {escape(ch['desc'])}")
        for label, url in ch["links"]:
            if url:
                lines.append(f"   🔗 {label}: {url}")
        lines.append("")
    return lines


YOUTUBE_DESC_TEMPLATE = """
═══════════════════════════════════════
🎮 JutsuGaming — Retro runs, dry humor, clean focus
📺 Abonniere: https://youtube.com/@jutsugaming
🔴 Live: https://twitch.tv/jutsugaming

🎨 Aesthetic Of Perspective — Creative Direction & Dev
🌐 https://web.asfmedia.org

🎙️ LivePlay — Talks, BBB Sessions & Community
📺 LivePlayTV — Stream Archive
═══════════════════════════════════════
"""

SOCIAL_TEMPLATES = """
📱 <b>Instagram / Community-Post Templates</b>

── Vorschlag 1: JutsuGaming → AOP ──
🎮 Gaming trifft auf Kunst.
Auf JutsuGaming zock ich Retro-Klassiker, Horror und Cyberpunk — 
clean, kein Hype-Bait, einfach gute Runs.
Aber hinter den Kulissen? Da entsteht was Größeres.
Schau auf Aesthetic Of Perspective vorbei — da geht's um Design,
Perspektive und den ganzen Creative Dev Kram.
➡️ https://web.asfmedia.org
➡️ https://twitch.tv/jutsugaming
#JutsuGaming #AestheticOfPerspective #EdgerunnerNetwork

── Vorschlag 2: AOP → JutsuGaming ──
🎨 Creative Direction, Illustration & Dev — alles unter einer Handschrift.
Aber wusstest du, dass ich auch Retro-Games zock?
Freitags Horror Night, Sonntags ROM Hacks, Mittwochs Cyberpunk.
Kein Hype, nur gute Runs. Schau mal rein:
➡️ https://twitch.tv/jutsugaming
➡️ https://youtube.com/@jutsugaming
#AestheticOfPerspective #JutsuGaming #LifePlay

── Vorschlag 3: Cross-Network ──
🎮🎨🎙️ Das Edgerunner Network:
• JutsuGaming — Retro Runs & Horror Nights
• Aesthetic Of Perspective — Design & Dev
• LivePlay — Deep Talks & BBB Sessions
• LivePlayTV — Stream Archive
Alles aus einer Hand. Alles fossnomade.
➡️ https://twitch.tv/jutsugaming
➡️ https://web.asfmedia.org
➡️ https://liveplaytv.de
#EdgerunnerNetwork #JutsuGaming #AestheticOfPerspective #LivePlay
"""


async def cmd_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = [
        "🔥 <b>Edgerunner Cross-Promotion</b>",
        "Alle Channels des Netzwerks auf einen Blick.\n",
    ]
    lines += _build_channel_block()

    lines += [
        "<b>── YouTube Description Template ──</b>",
        "<code>" + escape(YOUTUBE_DESC_TEMPLATE.strip()) + "</code>",
        "",
        "<b>── Social Media Vorlagen ──</b>",
        SOCIAL_TEMPLATES.strip(),
        "",
        "💀 <b>Built different. Einer für alles.</b>",
    ]

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML
    )
