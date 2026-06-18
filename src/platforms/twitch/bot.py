import os
import time
import logging
import asyncio
import ssl
from typing import Optional
from pathlib import Path

from src.core.persona_engine import PersonaFlowEngine, PersonaName
from src.ai.ollama_client import OllamaClient
from src.storage.database import Database
from src.platforms.twitch.helix import TwitchHelixClient, TwitchHelixError

logger = logging.getLogger(__name__)

IRC_PING_INTERVAL = 240
RECONNECT_DELAY = 5
MAX_RECONNECT_ATTEMPTS = 10


class TwitchBot:
    def __init__(self, persona_engine: PersonaFlowEngine,
                 ollama: OllamaClient, db: Database, config_dir: Path):
        self.engine = persona_engine
        self.ollama = ollama
        self.db = db
        self.config_dir = config_dir

        self.nick = os.getenv("TWITCH_BOT_NICK", "")
        self.token = os.getenv("TWITCH_BOT_TOKEN") or os.getenv("TWITCH_TOKEN", "")
        self.channel = os.getenv("TWITCH_CHANNEL", "")
        self.owner = os.getenv("TWITCH_OWNER", "")
        self.auto_reply = os.getenv("TWITCH_AUTO_REPLY", "false").lower() == "true"
        raw_admins = os.getenv("TWITCH_ADMIN_USERS", "")
        self.admin_users = [u.strip().lower() for u in raw_admins.split(",") if u.strip()]

        self.bot_start = time.time()
        self.running = False
        self.locked_persona: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._reconnect_attempts = 0
        self._outbound: Optional[asyncio.Queue[str]] = None
        self.helix = TwitchHelixClient()

    def _get_persona(self, user: str, channel: str) -> str:
        state = self.engine.get_state("twitch", channel, user)
        return state.current.value

    def _build_system_prompt(self, persona_name: str) -> str:
        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        return (
            f"You are {pdata.display_name} {pdata.emoji}\n"
            f"Style: {pdata.style}\n\n"
            f"You are a Twitch chat bot for {self.channel}. "
            f"Keep responses very short (1-3 sentences). "
            f"Use chat-friendly tone. "
            f"No markdown formatting. "
            f"Stay in character as {pdata.display_name}."
        )

    def _is_mod(self, user: str, raw_tags: str = "") -> bool:
        user_lower = user.lower()
        if user_lower == self.owner.lower():
            return True
        if user_lower in self.admin_users:
            return True
        if "mod=1" in raw_tags or "badges=moderator" in raw_tags or "badges=staff" in raw_tags:
            return True
        return False

    def _parse_message(self, raw: str) -> tuple:
        parts = raw.split(" ", 1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        return cmd, args

    def _format_irc_message(self, message: str) -> str:
        return f"PRIVMSG #{self.channel} :{message[:500]}"

    async def handle_chat_message(self, user: str, message: str, is_mod: bool = False):
        channel = self.channel
        uid = f"{channel}:{user}"

        if user.casefold() == self.nick.casefold():
            return

        ok, _ = self.db.check_rate_limit(uid, "twitch:chat", cooldown_seconds=1)
        if not ok:
            return

        self.db.upsert_user(uid, "twitch", user)

        cmd, args = self._parse_message(message)

        if cmd.startswith("!"):
            handler_name = f"cmd_{cmd[1:]}"
            handler = getattr(self, handler_name, None)
            if handler:
                await handler(user, args or "", channel, is_mod)
            return

        lowered = message.casefold()
        directed = (
            f"@{self.nick.casefold()}" in lowered
            or lowered.startswith(self.nick.casefold())
            or lowered.startswith("godfather")
        )
        if not self.auto_reply and not directed:
            return

        persona_name = self._get_persona(user, channel)
        next_persona, did_transition = self.engine.select_next(
            "twitch", channel, uid, message,
            stream_segment=self._detect_stream_segment(message)
        )

        if did_transition and next_persona.value != persona_name:
            pdata = self.engine.get_persona_info(next_persona)
            transition_msg = pdata.transition_to[:400]
            self._send(f"{transition_msg}")
            persona_name = next_persona.value

        system_prompt = self._build_system_prompt(persona_name)
        response = await self.ollama.chat(
            user_id=uid,
            user_message=message,
            system_prompt=system_prompt,
        )

        self.db.save_conversation(
            uid, "twitch", channel, "user", message, persona_name,
            response.model, response.tokens,
        )

        if response.success and response.content.strip():
            self._send(f"@{user} {response.content[:450]}")

        self.db.save_conversation(
            uid, "twitch", channel, "assistant", response.content,
            persona_name, response.model, response.tokens,
        )

    def _detect_stream_segment(self, message: str) -> Optional[str]:
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["hello", "hey", "hi", "welcome", "started"]):
            return "warmup"
        if any(w in msg_lower for w in ["code", "coding", "dev", "build", "feature"]):
            return "coding"
        if any(w in msg_lower for w in ["game", "play", "gg", "pog", "ez", "clutch"]):
            return "gaming"
        if any(w in msg_lower for w in ["bye", "thanks", "later", "next time"]):
            return "outro"
        return None

    def _send(self, message: str):
        if self.running and self._outbound is not None:
            self._outbound.put_nowait(self._format_irc_message(message))

    async def _write_line(self, writer: asyncio.StreamWriter, line: str) -> None:
        writer.write((line + "\r\n").encode("utf-8"))
        await writer.drain()

    async def _sender_loop(self, writer: asyncio.StreamWriter) -> None:
        assert self._outbound is not None
        while self.running:
            line = await self._outbound.get()
            await self._write_line(writer, line)

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        preflight = await self.helix.validate()
        require_mod = os.getenv("TWITCH_REQUIRE_MOD_SCOPES", "true").lower() == "true"
        if not preflight.chat_ready:
            missing = ", ".join(sorted(preflight.missing_chat_scopes))
            raise TwitchHelixError(f"Missing Twitch chat scopes: {missing}")
        if require_mod and not preflight.mod_ready:
            missing = ", ".join(sorted(preflight.missing_mod_scopes))
            raise TwitchHelixError(f"Missing Twitch moderator scopes: {missing}")
        self.token = self.helix.token
        context = ssl.create_default_context()
        reader, writer = await asyncio.open_connection(
            "irc.chat.twitch.tv", 6697, ssl=context,
        )
        token = self.token if self.token.startswith("oauth:") else f"oauth:{self.token}"
        await self._write_line(writer, f"PASS {token}")
        await self._write_line(writer, f"NICK {self.nick}")
        await self._write_line(writer, "CAP REQ :twitch.tv/tags twitch.tv/commands")
        await self._write_line(writer, f"JOIN #{self.channel}")
        logger.info("Twitch IRC connected: %s -> #%s", self.nick, self.channel)
        return reader, writer

    async def _process_line(self, line: str):
        line = line.strip()
        if not line:
            return

        if line.startswith("PING"):
            if self._outbound is not None:
                self._outbound.put_nowait("PONG :tmi.twitch.tv")
            return

        tags = ""
        rest = line
        if rest.startswith("@"):
            tags, rest = rest.split(" ", 1)
        prefix = ""
        if rest.startswith(":"):
            prefix, rest = rest[1:].split(" ", 1)
        if " :" in rest:
            head, message = rest.split(" :", 1)
        else:
            head, message = rest, ""
        parts = head.split()
        if not parts:
            return

        command = parts[0]

        if command != "PRIVMSG":
            return

        user = prefix.split("!")[0] if "!" in prefix else prefix
        is_mod = self._is_mod(user, tags)
        await self.handle_chat_message(user, message, is_mod)

    async def _read_loop(self):
        self._reconnect_attempts = 0
        while self.running and self._reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
            writer: Optional[asyncio.StreamWriter] = None
            sender: Optional[asyncio.Task] = None
            try:
                reader, writer = await self._connect()
                sender = asyncio.create_task(self._sender_loop(writer))
                while self.running:
                    raw = await reader.readline()
                    if not raw:
                        raise ConnectionError("Twitch IRC closed the connection")
                    await self._process_line(raw.decode("utf-8", errors="replace"))
                    self._reconnect_attempts = 0
            except (ConnectionError, EOFError, BrokenPipeError, OSError,
                    asyncio.TimeoutError, TwitchHelixError) as e:
                self._reconnect_attempts += 1
                logger.warning(
                    "Twitch IRC disconnected (attempt %d/%d): %s",
                    self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS, e,
                )
                if self._reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                    await asyncio.sleep(RECONNECT_DELAY * self._reconnect_attempts)
                else:
                    logger.error("Max reconnect attempts reached. Giving up.")
            finally:
                if sender is not None:
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
                if writer is not None:
                    writer.close()
                    await writer.wait_closed()

    async def cmd_persona(self, user: str, args: str, channel: str, is_mod: bool):
        uid = f"{channel}:{user}"
        if args:
            try:
                target = PersonaName(args.strip().lower())
                msg, switched = self.engine.force_persona("twitch", channel, uid, target)
                self._send(f"@{user} {msg}")
            except ValueError:
                names = ", ".join(p.value for p in PersonaName)
                self._send(f"@{user} Available: {names}")
        else:
            state = self.engine.get_state("twitch", channel, uid)
            pdata = self.engine.get_persona_info(state.current)
            self._send(f"@{user} Current: {pdata.emoji} {pdata.display_name} | Style: {pdata.style}")

    async def cmd_help(self, user: str, args: str, channel: str, is_mod: bool):
        commands = "!help !status !uptime !persona !vibe !wann !heute !follow !clip"
        if is_mod:
            commands += " | MOD: !modcheck !timeout !ban !unban !slow"
        self._send(f"@{user} {commands}")

    async def cmd_schedule(self, user: str, args: str, channel: str, is_mod: bool):
        schedule = os.getenv("STREAM_SCHEDULE", "Noch kein Streamplan gesetzt.")
        self._send(f"@{user} {schedule[:430]}")

    async def cmd_wann(self, user: str, args: str, channel: str, is_mod: bool):
        await self.cmd_schedule(user, args, channel, is_mod)

    async def cmd_heute(self, user: str, args: str, channel: str, is_mod: bool):
        message = os.getenv(
            "STREAM_TODAY_FALLBACK",
            "Heute ist kein fixer Stream eingetragen. Follow fuer den Ping.",
        )
        self._send(f"@{user} {message[:430]}")

    async def cmd_follow(self, user: str, args: str, channel: str, is_mod: bool):
        links = [
            os.getenv("TWITCH_CHANNEL_URL", f"https://twitch.tv/{self.channel}"),
            os.getenv("YOUTUBE_URL", ""),
        ]
        self._send(f"@{user} " + " | ".join(link for link in links if link)[:430])

    async def cmd_clip(self, user: str, args: str, channel: str, is_mod: bool):
        intake = os.getenv(
            "CLIP_INTAKE_URL",
            "Clip-Link bitte in die Live.Play Gruppe posten.",
        )
        self._send(f"@{user} Clip-Moment markiert. {intake[:380]}")

    async def cmd_flow(self, user: str, args: str, channel: str, is_mod: bool):
        uid = f"{channel}:{user}"
        state = self.engine.get_state("twitch", channel, uid)
        current = self.engine.get_persona_info(state.current)
        self._send(f"@{user} Flow: {current.emoji} {current.display_name} | {state.transition_count} transitions")

    async def cmd_vibe(self, user: str, args: str, channel: str, is_mod: bool):
        uid = f"{channel}:{user}"
        if not args:
            self._send(f"@{user} Usage: !vibe [hype/chill/deep/intense/focus]")
            return
        target, msg = self.engine.set_vibe("twitch", channel, uid, args.strip().lower())
        if target:
            pdata = self.engine.get_persona_info(target)
            self._send(f"@{user} Vibe set! {pdata.emoji} {pdata.display_name}")
        else:
            self._send(f"@{user} {msg}")

    async def cmd_status(self, user: str, args: str, channel: str, is_mod: bool):
        uptime = time.time() - self.bot_start
        days, rem = divmod(int(uptime), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        stats = self.db.get_global_stats()
        self._send(f"UP {days}d {hours}h {minutes}m | MSGS {stats['total_messages']} | USERS {stats['total_users']} | TOKENS {stats['total_tokens']:,}")

    async def cmd_uptime(self, user: str, args: str, channel: str, is_mod: bool):
        uptime = time.time() - self.bot_start
        days, rem = divmod(int(uptime), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        self._send(f"@{user} GodFather has been vibing for {days}d {hours}h {minutes}m {secs}s")

    async def cmd_persona_lock(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            self._send(f"@{user} Only mods can lock personas.")
            return
        uid = f"{channel}:{user}"
        if args:
            try:
                target = PersonaName(args.strip().lower())
                self.engine.force_persona("twitch", channel, uid, target, lock=True)
                self.locked_persona = target.value
                self._send(f"🔒 Persona locked to {target.value} by {user}")
            except ValueError:
                self._send(f"@{user} Unknown persona")

    async def cmd_timeout(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            self._send(f"@{user} Only mods can timeout.")
            return
        parts = args.split(maxsplit=2)
        if not parts:
            self._send(f"@{user} Usage: !timeout <user> [seconds] [reason]")
            return
        target = parts[0].lstrip("@")
        duration = 600
        reason = "Moderation by GodFather"
        if len(parts) >= 2 and parts[1].isdigit():
            duration = int(parts[1])
            if len(parts) == 3:
                reason = parts[2]
        elif len(parts) >= 2:
            reason = " ".join(parts[1:])
        try:
            await self.helix.ban(target, reason=reason, duration=duration)
            self._send(f"@{user} {target} timed out for {duration}s.")
        except TwitchHelixError as exc:
            logger.warning("Timeout failed: %s", exc)
            self._send(f"@{user} Timeout failed. Check bot mod role and OAuth scopes.")

    async def cmd_ban(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            self._send(f"@{user} Only mods can ban.")
            return
        parts = args.split(maxsplit=1)
        if not parts:
            self._send(f"@{user} Usage: !ban <user> [reason]")
            return
        target = parts[0].lstrip("@")
        reason = parts[1] if len(parts) == 2 else "Moderation by GodFather"
        try:
            await self.helix.ban(target, reason=reason)
            self._send(f"@{user} {target} banned.")
        except TwitchHelixError as exc:
            logger.warning("Ban failed: %s", exc)
            self._send(f"@{user} Ban failed. Check bot mod role and OAuth scopes.")

    async def cmd_unban(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            self._send(f"@{user} Only mods can unban.")
            return
        target = args.strip().lstrip("@")
        if not target:
            self._send(f"@{user} Usage: !unban <user>")
            return
        try:
            await self.helix.unban(target)
            self._send(f"@{user} {target} unbanned.")
        except TwitchHelixError as exc:
            logger.warning("Unban failed: %s", exc)
            self._send(f"@{user} Unban failed. Check bot mod role and OAuth scopes.")

    async def cmd_slow(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        try:
            seconds = int(args.strip() or "0")
            await self.helix.set_slow_mode(seconds)
            self._send(f"@{user} Slow mode {'off' if seconds <= 0 else f'{seconds}s'}.")
        except ValueError:
            self._send(f"@{user} Usage: !slow <0|3-120>")
        except TwitchHelixError as exc:
            logger.warning("Slow mode failed: %s", exc)
            self._send(f"@{user} Slow mode failed. Check bot mod role and OAuth scopes.")

    async def cmd_modcheck(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        try:
            status = await self.helix.validate()
            if status.chat_ready and status.mod_ready:
                self._send(f"@{user} GodFather Twitch mod preflight: READY.")
                return
            missing = sorted(status.missing_chat_scopes | status.missing_mod_scopes)
            self._send(f"@{user} Missing OAuth scopes: {', '.join(missing)}")
        except TwitchHelixError as exc:
            logger.warning("Twitch preflight failed: %s", exc)
            self._send(f"@{user} Twitch token validation failed.")

    async def cmd_followers(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        self._send(f".followers {args}")

    async def cmd_subonly(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        self._send(f".subonly")

    async def _run(self):
        logger.info("Twitch bot starting...")
        logger.info(f"Channel: #{self.channel}, Nick: {self.nick}")

        self.running = True
        self._loop = asyncio.get_running_loop()
        self._outbound = asyncio.Queue()

        try:
            await self._read_loop()
        finally:
            self.running = False

    def run(self):
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.info("Twitch bot stopped")
