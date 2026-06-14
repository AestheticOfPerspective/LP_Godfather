from __future__ import annotations
import os
import sys
import logging
import signal
import asyncio
from pathlib import Path

from src.core.persona_engine import PersonaFlowEngine
from src.ai.ollama_client import OllamaClient
from src.storage.database import Database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
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
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            logger.warning("TELEGRAM_BOT_TOKEN not set, skipping Telegram")
            return

        bot = self.init_telegram()
        app = bot.build()
        logger.info("Starting Telegram bot...")
        app.run_polling(allowed_updates=["message", "callback_query", "chat_member"])

    def run_twitch(self):
        if not os.getenv("TWITCH_BOT_TOKEN"):
            logger.warning("TWITCH_BOT_TOKEN not set, skipping Twitch")
            return

        bot = self.init_twitch()
        logger.info("Starting Twitch bot...")
        bot.run()

    def run_all(self):
        logger.info("=" * 50)
        logger.info("LP_GodFather v4 — Edgerunner Flowing Persona Engine")
        logger.info("=" * 50)
        logger.info(f"Personas loaded: {len(self.engine.personas)}")
        logger.info(f"Ollama primary: {self.ollama.primary_url}")
        logger.info(f"Ollama secondary: {self.ollama.secondary_url or 'none'}")

        has_telegram = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        has_twitch = bool(os.getenv("TWITCH_BOT_TOKEN"))

        if has_telegram and has_twitch:
            logger.info("Running Telegram + Twitch in sequence (Twitch first, then Telegram runs forever)")

            import threading

            def telegram_thread():
                self.run_telegram()

            t = threading.Thread(target=telegram_thread, daemon=True)
            t.start()

            self.run_twitch()

        elif has_telegram:
            self.run_telegram()
        elif has_twitch:
            self.run_twitch()
        else:
            logger.error("No bot configured! Set TELEGRAM_BOT_TOKEN or TWITCH_BOT_TOKEN")
            sys.exit(1)


def main():
    app = GodFatherApp()
    app.run_all()


if __name__ == "__main__":
    main()
