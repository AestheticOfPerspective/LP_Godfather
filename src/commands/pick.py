import random
import re

COMMAND_NAME = "pick"
COMMAND_HELP = "Wähle zufällig aus Optionen"
COMMAND_USAGE = "/pick option1 | option2 | option3"


async def execute(ollama, db, args, user_id=""):
    text = " ".join(args) if args else ""
    if not text:
        return (
            "🎯 <b>Pick</b> — Usage:\n"
            "  /pick Pizza | Pasta | Sushi\n"
            "  /pick option A or option B\n"
            "  /pick this, that, other"
        )

    options = None
    for sep in ["|", " or ", " oder ", ", "]:
        parts = [p.strip() for p in re.split(re.escape(sep), text) if p.strip()]
        if len(parts) >= 2:
            options = parts
            break

    if not options:
        return "🎯 Gib mindestens 2 Optionen an, getrennt durch <code>|</code>, <code>oder</code> oder <code>,</code>"

    chosen = random.choice(options)
    return f"🎯 <b>Ich wähle:</b> {chosen}"
