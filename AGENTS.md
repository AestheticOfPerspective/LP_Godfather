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

## Prompt Architecture

- Bot personality = `SOUL.md` + `PERSONA.md` + `GOLDEN_EXAMPLES.md` (Repo Root)
- `handlers/persona_loader.py:assemble_base_prompt()` loads them into every AI query
- 7 personas in `handlers/ai.py:PERSONAS` (GodFather, Cyber-Zen, Monkey-Mind, etc.)
- Intent router in `handlers/intents.py` catches natural language ("merk dir", "clip das")
- Fixes deployed 2026-06-03: template-strip (GOLDEN_EXAMPLES.md), mid-sentence-guard (num_predict=600), persona-prefix server-side strip
