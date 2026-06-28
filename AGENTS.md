# AGENTS.md — LP_Godfather

## Entrypoints

- `bot.py` — thin dispatcher. Reads `BOT_MODE` env var: `"telegram"` (default) or `"twitch"`.
- `runtimes/telegram.py:run()` — Telegram handler wiring (all `/` commands registered here, lines 570–636).
- `runtimes/twitch.py:run()` — Twitch `!` commands.

## Commands

```bash
python bot.py                          # local run (needs .env from .env.example)
docker compose up -d --build           # Docker (uses beast-ollama hostname)
docker compose --profile twitch up -d --build twitch-bot  # Twitch opt-in
```

No test suite exists — no pytest config, no test files.

## Dual Remote

```bash
bash scripts/push-all.sh main          # push to GitHub + GitLab
bash scripts/preflight-release.sh      # public safety check
```

## Architecture

- `python-telegram-bot` v21.6 — handlers fire in **registration order**; `CommandHandler` takes priority over `MessageHandler` regardless of order.
- `BOT_MODE=telegram` and `BOT_MODE=twitch` share `handlers/` modules but have separate `run()` wiring.
- SQLite via `utils/storage.py:Database()` singleton (`db`). Runtime state in `data/` (gitignored).
- 30 handler modules under `handlers/` — 7 major groups: AI, Moderation, Stream, Voice, DJ, Memory/Training, Hermes Router.

## Features

- **7 AI personas** — switch per-user via `/persona`. Prompt stack: `SOUL.md` → `PERSONA.md` → `GOLDEN_EXAMPLES.md` → `persona_loader.py`.
- **Intent router** — `handlers/ains.py` + `intents.py` catch natural language ("merk dir", "clip das").
- **Memory & Training** — `/remember`, `/recall`, `/forget`, `/mymemories` (per-user facts); `/teach`, `/knowledge`, `/trainings` (shared KB).
- **Hermes Router** — `/live`, `/dj`, `/ops`, `/chronik` namespace commands (requires external Hermes service).
- **FSK maturity** — per-chat age rating via `TELEGRAM_CHAT_FSK` config (default 12, Live.Play/AOP=18).

## Critical Gotchas (agent would miss)

1. **`route_mastering` blocks `handle_voice`** — `runtimes/telegram.py:600` registers `route_mastering` with `TEXT|AUDIO|VOICE` filter BEFORE `handle_voice` on line 634. Users in mastering flow who send voice get dual responses (track submitted + transcription). Fix: register `route_mastering` after `handle_voice` or exclude `VOICE`.

2. **`touch_user` called before spam check** — `runtimes/telegram.py:537` logs user activity before spam deletion at line 546. Spammers inflate activity stats. Fix: move `touch_user` after the deletion block.

3. **Python 3.14 compat fix** — `runtimes/telegram.py:15-18` has asyncio event-loop workaround. Keep if adding new top-level async code.

4. **Docker Ollama hostname** — `docker-compose.yml` sets `OLLAMA_HOST=http://beast-ollama:11434`. Local dev needs `localhost` or the env default.

5. **No tests** — changes are runtime-tested only via live Telegram/Twitch. No CI beyond syntax check + env guard (`.gitlab-ci.yml`).

6. **`config.py:load_dotenv(override=True)`** — .env always beats OS env vars. Important if deploying with systemd env injection.

## Repo Safety

- Never commit `.env` or `data/`.
- Bot token placeholders in `.env.example` only.
- Two git origins (`origin` and `gitlab` in `push-all.sh`).

## Color Key

🟢 Commands | 🟡 Gotcha | 🟠 Architecture | 🔴 Critical Bug
