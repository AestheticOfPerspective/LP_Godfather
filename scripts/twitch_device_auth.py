#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import stat
import time
from pathlib import Path

import httpx


SCOPES = [
    "chat:read",
    "chat:edit",
    "moderator:manage:banned_users",
    "moderator:manage:chat_settings",
]


def update_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                updated.append(f"{key}={remaining.pop(key)}")
                continue
        updated.append(line)
    if updated and updated[-1] != "":
        updated.append("")
    updated.extend(f"{key}={value}" for key, value in remaining.items())

    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("\n".join(updated) + "\n")
    temp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temp.replace(path)


async def authenticate(client_id: str, expected_login: str,
                       env_file: Path) -> int:
    async with httpx.AsyncClient(timeout=15.0) as client:
        device = await client.post(
            "https://id.twitch.tv/oauth2/device",
            data={"client_id": client_id, "scopes": " ".join(SCOPES)},
        )
        device.raise_for_status()
        grant = device.json()

        print(f"Open: {grant['verification_uri']}", flush=True)
        print(f"Code: {grant['user_code']}", flush=True)
        print(f"Authorize the Twitch account: {expected_login}", flush=True)

        deadline = time.monotonic() + int(grant.get("expires_in", 1800))
        interval = max(2, int(grant.get("interval", 5)))
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            token_response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": client_id,
                    "scope": " ".join(SCOPES),
                    "device_code": grant["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if token_response.status_code == 400:
                payload = token_response.json()
                error = " ".join(
                    str(payload.get(key, "")) for key in ("error", "message", "status")
                ).lower()
                if "pending" in error or "authorization" in error or "slow_down" in error:
                    continue
                raise RuntimeError(f"Twitch device polling failed: {payload}")
            token_response.raise_for_status()
            tokens = token_response.json()

            validation = await client.get(
                "https://id.twitch.tv/oauth2/validate",
                headers={"Authorization": f"OAuth {tokens['access_token']}"},
            )
            validation.raise_for_status()
            identity = validation.json()
            login = str(identity.get("login", ""))
            if login.casefold() != expected_login.casefold():
                raise RuntimeError(
                    f"Authorized {login!r}, expected {expected_login!r}; env not changed"
                )

            values = {
                "TWITCH_CLIENT_ID": client_id,
                "TWITCH_BOT_TOKEN": tokens["access_token"],
                "TWITCH_REFRESH_TOKEN": tokens.get("refresh_token", ""),
                "TWITCH_BOT_USER_ID": str(identity.get("user_id", "")),
            }
            client_secret = os.getenv("TWITCH_CLIENT_SECRET", "")
            if client_secret:
                values["TWITCH_CLIENT_SECRET"] = client_secret
            update_env(env_file, values)
            print(f"Authorized {login}; token stored in {env_file}", flush=True)
            return 0

    print("Authorization expired; env not changed", flush=True)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    client_id = os.getenv("TWITCH_CLIENT_ID", "")
    expected_login = os.getenv("TWITCH_BOT_NICK", "")
    if not client_id or not expected_login:
        parser.error("TWITCH_CLIENT_ID and TWITCH_BOT_NICK must be set")
    return asyncio.run(authenticate(client_id, expected_login, args.env_file))


if __name__ == "__main__":
    raise SystemExit(main())
