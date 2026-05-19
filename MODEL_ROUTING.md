# Model Routing Matrix (Nexus + Foss)

Practical model selection guide for LP_Godfather.

Goal: keep coding flow fast, keep quality high, and use heavier models only where they pay off.

## Default Routing

- Default everyday model: `gemini-2.5-flash`
- Fast draft/iteration model: `gemini-2.5-flash-lite`
- Deep strategy and synthesis: `gemini-3-flash-preview`
- Local style and private drafts: `gemma-4-31b-it` (fallback `gemma-4-26b-a4b-it`)

## Task -> Model Map

| Task type | Recommended model | Why |
|---|---|---|
| Small edits, command fixes, tiny refactors | `gemini-2.5-flash-lite` | Very fast turnaround |
| Normal feature work in handlers/utils | `gemini-2.5-flash` | Best speed/quality balance |
| Debugging multi-file runtime bugs | `gemini-2.5-flash` | Strong code reasoning with stable latency |
| Architecture decisions, repo strategy, release planning | `gemini-3-flash-preview` | Better long-horizon synthesis |
| Marketing voice, persona tuning, artist copy drafts | `gemma-4-31b-it` | Strong style consistency and tone control |
| Sensitive local drafting where cloud use is undesired | `gemma-4-31b-it` | Local-first privacy posture |
| Quick variant generation (many options) | `gemini-3.1-flash-lite-preview` | Good idea throughput |

## LP_Godfather Workflow Presets

1. Build loop (daily)
   - Start with `gemini-2.5-flash`
   - Drop to `gemini-2.5-flash-lite` for repetitive polish
   - Escalate to `gemini-3-flash-preview` if design tradeoffs appear

2. Release loop (showtime)
   - Use `gemini-3-flash-preview` for changelog/release framing
   - Run `bash scripts/preflight-release.sh`
   - Use `gemini-2.5-flash` for last-minute code fixes

3. Persona/content loop (artist mode)
   - Draft with `gemma-4-31b-it`
   - Tighten implementation text with `gemini-2.5-flash`

## Escalation Rules

- If answer quality is too shallow: move `lite -> flash -> 3-flash-preview`.
- If latency is too high for the current step: move down one tier.
- If task is security-sensitive and local model quality is sufficient: prefer `gemma`.

## Quality Guardrails (Always)

- Verify code with: `python -m compileall -q .`
- Keep secrets out of tracked files.
- For public pushes, run: `bash scripts/preflight-release.sh`
- Use CodeRabbit as final review layer before merge.

## Fast Decision Cheat Sheet

- Need speed now? -> `gemini-2.5-flash-lite`
- Need reliable coding output? -> `gemini-2.5-flash`
- Need deep strategic answer? -> `gemini-3-flash-preview`
- Need rich style/persona voice? -> `gemma-4-31b-it`

Build wild. Ship stable.
