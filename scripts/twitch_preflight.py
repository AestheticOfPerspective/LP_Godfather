#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json

from src.platforms.twitch.helix import TwitchHelixClient, TwitchHelixError


async def check() -> int:
    client = TwitchHelixClient()
    try:
        result = await client.validate()
    except TwitchHelixError as exc:
        print(json.dumps({"ready": False, "error": str(exc)}))
        return 1
    print(json.dumps({
        "ready": result.chat_ready and result.mod_ready,
        "login": result.login,
        "chat_ready": result.chat_ready,
        "mod_ready": result.mod_ready,
        "missing_chat_scopes": sorted(result.missing_chat_scopes),
        "missing_mod_scopes": sorted(result.missing_mod_scopes),
    }, sort_keys=True))
    return 0 if result.chat_ready and result.mod_ready else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))

