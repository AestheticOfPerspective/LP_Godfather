import json
import re

COMMAND_NAME = "risk_mirror"
COMMAND_HELP = "Reviews automation/MCP/script plans for safety, secrets, overreach, operational risk"
COMMAND_USAGE = "/risk_mirror <plan description>"

SYSTEM_PROMPT = """You are a risk mirror agent. Review the user's plan (automation, MCP, script, or deployment) for risks.

Evaluate these categories (each 0-10, higher = more risk):
- secrets_exposure: Could this leak credentials, tokens, API keys, or .env files?
- operational_blast_radius: How much damage if this goes wrong? (data loss, downtime, corruption)
- privilege_overreach: Does it ask for more permissions than needed? Root/admin access?
- dependency_risk: Fragile external dependencies, network calls, unvalidated inputs?
- idempotency_fail: If run twice, could it cause problems?

Also flag any specific concerns.

Return ONLY valid JSON with no markdown formatting or code fences:
{"scores": {"secrets_exposure": 0, "operational_blast_radius": 0, "privilege_overreach": 0, "dependency_risk": 0, "idempotency_fail": 0}, "overall_risk": "low", "flags": [], "recommendation": "..."}

overall_risk: "low" (0-15), "medium" (15-30), "high" (30-50).
flags: array of specific concerns.
recommendation: actionable advice."""


async def execute(ollama, db, args, user_id=""):
    text = " ".join(args) if args else ""
    if not text:
        return "⚠️ <b>Risk Mirror</b> — Usage:\n/risk_mirror &lt;plan description&gt;\n\nReviews automation/MCP/script plans for:\n• Secrets exposure 🔑\n• Blast radius 💥\n• Privilege overreach 👑\n• Dependency risk 🔗\n• Idempotency 🔄"

    response = await ollama.chat(
        user_id=user_id or "cmd_risk",
        user_message=text,
        system_prompt=SYSTEM_PROMPT,
    )

    if not response.success:
        return f"❌ Ollama error: {response.content}"

    result = _parse_json(response.content)
    if result and "scores" in result:
        return _format_result(result)
    return response.content


def _parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


RISK_CATS = {
    "secrets_exposure": ("🔑 Secrets Exposure", "Could leak credentials"),
    "operational_blast_radius": ("💥 Blast Radius", "Damage if it goes wrong"),
    "privilege_overreach": ("👑 Privilege Overreach", "Excessive permissions"),
    "dependency_risk": ("🔗 Dependency Risk", "External fragility"),
    "idempotency_fail": ("🔄 Idempotency", "Re-run safety"),
}


def _format_result(result):
    scores = result.get("scores") or {}
    overall = result.get("overall_risk", "unknown")
    flags = result.get("flags", [])
    recommendation = result.get("recommendation", "")

    total = sum(scores.values())

    if overall == "high":
        icon = "🔴"
    elif overall == "medium":
        icon = "🟡"
    else:
        icon = "🟢"

    lines = [f"{icon} <b>Risk Mirror — {overall.upper()} Risk</b>\n"]
    lines.append(f"<b>Combined Score:</b> {total}/50\n")

    for key, (label, desc) in RISK_CATS.items():
        score = scores.get(key, 0)
        bar = "█" * score + "░" * (10 - score)
        lines.append(f"{label}: {score}/10 {bar}")

    if flags:
        lines.append(f"\n<b>Flags:</b>")
        for f in flags:
            lines.append(f"  ⚠️ {f}")

    if recommendation:
        lines.append(f"\n<b>Recommendation:</b>\n<i>{recommendation}</i>")

    return "\n".join(lines)
