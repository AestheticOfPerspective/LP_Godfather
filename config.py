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
GITHUB_URL: str = os.getenv("GITHUB_URL", "https://github.com/lifeplay/godfather-bot")
