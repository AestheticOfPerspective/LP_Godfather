import json
import re

COMMAND_NAME = "brand_calibrate"
COMMAND_HELP = "Brand calibration — checks if content meets 24/30 threshold"
COMMAND_USAGE = "/brand_calibrate <text>"

DIMENSIONS = ["hook", "framing", "context", "brand", "privacy", "humor"]
DIMENSIONS_LABELS = {
    "hook": "🎣 Hook",
    "framing": "🖼️ Framing",
    "context": "📋 Context",
    "brand": "🏷️ Brand",
    "privacy": "🔒 Privacy",
    "humor": "😄 Humor",
}

SYSTEM_PROMPT = """You are a brand calibration expert. Evaluate the text against 6 dimensions, each scored 0-5.

Dimensions:
- hook: Does it grab attention immediately?
- framing: Is the message framed appropriately for the audience?
- context: Is enough context provided?
- brand: Does it align with brand identity and values?
- privacy: Does it respect privacy and avoid personal data leaks?
- humor: Is humor appropriate and effective?

Total score /30. PASS if >= 24.

Return ONLY valid JSON with no markdown formatting or code fences:
{"scores": {"hook": 0, "framing": 0, "context": 0, "brand": 0, "privacy": 0, "humor": 0}, "total": 0, "pass": false, "strengths": ["..."], "weaknesses": ["..."]}"""


async def execute(ollama, db, args, user_id=""):
    text = " ".join(args) if args else ""
    if not text:
        return "❌ <b>Usage:</b> /brand_calibrate &lt;text&gt;\n\nScored against: hook, framing, context, brand, privacy, humor.\nThreshold: 24/30 to pass."

    response = await ollama.chat(
        user_id=user_id or "cmd_brand",
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


def _format_result(result):
    scores = result.get("scores") or {}
    total = result.get("total", sum(scores.values()))
    passed = result.get("pass", total >= 24)
    strengths = result.get("strengths", [])
    weaknesses = result.get("weaknesses", [])

    lines = ["📊 <b>Brand Calibration</b>\n"]
    for dim in DIMENSIONS:
        score = scores.get(dim, 0)
        bar = "█" * score + "░" * (5 - score)
        label = DIMENSIONS_LABELS.get(dim, dim)
        lines.append(f"{label}: {score}/5 {bar}")

    lines.append(f"\n<b>Total:</b> {total}/30")
    if passed:
        lines.append("✅ <b>PASS</b> — Threshold met (≥24)")
    else:
        lines.append(f"❌ <b>FAIL</b> — {(30 - total)} points below threshold")

    if strengths:
        lines.append(f"\n<b>Strengths:</b>")
        for s in strengths:
            lines.append(f"  ✅ {s}")
    if weaknesses:
        lines.append(f"\n<b>Improvements:</b>")
        for w in weaknesses:
            lines.append(f"  ⚠️ {w}")

    return "\n".join(lines)
