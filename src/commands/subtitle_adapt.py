import json
import re

COMMAND_NAME = "subtitle_adapt"
COMMAND_HELP = "Suggests DE/EN/RU subtitle adaptations — translates comedic intent not literal words"
COMMAND_USAGE = "/subtitle_adapt <de|en|ru> <text>"

SYSTEM_PROMPT = """You are a cultural adaptation expert for subtitles. The user will provide a target language (de, en, or ru) and source text.

Your job: Adapt the text for subtitles in the target language while PRESERVING the comedic intent, tone, cultural references, and emotional impact — NOT translating literally.

For each adaptation, provide:
- adapted_text: The adapted subtitle text in target language
- intent_preserved: What comedic intent was kept (e.g., "sarcastic dismissal", "absurd comparison")
- cultural_notes: If references were localized, explain why
- difficulty: "easy", "medium", "hard"

If the text contains wordplay, puns, or culture-specific humor that can't be directly adapted, note this and provide the best approximation.

Return ONLY valid JSON with no markdown formatting or code fences:
{"target_language": "de", "original_text": "...", "adapted_text": "...", "intent_preserved": "...", "cultural_notes": "...", "difficulty": "medium"}"""

LANGUAGES = {"de": "Deutsch", "en": "English", "ru": "Русский"}


async def execute(ollama, db, args, user_id=""):
    if not args or len(args) < 2:
        return "🌐 <b>Subtitle Adapt</b> — Usage:\n/subtitle_adapt &lt;de|en|ru&gt; &lt;text&gt;\n\nAdapts comedic intent (not literal words) for target language."

    target = args[0].lower()
    if target not in LANGUAGES:
        available = ", ".join(LANGUAGES.keys())
        return f"❌ Unsupported language: <code>{target}</code>\nSupported: {available}"

    text = " ".join(args[1:])

    response = await ollama.chat(
        user_id=user_id or "cmd_subtitles",
        user_message=f"Target language: {target} ({LANGUAGES[target]})\n\nText to adapt:\n{text}",
        system_prompt=SYSTEM_PROMPT,
    )

    if not response.success:
        return f"❌ Ollama error: {response.content}"

    result = _parse_json(response.content)
    if result and "adapted_text" in result:
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
    target = result.get("target_language", "?")
    original = result.get("original_text", "")
    adapted = result.get("adapted_text", "")
    intent = result.get("intent_preserved", "")
    notes = result.get("cultural_notes", "")
    difficulty = result.get("difficulty", "unknown")

    diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "⚪")

    lines = [
        f"🌐 <b>Subtitle Adaptation</b> → {LANGUAGES.get(target, target.upper())}\n",
        f"<b>Difficulty:</b> {diff_icon} {difficulty}\n",
    ]

    if original:
        lines.append(f"<b>Original:</b>\n{original}\n")

    if adapted:
        lines.append(f"<b>Adapted:</b>\n{adapted}\n")

    if intent:
        lines.append(f"<b>Intent Preserved:</b> {intent}")

    if notes:
        lines.append(f"\n<b>Cultural Notes:</b>\n<i>{notes}</i>")

    return "\n".join(lines)
