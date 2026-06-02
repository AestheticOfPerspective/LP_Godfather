#!/usr/bin/env python3
"""
Telegram-context smoke test for Hermes router commands.

Runs command handlers with fake Telegram objects so routing logic can be
verified without a live bot token.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _set_test_env(route_url: str) -> None:
    os.environ.setdefault("HERMES_ROUTER_ENABLED", "true")
    os.environ.setdefault("HERMES_ROUTER_URL", route_url)
    os.environ.setdefault("HERMES_ALLOWED_CHAT_TITLES", "Aesthetic Of Perspective,LivePlay")
    os.environ.setdefault("HERMES_DEFAULT_PHASE", "prep")
    os.environ.setdefault("HERMES_DEFAULT_DJ_MODE", "cyber-zen")
    os.environ.setdefault("ADMIN_IDS", "111")


class FakeMessage:
    async def reply_text(self, text, parse_mode=None, reply_markup=None):  # noqa: ANN001
        del parse_mode, reply_markup
        print(f"BOT> {text}")


class FakeUser:
    def __init__(self, user_id: int, username: str):
        self.id = user_id
        self.username = username


class FakeChat:
    def __init__(self, chat_id: int, title: str):
        self.id = chat_id
        self.type = "supergroup"
        self.title = title


class FakeMember:
    def __init__(self, status):
        self.status = status


class FakeBot:
    def __init__(self, admin_status):
        self.admin_status = admin_status

    async def get_chat_member(self, chat_id: int, user_id: int):  # noqa: ARG002
        return FakeMember(self.admin_status)


class FakeContext:
    def __init__(self, args: list[str], bot: FakeBot):
        self.args = args
        self.bot = bot


class FakeUpdate:
    def __init__(self, user: FakeUser, chat: FakeChat):
        self.effective_user = user
        self.effective_chat = chat
        self.message = FakeMessage()


async def _run_scenario(group_title: str, group_id: int, route_url: str) -> None:
    from telegram.constants import ChatMemberStatus

    from handlers.hermes_router import (
        ROUTER_STATE,
        cmd_chronik,
        cmd_dj,
        cmd_live,
        cmd_ops,
    )

    print(f"\n=== Scenario for group: {group_title} ({group_id}) ===")
    user = FakeUser(user_id=111, username="fossnomade")
    chat = FakeChat(chat_id=group_id, title=group_title)
    update = FakeUpdate(user=user, chat=chat)
    bot = FakeBot(admin_status=ChatMemberStatus.ADMINISTRATOR)

    async def run_cmd(handler, *args: str):
        print(f"\nCMD> {handler.__name__} args={list(args)}")
        ctx = FakeContext(args=list(args), bot=bot)
        await handler(update, ctx)

    await run_cmd(cmd_ops, "chatid")
    await run_cmd(cmd_ops, "status")
    await run_cmd(cmd_live, "preflight")
    await run_cmd(cmd_live, "go")
    await run_cmd(cmd_dj, "mode", "nyx")
    await run_cmd(cmd_live, "checkpoint")
    await run_cmd(cmd_live, "outro")
    await run_cmd(cmd_chronik, "recap")
    await run_cmd(cmd_chronik, "next")

    print(f"\nRESULT> phase={ROUTER_STATE['phase']} dj_mode={ROUTER_STATE['dj_mode']} route={route_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Telegram Hermes router handlers.")
    parser.add_argument("--route-url", default="http://127.0.0.1:8088/route")
    args = parser.parse_args()

    _set_test_env(args.route_url)

    asyncio.run(_run_scenario("Aesthetic Of Perspective", -1001010101, args.route_url))
    asyncio.run(_run_scenario("LivePlay", -1002020202, args.route_url))


if __name__ == "__main__":
    main()
