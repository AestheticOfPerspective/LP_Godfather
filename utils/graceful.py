"""
utils/graceful.py — Graceful Shutdown Handler (SIGTERM/SIGINT)

Usage:
    from utils.graceful import shutdown_handler, is_shutting_down, on_shutdown

    async def cleanup():
        ...

    on_shutdown(cleanup)
"""
import asyncio
import logging
import signal

logger = logging.getLogger(__name__)


class ShutdownHandler:
    def __init__(self):
        self._shutdown = False
        self._handlers = []
        self._loop = None

    @property
    def is_shutting_down(self):
        return self._shutdown

    def register(self, handler):
        self._handlers.append(handler)

    def _signal_handler(self, sig, frame):
        logger.warning("Signal %s empfangen — Shutdown eingeleitet", sig)
        self._shutdown = True
        for handler in self._handlers:
            try:
                handler()
            except Exception:
                logger.exception("Shutdown handler failed")

    def install(self):
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        logger.info("Shutdown handler installiert (SIGTERM/SIGINT)")


shutdown_handler = ShutdownHandler()


def is_shutting_down() -> bool:
    return shutdown_handler.is_shutting_down


def on_shutdown(handler):
    shutdown_handler.register(handler)
