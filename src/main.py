from __future__ import annotations
import os
import sys
import logging
import signal
import asyncio
from pathlib import Path

from dotenv import load_dotenv
_dotenv_path = Path(__file__).parent.parent / ".env"
load_dotenv(_dotenv_path)

from src.core.persona_engine import PersonaFlowEngine
from src.ai.ollama_client import OllamaClient
from src.storage.database import Database

class SecretRedactionFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.secrets = [
            value for value in (
                os.getenv("TELEGRAM_BOT_TOKEN"),
                os.getenv("BOT_TOKEN"),
                os.getenv("TWITCH_BOT_TOKEN"),
                os.getenv("TWITCH_TOKEN"),
                os.getenv("TWITCH_CLIENT_SECRET"),
            ) if value
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
for handler in logging.getLogger().handlers:
    handler.addFilter(SecretRedactionFilter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("godfather")


class GodFatherApp:
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / "config"
        self.db = Database()
        self.ollama = OllamaClient()
        self.engine = PersonaFlowEngine(self.config_dir)
        self.telegram_bot = None
        self.twitch_bot = None
        self.running = True

    def init_telegram(self):
        from src.platforms.telegram import TelegramBot
        self.telegram_bot = TelegramBot(self.engine, self.ollama, self.db, self.config_dir)
        return self.telegram_bot

    def init_twitch(self):
        from src.platforms.twitch import TwitchBot
        self.twitch_bot = TwitchBot(self.engine, self.ollama, self.db, self.config_dir)
        return self.twitch_bot

    def run_telegram(self):
        if not (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")):
            logger.warning("TELEGRAM_BOT_TOKEN not set, skipping Telegram")
            return

        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        bot = self.init_telegram()
        app = bot.build()
        logger.info("Starting Telegram bot...")
        app.run_polling(allowed_updates=["message", "callback_query", "chat_member"], drop_pending_updates=True)

    def run_twitch(self):
        if not (os.getenv("TWITCH_BOT_TOKEN") or os.getenv("TWITCH_TOKEN")):
            logger.warning("TWITCH_BOT_TOKEN not set, skipping Twitch")
            return

        bot = self.init_twitch()
        logger.info("Starting Twitch bot...")
        bot.run()

    async def _run_cli(self):
        from src.copilot.cli import CLIBot
        cli = CLIBot(self.engine, self.ollama, self.db, self.config_dir)
        await cli.run()

    def _run_mcp(self):
        from src.copilot.mcp_server import init, run
        init(self.ollama, self.engine, self.db)
        run()

    def run_all(self):
        logger.info("=" * 50)
        logger.info("LP_GodFather v4 — Edgerunner Flowing Persona Engine")
        logger.info("=" * 50)
        logger.info(f"Personas loaded: {len(self.engine.personas)}")
        logger.info(f"Ollama primary: {self.ollama.primary_url}")
        logger.info(f"Ollama secondary: {self.ollama.secondary_url or 'none'}")

        mode = os.getenv("BOT_MODE", "telegram").strip().lower()
        if mode not in {"telegram", "twitch", "all", "cli", "mcp"}:
            logger.error("Invalid BOT_MODE=%s; expected telegram, twitch, all, cli, or mcp", mode)
            sys.exit(2)

        has_telegram = bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN"))
        has_twitch = bool(os.getenv("TWITCH_BOT_TOKEN") or os.getenv("TWITCH_TOKEN"))

        if mode == "cli":
            logger.info("Starting CO Pilot CLI mode...")
            asyncio.run(self._run_cli())
            return

        if mode == "mcp":
            logger.info("Starting CO Pilot MCP server...")
            self._run_mcp()
            return

        if mode == "telegram":
            if not has_telegram:
                logger.error("BOT_MODE=telegram but TELEGRAM_BOT_TOKEN is missing")
                sys.exit(1)
            self.run_telegram()
            return

        if mode == "twitch":
            if not has_twitch:
                logger.error("BOT_MODE=twitch but TWITCH_BOT_TOKEN is missing")
                sys.exit(1)
            self.run_twitch()
            return

        if has_telegram and has_twitch:
            logger.info("Running Telegram (main) + Twitch (background thread)")

            import threading

            def twitch_thread():
                self.run_twitch()

            t = threading.Thread(target=twitch_thread, daemon=True)
            t.start()

            self.run_telegram()

        elif has_telegram:
            self.run_telegram()
        elif has_twitch:
            self.run_twitch()
        else:
            logger.error("BOT_MODE=all but no bot token is configured")
            sys.exit(1)


def main():
    app = GodFatherApp()
    app.run_all()


if __name__ == "__main__":
    main()
