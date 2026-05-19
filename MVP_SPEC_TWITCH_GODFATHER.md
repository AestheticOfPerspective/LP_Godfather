# LP_GodFather - MVP Spec (Twitch Co-Pilot + Mod)

## 1) Product Goal

Build `LP_GodFather` as a focused Twitch companion that does three jobs well:

1. Reliable moderation
2. High chat engagement (Cyber-Zen / GodFather personality)
3. Streamer + trusted-chooms support automation

Tarot is intentionally out of this MVP scope (owner handles separately).

---

## 2) Scope (MVP)

### In Scope

- Twitch chat bot runtime
- Role-based command permissions
- AutoMod baseline (spam/caps/links)
- Engagement commands
- Support commands for streamer + trusted chooms
- Navidrome integration for song links
- Music recognition flow (Shazam-style) with chat post

### Out of Scope (for now)

- Full dashboard UI
- Complex economy/gamification
- Multi-platform orchestration beyond Twitch + existing Telegram runtime

---

## 3) Persona Contract (Bot Voice)

- Style: direct, warm, cyberpunk, occasionally philosophical
- No toxic/mod-abusive style
- No repeated greeting spam in every message
- Keep answers concise in live chat

Response profile:

- `mod actions`: short, clear, neutral + flavor
- `engagement`: playful cyber-zen
- `support`: uplifting and respectful

---

## 4) Roles + Permissions

### Roles

- `owner` (streamer)
- `mod`
- `trusted_choom`
- `viewer`

### Permission Matrix

- `owner`: full control
- `mod`: moderation + utility + engagement
- `trusted_choom`: engagement + limited support commands
- `viewer`: public commands only

High-impact commands (`ban`, `timeout`, `purge`, mode toggles) are owner/mod only.

---

## 5) Command Set (MVP)

### A) Moderation

- `!timeout <user> [seconds] [reason]`
- `!ban <user> [reason]`
- `!purge <user>`
- `!slow <seconds>`
- `!followers <minutes>`
- `!subonly on|off`

### B) Engagement

- `!choom`
- `!godfather`
- `!zen`
- `!vibe`
- `!hype`
- `!lore`
- `!gig`
- `!phantom`

### C) Support

- `!support <user>`
- `!respect <user>`
- `!motivate <user>`
- `!so <user>`

### D) Music / Stream Utility

- `!nowplaying` -> current track from Navidrome
- `!songid` -> identify currently captured song (Shazam-style)
- `!lastsong` -> last recognized song + link

---

## 6) Navidrome Integration (Docker)

Goal: Bot can post current track and direct links in chat.

### Required Env

- `NAVIDROME_URL`
- `NAVIDROME_USER`
- `NAVIDROME_PASS`
- `NAVIDROME_PUBLIC_BASE` (public link base for chat)

### MVP Behavior

- Bot logs in to Navidrome API
- `!nowplaying` fetches active/current track state
- Bot posts:
  - `artist - title`
  - optional album
  - clickable track/album URL

Fallback:

- If no track active: short "nichts laeuft gerade" message
- If API fails: short error + no stacktrace in chat

---

## 7) Shazam-Style Music Recognition (Mod Tool)

Goal: mod/owner can detect track from stream audio and instantly post link.

### Detection Options

1. **Audd API / ACRCloud API** (highest reliability, requires API key)
2. **Local matcher (songrec-like)** where feasible

### Input Path

- Capture short audio sample from stream output (5-12 seconds)
- Send sample to recognizer
- Parse top match

### Chat Output Format

`Now spinning: <Artist> - <Title> | <ProviderLink>`

Provider links priority:

- Navidrome search link (if local library match)
- Spotify/YouTube fallback link from recognition metadata

### Anti-Spam Rule

- Cooldown per command (e.g. 30-60 sec)
- Do not repost same song repeatedly within cooldown window

---

## 8) Suggested Service Layout

Current repo is Telegram-first. For MVP Twitch rollout, keep concerns separate:

- `godfather-bot` (existing core)
- `twitch-bot` (new runtime process/module)
- `music-id-worker` (optional helper service)

This avoids breaking existing Telegram behavior while adding Twitch.

---

## 9) Docker Compose Extension (Target)

Add a dedicated twitch worker service and optional music-id worker.

```yaml
services:
  twitch-bot:
    build: .
    container_name: godfather-twitch
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - BOT_MODE=twitch
      - NAVIDROME_URL=${NAVIDROME_URL}
      - NAVIDROME_USER=${NAVIDROME_USER}
      - NAVIDROME_PASS=${NAVIDROME_PASS}
      - NAVIDROME_PUBLIC_BASE=${NAVIDROME_PUBLIC_BASE}
    volumes:
      - ./data:/app/data

  music-id-worker:
    build: .
    container_name: godfather-musicid
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - BOT_MODE=musicid
      - AUDD_API_KEY=${AUDD_API_KEY}
    volumes:
      - ./data:/app/data
```

---

## 10) Data Model (Minimal)

### trusted_users

- `user_id`
- `username`
- `role` (`trusted_choom`)
- `added_by`
- `created_at`

### moderation_events

- `id`
- `action` (`timeout|ban|purge|warn`)
- `target_user`
- `actor_user`
- `reason`
- `created_at`

### song_events

- `id`
- `source` (`navidrome|musicid`)
- `artist`
- `title`
- `link`
- `created_at`

---

## 11) Reliability + Safety Requirements

- Command cooldowns for spam-prone commands
- Role checks before all mod actions
- Never expose secrets/API keys in chat/logs
- Graceful fallback on provider outages
- Structured logs for moderation + song events

---

## 12) Delivery Phases

### Phase 1 - Core Twitch Mod + Engagement

- Twitch runtime
- role/permission system
- mod commands + cooldown
- core engagement commands

### Phase 2 - Navidrome + Now Playing

- Navidrome auth + fetch
- `!nowplaying` + link output
- song event logging

### Phase 3 - Music-ID + Auto Post

- `!songid` pipeline
- duplicate suppression/cooldown
- fallback links

---

## 13) Definition of Done (MVP)

- Bot runs stable in Twitch chat for at least one full stream session
- Owner/mod commands enforce permissions correctly
- `!nowplaying` returns valid track + link when music is active
- `!songid` identifies and posts track link with cooldown protection
- No secret leakage and no chat-spam regressions
