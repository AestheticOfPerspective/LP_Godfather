# LP_GodFather v4 — Edgerunner Flowing Persona Engine

9 personas flow naturally based on context, time, sentiment, and user affinity.

## Stack
- Python 3.12, python-telegram-bot v21+, twitchio/IRC
- Ollama (dual-server failover: Beast Tower GPU + Pink Tiger CPU)
- SQLite (WAL mode)
- Docker (multi-stage, Tailscale sidecar optional)

## Personas
| Emoji | Name | Vibe | Triggers |
|-------|------|------|----------|
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

### Twitch
- `!persona [name]` — Switch persona
- `!flow` — Show flow state
- `!vibe [mode]` — Set vibe
- `!status` — Bot dashboard
- `!uptime` — Bot uptime

## Secrets (never commit)
- `.env`
- `data/*.db`

## Critical Gotchas
- db schema changes require manual DB update (CREATE TABLE IF NOT EXISTS)
- Twitch bot uses stdin/stdout IRC (no library, raw protocol)
- Tailscale sidecar needs TS_AUTHKEY in .env
- Ollama failover: Beast → Tiger → Local
- Persona transitions have cooldown (30s min interval, 3 msg min wait)
