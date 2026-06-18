# LP_GodFather v4

Canonical GodFather source for Beast Tower. Telegram and Twitch run as separate
Docker services; Twitch is positioned as the JutsuGaming community/mod utility.

## Verify

```bash
python -m pytest -q
python -m compileall -q src scripts tests
docker compose -f deploy/docker-compose.yml --profile twitch config --quiet
```

## Docker

```bash
# Telegram production (exclusive token ownership required)
docker compose -f deploy/docker-compose.yml up -d telegram

# Twitch moderator runtime
docker compose -f deploy/docker-compose.yml --profile twitch up -d twitch
```

Do not start `telegram` while `~/LP_Godfather_Deploy` still owns the same token.
The Twitch profile can run alongside the legacy Telegram container.

## Twitch Moderator Setup

The bot account is `ExtremeAlex27`; the channel is `jutsugaming`.

```bash
python -m scripts.twitch_device_auth --env-file .env
python -m scripts.twitch_preflight
```

Required OAuth scopes:

- `chat:read`
- `chat:edit`
- `moderator:manage:banned_users`
- `moderator:manage:chat_settings`

Grant moderator status in the JutsuGaming chat with `/mod ExtremeAlex27`.
Default interaction is commands/mentions only. `TWITCH_AUTO_REPLY=false` must remain
the production default.

Public commands: `!help`, `!status`, `!uptime`, `!persona`, `!vibe`, `!wann`,
`!heute`, `!follow`, `!clip`.

Moderator commands: `!modcheck`, `!timeout`, `!ban`, `!unban`, `!slow`.

## Legacy Data

`scripts/import_legacy_db.py` opens the old database read-only, archives every row
in `legacy_records`, and selectively maps compatible history/facts. It defaults to a
dry-run and creates a target backup when `--apply` is used.

