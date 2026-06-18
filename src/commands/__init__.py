import importlib
import pkgutil
import logging
from typing import Optional, List, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandDef:
    name: str
    help_text: str
    usage: str
    execute: Callable[..., Awaitable[str]]


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, CommandDef] = {}

    def register(self, cmd: CommandDef):
        self._commands[cmd.name] = cmd
        logger.info("Registered command: /%s", cmd.name)

    def discover(self):
        import src.commands as pkg
        for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            if modname.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"src.commands.{modname}")
                if hasattr(module, "COMMAND_NAME"):
                    self.register(CommandDef(
                        name=module.COMMAND_NAME,
                        help_text=module.COMMAND_HELP,
                        usage=module.COMMAND_USAGE,
                        execute=module.execute,
                    ))
            except Exception as e:
                logger.error("Failed to load command %s: %s", modname, e)

    def get(self, name: str) -> Optional[CommandDef]:
        return self._commands.get(name)

    def get_all(self) -> List[CommandDef]:
        return list(self._commands.values())

    def get_bot_command_defs(self):
        try:
            from telegram import BotCommand
            return [BotCommand(c.name, c.help_text[:100]) for c in self._commands.values()]
        except ImportError:
            return []


_registry: Optional[CommandRegistry] = None


def get_registry() -> CommandRegistry:
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        _registry.discover()
    return _registry
