# LP GodFather Bot

Telegram community bot for Life.Play with moderation, AI chat, voice handling, persona switching, and DJ playlist features.

Positioning: GodFather is the JutsuGaming / Live.Play stream utility and community operator — not a generic all-in-one bot.

## Stack

- Python 3
- `python-telegram-bot` (async)
- AI integrations via `google-genai` and optional local services
- Docker Compose setup with optional `ollama`

## Quick Start (Local)

1. Create env file:

```bash
cp .env.example .env
```

2. Fill required values in `.env`:

- `BOT_TOKEN`
- `ADMIN_IDS`

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run bot:

```bash
python bot.py
```

## Docker Run

```bash
docker-compose up -d --build
```

The Twitch runtime is opt-in so Telegram-only `.env` files do not crash-loop a second container:

```bash
docker-compose --profile twitch up -d --build twitch-bot
```

## Twitch Moderator Setup (Recommended: Second Account)

For reliable moderation commands (`!timeout`, `!ban`, `!slow`, ...), run LP_Godfather with a dedicated Twitch bot account.

1. Create/use a secondary Twitch account for the bot.
2. Fill Twitch env keys in `.env`:
   - `TWITCH_BOT_NICK` = secondary bot username
   - `TWITCH_CHANNEL` = your main channel
   - `TWITCH_OWNER` = your main channel owner username
   - `TWITCH_ADMIN_USERS` = comma list of trusted mods (optional)
3. In your Twitch chat, grant moderator rights:

```text
/mod <TWITCH_BOT_NICK>
```

4. Start runtime with `BOT_MODE=twitch`.

Note: Single-account mode (broadcaster = bot) can work for basic chat commands, but dedicated bot account + mod role is the stable setup for moderation flows.

## Stream Utility Commands

Telegram:

- `/wann` — Wochenplan
- `/heute` — heutiger Stream oder Fallback
- `/follow` — Twitch/YouTube Links
- `/clip` — Clip-Moment einreichen

Twitch:

- `!wann` / `!schedule`
- `!heute`
- `!follow`
- `!clip`

Configure copy via `STREAM_BRAND`, `STREAM_TIMEZONE`, `STREAM_SCHEDULE`, `TWITCH_CHANNEL_URL`, `YOUTUBE_URL`, and `CLIP_INTAKE_URL` in `.env`.

## Important Notes

- Never commit `.env`.
- Runtime data is in `data/` and ignored by git.
- `docker-compose.yml` currently sets `OLLAMA_HOST=http://ollama:11434` for container mode.
- `bot.py` dispatches by `BOT_MODE`; Telegram wiring lives in `runtimes/telegram.py`, Twitch commands live in `runtimes/twitch.py`.

## Hermes Primary Router (Telegram-First)

Enable Telegram namespace commands as a control plane in `.env`:

- `HERMES_ROUTER_ENABLED=true`
- `HERMES_ROUTER_URL=http://127.0.0.1:8088/route`
- Optional: `HERMES_ROUTER_TOKEN=...`
- Optional allowlist: `HERMES_ALLOWED_CHAT_IDS=-100...,123...`
- Optional title allowlist: `HERMES_ALLOWED_CHAT_TITLES=Aesthetic Of Perspective,LivePlay`

Available command namespaces:

- `/live preflight|go|checkpoint|brb|panic|outro|state`
- `/dj mode <name>|drop|switch8|recover|lock|state`
- `/ops status|diag|fallback|queue|chatid|state`
- `/chronik log <text>|recap|extract|next|state`

If Hermes forwarding is unavailable, LP_Godfather keeps local state guards active and reports fallback status in chat.

## Studio + Stage Workflow

- Strategy doc: `SHOWTIME_NEXUS.md`
- Model routing guide: `MODEL_ROUTING.md`
- Dual-remote setup: `bash scripts/setup-dual-remote.sh <github-ssh-url>`
- Push to GitLab + GitHub: `bash scripts/push-all.sh main`
- Public safety preflight: `bash scripts/preflight-release.sh`
