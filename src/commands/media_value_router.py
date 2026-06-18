import json
import re

COMMAND_NAME = "media_value_router"
COMMAND_HELP = "Routes content to the right brand (JutsuGaming, AestheticOfPerspective, LivePlayTV, Fossnomade)"
COMMAND_USAGE = "/media_value_router <text>"

BRANDS = {
    "jutsu_gaming": {
        "label": "JutsuGaming",
        "emoji": "🎮",
        "description": "Gaming content, anime, manga, game reviews, Let's Plays, streaming, e-sports, fighting games, Naruto, Jujutsu Kaisen, gaming culture",
    },
    "aesthetic_of_perspective": {
        "label": "AestheticOfPerspective",
        "emoji": "🎨",
        "description": "Art, photography, visual essays, creative theory, design thinking, aesthetics, visual philosophy, perspective, composition, color theory",
    },
    "liveplay_tv": {
        "label": "LivePlayTV",
        "emoji": "📺",
        "description": "Live streaming, VODs, community streams, interactive content, live events, multi-platform broadcasting, chat interaction, Live.Play ecosystem",
    },
    "fossnomade": {
        "label": "Fossnomade",
        "emoji": "🐧",
        "description": "Open source, FOSS, Linux, privacy, self-hosting, DevOps, infrastructure, tech tutorials, command-line, server administration, homelab",
    },
}

SYSTEM_PROMPT = """You are a media value router. Analyze the text and route it to the most appropriate brand.

Brands:
1. JutsuGaming (🎮) — Gaming content, anime, manga, game reviews, Let's Plays, streaming, e-sports, fighting games, Naruto, Jujutsu Kaisen, gaming culture
2. AestheticOfPerspective (🎨) — Art, photography, visual essays, creative theory, design thinking, aesthetics, visual philosophy, perspective, composition, color theory
3. LivePlayTV (📺) — Live streaming, VODs, community streams, interactive content, live events, multi-platform broadcasting, chat interaction, Live.Play ecosystem
4. Fossnomade (🐧) — Open source, FOSS, Linux, privacy, self-hosting, DevOps, infrastructure, tech tutorials, command-line, server administration, homelab

For each brand, score relevance 0-10. The highest score wins.
If no brand scores above 3, route to the best fit anyway.

Return ONLY valid JSON with no markdown formatting or code fences:
{"scores": {"jutsu_gaming": 0, "aesthetic_of_perspective": 0, "liveplay_tv": 0, "fossnomade": 0}, "winner": "jutsu_gaming", "reason": "explanation", "content_type": "game review", "confidence": "high"}

confidence: "high" (score gap > 3), "medium" (gap 1-3), "low" (tie or gap < 1)."""


async def execute(ollama, db, args, user_id=""):
    text = " ".join(args) if args else ""
    if not text:
        lines = ["📡 <b>Media Value Router</b> — Usage:\n/media_value_router &lt;text&gt;\n\nRoutes content to:"]
        for key, brand in BRANDS.items():
            lines.append(f"  {brand['emoji']} <b>{brand['label']}</b> — {brand['description']}")
        return "\n".join(lines)

    response = await ollama.chat(
        user_id=user_id or "cmd_router",
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
    winner_key = result.get("winner", "")
    reason = result.get("reason", "")
    content_type = result.get("content_type", "")
    confidence = result.get("confidence", "low")

    conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")

    winner_brand = BRANDS.get(winner_key, {})
    winner_label = winner_brand.get("label", winner_key)
    winner_emoji = winner_brand.get("emoji", "📡")

    lines = [
        f"📡 <b>Media Value Router</b>\n",
        f"{winner_emoji} <b>Route to: {winner_label}</b>\n",
        f"<b>Content Type:</b> {content_type}" if content_type else "",
        f"<b>Confidence:</b> {conf_icon} {confidence}\n",
    ]
    lines = [l for l in lines if l]

    lines.append("<b>Brand Scores:</b>")
    for key, brand in BRANDS.items():
        score = scores.get(key, 0)
        bar = "█" * score + "░" * (10 - score)
        marker = " ←" if key == winner_key else ""
        lines.append(f"  {brand['emoji']} <b>{brand['label']}:</b> {score}/10 {bar}{marker}")

    if reason:
        lines.append(f"\n<b>Why:</b>\n<i>{reason}</i>")

    return "\n".join(lines)
