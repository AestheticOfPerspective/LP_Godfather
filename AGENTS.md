# AGENTS.md

## Source of Truth

- Runtime entrypoint is `bot.py`.
- Environment keys come from `.env` (copy from `.env.example`).
- Container behavior is defined by `docker-compose.yml` and `Dockerfile`.

## Commands

- Local run: `python bot.py`
- Install deps: `pip install -r requirements.txt`
- Container run: `docker-compose up -d --build`

## Repo Safety

- Never commit `.env` or `data/` contents.
- Keep bot token placeholders in `.env.example` (no real tokens).
- Preserve async handler style used by `python-telegram-bot` v21.

## Structure

- `handlers/` contains feature handlers (AI, admin, voice, webapp, DJ).
- `utils/` contains decorators/storage helpers.
- `data/` is runtime state (SQLite, caches) and should stay git-ignored.

## Operational Gotchas

- In Docker mode, services expect internal hostnames (`ollama` service alias).
- In local mode, env host values may differ from container defaults.
