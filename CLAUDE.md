# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## LP_Godfather — SAMURAI OPERATIONS CONTRACT

### 1) MISSION: THE DOJO
- Build `LP_Godfather` into a legendary community bot platform.
- **EXECUTION MODE: SAMURAI_MAX_EFFORT (Opus 4.7)**.
- **Mentalität:** Bashen & Rasieren. Wir produzieren keine Fehler, wir produzieren Kunst. Schneller als Baki, härter als Yujiro.

### 2) MANDATORY STARTUP READING ORDER
Always initiate with:
1. `MODEL_ROUTING.md` (Strategy: AI Precision)
2. `SHOWTIME_NEXUS.md` (Strategy: GitLab Studio/GitHub Stage)
3. `README.md` (Context: Entry)
4. `MVP_SPEC_TWITCH_GODFATHER.md` (when working on the Twitch runtime)

### 3) NON-NEGOTIABLES (THE CODE)
1. **Secrets are Death:** Never commit `.env`, keys, or tokens. `.env.example` placeholders are the only allowed form (the GitLab CI `env_example_guard` job checks for them).
2. **Stability is Life:** Telegram runtime is the Dojo. Don't break it while building the Twitch Dojo — add the Twitch MVP as a feature-flagged runtime (`BOT_MODE=twitch` per MVP spec), don't refactor the live polling loop.
3. **Async Law:** No blocking loops. Whisper transcription must stay in `run_in_executor` (see `handlers/voice.py`). Outbound HTTP must use `httpx.AsyncClient`.
4. **Error Handling:** Don't spam stack traces. Catch, log via the module logger, whisper a fallback to the user (e.g. the Ollama `ConnectError` / `TimeoutException` branches in `handlers/ai.py`).

---

## Commands

Setup and run (local):
```bash
cp .env.example .env                 # fill BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS (CSV of int IDs)
pip install -r requirements.txt
python bot.py                        # entry point — long-poll, allowed_updates=ALL_TYPES
```

Container:
```bash
docker-compose up -d --build         # brings up ollama + godfather-bot, mounts ./data
```

Verify (mandatory gates before merge — these mirror `.gitlab-ci.yml` and `SHOWTIME_NEXUS.md`):
```bash
python -m compileall -q .            # syntax check (CI job: syntax_check)
bash scripts/preflight-release.sh    # .env ignored + secret-pattern scan + .env.example presence
```

Studio/Stage workflow (GitLab canonical, GitHub mirror — see `SHOWTIME_NEXUS.md`):
```bash
bash scripts/setup-dual-remote.sh git@github.com:lifeplay/godfather-bot.git
bash scripts/push-all.sh main        # pushes to gitlab then github; requires both remotes
git push gitlab vX.Y.Z && git push github vX.Y.Z   # tag release
```

There is no test suite in the repo. "Verify" = compileall + preflight + a local startup smoke (`python bot.py`).

---

## Architecture

**Entry point** (`bot.py`): wires every `CommandHandler` / `CallbackQueryHandler` / `MessageHandler` against `python-telegram-bot` v21 (async). All new commands must be registered here; `handle_callbacks` is the single dispatcher for inline-button callbacks (prefix-based: `vibe_*`, `persona_*`, `products_*`).

**Config** (`config.py`): `load_dotenv(override=True)` — `.env` always wins over OS env. `ADMIN_IDS` is parsed as `list[int]` from a CSV string; non-numeric tokens are silently dropped, so a malformed `.env` produces an empty admin list (and admin-only commands silently lock everyone out). Verify after editing.

**Handler layer** (`handlers/`):
- `ai.py` — **Smart Routing** is the core of the AI flow. `_classify_message` picks `fast` (Gemini Flash via REST) for short/simple messages, `deep` (local Ollama at `OLLAMA_HOST/api/chat`) for long messages or those containing keywords from `_COMPLEX_KEYWORDS`. Gemini failure transparently falls back to Ollama. The 7 personas (system prompts) live in `PERSONAS`; per-user selection is held in the in-process `_user_personas` dict and conversation memory in `_chat_history` (deque, `MAX_HISTORY=5` pairs). **All AI state is in-memory and lost on restart** — do not assume persistence here.
- `ains.py` — `handle_text_message` is the catch-all for non-command text in groups/DMs; it shares `ask_ai` with `/ask` so persona, history, and routing behave identically.
- `voice.py` — Voice/audio pipeline: download → `faster-whisper` transcription in a thread executor → `ask_ai` → `edge-tts` MP3 reply. Whisper model is lazy-loaded once (`_load_whisper`); `WHISPER_DEVICE=cuda` flips to `float16`, otherwise CPU/`int8`. Per-persona TTS voices in `_PERSONA_VOICES`.
- `admin.py` — Moderation commands. All decorated with `@group_only` + `@admin_only`. Warns auto-ban after `MAX_WARNS` and clear the counter.
- `dj.py` — Navidrome (Subsonic API) integration. `VIBE_PRESETS` map genre groups → playlists; `generate_vibe_playlist` deduplicates by song ID, shuffles, fills to target minutes, then caps artists at 3 songs each.
- `products.py`, `webapp.py` — Static product catalog and a single `WebAppInfo` button to the Netlify Goal Tracker.

**Utils** (`utils/`):
- `decorators.py` — `admin_only` allows either Bot-Owner (`ADMIN_IDS`) OR Telegram chat admin status. `group_only` blocks DM use.
- `storage.py` — SQLite singleton `db` (path from `DB_PATH`, default `data/godfather.db`). `check_same_thread=False` because PTB callbacks run on different threads. Two tables: `warns`, `stats` (key/value counters).

**Decision boundary — where to add code:**
- New Telegram command → handler function in the appropriate `handlers/*.py`, then `app.add_handler(CommandHandler(...))` in `bot.py`.
- New AI persona → entry in `PERSONAS` dict + optional `_PERSONA_KEYWORDS` entry for auto-suggest + optional `_PERSONA_VOICES` entry for TTS.
- New persistent state → extend `Database._init_tables` and add typed methods on `Database` (mirror the `warns`/`stats` style). Do not sprinkle raw SQL in handlers.
- New runtime mode (e.g. Twitch) → per `MVP_SPEC_TWITCH_GODFATHER.md`, feature-flag via `BOT_MODE` env, keep the Telegram polling loop in `bot.py` untouched.

---

## 4) WORKING STYLE: THE BAKI SAMURAI FLOW
For every non-trivial task, enter the **Deep Work Loop**:
1. **The Stance (Observe):** Read the actual call path in `bot.py` or `handlers/`. Know the flow.
2. **The Strike (Design):** Propose minimal, surgical architecture changes. No bloated hacks.
3. **The Cut (Implement):** Small, coherent, lethal steps.
4. **The Breath (Verify):** Run `python -m compileall -q .` and `bash scripts/preflight-release.sh`. If those fail, fix before continuing.
5. **The Witness (Document):** If behavior shifts, update `MODEL_ROUTING.md` or `SHOWTIME_NEXUS.md` immediately.

## 5) CODE STANDARDS: LETHAL QUALITY
- **Type Hints:** Use them. If the type is vague, the logic is soft.
- **Namespacing:** `handlers/` for logic, `utils/` for heavy lifting. Legacy modules are forbidden ground.
- **Logging:** Structured logs via `logger = logging.getLogger(__name__)` — never `print`. The root format is set in `bot.py`.
- **Twitch MVP:** Built as a feature-flagged runtime. Add, don't destroy.

## 6) TWITCH MVP PLAN (PHASE: THE ASCENSION)
- **Phase 1:** Mod + Engagement (The Basics of Combat)
- **Phase 2:** Navidrome Integration (The Music of War)
- **Phase 3:** Music ID (The Finishing Strike)

Full spec lives in `MVP_SPEC_TWITCH_GODFATHER.md` (roles, commands, env keys, data model, definition of done).

---
*Status: READY TO BASH AND SHAVE. COMMITMENT: 100%.*
