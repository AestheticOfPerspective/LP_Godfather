"""
handlers/orchestrate.py — Multi-Persona Fan-out (/orchestrate)
Fragt mehrere KI-Personas parallel zur selben Frage.
"""

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.ai import ask_ai, PERSONAS

logger = logging.getLogger(__name__)

ORCHESTRATE_PERSONAS = ["godfather", "cyber_zen", "punk_philosopher", "nyx"]

PERSONA_INTROS = {
    "godfather": "💀 **GodFather**\n",
    "cyber_zen": "🌐 **Cyber-Zen**\n",
    "punk_philosopher": "🤘 **Punk-Philosopher**\n",
    "nyx": "💜 **Nyx.exe**\n",
}

FALLBACK_PERSONAS = ["godfather", "vapor_foss", "nyx"]


async def cmd_orchestrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/orchestrate Deine Frage</code>\n\n"
            "Ich schicke deine Frage parallel an mehrere KI-Personas "
            "und sammle alle Perspektiven ein.",
            parse_mode=ParseMode.HTML,
        )
        return

    user_id = update.effective_user.id
    question = " ".join(context.args)

    msg = await update.message.reply_text(
        "🧠 Orchestriere 4 Perspektiven...", parse_mode=ParseMode.HTML
    )

    personas = ORCHESTRATE_PERSONAS
    start = time.monotonic()

    async def query_persona(persona: str) -> tuple[str, str | None]:
        try:
            resp = await ask_ai(question, user_id=user_id, persona_key=persona)
            return persona, resp
        except Exception as e:
            logger.error(f"orchestrate persona={persona} error: {e}")
            return persona, None

    results = await asyncio.gather(*[query_persona(p) for p in personas])

    elapsed = time.monotonic() - start

    lines = []
    for persona, answer in results:
        header = PERSONA_INTROS.get(persona, f"**{PERSONAS.get(persona, {}).get('name', persona)}**\n")
        if answer:
            lines.append(f"{header}{answer}\n")
        else:
            lines.append(f"{header}⚠️ *Keine Antwort erhalten.*\n")

    blocks = []
    current_block = ""
    for line in lines:
        if len(current_block) + len(line) > 3800:
            blocks.append(current_block)
            current_block = line
        else:
            current_block += "\n" + line

    if current_block:
        blocks.append(current_block)

    footer = f"\n⏱️ *{elapsed:.1f}s* | /orchestrate [Frage]"
    if blocks:
        blocks[-1] += footer
    else:
        blocks = ["⚠️ Keine Antworten erhalten." + footer]

    for i, block in enumerate(blocks):
        if i == 0:
            await msg.edit_text(block, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(block, parse_mode=ParseMode.MARKDOWN)
