"""Shared stream utility copy for Telegram and Twitch."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import (
    CLIP_INTAKE_URL,
    STREAM_BRAND,
    STREAM_SCHEDULE,
    STREAM_TIMEZONE,
    STREAM_TODAY_FALLBACK,
    TWITCH_CHANNEL,
    TWITCH_CHANNEL_URL,
    YOUTUBE_URL,
)


_DAY_ALIASES = {
    "mo": 0,
    "montag": 0,
    "di": 1,
    "dienstag": 1,
    "mi": 2,
    "mittwoch": 2,
    "do": 3,
    "donnerstag": 3,
    "fr": 4,
    "freitag": 4,
    "sa": 5,
    "samstag": 5,
    "so": 6,
    "sonntag": 6,
}


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(STREAM_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Berlin")


def _parse_schedule() -> list[tuple[int | None, str, str, str]]:
    entries = []
    for raw in STREAM_SCHEDULE.split(";"):
        item = " ".join(raw.split())
        if not item:
            continue
        parts = item.split(" ", 2)
        if len(parts) < 2:
            entries.append((None, "", item, item))
            continue
        day_raw = parts[0].lower().rstrip(":")
        time_raw = parts[1]
        title = parts[2] if len(parts) > 2 else "Stream"
        entries.append((_DAY_ALIASES.get(day_raw), time_raw, title, item))
    return entries


def _twitch_url() -> str:
    if TWITCH_CHANNEL_URL:
        return TWITCH_CHANNEL_URL
    if TWITCH_CHANNEL:
        return f"https://twitch.tv/{TWITCH_CHANNEL}"
    return "https://twitch.tv/jutsugaming"


def _compact(text: str, max_len: int = 430) -> str:
    return text if len(text) <= max_len else text[: max_len - 3].rstrip() + "..."


def format_wann(*, twitch: bool = False) -> str:
    schedule = STREAM_SCHEDULE.replace(";", " | ")
    text = (
        f"📅 {STREAM_BRAND} Wochenplan ({STREAM_TIMEZONE}):\n"
        f"{schedule}\n\n"
        f"Follow: {_twitch_url()}"
    )
    return _compact(text) if twitch else text


def format_heute(*, twitch: bool = False) -> str:
    now = datetime.now(_tz())
    matches = [entry for entry in _parse_schedule() if entry[0] == now.weekday()]
    if matches:
        _, time_raw, title, _ = matches[0]
        text = (
            f"🔥 Heute Stream: {title} um {time_raw} ({STREAM_TIMEZONE}).\n"
            f"Rein da: {_twitch_url()}"
        )
    else:
        text = f"📡 {STREAM_TODAY_FALLBACK}\n{_twitch_url()}"
    return _compact(text) if twitch else text


def format_follow(*, twitch: bool = False) -> str:
    links = [f"Twitch: {_twitch_url()}"]
    if YOUTUBE_URL:
        links.append(f"YouTube: {YOUTUBE_URL}")
    text = "🔗 Follow JutsuGaming / Live.Play:\n" + "\n".join(links)
    return _compact(text) if twitch else text


def format_clip(*, twitch: bool = False) -> str:
    if CLIP_INTAKE_URL:
        target = CLIP_INTAKE_URL
    else:
        target = "Poste den Twitch-Clip-Link in die Live.Play Gruppe oder markiere den Moment im Chat."
    text = (
        "🎬 Clip-Moment gesehen?\n"
        f"{target}\n"
        "Kurz dazu: Was war der Moment und warum war er clip-wuerdig?"
    )
    return _compact(text) if twitch else text


def format_clip_saved(clip_id: int, *, twitch: bool = False) -> str:
    text = f"🎬 Clip-Moment gespeichert. ID #{clip_id}. GodFather merkt sich den Kandidaten fuer den Recap."
    return _compact(text) if twitch else text


def format_recap(recap: tuple | None, *, twitch: bool = False) -> str:
    if not recap:
        text = (
            "🧾 Noch kein Stream-Recap gespeichert.\n"
            "Admins koennen einen Recap setzen mit: /recap add <Kurzfassung>"
        )
        return _compact(text) if twitch else text

    source, actor, body, created_at = recap
    text = (
        "🧾 Letzter Stream-Recap\n"
        f"Quelle: {source} | von {actor} | {created_at}\n\n"
        f"{escape(str(body))}"
    )
    return _compact(text) if twitch else text


def format_recap_saved(recap_id: int, *, twitch: bool = False) -> str:
    text = f"🧾 Recap gespeichert. ID #{recap_id}. Abrufbar mit /recap oder !recap."
    return _compact(text) if twitch else text
