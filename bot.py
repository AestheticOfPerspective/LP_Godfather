#!/usr/bin/env python3
"""
GodFather Bot — Life.Play Community Manager
FOSS (MIT License) | github.com/AestheticOfPerspective/LP_Godfather

Thin dispatcher — wählt Runtime basierend auf BOT_MODE.
"""

import logging
import sys

from config import BOT_MODE

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("GodFatherBot")


def main() -> None:
    logger.info("BOT_MODE=%s", BOT_MODE)

    if BOT_MODE == "telegram":
        from runtimes.telegram import run
        run()
    elif BOT_MODE == "twitch":
        from runtimes.twitch import run
        run()
    else:
        raise ValueError(f"Unbekannter BOT_MODE: {BOT_MODE}")


if __name__ == "__main__":
    main()
