import random

COMMAND_NAME = "8ball"
COMMAND_HELP = "Magic 8-Ball — Frage etwas"
COMMAND_USAGE = "/8ball <frage>"

ANSWERS_DE = [
    "🎱 Ja, definitiv.",
    "🎱 Es ist sicher so.",
    "🎱 Ohne Zweifel.",
    "🎱 Ja — aber sei bereit.",
    "🎱 Zeichen deuten auf Ja hin.",
    "🎱 Frag später nochmal.",
    "🎱 Sag ich dir jetzt nicht.",
    "🎱 Konzentrier dich und frag nochmal.",
    "🎱 Lieber nicht.",
    "🎱 Meine Quellen sagen Nein.",
    "🎱 Sehr unwahrscheinlich.",
    "🎱 Absolut nicht.",
    "🎱 Das ist nicht klar — vertrau deinem Bauch.",
    "🎱 Die Sterne sagen ja, der Verstand sagt nein.",
    "🎱 Nur wenn du wirklich bereit bist.",
    "🎱 CHOOOOOM — DO IT!",
    "🎱 Nova-Vibes sagen: alles fügt sich.",
    "🎱 BAKI sagt: PUSH HARDER.",
    "🎱 CYBER-ZEN sagt: atme erstmal durch.",
    "🎱 MONKEY-MIND sagt: WARUM NICHT?",
]


async def execute(ollama, db, args, user_id=""):
    question = " ".join(args) if args else ""
    if not question:
        return (
            "🔮 <b>Magic 8-Ball</b>\n"
            "Stell mir eine Frage:\n"
            "  /8ball Soll ich Pizza bestellen?\n"
            "  /8ball Wird heute ein guter Tag?"
        )
    answer = random.choice(ANSWERS_DE)
    return f"🔮 <b>Frage:</b> {question}\n{answer}"
