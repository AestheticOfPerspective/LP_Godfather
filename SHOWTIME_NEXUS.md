# SHOWTIME Nexus Blueprint

Studio + Stage workflow for LP_Godfather.

- Studio = private build space (GitLab, source of truth)
- Stage = public showcase (GitHub, curated mirror)
- Nexus = clear rules that keep both in sync without leaking secrets

## 1) Repo Model

- GitLab private repo is canonical: full product, internal experiments, protected main.
- GitHub public repo is curated: public-safe code, docs, and releases only.
- Never treat GitHub as secret-bearing runtime source.

Suggested names:

- GitLab: `AestheticOfPerspective/LP_Godfather`
- GitHub: `AestheticOfPerspective/LP_Godfather`

## 2) Branch + Release Rules

- `main` is protected on both platforms.
- Feature branches: `feat/nexus-*`, `feat/foss-*`, `fix/*`, `docs/*`.
- Merge only when CI is green and review is done.
- Public release is tag-driven: `vX.Y.Z`.

## 3) Quality Gates

Minimum required before merge:

1. `python -m compileall -q .`
2. Startup smoke (local) `python bot.py`
3. Secret safety (`.env` ignored, `.env.example` placeholders only)
4. Code review pass (human + optional CodeRabbit)

## 4) Dual-Remote Setup

Use GitLab as canonical remote and GitHub as mirror target.

```bash
# from repo root
bash scripts/setup-dual-remote.sh https://github.com/AestheticOfPerspective/LP_Godfather.git
```

This script:

- renames `origin` -> `gitlab` (if needed)
- adds/updates `github` remote
- prints remotes for verification

## 5) Push Strategies

Private daily work (Studio):

```bash
git push gitlab main
```

Showtime push (Studio + Stage):

```bash
bash scripts/push-all.sh main
```

Tag release to both:

```bash
git tag v0.1.0
git push gitlab v0.1.0
git push github v0.1.0
```

## 6) Public-Safe Checklist

Before any GitHub push:

- no `.env`, tokens, passwords, dumps, or private chat data
- no `data/` runtime state
- no internal-only docs that expose strategy/secrets
- README, `.env.example`, and setup commands are accurate
- CI passes locally and in GitLab

Run quick guard:

```bash
bash scripts/preflight-release.sh
```

## 7) Team Split (Duo)

- Foss (Artist/Product): personas, copy tone, UX moments, community-facing features.
- Nexus (Engineering): runtime stability, CI/CD, infra guardrails, security checks.
- Shared definition of done: stable behavior + safe public posture + clear docs.

## 8) Operating Principle

Build wild in Studio.
Ship sharp on Stage.
Keep the bridge explicit.
