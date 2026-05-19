# LP GodFather Bot

Telegram community bot for Life.Play with moderation, AI chat, voice handling, persona switching, and DJ playlist features.

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

## Important Notes

- Never commit `.env`.
- Runtime data is in `data/` and ignored by git.
- `docker-compose.yml` currently sets `OLLAMA_HOST=http://ollama:11434` for container mode.
- Bot command and handler wiring starts in `bot.py`.

## Studio + Stage Workflow

- Strategy doc: `SHOWTIME_NEXUS.md`
- Model routing guide: `MODEL_ROUTING.md`
- Dual-remote setup: `bash scripts/setup-dual-remote.sh <github-ssh-url>`
- Push to GitLab + GitHub: `bash scripts/push-all.sh main`
- Public safety preflight: `bash scripts/preflight-release.sh`
