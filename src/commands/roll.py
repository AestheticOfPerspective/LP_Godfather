import random
import re

COMMAND_NAME = "roll"
COMMAND_HELP = "Würfle XdY oder coinflip"
COMMAND_USAGE = "/roll [XdY | coin]"

COIN_ART = {
    "heads": "🪙 **Kopf**\n\n```\n   _______\n  /       /|\n /  ☠️   / |\n/_______/  |\n|  ☠️   |  |\n|  ☠️   | /\n|_______|/\n```",
    "tails": "🪙 **Zahl**\n\n```\n   _______\n  /       /|\n /  1€   / |\n/_______/  |\n|  1€   |  |\n|  1€   | /\n|_______|/\n```",
}

def _roll_dice(count: int, sides: int) -> tuple[list[int], int]:
    results = [random.randint(1, sides) for _ in range(count)]
    return results, sum(results)


async def execute(ollama, db, args, user_id=""):
    expr = " ".join(args).strip().lower() if args else ""

    if not expr or expr == "coin" or expr == "coinflip" or expr == "flip":
        result = random.choice(["heads", "tails"])
        return f"🪙 <b>Coin Flip:</b> {result}"

    match = re.match(r"^(\d+)?d(\d+)([+-]\d+)?$", expr.replace(" ", ""))
    if not match:
        return (
            "🎲 <b>Roll</b> — Usage:\n"
            "  /roll 2d6  — zwei 6-seitige Würfel\n"
            "  /roll d20  — ein 20-seitiger Würfel\n"
            "  /roll 3d8+2  — drei 8-seitige +2\n"
            "  /roll coin  — Münzwurf\n"
            "  /roll       — Münzwurf"
        )

    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    if count < 1 or count > 100:
        return "❌ Anzahl muss zwischen 1 und 100 liegen."
    if sides < 2 or sides > 1000:
        return "❌ Seitenzahl muss zwischen 2 und 1000 liegen."

    results, total = _roll_dice(count, sides)
    total += modifier

    parts = []
    if count <= 20:
        dice_str = ", ".join(str(r) for r in results)
        parts.append(f"🎲 <b>{count}d{sides}:</b> {dice_str}")
    else:
        parts.append(f"🎲 <b>{count}d{sides}:</b> {total - modifier} (Summe)")

    if modifier:
        sign = "+" if modifier > 0 else ""
        parts.append(f"Modifikator: {sign}{modifier}")

    parts.append(f"<b>Total:</b> {total}")

    if count == 1 and sides == 20:
        if results[0] == 20:
            parts.append("\n🔥 <b>NAT 20!</b> Kritischer Erfolg!")
        elif results[0] == 1:
            parts.append("\n💀 <b>NAT 1!</b> Kritischer Fail!")

    return "\n".join(parts)
