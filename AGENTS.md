# LP_GodFather v4 — Edgerunner Flowing Persona Engine

9 personas flow naturally based on context, time, sentiment, and user affinity.

## Stack
- Python 3.12, python-telegram-bot v21+, twitchio/IRC
- Ollama (dual-server failover: Beast Tower GPU + Pink Tiger CPU)
- SQLite (WAL mode, rate_limits + user_memories tables)
- Docker (multi-stage, Tailscale sidecar optional)
- Interviewer prompts: `config/interviewers.yaml` (not hardcoded)

## Personas
| Emoji | Name | Vibe | Triggers |
|-------|------|------|----------|
| 💀 | GODFATHER | Default Fixer — pragmatisch, direkt, help-first | help, frage, bitte, support, brauche, yo, bratan, choom, danke, question, how, what, warum, wieso |
| 🎮 | CHOOM | Gamer hype | gg, pog, gaming, preem |
| 🌌 | NOVA | Gene Keys bard | meaning, purpose, shadow, gift |
| 🌐 | CYBER-ZEN | Code monk | refactor, clean, zen, focus |
| 🌈 | VAPOR-FOSS | Open source chill | foss, libre, open source, chill |
| 🥊 | BAKI | Raw power | grind, push, limit, beast |
| ⚔️ | SAMURAI | Warrior code | discipline, mastery, honor |
| 🤘 | PUNK-PHILOSOPHER | Deep rebel | why, truth, question, system |
| 🌴 | TROPICAL-INFINITY | Galaxy chill | vibe, flow, relax, universe |
| 🐒 | MONKEY-MIND | Creative chaos | idea, brainstorm, random, poetry |

## Quick Start

### Local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env with your tokens
python -m src.main
```

### Docker (standalone)
```bash
cd deploy
docker compose -f docker-compose.yml up --build -d
```

### Docker (with Tailscale sidecar)
```bash
cd deploy
docker compose -f docker-compose.tailscale.yml up --build -d
```

## Commands

### Telegram
- `/start` — Welcome
- `/help` — All commands
- `/persona [name]` — Switch persona
- `/vibe [mode]` — Set vibe (hype/chill/deep/intense/focus/creative/rebel/warrior/free)
- `/flow` — Show current flow state
- `/supernova` — FORCE SUPERNOVA MODE
- `/status` — System dashboard
- `/servers` — Ollama server status
- `/model [name]` — Show/switch model
- `/models` — List all models
- `/pull [name]` — Download model
- `/history` — Conversation stats
- `/clear` — Reset conversation
- `/about` — Bot info
- `/remember <key> <value>` — Save a persistent memory
- `/recall [key]` — Recall saved memories
- `/forget <key>` — Delete a memory
- `/interview [agent]` — Launch interviewer agent (anchor, recruiter-x, code-hammer, mind-mirror, shark, press-room)
- `/hard` — Launch Hard Mode Gauntlet (all 6 interviewers in sequence)
- `/whitelist` — [Admin] Whitelist current group
- `/unwhitelist` — [Admin] Remove group from whitelist
- `/brand_calibrate <text>` — Brand calibration check
- `/comedy_test <text>` — Comedy gate checker
- `/media_value_router <text>` — Route content to brand
- `/privacy_pass <text>` — Privacy scanner
- `/risk_mirror <plan>` — Review plans for safety/secrets/overreach
- `/subtitle_adapt <lang> <text>` — Subtitle adaptation
- `/roll [XdY\|coin]` — Dice roller / coinflip
- `/pick A \| B \| C` — Random picker
- `/8ball <frage>` — Magic 8-Ball
- `/tarot [1-3]` — Cyberpunk 2077 Tarot (22 Major Arcana mit Lore)

### Twitch
- `!persona [name]` — Switch persona
- `!flow` — Show flow state
- `!vibe [mode]` — Set vibe
- `!status` — Bot dashboard
- `!uptime` — Bot uptime
- Default interaction is commands/mentions only (`TWITCH_AUTO_REPLY=false`); never enable broad auto-replies in a live channel without a dedicated spam test.
- JutsuGaming utility: `!wann`, `!schedule`, `!heute`, `!follow`, `!clip`.
- `!modcheck` — OAuth/Moderator-Scope preflight
- `!timeout <user> [seconds] [reason]` — Helix timeout (mods only)
- `!ban <user> [reason]` / `!unban <user>` — Helix moderation (mods only)
- `!slow <0|3-120>` — Helix slow-mode control (mods only)

## Secrets (never commit)
- `.env`
- `data/*.db`

## Critical Gotchas
- db schema changes require manual DB update (CREATE TABLE IF NOT EXISTS)
- Twitch bot uses raw IRC protocol via socket — rewritten with persistent event loop + auto-reconnect (10 attempts, exponential backoff)
- Chat transport uses TLS IRC; moderation actions use Twitch Helix APIs.
- Required bot token scopes: `chat:read`, `chat:edit`, `moderator:manage:banned_users`, `moderator:manage:chat_settings`.
- Tailscale sidecar needs TS_AUTHKEY in .env
- Ollama failover: Beast → Tiger → Local
- Persona transitions have cooldown (30s min interval, 3 msg min wait)
- **Rate limiting**: 1s cooldown on chat messages, per-user per-command (SQLite-backed, survives restart)
- **Memory system**: `/remember`/`/recall`/`/forget` backed by `user_memories` table — category scoped, persistent
- **Conversations**: last 20 messages restored from SQLite on first chat (not cold start)
- **Ollama HTML output**: sanitized via allowlist (`<b>`, `<i>`, `<code>`, `<pre>`, `<a>` HTTPS-only) — no external deps
- **Interviewer prompts**: loaded from `config/interviewers.yaml` — edit prompts without touching Python code
- **Group whitelist**: `/whitelist` enables ALL members to chat freely (not just admin). Non-whitelisted groups still need trigger words.
- **`.env` placeholders**: `your_telegram_bot_token`, `your_twitch_oauth_token` must be replaced with real credentials before live run

## v4.1 Upgrade (2026-06-16)

### What changed
- **GODFATHER is now the default persona** — no more random NOVA/CYBER-ZEN defaults. Fixer mode first, flavor personas only on strong context match.
- **Context detection** added: practical/business questions → force GODFATHER; personal struggles → TROPICAL-INFINITY (supportive); tech → CYBER-ZEN; gaming → CHOOM.
- **System prompt guardrails**: Bot can no longer hallucinate voice/video/image capabilities. Explicitly forbidden from recommending Gene Keys cards for practical questions.
- **Timeout handling**: If Ollama takes >25s, user gets a polite "try again" message instead of a silent timeout.
- **Reduced randomness**: Persona transitions are now deterministic (confidence threshold >0.25). No more coin-flip persona switches.
- **`/personas`** now works as an alias for `/persona`.
- **Conflict bug fixed**: Docker container `godfather-bot` (ID `883f8192a98e`) was running old v4.0 `python bot.py` as root via containerd-shim, causing 409 Conflict polling errors on the same token. Container stopped + removed. Local `python -m src.main` instance now runs cleanly at PID 84271.

### Files changed
- `config/personas.yaml` — +GODFATHER persona + transition graph edges
- `config/transitions.yaml` — +practical/personal_support categories + rules
- `src/core/persona_engine.py` — Default = GODFATHER, reduced randomness, new sentiment mapping
- `src/platforms/telegram/bot.py` — Context detection, guardrails, timeout, asyncio import, /personas alias

### Gotcha: Docker vs Local
The `deploy/docker-compose.yml` runs the old v4.0 Docker image with `restart: unless-stopped`. The container was **removed** — v4.1 runs locally only. If `docker compose up` is ever run again from `deploy/`, the old version will conflict again. Keep the container stopped or update the Dockerfile to match v4.1.
