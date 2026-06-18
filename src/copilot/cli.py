from __future__ import annotations
import os
import sys
import time
import json
import logging
import asyncio
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from src.ai.ollama_client import OllamaClient
from src.core.persona_engine import PersonaFlowEngine, PersonaName
from src.storage.database import Database

logger = logging.getLogger("copilot.cli")


CLI_STYLE = Style.from_dict({
    "prompt": "ansibrightmagenta bold",
    "persona-tag": "ansibrightyellow",
    "timestamp": "ansibrightblack",
    "error": "ansired bold",
})


class CLIBot:
    def __init__(self, engine: PersonaFlowEngine, ollama: OllamaClient,
                 db: Database, config_dir: Path):
        self.engine = engine
        self.ollama = ollama
        self.db = db
        self.config_dir = config_dir
        self.user_id = "cli_user"
        self.chat_id = "cli"
        self.current_persona = "godfather"
        self.history_file = str(Path.home() / ".godfather_history")

    def _print_response(self, persona: str, content: str, meta: str = ""):
        print(f"\n  [{persona.upper()}] {content}")
        if meta:
            print(f"  \033[90m{meta}\033[0m")
        print()

    def _get_prompt_text(self) -> str:
        return f"  [{self.current_persona.upper()}] \033[35m>>\033[0m "

    async def handle_message(self, text: str):
        text = text.strip()
        if not text:
            return

        if text.startswith("/"):
            await self._handle_command(text)
            return

        self.db.upsert_user(self.user_id, "cli", "cli_user")

        system_prompt = self._build_system_prompt(self.current_persona)

        try:
            response = await asyncio.wait_for(
                self.ollama.chat(
                    user_id=self.user_id,
                    user_message=text,
                    system_prompt=system_prompt,
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            print("\n  \033[91m⏳ Ollama timeout. Try again.\033[0m\n")
            return

        self.db.save_conversation(
            self.user_id, "cli", self.chat_id, "user", text,
            self.current_persona, response.model, response.tokens,
        )
        self.db.save_conversation(
            self.user_id, "cli", self.chat_id, "assistant", response.content,
            self.current_persona, response.model, response.tokens,
        )
        self.db.log_ollama_call(
            response.server, response.model,
            response.tokens, response.latency_ms, response.success,
        )

        meta = f"{response.model} | {response.server} | {response.latency_ms}ms | {response.tokens}tok"
        self._print_response(self.current_persona, response.content, meta)

    async def _handle_command(self, text: str):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        cmds = {
            "persona": self._cmd_persona,
            "help": self._cmd_help,
            "clear": self._cmd_clear,
            "status": self._cmd_status,
            "model": self._cmd_model,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
        }
        handler = cmds.get(cmd)
        if handler:
            await handler(arg)
        else:
            print(f"  \033[93mUnknown command: /{cmd}. Try /help\033[0m\n")

    async def _cmd_persona(self, arg: str):
        if not arg:
            names = ", ".join(p.value for p in PersonaName)
            print(f"  Personas: {names}")
            print(f"  Current: {self.current_persona}\n")
            return
        try:
            target = PersonaName(arg.lower())
            self.current_persona = target.value
            pdata = self.engine.get_persona_info(target)
            print(f"  Switched to: {pdata.emoji} {pdata.display_name}\n")
        except ValueError:
            print(f"  \033[91mUnknown persona: {arg}\033[0m\n")

    async def _cmd_help(self, arg: str):
        print("""
  \033[1mLP_GodFather v4 — CO Pilot\033[0m
  \033[90m──────────────────────────\033[0m
  /persona [name]   Switch persona
  /model [name]     Switch model
  /clear            Reset conversation
  /status           Show system status
  /exit, /quit      Exit CO Pilot

  Just type to chat. Ctrl+C to exit anytime.
""")

    async def _cmd_clear(self, arg: str):
        print("  Conversation cleared.\n")

    async def _cmd_status(self, arg: str):
        uptime = time.time() - _get_bot_start()
        days, rem = divmod(int(uptime), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        servers = await self.ollama.check_all_servers()
        lines = [
            f"\n  \033[1mSystem Status\033[0m",
            f"  Uptime: {days}d {hours:02d}:{minutes:02d}:{secs:02d}",
            f"  Persona: {self.current_persona}",
            f"  Ollama Servers:",
        ]
        for s in servers:
            status = "\033[32mONLINE\033[0m" if s.get("ok") else "\033[31mOFFLINE\033[0m"
            lines.append(f"    {s.get('name', '?')}: {status}")
        lines.append("")
        print("\n".join(lines))

    async def _cmd_model(self, arg: str):
        if arg:
            self.ollama.primary_model = arg
            print(f"  Model set to: {arg}\n")
        else:
            print(f"  Current model: {self.ollama.primary_model}\n")

    async def _cmd_exit(self, arg: str):
        print("\n  Later, Choom! 🤘\n")
        sys.exit(0)

    def _build_system_prompt(self, persona_name: str) -> str:
        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        return (
            f"You are {pdata.display_name} {pdata.emoji}\n"
            f"Style: {pdata.style}\n\n"
            f"You are the CO Pilot for Live.Play on Beast Tower. "
            f"Answer concisely but with personality. "
            f"Antworte in 2-4 Sätzen auf Deutsch. "
            f"Stay in character as {pdata.display_name}."
        )

    async def run(self):
        print("""
  \033[35m╔══════════════════════════════════════╗
  ║  🦾 LP_GodFather v4 — CO Pilot     ║
  ║  Edgerunner Flowing Persona Engine  ║
  ╚══════════════════════════════════════╝\033[0m
""")
        print(f"  Persona: \033[33m{self.current_persona.upper()}\033[0m | /help for commands\n")

        session = PromptSession(
            history=FileHistory(self.history_file),
            style=CLI_STYLE,
        )
        while True:
            try:
                text = await session.prompt_async(
                    self._get_prompt_text(),
                )
                await self.handle_message(text)
            except (EOFError, KeyboardInterrupt):
                print("\n  Later, Choom! 🤘")
                break


_bot_start_time: float = time.time()


def _get_bot_start() -> float:
    return _bot_start_time
