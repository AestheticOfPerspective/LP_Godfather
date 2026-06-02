"""
handlers/dj.py — DJ-Agent Integration
Verbindet sich mit Navidrome (Subsonic API) und erstellt Vibe-Playlists.
Laeuft auf Emils Server oder lokal — Port 4533.
"""

import os
import random
import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

NAVIDROME_URL = os.getenv("NAVIDROME_URL", "http://localhost:4533")
NAVIDROME_USER = os.getenv("NAVIDROME_USER", "")
NAVIDROME_PASS = os.getenv("NAVIDROME_PASS", "")

# ── Vibe Presets ─────────────────────────────────────────────────────────────
VIBE_PRESETS: dict[str, dict] = {
    "focus": {
        "name": "🎯 Focus",
        "description": "Deep Work, Coding — minimal distraction",
        "genres": ["Electronic", "Ambient", "Lo-Fi", "Post-Rock", "Instrumental"],
    },
    "chill": {
        "name": "🌅 Chill",
        "description": "Feierabend, Relaxen",
        "genres": ["Chillout", "Jazz", "Acoustic", "Soul", "R&B"],
    },
    "party": {
        "name": "🎉 Party",
        "description": "Streams, Gaming, High Energy",
        "genres": ["Dance", "House", "Pop", "Hip-Hop", "Rock"],
    },
    "coding": {
        "name": "💻 Coding",
        "description": "Programming Sessions",
        "genres": ["Electronic", "Synthwave", "Drum and Bass", "Techno"],
    },
    "morning": {
        "name": "☀️ Morning",
        "description": "Uplifting Start in den Tag",
        "genres": ["Indie", "Pop", "Folk", "Electronic"],
    },
}


def _subsonic_params() -> dict:
    return {
        "u": NAVIDROME_USER,
        "p": NAVIDROME_PASS,
        "v": "1.11.0",
        "c": "godfather-bot",
        "f": "json",
    }


async def _fetch_random_songs(count: int = 50, genre: str | None = None) -> list[dict]:
    """Holt zufaellige Songs von Navidrome via Subsonic API."""
    params = _subsonic_params()
    params["size"] = str(count)
    if genre:
        params["genre"] = genre

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{NAVIDROME_URL}/rest/getRandomSongs.view",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs
    except Exception as e:
        logger.error(f"Navidrome Fehler: {e}")
        return []


async def create_song_share_link(song_id: str) -> str:
    """Erstellt einen oeffentlichen Share-Link fuer einen Song (falls serverseitig aktiviert)."""
    sid = (song_id or "").strip()
    if not sid:
        return ""

    params = _subsonic_params()
    params["id"] = sid

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{NAVIDROME_URL}/rest/createShare.view",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        shares = data.get("subsonic-response", {}).get("shares", {}).get("share", [])
        if isinstance(shares, dict):
            shares = [shares]
        if not shares or not isinstance(shares[0], dict):
            return ""

        url = shares[0].get("url", "")
        return url.strip() if isinstance(url, str) else ""
    except Exception as e:
        logger.info(f"Navidrome Share-Link nicht verfuegbar: {e}")
        return ""


async def generate_vibe_playlist(vibe_name: str, duration_minutes: int = 60) -> list[dict]:
    """Erstellt eine Playlist basierend auf einem Vibe-Preset."""
    preset = VIBE_PRESETS.get(vibe_name)
    if not preset:
        return []

    all_songs = []
    for genre in preset["genres"]:
        songs = await _fetch_random_songs(count=30, genre=genre)
        all_songs.extend(songs)

    if not all_songs:
        # Fallback: random songs ohne Genre-Filter
        all_songs = await _fetch_random_songs(count=100)

    # Deduplizieren
    seen = set()
    unique = []
    for s in all_songs:
        sid = s.get("id")
        if sid and sid not in seen:
            seen.add(sid)
            unique.append(s)

    random.shuffle(unique)

    # Playlist nach Dauer zusammenstellen
    target_sec = duration_minutes * 60
    playlist = []
    total = 0
    for song in unique:
        dur = int(song.get("duration", 180))
        if total + dur <= target_sec:
            playlist.append(song)
            total += dur
        if total >= target_sec * 0.9:
            break

    # Artist Diversity: max 3 Songs pro Artist
    artist_count: dict[str, int] = {}
    diverse = []
    for song in playlist:
        artist = song.get("artist", "Unknown")
        if artist_count.get(artist, 0) < 3:
            diverse.append(song)
            artist_count[artist] = artist_count.get(artist, 0) + 1

    return diverse


def format_playlist(playlist: list[dict], preset_name: str) -> str:
    """Formatiert die Playlist fuer Telegram-Output."""
    preset = VIBE_PRESETS.get(preset_name, {})
    name = preset.get("name", preset_name)

    if not playlist:
        return f"🎧 <b>{name}</b>\n\nKeine Songs gefunden. Ist Navidrome erreichbar?"

    total_min = sum(int(s.get("duration", 0)) for s in playlist) // 60
    lines = [f"🎧 <b>{name} Playlist</b> ({len(playlist)} Songs, ~{total_min} Min)\n"]

    for i, song in enumerate(playlist[:15], 1):
        title = song.get("title", "?")
        artist = song.get("artist", "?")
        dur = int(song.get("duration", 0))
        m, s = divmod(dur, 60)
        lines.append(f"{i}. <b>{title}</b> — {artist} ({m}:{s:02d})")

    if len(playlist) > 15:
        lines.append(f"\n... und {len(playlist) - 15} weitere Songs")

    return "\n".join(lines)


def get_vibe_keyboard():
    """Inline-Keyboard fuer Vibe-Auswahl."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    row = []
    for key, preset in VIBE_PRESETS.items():
        row.append(InlineKeyboardButton(preset["name"], callback_data=f"vibe_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)
