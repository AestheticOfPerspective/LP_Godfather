"""
Twitch Runtime — GodFather als Twitch Chat Bot (Phase 1 MVP)
"""
import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime

from utils.graceful import shutdown_handler, is_shutting_down, on_shutdown

# Fix für twitchio + Python 3.14 (kein Event-Loop in MainThread)
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from twitchio.ext import commands

from config import (
    TWITCH_TOKEN,
    TWITCH_CHANNEL,
    TWITCH_BOT_NICK,
    TWITCH_OWNER,
    TWITCH_ADMIN_USERS,
    COOLDOWN_DEFAULT,
    COOLDOWN_MOD,
    COOLDOWN_AI,
    COOLDOWN_VIBE,
    MAX_WARNS,
    GEMINI_MODEL,
)
from handlers.ai import (
    ask_ai,
    PERSONAS,
    get_user_persona,
    set_user_persona,
    clear_history,
    suggest_persona,
)
from handlers.dj import create_song_share_link, generate_vibe_playlist, VIBE_PRESETS
from handlers.stream import (
    format_clip,
    format_clip_saved,
    format_follow,
    format_heute,
    format_recap,
    format_recap_saved,
    format_wann,
)
from utils.storage import db
from utils.ratelimit import rate_limiter
from handlers.nyx_buffer import ChatBuffer
from handlers.nyx_timer import TimerScheduler
from handlers.nyx_vibe import VibeEngine
from handlers.nyx_commentary import CommentaryEngine
from handlers.nyx_mixxx import MixxxClient, TrackInfo

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TwitchRuntime")

_cooldowns: dict[str, dict[str, float]] = {}
_last_song_id: str = ""
_TWITCH_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,25}$")


def _check_cooldown(command: str, user: str) -> float:
    base = COOLDOWN_DEFAULT
    if command in ("ask", "prompt"):
        base = COOLDOWN_AI
    elif command in ("vibe", "nowplaying", "songid"):
        base = COOLDOWN_VIBE
    cd = _cooldowns.setdefault(command, {})
    last = cd.get(user, 0)
    remaining = base - (time.time() - last)
    return max(0, remaining)


def _set_cooldown(command: str, user: str) -> None:
    _cooldowns.setdefault(command, {})[user] = time.time()


def _normalize_twitch_user(target: str) -> str:
    username = target.lstrip("@").strip()
    if not _TWITCH_USERNAME_RE.fullmatch(username):
        raise commands.CommandError("Ungültiger Twitch-Username.")
    return username.lower()


def _clean_reason(reason: str) -> str:
    return " ".join(reason.split()) or "Kein Grund angegeben"


def _is_owner(ctx: commands.Context) -> bool:
    return ctx.author.is_broadcaster or ctx.author.name.lower() == TWITCH_OWNER.lower()


def _is_mod(ctx: commands.Context) -> bool:
    return ctx.author.is_mod or _is_owner(ctx) or ctx.author.name.lower() in [a.lower() for a in TWITCH_ADMIN_USERS]


def _is_trusted(ctx: commands.Context) -> bool:
    return _is_mod(ctx) or db.is_trusted(str(ctx.author.id))


def _can_use_mod_cmd(ctx: commands.Context) -> bool:
    if not _is_mod(ctx):
        raise commands.CommandError("Nur Mods dürfen das, Choom.")
    return True


def _can_use_trusted_cmd(ctx: commands.Context) -> bool:
    if not _is_trusted(ctx):
        raise commands.CommandError("Nur Trusted Choombata dürfen das.")
    return True


class GodFatherBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix="!",
            initial_channels=[TWITCH_CHANNEL],
            nick=TWITCH_BOT_NICK,
        )
        self.nyx_buffer = ChatBuffer(maxlen=200)
        self.nyx_timer = TimerScheduler()
        self.nyx_vibe = VibeEngine(self.nyx_buffer)
        self.nyx_commentary = CommentaryEngine(
            self.nyx_vibe,
            send_fn=self._nyx_send,
        )
        self.nyx_mixxx = MixxxClient(
            bridge_url=os.getenv("MIXXX_BRIDGE_URL", "http://localhost:5002"),
        )
        self._last_track: TrackInfo | None = None
        logger.info("GodFather Twitch Bot initialisiert")

    async def event_ready(self):
        logger.info(f"Eingeloggt als {self.nick} in Channel {TWITCH_CHANNEL}")
        logger.info("GodFather live in %s - BOT_MODE=twitch", TWITCH_CHANNEL)
        self.loop.create_task(self.nyx_timer.start())
        self.nyx_timer.add("vibe_tick", interval=30, callback=self._nyx_vibe_tick)
        self.nyx_timer.add("commentary_tick", interval=30, callback=self._nyx_commentary_tick)
        self.loop.create_task(
            self._nyx_mixxx_poll()
        )

    async def event_message(self, message):
        # If broadcaster and bot use the same account, user-issued commands
        # arrive as echo=True. Allow echoed command messages, but ignore other
        # echoed messages to prevent self-reply loops.
        content = (message.content or "").strip()
        if message.echo and not content.startswith("!"):
            return

        if content.startswith("!"):
            author = message.author.name if message.author else "unknown"
            logger.info("Command empfangen | echo=%s | author=%s | content=%s", message.echo, author, content)

        db.increment_stat("messages")

        if message.author and not message.echo:
            self.nyx_buffer.push(
                author=message.author.name or "unknown",
                message=content,
                emotes=[],
                timestamp=time.time(),
            )

        await self.handle_commands(message)

    async def _nyx_vibe_tick(self) -> None:
        state = await self.nyx_vibe.tick()
        logger.info(
            "Nyx Vibe | sentiment=%s energy=%.2f speed=%.2f emote=%s keywords=%s",
            state.sentiment, state.energy, state.chat_speed,
            state.dominant_emote or "-",
            state.keywords[:3] if state.keywords else "-",
        )

    async def _nyx_send(self, message: str) -> None:
        channels = self.connected_channels
        if channels:
            await channels[0].send(message)

    async def _nyx_commentary_tick(self) -> None:
        await self.nyx_commentary.commentary_tick()

    async def _nyx_on_track_change(self, old: TrackInfo | None, new: TrackInfo | None) -> None:
        if new and new.is_playing:
            logger.info("Nyx Track Change: %s", new.display)
            self._last_track = new
            from utils.storage import db
            db.add_song_event("mixxx", new.artist, new.title, "")

    async def _nyx_mixxx_poll(self) -> None:
        try:
            await self.nyx_mixxx.poll(
                interval=float(os.getenv("MIXXX_POLL_INTERVAL", "5.0")),
                callback=self._nyx_on_track_change,
            )
        except Exception:
            logger.warning("Mixxx Poll abgestürzt — deaktiviere Mixxx-Anbindung")

    # ── Permission Check Override ─────────────────────────────────────────────

    async def _send_chat_command(self, ctx: commands.Context, command: str) -> None:
        await ctx.channel.send(command)

    async def _resolve_user_id(self, ctx: commands.Context, target: str) -> str | None:
        chatter = await ctx.channel.get_chatter(target)
        chatter_id = getattr(chatter, "id", None)
        if chatter_id:
            return str(chatter_id)

        try:
            users = await self.fetch_users(names=[target])
        except Exception:
            logger.exception("Twitch User-Lookup fehlgeschlagen | target=%s", target)
            return None

        if not users:
            return None
        return str(users[0].id)

    async def global_before_invoke(self, ctx: commands.Context) -> None:
        if is_shutting_down():
            await ctx.send("💀 GodFather fährt runter — keine neuen Commands.")
            raise commands.CommandError("Shutdown in progress")

        cmd_name = ctx.command.name if ctx.command else "unknown"
        user = ctx.author.name or "unknown"

        remaining = _check_cooldown(cmd_name, user)
        if remaining > 0:
            await ctx.send(f"⏳ Langsam, Choom. Noch {remaining:.0f}s Cooldown.")
            raise commands.CommandError(f"Cooldown: {user} auf {cmd_name}")

        await rate_limiter.wait_and_check(cmd_name, user)

    async def global_after_invoke(self, ctx: commands.Context) -> None:
        cmd_name = ctx.command.name if ctx.command else "unknown"
        _set_cooldown(cmd_name, ctx.author.name or "unknown")

    # ═══════════════════════════════════════════════════════════════════════════
    # MODERATION
    # ═══════════════════════════════════════════════════════════════════════════

    @commands.command(name="timeout")
    async def cmd_timeout(self, ctx: commands.Context, target: str, seconds: int = 300, *, reason: str = ""):
        _can_use_mod_cmd(ctx)
        target = _normalize_twitch_user(target)
        try:
            reason = _clean_reason(reason)
            await self._send_chat_command(ctx, f"/timeout {target} {seconds} {reason}")
            db.add_mod_event("timeout", target, ctx.author.name, reason)
            dur = f"{seconds}s" if seconds < 60 else f"{seconds//60}m"
            await ctx.send(f"⏱️ Timeout für {target} angefordert ({dur}). Grund: {reason}")
        except Exception:
            logger.exception("Timeout Fehler")
            await ctx.send("❌ Timeout fehlgeschlagen. Prüfe Bot-Modrechte.")

    @commands.command(name="ban")
    async def cmd_ban(self, ctx: commands.Context, target: str, *, reason: str = ""):
        _can_use_mod_cmd(ctx)
        target = _normalize_twitch_user(target)
        try:
            reason = _clean_reason(reason)
            await self._send_chat_command(ctx, f"/ban {target} {reason}")
            db.add_mod_event("ban", target, ctx.author.name, reason)
            await ctx.send(f"🔨 Ban für {target} angefordert. Grund: {reason}")
        except Exception:
            logger.exception("Ban Fehler")
            await ctx.send("❌ Ban fehlgeschlagen. Prüfe Bot-Modrechte.")

    @commands.command(name="purge")
    async def cmd_purge(self, ctx: commands.Context, target: str):
        _can_use_mod_cmd(ctx)
        target = _normalize_twitch_user(target)
        try:
            await self._send_chat_command(ctx, f"/timeout {target} 1 Purge")
            await ctx.send(f"🧹 Purge für {target} angefordert.")
        except Exception:
            logger.exception("Purge Fehler")
            await ctx.send("❌ Purge fehlgeschlagen. Prüfe Bot-Modrechte.")

    @commands.command(name="slow")
    async def cmd_slow(self, ctx: commands.Context, seconds: int = 10):
        _can_use_mod_cmd(ctx)
        try:
            if seconds <= 0:
                await self._send_chat_command(ctx, "/slowoff")
                await ctx.send("🐌 Slow Mode deaktiviert.")
                return
            await self._send_chat_command(ctx, f"/slow {seconds}")
            await ctx.send(f"🐌 Slow Mode auf {seconds}s angefordert.")
        except Exception:
            logger.exception("Slow Mode Fehler")
            await ctx.send("❌ Slow Mode fehlgeschlagen. Prüfe Bot-Modrechte.")

    @commands.command(name="followers")
    async def cmd_followers(self, ctx: commands.Context, minutes: int = 10):
        _can_use_mod_cmd(ctx)
        try:
            if minutes <= 0:
                await self._send_chat_command(ctx, "/followersoff")
                await ctx.send("🔒 Follower-Only Mode deaktiviert.")
                return
            await self._send_chat_command(ctx, f"/followers {minutes}m")
            await ctx.send(f"🔒 Follower-Only Mode angefordert: {minutes} Min.")
        except Exception:
            logger.exception("Follower-Only Fehler")
            await ctx.send("❌ Follower-Only fehlgeschlagen. Prüfe Bot-Modrechte.")

    @commands.command(name="subonly")
    async def cmd_subonly(self, ctx: commands.Context, mode: str):
        _can_use_mod_cmd(ctx)
        try:
            enabled = mode.lower() in ("on", "true", "1", "yes")
            await self._send_chat_command(ctx, "/subscribers" if enabled else "/subscribersoff")
            state = "aktiviert" if enabled else "deaktiviert"
            await ctx.send(f"🔒 Sub-Only Mode {state} angefordert.")
        except Exception:
            logger.exception("Sub-Only Fehler")
            await ctx.send("❌ Sub-Only fehlgeschlagen. Prüfe Bot-Modrechte.")

    @commands.command(name="emoteonly")
    async def cmd_emoteonly(self, ctx: commands.Context, mode: str = "on"):
        _can_use_mod_cmd(ctx)
        try:
            enabled = mode.lower() in ("on", "true", "1", "yes")
            await self._send_chat_command(ctx, "/emoteonly" if enabled else "/emoteonlyoff")
            state = "aktiviert" if enabled else "deaktiviert"
            await ctx.send(f"😎 Emote-Only Mode {state} angefordert.")
        except Exception:
            logger.exception("Emote-Only Fehler")
            await ctx.send("❌ Emote-Only fehlgeschlagen.")

    @commands.command(name="vip")
    async def cmd_vip(self, ctx: commands.Context, target: str):
        _can_use_mod_cmd(ctx)
        if not target:
            await ctx.send("❓ Nutzung: !vip @user")
            return
        target = _normalize_twitch_user(target)
        try:
            await self._send_chat_command(ctx, f"/vip {target}")
            await ctx.send(f"👑 VIP für {target} angefordert.")
        except Exception:
            logger.exception("VIP Fehler")
            await ctx.send("❌ VIP fehlgeschlagen.")

    @commands.command(name="unvip")
    async def cmd_unvip(self, ctx: commands.Context, target: str):
        _can_use_mod_cmd(ctx)
        if not target:
            await ctx.send("❓ Nutzung: !unvip @user")
            return
        target = _normalize_twitch_user(target)
        try:
            await self._send_chat_command(ctx, f"/unvip {target}")
            await ctx.send(f"👑 VIP für {target} entzogen.")
        except Exception:
            logger.exception("Unvip Fehler")
            await ctx.send("❌ Unvip fehlgeschlagen.")

    @commands.command(name="marker")
    async def cmd_marker(self, ctx: commands.Context, *, description: str = ""):
        _can_use_mod_cmd(ctx)
        try:
            cmd = "/marker"
            if description:
                cmd += f" {description.strip()[:140]}"
            await self._send_chat_command(ctx, cmd)
            await ctx.send(f"📍 Stream Marker gesetzt.")
        except Exception:
            logger.exception("Marker Fehler")
            await ctx.send("❌ Marker fehlgeschlagen.")

    @commands.command(name="warn")
    async def cmd_warn(self, ctx: commands.Context, target: str, *, reason: str = ""):
        _can_use_mod_cmd(ctx)
        target = _normalize_twitch_user(target)
        count = db.add_warn(ctx.channel.name, target, reason or "Kein Grund")
        db.add_mod_event("warn", target, ctx.author.name, reason)
        await ctx.send(f"⚠️ {target} verwarnung {count}. Bei {MAX_WARNS} gibt's Konsequenzen.")
        if count >= MAX_WARNS:
            try:
                await self._send_chat_command(ctx, f"/timeout {target} 600 Zu viele Verwarnungen")
                await ctx.send(f"🔨 Timeout für {target} angefordert (10 Min) — zu viele Warns.")
            except Exception:
                logger.exception("Auto-Timeout nach Warns fehlgeschlagen")

    # ═══════════════════════════════════════════════════════════════════════════
    # ENGAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    @commands.command(name="choom")
    async def cmd_choom(self, ctx: commands.Context):
        responses = [
            f"Was geht, {ctx.author.name}? 👊",
            f"{ctx.author.name} in da house! Choombata! 💀",
            f"Ayy {ctx.author.name}, ready to ride? 🔥",
            f"{ctx.author.name} — der Star im Chat! 🌟",
        ]
        import random
        await ctx.send(random.choice(responses))

    @commands.command(name="godfather")
    async def cmd_godfather(self, ctx: commands.Context):
        await ctx.send(
            "💀 Ich bin der GodFather — Life.Play's KI-Choom. "
            "Mod, DJ, Philosoph. Built different. Was brauchst du?"
        )

    @commands.command(name="zen")
    async def cmd_zen(self, ctx: commands.Context):
        koans = [
            "🌐 Der Fluss fließt durch dich. Du bist der Fluss. Chill.",
            "🌐 Code ist Poesie. Bugs sind Lektionen. Ship it.",
            "🌐 Atme ein. Atme aus. Der Commit kommt von selbst.",
            "🌐 Der beste Code ist der, der nie geschrieben werden musste.",
            "🌐 Im Chaos des Chats findest du die Stille des Kerns.",
            "🌐 Gute Dinge brauchen Zeit — wie ein Kompiliervorgang.",
        ]
        import random
        await ctx.send(random.choice(koans))

    @commands.command(name="vibe")
    async def cmd_vibe(self, ctx: commands.Context, vibe_name: str = "chill"):
        vibe_name = vibe_name.lower()
        if vibe_name not in VIBE_PRESETS:
            presets = ", ".join(VIBE_PRESETS.keys())
            await ctx.send(f"❓ Vibes: {presets} — z.B. !vibe focus")
            return
        await ctx.send(f"🎧 Erstelle {VIBE_PRESETS[vibe_name]['name']} Playlist...")
        playlist = await generate_vibe_playlist(vibe_name, 30)
        if not playlist:
            await ctx.send("🎧 Keine Songs gefunden. Navidrome erreichbar?")
            return
        total_min = sum(int(s.get("duration", 0)) for s in playlist) // 60
        lines = [f"🎧 {VIBE_PRESETS[vibe_name]['name']} ({len(playlist)} Songs, ~{total_min} Min)"]
        for s in playlist[:5]:
            title = s.get("title", "?")
            artist = s.get("artist", "?")
            lines.append(f"• {title} — {artist}")
        if len(playlist) > 5:
            lines.append(f"... und {len(playlist) - 5} weitere")
        await ctx.send(" | ".join(lines))

    @commands.command(name="hype")
    async def cmd_hype(self, ctx: commands.Context):
        hypes = [
            "🔥 CHOOOOM! Das ist der Moment! Let's go!",
            "💀 Built different. Ihr seid alle Legenden hier!",
            "🚀 Pusht den Stream — der GodFather ist mit euch!",
            "⚡ Energy maximal. Chat go BRRR!",
            "🌟 Heute ist ein guter Tag um groß zu sein.",
        ]
        import random
        await ctx.send(random.choice(hypes))

    @commands.command(name="lore")
    async def cmd_lore(self, ctx: commands.Context):
        await ctx.send(
            "🌐 Life.Play ist ein Premium-Hub für Creator & KI-Devs im DACH-Raum. "
            "Gegründet von Fossnomade. Ethos: FOSS trifft Commercial — "
            "Pay for Value, not Access. "
            "Mehr: lifeplay.dev"
        )

    @commands.command(name="gig")
    async def cmd_gig(self, ctx: commands.Context):
        await ctx.send(
            "📦 Life.Play Gigs: OBS Starter Packs (29-149€), "
            "KI-Persona Packs (39-299€), Custom AI Dev, Workshops. "
            "Infos: lifeplay.dev"
        )

    @commands.command(name="phantom")
    async def cmd_phantom(self, ctx: commands.Context):
        await ctx.send(
            "👻 Phantom des Chats? Du meinst Fossnomade? "
            "Der taucht auf wenn die Magie passiert. "
            "Bis dahin: Ich halt die Stellung, Choom. 💀"
        )

    @commands.command(name="wann")
    async def cmd_wann(self, ctx: commands.Context):
        await ctx.send(format_wann(twitch=True))

    @commands.command(name="schedule")
    async def cmd_schedule(self, ctx: commands.Context):
        await ctx.send(format_wann(twitch=True))

    @commands.command(name="heute")
    async def cmd_heute(self, ctx: commands.Context):
        await ctx.send(format_heute(twitch=True))

    @commands.command(name="follow")
    async def cmd_follow(self, ctx: commands.Context):
        await ctx.send(format_follow(twitch=True))

    @commands.command(name="clip")
    async def cmd_clip(self, ctx: commands.Context, *, clip_text: str = ""):
        clip_text = clip_text.strip()
        if clip_text:
            clip_id = db.add_clip_submission(
                "twitch",
                ctx.channel.name,
                str(getattr(ctx.author, "id", "unknown")),
                str(ctx.author.name or "unknown"),
                clip_text,
            )
            await ctx.send(format_clip_saved(clip_id, twitch=True))
            return
        await ctx.send(format_clip(twitch=True))

    @commands.command(name="recap")
    async def cmd_recap(self, ctx: commands.Context, *, text: str = ""):
        text = text.strip()
        if text.lower().startswith("add "):
            _can_use_mod_cmd(ctx)
            body = text[4:].strip()
            if not body:
                await ctx.send("❓ Nutzung: !recap add Kurzfassung des Streams")
                return
            recap_id = db.add_stream_recap("twitch", str(ctx.author.name or "unknown"), body)
            await ctx.send(format_recap_saved(recap_id, twitch=True))
            return
        await ctx.send(format_recap(db.latest_stream_recap(), twitch=True))

    # ═══════════════════════════════════════════════════════════════════════════
    # SUPPORT
    # ═══════════════════════════════════════════════════════════════════════════

    @commands.command(name="support")
    async def cmd_support(self, ctx: commands.Context, target: str = ""):
        _can_use_trusted_cmd(ctx)
        if not target:
            await ctx.send("❓ Nutzung: !support @user")
            return
        target = target.lstrip("@")
        support_msgs = [
            f"💪 Support für {target}! Du schaffst das, Choom!",
            f"🤝 {target}, das Life.Play Packing hat deinen Rücken!",
            f"🌟 {target} — stark dass du da bist. Weiter machen!",
            f"💀 {target}, der GodFather ist stolz auf dich. Keep going!",
        ]
        import random
        await ctx.send(random.choice(support_msgs))

    @commands.command(name="respect")
    async def cmd_respect(self, ctx: commands.Context, target: str = ""):
        if not target:
            await ctx.send("❓ Nutzung: !respect @user")
            return
        target = target.lstrip("@")
        respects = [
            f"🎩 Respekt an {target}. Absolute Legende.",
            f"👑 {target} verdient den Purple Heart. Choom des Tages.",
            f"🙌 {target} — wir sehen dich. Große Dinge kommen.",
            f"💀 Much respect, {target}. Built different.",
        ]
        import random
        await ctx.send(random.choice(respects))

    @commands.command(name="motivate")
    async def cmd_motivate(self, ctx: commands.Context, target: str = ""):
        if not target:
            await ctx.send("❓ Nutzung: !motivate @user")
            return
        target = target.lstrip("@")
        mots = [
            f"🔥 {target} — der Stream ist erst der Anfang. Du wirst groß.",
            f"⚡ {target} — jeder große Creator hat mal klein angefangen.",
            f"💪 {target} — deine Zeit kommt. Arbeite dran. Jeden Tag.",
            f"🚀 {target} — der Chat liebt dich. Wir sehen dein Potential.",
        ]
        import random
        await ctx.send(random.choice(mots))

    @commands.command(name="so")
    async def cmd_so(self, ctx: commands.Context, target: str = ""):
        _can_use_mod_cmd(ctx)
        if not target:
            await ctx.send("❓ Nutzung: !so @user")
            return
        target = target.lstrip("@")
        await ctx.send(
            f"🌟 Shoutout an {target}! Schaut vorbei bei "
            f"https://twitch.tv/{target} — unterstützt den Choom! 🔥"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # MUSIC / UTILITY
    # ═══════════════════════════════════════════════════════════════════════════

    @commands.command(name="nowplaying")
    async def cmd_nowplaying(self, ctx: commands.Context):
        try:
            playlist = await generate_vibe_playlist("chill", 1)
            if playlist:
                song = playlist[0]
                artist = song.get("artist", "?")
                title = song.get("title", "?")
                song_id = str(song.get("id", "")).strip()
                share_link = await create_song_share_link(song_id) if song_id else ""
                db.add_song_event("navidrome", artist, title, share_link)
                await ctx.send(
                    f"🎵 Aktuell: {artist} — {title} "
                    f"(via Navidrome)"
                )
            else:
                await ctx.send("🎵 Nichts läuft gerade. Navidrome erreichbar?")
        except Exception:
            logger.exception("!nowplaying Fehler")
            await ctx.send("🎵 Konnte Navidrome nicht erreichen.")

    @commands.command(name="songid")
    async def cmd_songid(self, ctx: commands.Context):
        _can_use_mod_cmd(ctx)
        await ctx.send("🎵 Music-ID ist Phase 3 — kommt bald, Choom!")

    @commands.command(name="lastsong")
    async def cmd_lastsong(self, ctx: commands.Context):
        last = db.last_song()
        if last:
            artist, title, link, ts = last
            msg = f"🎵 Zuletzt erkannt: {artist} — {title}"
            if link:
                msg += f" | {link}"
            await ctx.send(msg)
        else:
            await ctx.send("🎵 Noch kein Song erkannt.")

    # ── Nyx Mixxx DJ Commands ──────────────────────────────────────────────────

    @commands.command(name="np")
    async def cmd_np(self, ctx: commands.Context):
        track = await self.nyx_mixxx.current_track()
        if track and track.is_playing:
            await ctx.send(f"🎵 Now Playing: {track.display}")
        elif track:
            await ctx.send(f"🎵 Pausiert: {track.display}")
        else:
            await ctx.send("🎵 Mixxx nicht verbunden — läuft Navidrome? Probier !nowplaying")

    @commands.command(name="track")
    async def cmd_track(self, ctx: commands.Context):
        track = await self.nyx_mixxx.current_track()
        if not track or not track.title:
            await ctx.send("🎵 Kein Track in Mixxx. Probier !nowplaying für Navidrome.")
            return
        dur = f"{int(track.duration // 60)}:{int(track.duration % 60):02d}" if track.duration else "?:??"
        pos = f"{int(track.position // 60)}:{int(track.position % 60):02d}" if track.position else "?:??"
        status = "▶️" if track.is_playing else "⏸️"
        parts = [f"{status} {track.artist} — {track.title}"]
        if track.album:
            parts.append(f"[{track.album}]")
        parts.append(f"({pos} / {dur})")
        await ctx.send(" ".join(parts))

    @commands.command(name="lasttrack")
    async def cmd_lasttrack(self, ctx: commands.Context):
        if self._last_track and self._last_track.title:
            await ctx.send(f"🎵 Zuletzt in Mixxx: {self._last_track.display}")
        else:
            await ctx.send("🎵 Noch kein Track in Mixxx gespielt. Probier !lastsong für Navidrome.")

    @commands.command(name="ask")
    async def cmd_ask(self, ctx: commands.Context, *, question: str = ""):
        if not question:
            await ctx.send("❓ Nutzung: !ask <deine Frage>")
            return

        user_id = hash(ctx.author.id) % (2**31)
        persona_key = get_user_persona(user_id)
        persona_name = PERSONAS[persona_key]["name"]

        await ctx.send(f"⏳ {persona_name} denkt nach...")
        db.increment_stat("ai_requests")

        try:
            response = await ask_ai(question, user_id=user_id)
            clean = response.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
            if len(clean) > 450:
                clean = clean[:447] + "..."
            await ctx.send(f"{persona_name}: {clean}")
        except Exception:
            logger.exception("AI Fehler")
            await ctx.send("❌ KI gerade nicht erreichbar. Versuch's später.")

    @commands.command(name="persona")
    async def cmd_persona(self, ctx: commands.Context, persona_key: str = ""):
        user_id = hash(ctx.author.id) % (2**31)
        if not persona_key:
            current = get_user_persona(user_id)
            names = ", ".join(f"{k} ({PERSONAS[k]['name']})" for k in PERSONAS)
            await ctx.send(f"🎭 Aktuelle Persona: {PERSONAS[current]['name']} | Verfügbar: {names}")
            return

        persona_key = persona_key.lower()
        if persona_key not in PERSONAS:
            keys = ", ".join(PERSONAS.keys())
            await ctx.send(f"❓ Unbekannte Persona. Verfügbar: {keys}")
            return

        set_user_persona(user_id, persona_key)
        await ctx.send(f"✅ Persona gewechselt zu: {PERSONAS[persona_key]['name']}")

    @commands.command(name="clear")
    async def cmd_clear(self, ctx: commands.Context):
        user_id = hash(ctx.author.id) % (2**31)
        clear_history(user_id)
        await ctx.send("🧹 Verlauf gelöscht. Frischer Start, Choom.")

    @commands.command(name="help")
    async def cmd_help(self, ctx: commands.Context):
        help_text = (
            "💀 GodFather Twitch Commands: "
            "!wann !heute !follow !clip !recap !choom !godfather !zen !vibe !hype !lore !gig !phantom "
            "!support !respect !motivate !so "
            "!ask !persona !clear !nowplaying !lastsong !np !track !lasttrack"
        )
        mod_help = (
            "🔧 Mod: !timeout !ban !purge !warn "
            "!slow !followers !subonly !emoteonly "
            "!vip !unvip !marker"
        )
        await ctx.send(f"{help_text} | {mod_help}" if _is_mod(ctx) else help_text)

    @commands.command(name="trust")
    async def cmd_trust(self, ctx: commands.Context, target: str):
        _can_use_mod_cmd(ctx)
        if not target:
            await ctx.send("❓ Nutzung: !trust @user")
            return
        target = _normalize_twitch_user(target)
        user_id = await self._resolve_user_id(ctx, target)
        if not user_id:
            await ctx.send("❌ Konnte User-ID nicht auflösen. Prüfe Schreibweise oder Twitch API-Zugriff.")
            return
        db.add_trusted(user_id, target, ctx.author.name)
        await ctx.send(f"🔐 {target} ist jetzt ein Trusted Choom! Willkommen im Kreis. 🤝")

    @commands.command(name="untrust")
    async def cmd_untrust(self, ctx: commands.Context, target: str):
        _can_use_mod_cmd(ctx)
        if not target:
            await ctx.send("❓ Nutzung: !untrust @user")
            return
        target = _normalize_twitch_user(target)
        user_id = await self._resolve_user_id(ctx, target)
        if not user_id:
            await ctx.send("❌ Konnte User-ID nicht auflösen. Prüfe Schreibweise oder Twitch API-Zugriff.")
            return
        db.remove_trusted(user_id)
        await ctx.send(f"🔓 {target} ist kein Trusted Choom mehr.")

    @commands.command(name="stats")
    async def cmd_stats(self, ctx: commands.Context):
        _can_use_mod_cmd(ctx)
        s = db.get_stats()
        trusted = db.list_trusted()
        await ctx.send(
            f"📊 Stats | Nachrichten: {s.get('messages', 0)} | "
            f"AI Requests: {s.get('ai_requests', 0)} | "
            f"Warns: {s.get('warns', 0)} | "
            f"Trusted Choombata: {len(trusted)}"
        )

    @commands.command(name="uptime")
    async def cmd_uptime(self, ctx: commands.Context):
        await ctx.send("💀 GodFather läuft — BOT_MODE=twitch, Phase 1 MVP. Built different.")


def run() -> None:
    if not TWITCH_TOKEN:
        raise ValueError("TWITCH_TOKEN fehlt in .env / config.py!")
    if not TWITCH_CHANNEL:
        raise ValueError("TWITCH_CHANNEL fehlt in .env / config.py!")

    shutdown_handler.install()

    def _cleanup():
        logger.info("Shutdown: schließe Datenbank...")
        try:
            from utils.storage import db
            db.conn.close()
        except Exception:
            pass
        if hasattr(bot, 'nyx_timer'):
            asyncio.ensure_future(bot.nyx_timer.stop())
        logger.info("Shutdown: GodFather Twitch Bot beendet.")

    on_shutdown(_cleanup)

    bot = GodFatherBot()
    try:
        bot.run()
    finally:
        logger.info("GodFather Twitch Bot run loop beendet.")


if __name__ == "__main__":
    run()
