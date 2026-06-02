"""handlers/skill_creator.py — Skill creation commands and intents.

Commands:
  /skills                 — List all skills
  /skills show <name>     — Show a skill's SKILL.md
  /skills activate <name> — Activate a draft skill (admin)
  /skills delete <name>   — Delete a skill (admin)

Natural intent:
  "bau mir einen Skill fuer <purpose>" — generates a skill draft via AI
"""

from __future__ import annotations

import logging
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from utils.skill_store import (
    activate_skill,
    create_skill,
    delete_skill,
    list_skills,
    read_skill,
    skill_help_text,
)

logger = logging.getLogger(__name__)

_SKILL_TEMPLATE = """# {name} Skill

## Description
{description}

## When to Use
{when}

## Signals
{signals}

## Procedure
{procedure}

## Tone
{tone}

## Guardrails
{guardrails}

## Examples
- Gut: {example_good}
- Schlecht: {example_bad}
"""


async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    args = context.args or []

    if not args:
        await update.message.reply_text(
            skill_help_text(), parse_mode=ParseMode.HTML
        )
        return

    sub = args[0].lower()

    if sub == "show" and len(args) >= 2:
        name = args[1].lower()
        content = read_skill(name)
        if not content:
            await update.message.reply_text(
                '❌ Skill "%s" nicht gefunden.' % escape(name),
                parse_mode=ParseMode.HTML,
            )
            return
        preview = content[:1500]
        await update.message.reply_text(
            f"<b>{escape(name)}</b>\n\n<pre>{escape(preview)}</pre>",
            parse_mode=ParseMode.HTML,
        )
        return

    if sub == "activate" and len(args) >= 2:
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("🚫 Nur Admins koennen Skills aktivieren.")
            return
        name = args[1].lower()
        if activate_skill(name):
            await update.message.reply_text(
                '✅ Skill "%s" aktiviert!' % escape(name),
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                '❌ Skill "%s" nicht gefunden oder bereits aktiv.' % escape(name),
                parse_mode=ParseMode.HTML,
            )
        return

    if sub == "delete" and len(args) >= 2:
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("🚫 Nur Admins koennen Skills loeschen.")
            return
        name = args[1].lower()
        if delete_skill(name):
            await update.message.reply_text(
                '🗑️ Skill "%s" geloescht.' % escape(name),
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                '❌ Skill "%s" nicht gefunden.' % escape(name),
                parse_mode=ParseMode.HTML,
            )
        return

    await update.message.reply_text(
        "❓ Nutzung: /skills, /skills show &lt;name&gt;, /skills activate &lt;name&gt;, /skills delete &lt;name&gt;",
        parse_mode=ParseMode.HTML,
    )


def format_skill_draft(name: str, description: str) -> str:
    return (
        f"📝 <b>Skill-Entwurf: {escape(name)}</b>\n\n"
        f"{escape(description)}\n\n"
        f"Admin muss aktivieren: <code>/skills activate {escape(name)}</code>"
    )


async def generate_skill_draft(
    purpose: str,
    ask_ai_func,
    user_id: int = 0,
    extra_context: str = "",
    is_group: bool = True,
    fsk_level: int = 12,
) -> str | None:
    prompt = (
        "Erstelle einen Skill fuer GodFather (den Life.Play Community-Bot) "
        f"mit folgendem Zweck:\n\n{purpose}\n\n"
        "Format (genau dieses Schema einhalten):\n"
        "Name: <skill-name>\n"
        "Description: <ein-satz-beschreibung-max-100-zeichen>\n"
        "When: <wann-einsetzen-ein-zwei-saetze>\n"
        "Signals: <komma-separierte-keywords-die-diesen-skill-triggern>\n"
        "Procedure: <schritt-1-schritt-2-schritt-3>\n"
        "Tone: <ton-angabe-ein-satz>\n"
        "Guardrails: <was-nicht-tun-ein-satz>\n"
        "ExampleGood: <gutes-beispiel>\n"
        "ExampleBad: <schlechtes-beispiel>\n\n"
        "Nur das Format ausgeben, keine Einleitung, kein Summary."
    )
    response = await ask_ai_func(
        prompt,
        user_id=user_id,
        extra_context=extra_context,
        is_group=is_group,
        fsk_level=fsk_level,
    )
    if not response:
        return None
    return _parse_draft(response, purpose)


def _parse_draft(raw: str, fallback_name: str) -> str | None:
    """Parse AI response into SKILL.md content. Returns None if parsing fails."""
    lines = raw.strip().split("\n")
    fields = {
        "name": fallback_name,
        "description": "",
        "when": "",
        "signals": "",
        "procedure": "",
        "tone": "",
        "guardrails": "",
        "example_good": "",
        "example_bad": "",
    }
    # Aliases for keys the AI might output (e.g. ExampleGood -> example_good)
    key_aliases = {
        "name": ("name",),
        "description": ("description", "desc"),
        "when": ("when",),
        "signals": ("signals", "signal", "keywords", "triggers"),
        "procedure": ("procedure", "steps", "how"),
        "tone": ("tone", "voice", "style"),
        "guardrails": ("guardrails", "guardrail", "pitfalls", "no-go"),
        "example_good": ("example_good", "examplegood", "good_example", "examplegood:"),
        "example_bad": ("example_bad", "examplebad", "bad_example", "examplebad:"),
    }
    # Build reverse alias map: lowercase alias -> canonical key
    alias_map = {}
    for canonical, aliases in key_aliases.items():
        for alias in aliases:
            alias_map[alias.lower()] = canonical

    current_key = None
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Check if line starts with a known key
        matched = False
        for alias in alias_map:
            if line_stripped.lower().startswith(f"{alias}:"):
                canonical = alias_map[alias]
                current_key = canonical
                value = line_stripped[len(alias) + 1:].strip()
                if value:
                    fields[canonical] = value
                matched = True
                break
            if line_stripped.lower().startswith(f"{alias}="):
                canonical = alias_map[alias]
                current_key = canonical
                value = line_stripped.split("=", 1)[1].strip()
                if value:
                    fields[canonical] = value
                matched = True
                break
        if matched:
            continue

        # Continuation of current field
        if current_key and not line_stripped.startswith("```"):
            continuation = fields.get(current_key, "")
            if continuation:
                fields[current_key] = continuation + " " + line_stripped

    safe_name = fields["name"].lower().replace(" ", "-")
    import re
    safe_name = re.sub(r"[^a-z0-9-]", "", safe_name) or fallback_name.lower().replace(" ", "-")

    return _SKILL_TEMPLATE.format(
        name=fields["name"],
        description=fields["description"] or "Noch keine Beschreibung.",
        when=fields["when"] or "Noch keine Verwendung angegeben.",
        signals=fields["signals"] or "noch-keine-signals",
        procedure=fields["procedure"] or "Noch keine Schritte definiert.",
        tone=fields["tone"] or "GodFather-Standard-Ton.",
        guardrails=fields["guardrails"] or "Standard-Guardrails.",
        example_good=fields["example_good"] or "Noch kein Beispiel.",
        example_bad=fields["example_bad"] or "Noch kein Beispiel.",
    )
