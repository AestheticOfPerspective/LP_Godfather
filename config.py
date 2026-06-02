"""
config.py — GodFather Bot Konfiguration
Alle Einstellungen aus .env laden (python-dotenv)
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)  # .env hat immer Vorrang vor OS-Umgebungsvariablen

# ── Bot Credentials ───────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ── Admin User IDs (Telegram User-IDs als int) ────────────────────────────────
# Komma-separiert in .env: ADMIN_IDS=123456789,987654321
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(uid.strip()) for uid in _raw_admins.split(",") if uid.strip().isdigit()
]

# ── Features ──────────────────────────────────────────────────────────────────
WELCOME_ENABLED: bool = os.getenv("WELCOME_ENABLED", "true").lower() == "true"
ANTISPAM_ENABLED: bool = os.getenv("ANTISPAM_ENABLED", "true").lower() == "true"

# Max Verwarnungen bevor Auto-Kick
MAX_WARNS: int = int(os.getenv("MAX_WARNS", "3"))

# Gemini Modell
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Datenbank ─────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "data/godfather.db")

# ── Community Links ───────────────────────────────────────────────────────────
DISCORD_LINK: str = os.getenv("DISCORD_LINK", "")
WEBSITE_URL: str = os.getenv("WEBSITE_URL", "https://lifeplay.dev")
GITHUB_URL: str = os.getenv("GITHUB_URL", "https://github.com/AestheticOfPerspective/LP_Godfather")

# ── Stream / JutsuGaming Community Utility ───────────────────────────────────
STREAM_BRAND: str = os.getenv("STREAM_BRAND", "JutsuGaming powered by Live.Play")
STREAM_TIMEZONE: str = os.getenv("STREAM_TIMEZONE", "Europe/Berlin")
STREAM_SCHEDULE: str = os.getenv(
    "STREAM_SCHEDULE",
    "mi 19:30 Cyberpunk Night City; fr 19:30 Horror Night; so 18:00 Retro ROM Hacks",
)
STREAM_TODAY_FALLBACK: str = os.getenv(
    "STREAM_TODAY_FALLBACK",
    "Heute ist kein fixer Stream eingetragen. Spontan kann immer Magie passieren — follow fuer Ping.",
)
TWITCH_CHANNEL_URL: str = os.getenv("TWITCH_CHANNEL_URL", "")
YOUTUBE_URL: str = os.getenv("YOUTUBE_URL", "")
CLIP_INTAKE_URL: str = os.getenv("CLIP_INTAKE_URL", "")

# ── Runtime Mode ───────────────────────────────────────────────────────────────
# Choose between "telegram" and "twitch"
BOT_MODE: str = (os.getenv("BOT_MODE") or "telegram").lower()

# ── Twitch Credentials ────────────────────────────────────────────────────────
TWITCH_TOKEN: str = os.getenv("TWITCH_TOKEN", "")
TWITCH_CLIENT_ID: str = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET: str = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_CHANNEL: str = os.getenv("TWITCH_CHANNEL", "")
TWITCH_BOT_NICK: str = os.getenv("TWITCH_BOT_NICK", "lp_godfather")
TWITCH_BOT_ID: int = int(os.getenv("TWITCH_BOT_ID") or "0")
TWITCH_OWNER: str = os.getenv("TWITCH_OWNER", "")
TWITCH_ADMIN_USERS: list[str] = [
    u.strip().lower() for u in os.getenv("TWITCH_ADMIN_USERS", "").split(",") if u.strip()
]

# ── Command Cooldowns (Sekunden) ──────────────────────────────────────────────
COOLDOWN_DEFAULT: int = int(os.getenv("COOLDOWN_DEFAULT", "3"))
COOLDOWN_MOD: int = int(os.getenv("COOLDOWN_MOD", "1"))
COOLDOWN_AI: int = int(os.getenv("COOLDOWN_AI", "10"))
COOLDOWN_VIBE: int = int(os.getenv("COOLDOWN_VIBE", "30"))

# ── Hermes Primary Router (Telegram-First Control Plane) ──────────────────────
HERMES_ROUTER_ENABLED: bool = os.getenv("HERMES_ROUTER_ENABLED", "false").lower() == "true"
HERMES_ROUTER_URL: str = os.getenv("HERMES_ROUTER_URL", "")
HERMES_ROUTER_TOKEN: str = os.getenv("HERMES_ROUTER_TOKEN", "")
HERMES_ROUTER_TIMEOUT: float = float(os.getenv("HERMES_ROUTER_TIMEOUT", "8"))
HERMES_DEFAULT_PHASE: str = (os.getenv("HERMES_DEFAULT_PHASE") or "prep").lower()
HERMES_DEFAULT_DJ_MODE: str = (os.getenv("HERMES_DEFAULT_DJ_MODE") or "cyber-zen").lower()
_raw_router_chats = os.getenv("HERMES_ALLOWED_CHAT_IDS", "")
HERMES_ALLOWED_CHAT_IDS: list[int] = [
    int(cid.strip())
    for cid in _raw_router_chats.split(",")
    if cid.strip().lstrip("-").isdigit()
]
_raw_router_titles = os.getenv("HERMES_ALLOWED_CHAT_TITLES", "")
HERMES_ALLOWED_CHAT_TITLES: list[str] = [
    title.strip().lower()
    for title in _raw_router_titles.split(",")
    if title.strip()
]

# ── Telegram Tone / FSK Maturity ─────────────────────────────────────────────
TELEGRAM_DEFAULT_FSK: int = int(os.getenv("TELEGRAM_DEFAULT_FSK", "12"))
_raw_chat_fsk = os.getenv(
    "TELEGRAM_CHAT_FSK",
    "Live.Play=18,Aesthetic Of Perspective=18",
)
TELEGRAM_CHAT_FSK: dict[str, int] = {}
for item in _raw_chat_fsk.split(","):
    if "=" not in item:
        continue
    title, level = [part.strip() for part in item.split("=", 1)]
    if title and level.isdigit():
        TELEGRAM_CHAT_FSK[title.lower()] = int(level)
