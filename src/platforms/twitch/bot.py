import os
import time
import logging
from typing import Optional
from pathlib import Path

from src.core.persona_engine import PersonaFlowEngine, PersonaName
from src.ai.ollama_client import OllamaClient
from src.storage.database import Database

logger = logging.getLogger(__name__)


class TwitchBot:
    def __init__(self, persona_engine: PersonaFlowEngine,
                 ollama: OllamaClient, db: Database, config_dir: Path):
        self.engine = persona_engine
        self.ollama = ollama
        self.db = db
        self.config_dir = config_dir

        self.nick = os.getenv("TWITCH_BOT_NICK", "")
        self.token = os.getenv("TWITCH_BOT_TOKEN", "")
        self.channel = os.getenv("TWITCH_CHANNEL", "")
        self.owner = os.getenv("TWITCH_OWNER", "")
        self.admin_users = os.getenv("TWITCH_ADMIN_USERS", "").split(",") if os.getenv("TWITCH_ADMIN_USERS") else []

        self.bot_start = time.time()
        self.running = False
        self.locked_persona: Optional[str] = None

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

    def _is_mod(self, user: str) -> bool:
        return user.lower() == self.owner.lower() or user.lower() in [u.lower() for u in self.admin_users]

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
        self.db.upsert_user(uid, "twitch", user)

        cmd, args = self._parse_message(message)

        if cmd.startswith("!"):
            handler_name = f"cmd_{cmd[1:]}"
            handler = getattr(self, handler_name, None)
            if handler:
                await handler(user, args or "", channel, is_mod)
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
        self.db.save_conversation(
            uid, "twitch", channel, "assistant", response.content,
            persona_name, response.model, response.tokens,
        )

        if response.success and response.content.strip():
            self._send(f"@{user} {response.content[:450]}")

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
        print(self._format_irc_message(message), flush=True)

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
        self._send(f".timeout {args}")

    async def cmd_slow(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        self._send(f".slow {args}")

    async def cmd_followers(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        self._send(f".followers {args}")

    async def cmd_subonly(self, user: str, args: str, channel: str, is_mod: bool):
        if not is_mod:
            return
        self._send(f".subonly")

    def run(self):
        import sys
        logger.info("Twitch bot starting...")
        logger.info(f"Channel: #{self.channel}, Nick: {self.nick}")

        print(f"PASS oauth:{self.token}", flush=True)
        print(f"NICK {self.nick}", flush=True)
        print(f"JOIN #{self.channel}", flush=True)

        self.running = True
        message_buffer = []

        for line in sys.stdin:
            if not self.running:
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("PING"):
                print("PONG :tmi.twitch.tv", flush=True)
                continue

            parts = line.split(" ", 3)
            if len(parts) < 4:
                continue

            prefix = parts[0]
            command = parts[1]
            channel = parts[2]
            message = parts[3][1:] if parts[3].startswith(":") else parts[3]

            if command != "PRIVMSG":
                continue

            user = prefix.split("!")[0] if "!" in prefix else prefix
            is_mod = "mod=" in message or user.lower() == self.owner.lower()

            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.handle_chat_message(user, message, is_mod))
                loop.close()
            except Exception as e:
                logger.error("Error handling message: %s", e)
