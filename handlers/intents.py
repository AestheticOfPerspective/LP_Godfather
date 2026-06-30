"""Natural language intent router for Telegram.

Commands stay available as explicit fallbacks. This layer makes common chat
phrases feel natural: "merk dir ...", "clip das", "lern: ...", "push mich".
"""

from __future__ import annotations

import random
import re
from html import escape

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from handlers.chat_context import chat_title, chat_maturity_level, build_chat_context_text, format_chat_context
from handlers.hilfe import format_help_category, format_help_menu
from handlers.ai import ask_ai, get_user_persona, PERSONAS, telegram_safe_response
from handlers.skill_creator import format_skill_draft, generate_skill_draft
from handlers.stream import (
    format_follow,
    format_heute,
    format_recap,
    format_recap_saved,
    format_wann,
)
from utils.skill_store import create_skill, list_skills, read_skill
from utils.storage import db

_CONTINUE_SIGNALS = (
    "continue", "weiter", "mehr", "erzähl weiter", "erzaehl weiter",
    "go on", "und weiter", "und?", "und dann", "rest", "the rest",
    "fertig?", "bist du fertig", "vollständig", "vollstaendig",
    "vervollständig", "vervollstaendige", "mach weiter",
)
_MEMORY_ADD_RE = re.compile(
    r"(?:^|[\n.!?]\s*)(?:godfather[, ]+)?(?:merk dir|merke dir|speicher|notier|notiere|fuer spaeter|für später)(?:\s+(?:das\s+)?(?:über|ueber)\s+mich)?[:\s]+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TRAIN_RE = re.compile(
    r"(?:^|[\n.!?]\s*)(?:godfather[, ]+)?(?:lern|lerne|trainier dich|trainiere dich)[:\s]+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_RECAP_RE = re.compile(
    r"(?:^|[\n.!?]\s*)(?:godfather[, ]+)?(?:recap|stream recap|zusammenfassung)[:\s]+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_CHAT_CONTEXT_RE = re.compile(
    r"(?:^|[\n.!?]\s*|\b)(?:godfather[, ]+)?(?:lern diese gruppe|lerne diese gruppe|read the room|gruppen kontext|gruppenkontext)[:\s]+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

_SENSITIVE_HINTS = {
    "adresse",
    "anschrift",
    "passwort",
    "password",
    "token",
    "api key",
    "apikey",
    "secret",
    "bank",
    "iban",
    "krankheit",
    "diagnose",
}

_WIN_SIGNALS = (
    "geschafft",
    "done",
    "fertig",
    "win",
    "abgeliefert",
    "erledigt",
    "geschafft bro",
)
_STRESS_SIGNALS = (
    "bin kaputt",
    "ich bin kaputt",
    "stress",
    "ugh",
    "ich kann nicht mehr",
    "zu viel",
    "überfordert",
    "ueberfordert",
    "push mich",
    "motivier mich",
    "motivieren",
    "brauch energie",
    "brauche energie",
    "gib mir energie",
)
_CLIP_SIGNALS = (
    "clip das",
    "clippen",
    "clip würdig",
    "clipwuerdig",
    "clipwürdig",
    "das war ein clip",
    "das war sick",
)
_STREAM_STATUS_SIGNALS = (
    "wann stream",
    "wann bist du live",
    "heute live",
    "stream heute",
    "wann zockst",
)
_HELP_SIGNALS = (
    "was kannst du",
    "wie benutze ich dich",
    "wie kannst du",
    "wie können dich",
    "wie koennen dich",
    "hilfe",
    "help",
    "was kann ich sagen",
)
_CHAT_CONTEXT_SIGNALS = (
    "wo bist du gerade",
    "in welcher umgebung",
    "welcher gruppe",
    "chat kontext",
    "chat-kontext",
    "gruppen kontext",
    "gruppenkontext",
    "read the room",
    "reade mal",
    "lies dich ein",
    "einlesen",
    "einarbeiten",
    "einbringen",
    "wo du dich gerade befindest",
    "verlauf",
)
_ROOM_ONBOARDING_SIGNALS = (
    "einarbeiten",
    "einbringen",
    "mach mal dein job",
    "mach deinen job",
    "funktionierst du gerade net",
    "funktionierst gerade net",
    "woran es happert",
    "was ist mit dir los",
    "stell deine fragen",
    "stelle deine fragen",
)
_COMMUNITY_HELP_SIGNALS = (
    "community",
    "telegram gruppe",
    "gruppe",
    "edgerunner",
    "choom",
    "chooms",
    "weiterhelfen",
    "benutzen",
    "nutzen",
)
_CONTRIBUTION_SIGNALS = (
    "wie schaut es jetzt aus",
    "wie bist du jetzt drauf",
    "was kannst du jetzt",
    "was kannst du beitragen",
    "was kannst du in diese gruppe",
    "was kannst du in dieser gruppe",
    "bot-ecke",
    "nova bot",
    "nova",
    "zusammenarbeiten",
    "kooperieren",
    "collab",
)
_MEMORY_RECALL_SIGNALS = (
    "was weißt du über mich",
    "was weisst du ueber mich",
    "was weisst du über mich",
    "erinnerst du dich an mich",
    "was hast du dir gemerkt",
)
_SKILL_CREATION_SIGNALS = (
    "bau mir einen skill",
    "bau mir einen skill fuer",
    "erstell mir einen skill",
    "erstelle einen skill",
    "create a skill",
    "neuen skill",
    "skill erstellen",
)

_BUFFS = [
    "Nyx.exe: Preem work, Choom. Kleiner Win, echtes Momentum. Halt die Combo am Laufen.",
    "Nyx.exe: Buff applied. Du hast gerade geliefert. Jetzt nicht zerdenken, nächster sauberer Schritt.",
    "Nyx.exe: Tiny win logged. Genau so baut man einen Run: nicht perfekt, aber konsequent.",
    "Nyx.exe: Das System hat gezittert. Du bist noch online, noch scharf, noch im Spiel.",
]
_SUPPORTS = [
    "Nyx.exe: Kurz runtertakten, Choom. Ein Atemzug, ein Glas Wasser, ein nächster Schritt. Nicht der ganze Berg. Nur der nächste Griff.",
    "Nyx.exe: Secure Harbor aktiv. Du musst gerade nicht alles lösen. Sag mir den kleinsten Knoten, dann schneiden wir ihn sauber auf.",
    "Nyx.exe: Ich seh den Overload. Kein Drama. Drei Minuten Pause, dann nur eine Sache zurück ins Grid.",
    "Nyx.exe: Systemlast hoch, aber du bist kein kaputter Prozess. Du brauchst Scheduling, nicht Selbsthass.",
]


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def _username(user) -> str:
    if not user:
        return "unknown"
    return user.username or user.first_name or str(user.id)


def _target_text(update: Update, text: str) -> str:
    reply = update.message.reply_to_message if update.message else None
    if reply:
        reply_text = reply.text or reply.caption or ""
        if reply_text:
            return reply_text.strip()
    return text.strip()


def _looks_sensitive(text: str) -> bool:
    lower = text.lower()
    return any(hint in lower for hint in _SENSITIVE_HINTS)


def _format_community_help() -> str:
    return (
        "💀 GodFather im Live.Play-Chat\n\n"
        "Ich bin hier nicht als Command-Liste gedacht, sondern als Crew-Fixer. "
        "Sprich mich normal an, per Reply oder mit @Mention.\n\n"
        "So helfe ich hier konkret:\n"
        "• Memory: Sag „merk dir ...“, dann merke ich relevante Fakten über dich.\n"
        "• Stream-Utility: Sag „wann stream?“, „heute live?“ oder „clip das“.\n"
        "• Training: Admins können sagen „lern: Thema | Inhalt“, damit ich Community-Wissen behalte.\n"
        "• Nyx-Support: Sag „push mich kurz“, „bin überfordert“ oder „done“, dann kommt Momentum statt Bot-Gelaber.\n"
        "• Orientierung: Sag „was kannst du?“ oder „wie nutze ich dich?“, und ich zeige Beispiele.\n\n"
        "Kurz: weniger Befehle, mehr natürlich reden. Commands bleiben nur Fallback, Choom."
    )


def _format_room_read_response(chat, user) -> str:
    title = escape(chat_title(chat, user))
    return (
        "🌐 Room-Read Status\n\n"
        f"Ich bin gerade in: {title}\n\n"
        "Ehrlicher Stand, Choom: Ich kann nicht rückwirkend frei durch den Telegram-Verlauf scrollen wie ein Mensch mit Kaffeetasse und zu vielen Tabs. "
        "Ich sehe den aktuellen Kontext, Replies, Mentions und das, was wir als Gruppenkontext speichern.\n\n"
        "Damit ich mich hier gescheit einarbeite, gib mir bitte einmal:\n"
        "1. Wofür ist diese Gruppe oder dieses Thema da?\n"
        "2. Welche Art Hilfe erwartet die Crew von mir?\n"
        "3. Wie frech darf ich sein? FSK 12, 16, 18 oder 21?\n"
        "4. Was soll ich hier nie tun?\n\n"
        "Kurzform zum Speichern:\n"
        "lern diese Gruppe: Zweck | Bedürfnisse, Ton, Grenzen @meinGodFatherBot\n\n"
        "Telegram-Gruppen-Tipp: Schreib den Text zuerst und setz die Bot-Mention danach mittendrin oder ans Ende."
    )


def _format_bot_feedback_response() -> str:
    return (
        "Fairer Hit, Bro. Wenn du sagst 'Bratan, mach deinen Job gescheit', lese ich das ab jetzt als Bug-/UX-Feedback, nicht als Beef.\n\n"
        "Was gerade haperte:\n"
        "1. Ich hatte noch zu wenig gespeicherten Room-Kontext.\n"
        "2. Ich kann Telegram-Verlauf nicht magisch rückwirkend scannen.\n"
        "3. Mein Intent-Router war noch zu eng bei Formulierungen wie Chat-Kontext, reade mal, einarbeiten.\n\n"
        "Meine Fragen an dich:\n"
        "1. Was ist der höhere Zweck dieser Gruppe?\n"
        "2. Welche Rolle soll ich hier spielen: Mod, Fixer, Coach, Nyx-Support, Stream-Butler oder Chaos-Kobold mit Lizenz?\n"
        "3. Welche No-Gos gelten hier?\n"
        "4. Soll ich in dieser Gruppe standardmäßig FSK 18 fahren?"
    )


def _format_contribution_response(chat, user, text: str) -> str:
    title = escape(chat_title(chat, user))
    saved = db.get_chat_context(str(chat.id)) if chat else None
    purpose = "noch nicht gespeichert"
    needs = "noch nicht gespeichert"
    if saved:
        _, _, _, saved_purpose, saved_needs, _, _ = saved
        purpose = saved_purpose or purpose
        needs = saved_needs or needs

    wants_nova = "nova" in text.lower() or "chrispresent" in text.lower()
    nova_block = ""
    if wants_nova:
        nova_block = (
            "\n\nNova-Collab: Ja, sinnvoll. Nova klingt nach Vision/Barden-/Bild-/Resonanz-Output. "
            "Ich kann daneben den Fixer machen: Kontext strukturieren, Absichten klären, Prompts schärfen, Ergebnisse in Aufgaben/Recaps/Memory übersetzen. "
            "Wenn Nova zaubert, halte ich den Werkzeugkasten und beschrifte die Sicherungen, bevor der Flux-Kern wieder mit Glitzer um sich wirft."
        )

    return (
        "💀 Status: Ich bin jetzt eher Room-aware, Choom.\n\n"
        f"Ort: {title}\n"
        f"Zweck/Thema: {escape(purpose)}\n"
        f"Bedürfnisse/Ton: {escape(needs)}\n\n"
        "Was ich hier in der Bot-Ecke beitragen kann:\n"
        "• Bot-Tests in klare Fehlerbilder und nächste Patches übersetzen.\n"
        "• Feedback einsammeln, ohne beleidigte Lederjacke zu spielen.\n"
        "• Memory, Training, Stream-Utility und Recaps natürlich statt command-lastig nutzbar machen.\n"
        "• FSK-18 Live.Play Ton fahren: direkt, offen, Denglish, bisschen schwarzer Humor, aber mit Guardrails.\n"
        "• Zwischen Chaos-Idee und ausführbarer Aufgabe vermitteln.\n\n"
        "Kurz: Ich bin hier nicht der Alleinunterhalter. Ich bin der Fixer im Maschinenraum. Wenn etwas komisch reagiert, nenn mir den Satz und ich helfe beim Tuning."
        f"{nova_block}"
    )


async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return False
    if user.id in ADMIN_IDS:
        return True
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
    return False


async def handle_natural_intent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> bool:
    """Handle high-confidence natural intents.

    Returns True if the message was handled and should not fall through to AI.
    """
    msg = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat:
        return False

    raw = text.strip()
    lower = raw.lower()

    match = _MEMORY_ADD_RE.search(raw)
    if match:
        fact = match.group(1).strip()
        if not fact:
            return False
        if len(fact) > 500:
            await msg.reply_text("Memory zu lang, Choom. Maximal 500 Zeichen.")
            return True
        if _looks_sensitive(fact):
            await msg.reply_text(
                "Guardrail aktiv: Das sieht sensibel aus. Ich speichere sowas nicht automatisch."
            )
            return True
        if db.count_user_facts(str(user.id)) >= 50:
            await msg.reply_text("Memory voll: maximal 50 Fakten pro User. Lösche alte mit /forget.")
            return True
        fact_id = db.add_user_fact(str(user.id), fact)
        await msg.reply_text(
            f"🧠 Gemerkt. ID #{fact_id}\n{escape(fact)}",
            parse_mode=ParseMode.HTML,
        )
        return True

    if _contains_any(lower, _MEMORY_RECALL_SIGNALS):
        facts = db.get_user_facts(str(user.id))[:10]
        if not facts:
            await msg.reply_text("🧠 Noch nichts über dich gespeichert. Sag: merk dir ... @meinGodFatherBot")
            return True
        lines = ["🧠 Das habe ich mir über dich gemerkt:"]
        for fact_id, fact, _ in facts:
            lines.append(f"#{fact_id}: {escape(fact)}")
        await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return True

    match = _CHAT_CONTEXT_RE.search(raw)
    if match:
        if not await _is_admin(update, context):
            await msg.reply_text("Guardrail: Gruppenkontext setzen nur Admin/Owner, Choom.")
            return True
        if chat.type == ChatType.PRIVATE:
            await msg.reply_text("Das ist ein DM. Gruppenkontext gibt es hier nicht zu setzen.")
            return True
        body = match.group(1).strip()
        if "|" in body:
            purpose, needs = [part.strip() for part in body.split("|", 1)]
        else:
            purpose, needs = body, ""
        if not purpose:
            await msg.reply_text("Format: lern diese gruppe: Zweck | typische Bedürfnisse")
            return True
        db.upsert_chat_context(
            str(chat.id),
            chat.type,
            chat_title(chat, user),
            purpose[:1000],
            needs[:1000],
            str(user.id),
        )
        await msg.reply_text(
            "🌐 Room gelesen und gespeichert.\n"
            f"Gruppe: {escape(chat_title(chat, user))}\n"
            f"Zweck: {escape(purpose[:300])}",
            parse_mode=ParseMode.HTML,
        )
        return True

    if _contains_any(lower, _ROOM_ONBOARDING_SIGNALS):
        await msg.reply_text(_format_bot_feedback_response())
        return True

    if _contains_any(lower, _CONTRIBUTION_SIGNALS):
        await msg.reply_text(_format_contribution_response(chat, user, raw))
        return True

    if _contains_any(lower, _CHAT_CONTEXT_SIGNALS):
        if "verlauf" in lower or "reade" in lower or "einlesen" in lower or "einarbeiten" in lower:
            await msg.reply_text(_format_room_read_response(chat, user))
        else:
            await msg.reply_text(format_chat_context(chat, user), parse_mode=ParseMode.HTML)
        return True

    match = _TRAIN_RE.search(raw)
    if match:
        if not await _is_admin(update, context):
            await msg.reply_text("Guardrail: Training darf nur Admin/Owner, Choom.")
            return True
        body = match.group(1).strip()
        if "|" in body:
            topic, content = [part.strip() for part in body.split("|", 1)]
        elif "=" in body:
            topic, content = [part.strip() for part in body.split("=", 1)]
        else:
            await msg.reply_text("Training-Format: lern: Thema | Inhalt")
            return True
        if not topic or not content:
            await msg.reply_text("Training braucht Thema und Inhalt: lern: Thema | Inhalt")
            return True
        kid = db.add_knowledge(topic, content[:2000], "telegram-intent", str(user.id))
        await msg.reply_text(
            f"📚 Gelernt. ID #{kid}\nThema: {escape(topic)}",
            parse_mode=ParseMode.HTML,
        )
        return True

    if _contains_any(lower, _CLIP_SIGNALS):
        clip_text = _target_text(update, raw)
        clip_id = db.add_clip_submission(
            "telegram-intent",
            str(chat.id),
            str(user.id),
            _username(user),
            clip_text,
        )
        await msg.reply_text(f"🎬 Clip-Kandidat gespeichert. ID #{clip_id}")
        return True

    match = _RECAP_RE.search(raw)
    if match:
        if not await _is_admin(update, context):
            await msg.reply_text("Guardrail: Recaps setzen nur Admins.")
            return True
        body = match.group(1).strip()
        if not body:
            await msg.reply_text("Recap braucht Inhalt: recap: Kurzfassung des Streams")
            return True
        recap_id = db.add_stream_recap("telegram-intent", _username(user), body[:2000])
        await msg.reply_text(format_recap_saved(recap_id), parse_mode=ParseMode.HTML)
        return True

    if _contains_any(lower, _STREAM_STATUS_SIGNALS):
        if "heute" in lower:
            await msg.reply_text(format_heute(), parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text(format_wann(), parse_mode=ParseMode.HTML)
        return True

    if "follow" in lower or "twitch" in lower and "link" in lower:
        await msg.reply_text(format_follow(), parse_mode=ParseMode.HTML)
        return True

    if "recap" in lower and any(w in lower for w in ("letzte", "letzter", "zeig", "zeigen")):
        await msg.reply_text(format_recap(db.latest_stream_recap()), parse_mode=ParseMode.HTML)
        return True

    if _contains_any(lower, _HELP_SIGNALS):
        if _contains_any(lower, _COMMUNITY_HELP_SIGNALS):
            await msg.reply_text(_format_community_help())
        elif "memory" in lower or "merk" in lower:
            await msg.reply_text(format_help_category("memory"), parse_mode=ParseMode.HTML)
        elif "train" in lower or "lern" in lower:
            await msg.reply_text(format_help_category("training"), parse_mode=ParseMode.HTML)
        elif "stream" in lower or "clip" in lower:
            await msg.reply_text(format_help_category("stream"), parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text(format_help_menu(), parse_mode=ParseMode.HTML)
        return True

    if _contains_any(lower, _WIN_SIGNALS):
        await msg.reply_text(random.choice(_BUFFS))
        return True

    if _contains_any(lower, _STRESS_SIGNALS):
        await msg.reply_text(random.choice(_SUPPORTS))
        return True

    if _contains_any(lower, _CONTINUE_SIGNALS):
        await msg.reply_chat_action("typing")
        persona_key = get_user_persona(user.id)
        persona_name = PERSONAS[persona_key]["name"]
        maturity = chat_maturity_level(chat)
        extra = build_chat_context_text(chat, user)
        response = await ask_ai(
            "Fahre mit deiner letzten Antwort fort. Wiederhole nichts, mach genau da weiter wo du aufgehört hast.",
            user_id=user.id,
            persona_key=persona_key,
            extra_context=extra,
            is_group=chat.type in ("group", "supergroup"),
            fsk_level=maturity,
        )
        reply = f"{persona_name}:\n\n{telegram_safe_response(response)}"
        await msg.reply_text(reply, parse_mode=ParseMode.HTML)
        return True

    if _contains_any(lower, _SKILL_CREATION_SIGNALS):
        purpose = raw
        for prefix in _SKILL_CREATION_SIGNALS:
            idx = lower.find(prefix)
            if idx >= 0:
                after = raw[idx + len(prefix):].strip(" :.,;!?\n")
                if after:
                    purpose = after
                break

        await msg.reply_text("⏳ Generiere Skill-Entwurf...")
        extra = build_chat_context_text(chat, user)
        maturity = chat_maturity_level(chat)
        draft = await generate_skill_draft(
            purpose,
            ask_ai,
            user_id=user.id,
            extra_context=extra,
            is_group=chat.type in ("group", "supergroup"),
            fsk_level=maturity,
        )
        if not draft:
            await msg.reply_text("Konnte keinen Skill-Entwurf erstellen. Versuchs nochmal.")
            return True

        import re as _re
        name_match = _re.search(r"^#\s+(.+?)\s+Skill", draft, _re.MULTILINE)
        skill_name = name_match.group(1).strip().lower().replace(" ", "-") if name_match else "unnamed"
        skill_name = _re.sub(r"[^a-z0-9-]", "", skill_name) or "unnamed"

        description = ""
        desc_match = _re.search(r"^## Description\s*\n(.+)$", draft, _re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()

        if create_skill(skill_name, draft, description):
            await msg.reply_text(
                format_skill_draft(skill_name, description),
                parse_mode=ParseMode.HTML,
            )
        else:
            existing = read_skill(skill_name)
            if existing:
                await msg.reply_text(
                    f"Skill \"{escape(skill_name)}\" existiert bereits. "
                    "Loesche ihn zuerst mit /skills delete oder waehl einen anderen Namen.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await msg.reply_text(
                    "Konnte Skill nicht speichern. Pruef Logs.",
                    parse_mode=ParseMode.HTML,
                )
        return True

    return False
