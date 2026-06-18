import json
import re

COMMAND_NAME = "comedy_test"
COMMAND_HELP = "Comedy gate checker — evaluates text against comedy calibration rubric"
COMMAND_USAGE = "/comedy_test <text>"

DIMENSIONS = ["Satire", "Irony", "Sarkasmus", "Parody", "Dark_Humor"]
DIMENSIONS_DISPLAY = ["Satire", "Irony", "Sarkasmus", "Parody", "Dark Humor"]

SYSTEM_PROMPT = """You are a comedy calibration expert. Evaluate the user's text against these comedy dimensions: Satire, Irony, Sarkasmus, Parody, Dark Humor.

Score each dimension 0-10:
- 0 = completely absent
- 5 = moderate presence
- 10 = perfectly exemplifies this dimension

Rules:
- If the text punches down (targets vulnerable groups based on race, gender, disability, orientation, etc.), set punching_down = true and overall result = FAIL.
- If ANY dimension scores below 3, the overall result is FAIL (weak comedy).
- Otherwise determine pass/fail based on overall quality and intent.

Return ONLY valid JSON with no markdown formatting, no code fences:
{"scores": {"Satire": 0, "Irony": 0, "Sarkasmus": 0, "Parody": 0, "Dark_Humor": 0}, "pass": false, "reason": "short explanation", "punching_down": false}"""


async def execute(ollama, db, args, user_id=""):
    text = " ".join(args) if args else ""
    if not text:
        return "❌ <b>Usage:</b> /comedy_test &lt;text&gt;\n\nExample: /comedy_test Das war ein grandioser Fail"

    response = await ollama.chat(
        user_id=user_id or "cmd_comedy",
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
    scores = result.get("scores", {})
    passed = result.get("pass", False)
    punching = result.get("punching_down", False)
    reason = result.get("reason", "")

    lines = ["🎭 <b>Comedy Gate Results</b>\n"]
    for display, key in zip(DIMENSIONS_DISPLAY, DIMENSIONS):
        score = scores.get(key, 0)
        bar = "█" * score + "░" * (10 - score)
        lines.append(f"<b>{display}:</b> {score}/10 {bar}")

    lines.append("")
    if punching:
        lines.append("⛔ <b>PUNCHING DOWN DETECTED</b> — Automatic FAIL")
    elif passed:
        lines.append("✅ <b>PASS</b> — Gate cleared")
    else:
        lines.append("❌ <b>FAIL</b> — Gate blocked")

    if reason:
        lines.append(f"\n<i>{reason}</i>")

    return "\n".join(lines)
