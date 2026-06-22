# GodFather Bot — Developer Guide

## Machine Identity

| Hostname | Alias | Tailscale IP | Role |
|----------|-------|-------------|------|
| `aopmedia-tiger` | `tiger` / `pink-tiger` | `100.66.191.86` | Dev laptop — source of truth |
| `beast-tower` | `beast-tower` | `100.67.192.68` | Server — Docker runtime |

## Quick Ops

```bash
# Deploy code Tiger→Beast
~/bin/lp-godfather-deploy.sh

# Sync configs bidirektional (auto-detect hostname)
~/bin/sync-opencode.sh push
~/bin/sync-opencode.sh pull

# Check bot on Beast
ssh beast-tower "docker logs godfather-bot --tail 20"

# Local run
python bot.py
# Container build
docker compose up -d --build
```

## SSH Layout

```
Tiger ──ssh beast-tower──→ Beast   (code deploy, config push)
Beast ──ssh tiger────────→ Tiger   (config pull, mgmt)
```

## Key Paths

| Path | Purpose |
|------|---------|
| `~/Repos/LP_Godfather/` | Git repo (source of truth) |
| `~/Projects/LP_Godfather/` | Deploy source (rsync mirror of Repos) |
| `~/LP_Godfather_Deploy/` | Docker build context on Beast |
| `~/.config/opencode/instructions/` | Agent instructions (synced bidir) |
| `~/bin/sync-opencode.sh` | Config sync script (both machines) |
| `~/bin/lp-godfather-deploy.sh` | Code + Docker deploy (Tiger only) |

## Sync Architecture

- **Code**: Tiger→Beast via `lp-godfather-deploy.sh` (systemd timer alle 15min)
- **Config**: `sync-opencode.sh push|pull` manuell (auto-detects direction)
- **Kritisch**: Beide Scripts liegen in `~/bin/` und werden bidirektional gesynct

## Bot Behavior Pipeline

PromptStack: `SOUL.md` → `PERSONA.md` → `GOLDEN_EXAMPLES.md` → Runtime (persona_loader.py)
IntentRouter: `ains.py` → `intents.py` (natural language) → `ask_ai()` (Ollama/Gemini)
PersonaSystem: 7 personas in `ai.py:PERSONAS`, switch via `/persona`

## Recent Fixes (2026-06-03)

1. **Template-Overload:** `GOLDEN_EXAMPLES.md` Anti-Instruction + server-side `_strip_persona_prefix()` in `ai.py`
2. **Mid-Sentence Break:** 250 word limit (was 150) + `num_predict=600` in Ollama payload
3. **Persona-Prefix Conflict:** `persona_loader.py` identity instruction changed + server-side prefix strip in `ask_ai()`
