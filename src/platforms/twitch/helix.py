from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import httpx


REQUIRED_CHAT_SCOPES = {"chat:read", "chat:edit"}
REQUIRED_MOD_SCOPES = {
    "moderator:manage:banned_users",
    "moderator:manage:chat_settings",
}


@dataclass
class TwitchPreflight:
    user_id: str
    login: str
    scopes: set[str]
    missing_chat_scopes: set[str]
    missing_mod_scopes: set[str]

    @property
    def chat_ready(self) -> bool:
        return not self.missing_chat_scopes

    @property
    def mod_ready(self) -> bool:
        return not self.missing_mod_scopes


class TwitchHelixError(RuntimeError):
    pass


class TwitchHelixClient:
    def __init__(self) -> None:
        raw_token = os.getenv("TWITCH_BOT_TOKEN") or os.getenv("TWITCH_TOKEN", "")
        self.token = raw_token.removeprefix("oauth:")
        self.client_id = os.getenv("TWITCH_CLIENT_ID", "")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("TWITCH_REFRESH_TOKEN", "")
        self.bot_login = os.getenv("TWITCH_BOT_NICK", "")
        self.channel_login = os.getenv("TWITCH_CHANNEL", "")
        self.bot_user_id = os.getenv("TWITCH_BOT_USER_ID") or os.getenv("TWITCH_BOT_ID", "")
        self.broadcaster_id = os.getenv("TWITCH_BROADCASTER_ID", "")
        self.base_url = "https://api.twitch.tv/helix"

    @property
    def configured(self) -> bool:
        return bool(self.token and self.client_id and self.bot_login and self.channel_login)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.configured:
            raise TwitchHelixError("Twitch Helix credentials are incomplete")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method, f"{self.base_url}{path}", headers=self._headers(), **kwargs,
            )
        if response.status_code == 401 and self.refresh_token and self.client_secret:
            await self.refresh()
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", headers=self._headers(), **kwargs,
                )
        if response.status_code >= 400:
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise TwitchHelixError(f"Twitch API {response.status_code}: {message[:240]}")
        return response

    async def refresh(self) -> None:
        if not (self.refresh_token and self.client_id and self.client_secret):
            raise TwitchHelixError("Twitch refresh credentials are incomplete")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
        if response.status_code >= 400:
            raise TwitchHelixError("Twitch token refresh failed")
        data = response.json()
        self.token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)

    async def validate(self) -> TwitchPreflight:
        if not self.token:
            raise TwitchHelixError("Twitch token is missing")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://id.twitch.tv/oauth2/validate",
                headers={"Authorization": f"OAuth {self.token}"},
            )
        if response.status_code != 200 and self.refresh_token and self.client_secret:
            await self.refresh()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {self.token}"},
                )
        if response.status_code != 200:
            raise TwitchHelixError("Twitch token validation failed")
        data = response.json()
        scopes = set(data.get("scopes", []))
        self.bot_user_id = str(data.get("user_id", self.bot_user_id))
        return TwitchPreflight(
            user_id=self.bot_user_id,
            login=str(data.get("login", "")),
            scopes=scopes,
            missing_chat_scopes=REQUIRED_CHAT_SCOPES - scopes,
            missing_mod_scopes=REQUIRED_MOD_SCOPES - scopes,
        )

    async def _user_id(self, login: str) -> str:
        response = await self._request("GET", "/users", params={"login": login})
        users = response.json().get("data", [])
        if not users:
            raise TwitchHelixError(f"Unknown Twitch user: {login}")
        return str(users[0]["id"])

    async def ensure_ids(self) -> tuple[str, str]:
        if not self.bot_user_id:
            self.bot_user_id = await self._user_id(self.bot_login)
        if not self.broadcaster_id:
            self.broadcaster_id = await self._user_id(self.channel_login)
        return self.bot_user_id, self.broadcaster_id

    async def ban(self, target_login: str, reason: str = "",
                  duration: Optional[int] = None) -> None:
        moderator_id, broadcaster_id = await self.ensure_ids()
        target_id = await self._user_id(target_login)
        body: dict[str, object] = {"user_id": target_id}
        if reason:
            body["reason"] = reason[:500]
        if duration is not None:
            body["duration"] = max(1, min(int(duration), 1_209_600))
        await self._request(
            "POST", "/moderation/bans",
            params={"broadcaster_id": broadcaster_id, "moderator_id": moderator_id},
            json={"data": body},
        )

    async def unban(self, target_login: str) -> None:
        moderator_id, broadcaster_id = await self.ensure_ids()
        target_id = await self._user_id(target_login)
        await self._request(
            "DELETE", "/moderation/bans",
            params={
                "broadcaster_id": broadcaster_id,
                "moderator_id": moderator_id,
                "user_id": target_id,
            },
        )

    async def set_slow_mode(self, seconds: int) -> None:
        moderator_id, broadcaster_id = await self.ensure_ids()
        enabled = seconds > 0
        payload: dict[str, object] = {"slow_mode": enabled}
        if enabled:
            payload["slow_mode_wait_time"] = max(3, min(seconds, 120))
        await self._request(
            "PATCH", "/chat/settings",
            params={"broadcaster_id": broadcaster_id, "moderator_id": moderator_id},
            json=payload,
        )
