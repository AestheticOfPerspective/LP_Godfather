import asyncio
import os

from src.platforms.twitch.bot import TwitchBot
from src.platforms.twitch.helix import REQUIRED_CHAT_SCOPES, REQUIRED_MOD_SCOPES


def test_required_twitch_scopes_cover_chat_and_moderation():
    assert REQUIRED_CHAT_SCOPES == {"chat:read", "chat:edit"}
    assert "moderator:manage:banned_users" in REQUIRED_MOD_SCOPES
    assert "moderator:manage:chat_settings" in REQUIRED_MOD_SCOPES


def test_irc_parser_handles_tags_and_privmsg(monkeypatch):
    bot = object.__new__(TwitchBot)
    bot._outbound = asyncio.Queue()
    bot._loop = None
    bot.owner = "jutsugaming"
    bot.admin_users = []
    called = {}

    async def handle(user, message, is_mod=False):
        called.update(user=user, message=message, is_mod=is_mod)

    bot.handle_chat_message = handle
    asyncio.run(bot._process_line(
        "@badges=moderator/1;color=#fff;mod=1 "
        ":alice!alice@alice.tmi.twitch.tv PRIVMSG #jutsugaming :!status"
    ))
    assert called == {"user": "alice", "message": "!status", "is_mod": True}
