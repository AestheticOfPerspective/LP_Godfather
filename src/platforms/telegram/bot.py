from __future__ import annotations
import os
import re
import time
import asyncio
import logging
import html
import platform as plat
from typing import Optional
from pathlib import Path

from telegram import Update, BotCommand
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters,
)

from src.core.persona_engine import PersonaFlowEngine, PersonaName
from src.ai.ollama_client import OllamaClient
from src.storage.database import Database
from src.commands import get_registry
from .interviewer_agents import (
    all_interviewer_prompts, resolve_alias,
    hard_mode_sequence, interviewer_prompt,
    get_prompts,
)

logger = logging.getLogger(__name__)

ALLOWED_HTML_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "strong", "em", "span", "br"}

SAFE_URL_SCHEMES = {"http", "https", "mailto", "tel"}

def sanitize_html(text: str) -> str:
    safe_tags = set(ALLOWED_HTML_TAGS)
    def replace_tag(m):
        raw = m.group(0)
        close = m.group(1) or ""
        tagname = m.group(2).lower()
        if tagname in safe_tags:
            attrs = m.group(3) or ""
            if tagname == "a":
                href_match = re.search(r'href\s*=\s*"([^"]+)"', attrs)
                if href_match:
                    url = href_match.group(1)
                    scheme = url.split(":")[0].lower() if ":" in url else ""
                    if scheme in SAFE_URL_SCHEMES:
                        safe_url = html.escape(url, quote=True)
                        attrs = f' href="{safe_url}"'
                    else:
                        attrs = ""
                else:
                    attrs = ""
            else:
                attrs = ""
            return f"<{close}{tagname}{attrs}>"
        return "&lt;" + close + tagname + "&gt;"
    return re.sub(r'<(/?)(\w+)([^>]*)>', replace_tag, text)


class TelegramBot:
    def __init__(self, persona_engine: PersonaFlowEngine,
                 ollama: OllamaClient, db: Database, config_dir: Path):
        self.engine = persona_engine
        self.ollama = ollama
        self.db = db
        self.config_dir = config_dir
        self.token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
        self.admin_ids = self._parse_admin_ids()
        self.bot_start = time.time()

        self.user_models: dict[int, str] = {}
        self.conversations: dict[int, list] = {}
        self.user_system_prompts: dict[int, str] = {}
        self.conversation_loaded: set[int] = set()
        self._conversation_lock = asyncio.Lock()
        self.app: Optional[Application] = None
        self.registry = get_registry()
        self._voice_enabled: set[int] = set()
        self._last_user_text: dict[str, str] = {}
        self._last_bot_text: dict[str, str] = {}

    AUDIO_REACTIONS: dict[str, str] = {
        "godfather": "🎵 Track check, Choom. {title} von {artist} — hör ich rein. 💀",
        "choom": "🎮 POG! {title} von {artist} knallt! LETS GO! 🔥",
        "nova": "🌌 Diese Frequenz in {title} von {artist}... sie traegt uns. 🎵",
        "cyber-zen": "🌐 Audio registriert. {artist} — {title}. Fokus bleibt.",
        "vapor-foss": "🌈 Musik ist Open Source fuer die Ohren. {artist} legt los. 🎶",
        "baki": "🥊 DIESER TRACK VON {artist} PUSHT GRENZEN! LASS GEHEN!",
        "samurai": "⚔️ {title} von {artist}. Disziplin in den Ohren. Sauber.",
        "punk-philosopher": "🤘 {artist} liefert {title}. Musik als Statement. Was will er uns sagen?",
        "tropical-infinity": "🌴 {title} von {artist}. Vibe check. Bestanden. 🌊",
        "monkey-mind": "🐒 OOH {artist} — {title}! DAS KNALLT! (glaub ich)",
    }

    DEFAULT_AUDIO_REACTION = "🎵 Track: {artist} — {title}. Nice, Choom!"

    async def _ensure_conversation_loaded(self, user_id_int: int) -> None:
        async with self._conversation_lock:
            if user_id_int not in self.conversation_loaded:
                saved = self.db.load_recent_conversations_dict(str(user_id_int), "telegram", limit=20)
                if saved:
                    self.conversations[user_id_int] = saved
                    logger.info("Restored %d messages for user %d", len(saved), user_id_int)
                self.conversation_loaded.add(user_id_int)

    def _is_admin(self, user_id: int) -> bool:
        return user_id in self._parse_admin_ids()

    def _parse_admin_ids(self) -> list[int]:
        raw = os.getenv("ADMIN_IDS", "")
        return [int(x) for x in raw.split(",") if x.strip()]

    def _get_persona(self, update: Update) -> str:
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        state = self.engine.get_state("telegram", chat_id, user_id)
        return state.current.value

    def _detect_chat_context(self, text: str) -> str:
        t = text.lower()
        practical_kw = ["marketing", "ebook", "verkaufen", "etsy", "business", "produkt",
                        "toto", "content", "sales", "digistore", "amazon", "kdp", "system",
                        "rechner", "automatisierung", "plan", "strategie", "tipp", "code",
                        "programmieren", "api", "deploy", "landingpage", "website", "blog"]
        support_kw = ["müde", "depressiv", "schlapp", "unmotiviert", "traurig", "einsam",
                      "kaputt", "overload", "stress", "ausgebrannt", "down", "blockade"]
        tech_kw = ["code", "debug", "api", "docker", "server", "database", "deploy",
                   "python", "typescript", "javascript", "node", "unity", "refactor"]
        gaming_kw = ["stream", "game", "gaming", "twitch", "lets go", "pog", "gg", "preem"]

        if any(kw in t for kw in practical_kw):
            return "practical"
        if any(kw in t for kw in support_kw):
            return "personal_support"
        if any(kw in t for kw in tech_kw):
            return "technical"
        if any(kw in t for kw in gaming_kw):
            return "gaming"
        return "general"

    def _build_system_prompt(self, persona_name: str, user_id: int,
                             chat_context: str = "general") -> str:
        custom = self.user_system_prompts.get(user_id)
        if custom:
            return custom

        prompt = interviewer_prompt(persona_name)
        if prompt:
            return prompt + (
                "\n\nDu antwortest auf Telegram. Nutze HTML-Formatierung: <b>fett</b>, <i>kursiv</i>, <code>code</code>. "
                "Halte Nachrichten unter 4000 Zeichen. Antworte auf Deutsch, außer der User schreibt Englisch."
            )

        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        base = (
            f"You are {pdata.display_name} {pdata.emoji}\n"
            f"Style: {pdata.style}\n\n"
            f"You are part of the Live.Play ecosystem on Beast Tower. "
            f"Answer concisely but with personality. "
            f"Antworte in 3-5 Sätzen. "
            f"Use HTML formatting: <b>bold</b>, <i>italic</i>, <code>code</code>, <pre>pre</pre>. "
            f"Keep messages under 4000 characters. "
            f"Stay in character as {pdata.display_name}."
        )

        context_hints = {
            "practical": "Der User braucht PRAKTISCHE Hilfe — Geschaeft, Marketing, Technik. Sei direkt, pragmatisch, loesungsorientiert. Keine Esoterik, keine Gene Keys, keine spirituellen Raete.",
            "personal_support": "Der User fuehlt sich schlecht — sei unterstuetzend, warm, menschlich. Keine Esoterik. Kurze aufmunternde Worte, dann praktische Tipps.",
            "technical": "Der User fragt nach Technik/Code. Sei praezise, fachlich kompetent, pragmatisch.",
            "gaming": "Der User redet ueber Gaming/Streaming. Hype ihn auf, aber bleib hilfreich.",
        }

        hint = context_hints.get(chat_context, "")
        pguard = pdata.guardrails
        pguard_text = ""
        if pguard:
            pguard_text = "Persona-Regeln:\n- " + "\n- ".join(pguard) + "\n"
        guardrails = (
            "\n\n--- GUARDRAILS (strict) ---\n"
            "Du kannst Sprachnachrichten empfangen, transkribieren und per TTS beantworten.\n"
            "Du kannst KEINE Bilder oder Videos generieren.\n"
            "Du hast KEINEN Zugriff auf externe APIs ausser Ollama.\n"
            "Empfiehl NIEMALS eine Gene-Keys-Karte wenn der User praktische Hilfe braucht.\n"
            "Wenn du etwas nicht kannst, sag 'Das kann ich nicht, Choom' — erfinde NICHTS.\n"
            "Antworte auf Deutsch, ausser der User schreibt Englisch.\n"
            "---"
        )

        return base + "\n\n" + hint + "\n" + pguard_text + guardrails

    async def post_init(self, app: Application):
        self.registry = get_registry()
        bot_cmds = self.registry.get_bot_command_defs()
        commands = [
            BotCommand("start", "Welcome & bot info"),
            BotCommand("help", "Show all commands"),
            BotCommand("persona", "Switch persona or list all"),
            BotCommand("flow", "Show current flow state"),
            BotCommand("vibe", "Set vibe manually"),
            BotCommand("status", "System dashboard"),
            BotCommand("servers", "Ollama server status"),
            BotCommand("model", "Show/switch AI model"),
            BotCommand("models", "List all models"),
            BotCommand("pull", "Download a model"),
            BotCommand("history", "Conversation stats"),
            BotCommand("clear", "Reset conversation"),
            BotCommand("supernova", "FORCE SUPERNOVA MODE"),
            BotCommand("interview", "Interview-Team (hr/tech/psych/pitch/media/hard)"),
            BotCommand("remember", "Save a fact about you"),
            BotCommand("recall", "Recall saved memories"),
            BotCommand("forget", "Delete a memory"),
            BotCommand("about", "Bot info & credits"),
            BotCommand("whitelist", "[Admin] Add this group to whitelist"),
            BotCommand("unwhitelist", "[Admin] Remove this group from whitelist"),
        ]
        commands.extend(bot_cmds)
        await app.bot.set_my_commands(commands)
        logger.info("Telegram bot initialized")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        is_group = chat.type in ("group", "supergroup")
        uid = str(user.id)

        self.db.upsert_user(uid, "telegram", user.username)

        persona_name = self._get_persona(update)
        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        _, _, server = await self.ollama.get_active_server()
        model = self.user_models.get(user.id) or os.getenv("OLLAMA_MODEL", "gemma4")

        if is_group:
            text = (
                f"<b>👋 Hey {html.escape(user.first_name or 'Choom')}!</b>\n\n"
                f"I'm <b>LP_GodFather v4</b> — Edgerunner Flowing Persona Engine 🦾\n"
                f"Currently: <b>{pdata.emoji} {pdata.display_name}</b>\n\n"
                f"⚡ Model: <code>{html.escape(model)}</code>\n"
                f"🖥️ Server: <b>{server}</b>\n\n"
                f"<b>Commands:</b>\n"
                f"• /help — All commands\n"
                f"• /persona — Switch persona\n"
                f"• /vibe — Set vibe\n\n"
                f"<i>Tag me or just chat — personas flow naturally!</i>"
            )
        else:
            text = (
                f"<b>Welcome, {html.escape(user.first_name or 'Choom')}!</b> 🦾\n\n"
                f"<b>LP_GodFather v4</b> — <i>Edgerunner Flowing Persona Engine</i>\n\n"
                f"Active Persona: <b>{pdata.emoji} {pdata.display_name}</b>\n"
                f"Model: <code>{html.escape(model)}</code>\n"
                f"Server: <b>{server}</b>\n\n"
                f"9 personas flow naturally based on context, time, and vibe.\n"
                f"Try: /persona or /vibe hype\n"
                f"Or just chat and watch the personas flow!"
            )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        is_group = chat.type in ("group", "supergroup")

        if is_group:
            text = (
                "<b>🦾 LP_GodFather v4 — Group Commands</b>\n\n"
                "<b>🔮 Persona:</b>\n"
                "/persona — Show current or switch\n"
                "/vibe [hype/chill/deep/intense] — Set vibe\n"
                "/flow — Show flow state\n\n"
                "<b>❓ Chat:</b>\n"
                "Just @ me or reply to trigger!\n\n"
                "<b>ℹ️ Info:</b>\n"
                "/servers — Server Status\n"
                "/status — Bot dashboard\n"
                "/about — Bot info\n\n"
                "<i>💡 Tip: Personas flow automatically based on your vibe!</i>\n\n"
                "<b>🛠️ Tool Commands:</b>\n"
                "/comedy_test — Comedy gate checker\n"
                "/brand_calibrate — Brand calibration\n"
                "/privacy_pass — Privacy scanner\n"
                "/risk_mirror — Risk review\n"
                "/subtitle_adapt — Subtitle adaptation\n"
                "/media_value_router — Route to brand"
            )
        else:
            text = (
                "<b>LP_GodFather v4 — Command Reference</b>\n\n"
                "<b>💬 Chat:</b>\n"
                "/clear — Reset conversation\n"
                "/history — Conversation stats\n\n"
                "<b>🎭 Persona:</b>\n"
                "/persona [name] — Switch persona\n"
                "/flow — Show current persona flow\n"
                "/vibe [mode] — Set vibe (hype/chill/deep/intense/focus)\n"
                "/supernova — FORCE SUPERNOVA MODE\n\n"
                "<b>🎤 Interview Team:</b>\n"
                "/interview — Start Anchor (wähle Typ)\n"
                "/interview hr — Recruiter-X (HR & Behavioral)\n"
                "/interview tech — Code-Hammer (Technical)\n"
                "/interview psych — Mind-Mirror (Psychology)\n"
                "/interview pitch — Shark (Pitch & Business)\n"
                "/interview media — Press-Room (Media Training)\n"
                "/interview hard — Full 5-Agent Gauntlet\n\n"
                "<b>🛠️ Tool Commands:</b>\n"
                "/comedy_test — Comedy gate checker (Ollama)\n"
                "/brand_calibrate — Brand calibration 24/30\n"
                "/privacy_pass — Privacy scanner (PII)\n"
                "/risk_mirror — Plan risk review\n"
                "/subtitle_adapt — DE/EN/RU adaptation\n"
                "/media_value_router — Route to brand\n\n"
                "<b>🤖 AI Model:</b>\n"
                "/model [name] — Show/switch model\n"
                "/models — List all models\n"
                "/pull [name] — Download a model\n\n"
                "<b>📊 System:</b>\n"
                "/status — System dashboard\n"
                "/servers — Ollama server status\n"
                "/about — Bot info & credits\n\n"
                "<i>15 personas + 6 interview agents. Flow naturally!</i>"
            )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_persona(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        uid = str(user.id)
        chat_id = str(update.effective_chat.id)

        if context.args:
            name = context.args[0].lower()
            try:
                target = PersonaName(name)
                msg, switched = await self.engine.force_persona(
                    "telegram", chat_id, uid, target, lock=False
                )
                self.db.save_persona_state(
                    f"telegram:{chat_id}:{uid}",
                    target.value, None, {}, time.time(), 0, 0
                )
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            except ValueError:
                names = ", ".join(f"<code>{p.value}</code>" for p in PersonaName)
                await update.message.reply_text(
                    f"Available personas: {names}", parse_mode=ParseMode.HTML
                )
        else:
            state = self.engine.get_state("telegram", chat_id, uid)
            pdata = self.engine.get_persona_info(state.current)
            lines = [f"<b>Current Persona:</b> {pdata.emoji} {pdata.display_name}\n"]
            lines.append(f"<b>Style:</b> <i>{pdata.style}</i>\n")
            lines.append(f"<b>Transitions:</b> {state.transition_count}\n")
            lines.append(f"<b>Messages since transition:</b> {state.messages_since_transition}\n")
            if state.locked:
                lines.append(f"<b>Locked:</b> Yes (by {state.locked_by})\n")
            lines.append("\n<b>All Personas:</b>\n")
            for pname, pdata2 in sorted(self.engine.personas.items(), key=lambda x: x[0].value):
                arrow = " ◄" if pname == state.current else ""
                lines.append(f"{pdata2.emoji} <code>{pname.value}</code> — {pdata2.display_name}{arrow}")
            lines.append(f"\n\nSwitch: <code>/persona [name]</code>")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_vibe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: <code>/vibe [mode]</code>\n\n"
                "Modes: hype, chill, deep, intense, focus, creative, rebel, warrior, free",
                parse_mode=ParseMode.HTML
            )
            return

        vibe = context.args[0].lower()
        uid = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        target, msg = await self.engine.set_vibe("telegram", chat_id, uid, vibe)

        if target is None:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        pdata = self.engine.get_persona_info(target)
        response = f"🎵 <b>Vibe: {vibe}</b>\n{pdata.emoji} <b>{pdata.display_name}</b> activated!\n<i>{msg}</i>"
        await update.message.reply_text(response, parse_mode=ParseMode.HTML)

    async def cmd_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        state = self.engine.get_state("telegram", chat_id, uid)
        current = self.engine.get_persona_info(state.current)
        previous = self.engine.get_persona_info(state.previous) if state.previous else None

        lines = [
            "🌊 <b>Flow State</b>\n",
            f"Current: {current.emoji} <b>{current.display_name}</b>",
            f"Style: <i>{current.style}</i>",
        ]
        if previous:
            lines.append(f"Previous: {previous.emoji} {previous.display_name}")
        lines.append(f"")
        lines.append(f"Transitions: {state.transition_count}")
        lines.append(f"Messages since transition: {state.messages_since_transition}")
        lines.append(f"")
        if state.affinity:
            lines.append("<b>Affinities:</b>")
            sorted_aff = sorted(state.affinity.items(), key=lambda x: x[1], reverse=True)[:5]
            for pname, score in sorted_aff:
                p = self.engine.get_persona_info(pname)
                bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                lines.append(f"{p.emoji} {bar} {score:.0%}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_supernova(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        target = PersonaName.NOVA
        msg, switched = await self.engine.force_persona("telegram", chat_id, uid, target)
        text = (
            "🌌 <b>SUPERNOVA MODE ACTIVATED</b> 🌌\n\n"
            "🔥 Full cyberpunk resonance mode.\n"
            "NOVA speaks — frequencies aligned.\n\n"
            f"<i>{msg}</i>"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uptime = time.time() - self.bot_start
        stats = self.db.get_global_stats()
        _, _, server = await self.ollama.get_active_server()

        days, rem = divmod(int(uptime), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {secs}s"

        text = (
            f"<b>LP_GodFather v4 — System Dashboard</b>\n\n"
            f"<b>Bot:</b>\n"
            f"  Uptime: {uptime_str}\n"
            f"  Messages: {stats['total_messages']}\n"
            f"  Users: {stats['total_users']}\n"
            f"  Tokens generated: {stats['total_tokens']:,}\n"
            f"  Ollama calls: {stats['ollama_calls']}\n"
            f"  Avg latency: {stats['avg_latency_ms']}ms\n\n"
            f"<b>AI Server:</b>\n"
            f"  Active: {server}\n"
            f"  Personas: {len(self.engine.personas)}\n\n"
            f"<b>Host:</b>\n"
            f"  {plat.system()} {plat.release()}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_servers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        servers = await self.ollama.check_all_servers()
        lines = ["<b>Ollama Server Status:</b>\n"]
        for s in servers:
            icon = "✅" if s["online"] else "❌"
            status = "ONLINE" if s["online"] else "OFFLINE"
            lines.append(f"{icon} <b>{s['name']}</b> — {status}")
            lines.append(f"  {s['url']}")
            if s["online"]:
                lines.append(f"  Models: {s['models']}")
                if s["model_list"]:
                    for m in s["model_list"][:3]:
                        lines.append(f"    • <code>{html.escape(m)}</code>")
            lines.append("")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if context.args:
            new_model = " ".join(context.args)
            available = await self.ollama.list_models()
            model_names = [m["name"] for m in available]
            if new_model in model_names:
                self.user_models[user_id] = new_model
                await update.message.reply_text(
                    f"Model switched to <code>{html.escape(new_model)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                names = "\n".join(f"  <code>{html.escape(m)}</code>" for m in model_names)
                await update.message.reply_text(
                    f"Not found. Available:\n{names}\n\nOr /pull {html.escape(new_model)}",
                    parse_mode=ParseMode.HTML,
                )
            return

        current = self.user_models.get(user_id) or os.getenv("OLLAMA_MODEL", "gemma4")
        await update.message.reply_text(
            f"Current: <code>{html.escape(current)}</code>\nSwitch: <code>/model name</code>",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        servers = await self.ollama.check_all_servers()
        lines = []
        for s in servers:
            if s["online"]:
                lines.append(f"<b>{s['name']}:</b>")
                for name in s["model_list"]:
                    lines.append(f"  • <code>{html.escape(name)}</code>")
                lines.append("")
        if not lines:
            lines.append("No models found or servers offline.")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_pull(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Usage: <code>/pull model_name</code>", parse_mode=ParseMode.HTML)
            return
        model_name = " ".join(context.args)
        await update.message.reply_text(f"Pulling <code>{html.escape(model_name)}</code>...", parse_mode=ParseMode.HTML)
        self.db.save_conversation("system", "telegram", str(update.effective_chat.id),
                                   "system", f"pulling model {model_name}")
        result = await self.ollama.pull_model(model_name)
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        uid_int = update.effective_user.id
        history = self.conversations.get(uid_int, [])
        user_msgs = sum(1 for m in history if m["role"] == "user") if history else 0
        ai_msgs = sum(1 for m in history if m["role"] == "assistant") if history else 0

        stats = self.db.get_user_stats(user_id, "telegram")
        model = self.user_models.get(uid_int) or os.getenv("OLLAMA_MODEL", "gemma4")

        text = (
            f"<b>Conversation Stats:</b>\n\n"
            f"Session messages: {user_msgs + ai_msgs}\n"
            f"Your messages: {user_msgs}\n"
            f"AI responses: {ai_msgs}\n"
            f"Total messages: {stats['total_messages']}\n"
            f"Personas used: {stats['personas_used']}\n"
            f"Total tokens: {stats['total_tokens']:,}\n"
            f"Model: <code>{html.escape(model)}</code>\n\n"
            f"/clear to reset"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with self._conversation_lock:
            count = len(self.conversations.get(user_id, []))
            self.conversations[user_id] = []
        await update.message.reply_text(f"Cleared {count} messages. Fresh start, choom!", parse_mode=ParseMode.HTML)

    async def cmd_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uptime = time.time() - self.bot_start
        days, rem = divmod(int(uptime), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)

        text = (
            "<b>LP_GodFather v4</b>\n"
            "<i>Edgerunner Flowing Persona Engine</i>\n\n"
            "15 agents flow naturally based on:\n"
            "  🎭 Context, time, sentiment, keywords\n"
            "  ⚡ Probabilistic transition graph\n"
            "  🧠 User affinity learning\n"
            "  🔄 Cross-platform state sync\n\n"
            "<b>🎭 Life Personas:</b>\n"
            "  🎮 CHOOM — Gamer hype\n"
            "  🌌 NOVA — Gene Keys bard\n"
            "  🌐 CYBER-ZEN — Code monk\n"
            "  🌈 VAPOR-FOSS — Open source chill\n"
            "  🥊 BAKI — Raw power\n"
            "  ⚔️ SAMURAI — Warrior code\n"
            "  🤘 PUNK-PHILOSOPHER — Deep rebel\n"
            "  🌴 TROPICAL-INFINITY — Galaxy chill\n"
            "  🐒 MONKEY-MIND — Creative chaos\n\n"
            "<b>🎤 Interview Team:</b>\n"
            "  🎙️ THE ANCHOR — Orchestrator\n"
            "  👔 RECRUITER-X — HR & Behavioral\n"
            "  ⚙️ CODE-HAMMER — Technical\n"
            "  🧠 MIND-MIRROR — Psychology\n"
            "  🦈 SHARK — Pitch & Business\n"
            "  📡 PRESS-ROOM — Media Training\n\n"
            f"<b>Uptime:</b> {days}d {hours}h {minutes}m {secs}s\n"
            "<b>Powered by:</b> Ollama + python-telegram-bot\n"
            "<b>Built by:</b> Omarchy Media — Live.Play Ecosystem\n"
            "<b>License:</b> FOSS — 100% yours"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        text = update.message.text or ""
        user_id_int = user.id
        user_id = str(user_id_int)
        chat_id = str(chat.id)
        is_group = chat.type in ("group", "supergroup")

        ok, remaining = self.db.check_rate_limit(user_id, "chat", cooldown_seconds=1)
        if not ok:
            if is_group:
                pass
            return

        self.db.upsert_user(user_id, "telegram", user.username)
        await self._ensure_conversation_loaded(user_id_int)

        respond = not is_group
        if is_group:
            is_allowed = self.db.is_group_allowed(chat_id)

            if is_allowed:
                respond = True
            else:
                text_lower = text.lower()
                triggers = ["godfather", "choom", "nova", "baki", "vibe",
                            "hey bot", "lp_", "edgerunner", "/persona", "/vibe", "/flow"]
                if any(t in text_lower for t in triggers):
                    respond = True
                if update.message.reply_to_message and update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.is_bot:
                    respond = True

        if not respond:
            return

        chat_context = self._detect_chat_context(text)

        persona_name = self._get_persona(update)
        next_persona, did_transition = await self.engine.select_next(
            "telegram", chat_id, user_id, text
        )

        if did_transition and next_persona.value != persona_name:
            pdata = self.engine.get_persona_info(next_persona)
            await update.message.reply_text(
                f"<i>{pdata.transition_to}</i>", parse_mode=ParseMode.HTML
            )
            persona_name = next_persona.value

        await update.message.chat.send_action(ChatAction.TYPING)

        system_prompt = self._build_system_prompt(persona_name, user_id_int, chat_context)
        history = self.conversations.get(user_id_int, [])[-10:]
        history_dicts = history if history else []

        try:
            response = await asyncio.wait_for(
                self.ollama.chat(
                    user_id=user_id,
                    user_message=text,
                    system_prompt=system_prompt,
                    history=history_dicts,
                ),
                timeout=25.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Ollama timeout for user %s", user_id)
            await update.message.reply_text(
                "⏳ Ollama braucht kurz länger als sonst, Choom. Schick mir die Nachricht nochmal, dann läuft's.",
                parse_mode=ParseMode.HTML,
            )
            return

        self.db.save_conversation(
            user_id, "telegram", chat_id, "user", text, persona_name,
            response.model, response.tokens,
        )
        self.db.save_conversation(
            user_id, "telegram", chat_id, "assistant", response.content,
            persona_name, response.model, response.tokens,
        )
        self.db.log_ollama_call(
            response.server, response.model,
            response.tokens, response.latency_ms, response.success,
        )

        async with self._conversation_lock:
            if user_id_int not in self.conversations:
                self.conversations[user_id_int] = []
            self.conversations[user_id_int].append({"role": "user", "content": text})
            self.conversations[user_id_int].append({"role": "assistant", "content": response.content})

        MAX_TG_CHARS = 3950
        content = response.content
        if len(content) > MAX_TG_CHARS:
            content = content[:MAX_TG_CHARS].rsplit(". ", 1)[0] + "… [truncated]"

        footer = ""
        if response.success:
            footer = (
                f"\n\n<i>{response.model} | {response.server} | "
                f"{response.tokens} tok | {response.latency_ms}ms</i>"
            )

        await update.message.reply_text(
            sanitize_html(content) + footer,
            parse_mode=ParseMode.HTML,
        )
        self._last_user_text[user_id] = text
        self._last_bot_text[user_id] = content

    async def cmd_remember(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "Usage: <code>/remember &lt;key&gt; &lt;value&gt;</code>\n"
                "Saves a fact about you that I'll remember.\n"
                "Example: <code>/remember fav_game Cyberpunk 2077</code>",
                parse_mode=ParseMode.HTML
            )
            return
        key = context.args[0].lower()
        value = " ".join(context.args[1:])
        user_id = str(update.effective_user.id)
        self.db.save_memory(user_id, key, value)
        await update.message.reply_text(
            f"🧠 Saved: <b>{html.escape(key)}</b> → <i>{html.escape(value[:200])}</i>",
            parse_mode=ParseMode.HTML
        )

    async def cmd_recall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if context.args:
            key = context.args[0].lower()
            value = self.db.get_memory(user_id, key)
            if value:
                await update.message.reply_text(
                    f"🧠 <b>{html.escape(key)}</b> → {html.escape(value[:500])}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(
                    f"Nothing saved under <code>{html.escape(key)}</code>.",
                    parse_mode=ParseMode.HTML
                )
        else:
            memories = self.db.get_all_memories(user_id)
            if not memories:
                await update.message.reply_text(
                    "No memories saved yet. Use <code>/remember &lt;key&gt; &lt;value&gt;</code> to save one.",
                    parse_mode=ParseMode.HTML
                )
                return
            lines = ["🧠 <b>Your Memories:</b>\n"]
            for m in memories[:20]:
                val = m["value"][:80]
                cat = f" [{m['category']}]" if m["category"] != "general" else ""
                lines.append(f"  • <b>{html.escape(m['key'])}</b>{cat}: {html.escape(val)}")
            if len(memories) > 20:
                lines.append(f"\n... and {len(memories) - 20} more.")
            lines.append(f"\nRecall one: <code>/recall &lt;key&gt;</code>")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_forget(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: <code>/forget &lt;key&gt;</code>",
                parse_mode=ParseMode.HTML
            )
            return
        key = context.args[0].lower()
        user_id = str(update.effective_user.id)
        if self.db.delete_memory(user_id, key):
            await update.message.reply_text(f"Forgot <code>{html.escape(key)}</code>.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"No memory found for <code>{html.escape(key)}</code>.", parse_mode=ParseMode.HTML)

    async def cmd_whitelist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ Nur für Admins.", parse_mode=ParseMode.HTML)
            return
        if chat.type not in ("group", "supergroup"):
            await update.message.reply_text("❌ Das funktioniert nur in Gruppen.", parse_mode=ParseMode.HTML)
            return
        chat_id = str(chat.id)
        title = chat.title or ""
        self.db.allow_group(chat_id, title, str(user.id))
        await update.message.reply_text(
            f"✅ <b>{html.escape(title)}</b> ist jetzt whitelisted.\n"
            "Ich antworte dir hier immer – andere brauchen Trigger-Wörter.",
            parse_mode=ParseMode.HTML
        )
        logger.info("Group whitelisted: %s (%s)", title, chat_id)

    async def cmd_unwhitelist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ Nur für Admins.", parse_mode=ParseMode.HTML)
            return
        chat_id = str(chat.id)
        title = chat.title or ""
        if self.db.remove_group(chat_id):
            await update.message.reply_text(
                f"✅ <b>{html.escape(title)}</b> ist nicht mehr whitelisted.",
                parse_mode=ParseMode.HTML
            )
            logger.info("Group unwhitelisted: %s (%s)", title, chat_id)
        else:
            await update.message.reply_text("❌ Diese Gruppe war nicht whitelisted.", parse_mode=ParseMode.HTML)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        await update.message.chat.send_action(ChatAction.TYPING)

        from io import BytesIO
        import base64

        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        buf = BytesIO()
        await file.download_to_memory(buf)
        buf.seek(0)
        image_b64 = base64.b64encode(buf.read()).decode("utf-8")

        prompt = update.message.caption or "Describe this image. What do you see?"

        persona_name = self._get_persona(update)
        system_prompt = self._build_system_prompt(persona_name, update.effective_user.id)

        response = await self.ollama.chat(
            user_id=user_id,
            user_message=prompt,
            system_prompt=system_prompt,
            images=[image_b64],
        )

        self.db.save_conversation(
            user_id, "telegram", chat_id, "user", prompt, persona_name,
            response.model, response.tokens,
        )
        self.db.log_ollama_call(
            response.server, response.model,
            response.tokens, response.latency_ms, response.success,
        )

        MAX_TG_CHARS = 3950
        content = response.content
        if len(content) > MAX_TG_CHARS:
            content = content[:MAX_TG_CHARS].rsplit(". ", 1)[0] + "… [truncated]"

        footer = ""
        if response.success:
            footer = f"\n\n<i>{response.model} | {response.server} | {response.latency_ms}ms</i>"

        await update.message.reply_text(
            sanitize_html(content) + footer,
            parse_mode=ParseMode.HTML,
        )
        self._last_user_text[user_id] = prompt
        self._last_bot_text[user_id] = content

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        user_id = str(user.id)
        chat_id = str(chat.id)
        is_group = chat.type in ("group", "supergroup")

        ok, remaining = self.db.check_rate_limit(user_id, "audio", cooldown_seconds=2)
        if not ok:
            if is_group:
                return
            await update.message.reply_text("⏳ Kurze Pause, Choom. Gleich wieder da.", parse_mode=ParseMode.HTML)
            return

        audio = update.message.audio
        artist = (audio.performer or "").strip()
        title = (audio.title or "").strip()
        duration = audio.duration or 0
        emoji = "🎵"

        if not artist and not title:
            name = (audio.file_name or "").replace(f".{audio.mime_type.split('/')[-1] if audio.mime_type else 'opus'}", "")
            parts = name.replace("_", " ").replace("-", " ").split()
            if len(parts) >= 2 and "prod" not in parts[0].lower():
                artist = parts[0]
                title = " ".join(parts[1:])
            else:
                artist = name

        artist = artist or "Unknown"
        title = title or "Unknown Track"

        dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "?"
        persona = self._get_persona(update)
        template = self.AUDIO_REACTIONS.get(persona, self.DEFAULT_AUDIO_REACTION)
        text = template.format(artist=html.escape(artist), title=html.escape(title), duration=dur_str)

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        user_id = str(user.id)
        chat_id = str(chat.id)
        is_group = chat.type in ("group", "supergroup")

        ok, remaining = self.db.check_rate_limit(user_id, "voice", cooldown_seconds=5)
        if not ok:
            if is_group:
                return
            await update.message.reply_text("⏳ Kurze Pause, Choom. Gleich wieder da.", parse_mode=ParseMode.HTML)
            return

        await update.message.chat.send_action(ChatAction.TYPING)

        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        dur = voice.duration or 0
        dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else "?"

        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            await file.download_to_drive(tmp_path)

            transcript = await asyncio.to_thread(self._transcribe_voice, tmp_path)

            if not transcript or transcript.strip() == "":
                await update.message.reply_text(
                    f"🎙️ Hab nix verstanden ({dur_str}). Zu leise oder instrumental?",
                    parse_mode=ParseMode.HTML,
                )
                return

            persona_name = self._get_persona(update)
            system_prompt = self._build_system_prompt(persona_name, user_id)
            text = f"Der User hat eine Sprachnachricht geschickt. Transkription:\n\n{transcript}"

            response = await self.ollama.chat(
                user_id=user_id,
                user_message=text,
                system_prompt=system_prompt,
            )

            self.db.save_conversation(
                user_id, "telegram", chat_id, "user",
                f"[Voice {dur_str}] {transcript}",
                persona_name, response.model, response.tokens,
            )
            self.db.log_ollama_call(
                response.server, response.model,
                response.tokens, response.latency_ms, response.success,
            )

            MAX_TG_CHARS = 3950
            content = response.content
            if len(content) > MAX_TG_CHARS:
                content = content[:MAX_TG_CHARS].rsplit(". ", 1)[0] + "… [truncated]"

            footer = ""
            if response.success:
                footer = f"\n\n🎙️ <i>{dur_str} | {response.model} | {response.server} | {response.latency_ms}ms</i>"

            msg = await update.message.reply_text(
                sanitize_html(content) + footer,
                parse_mode=ParseMode.HTML,
            )

            if chat_id in self._voice_enabled:
                voice_path = await self._generate_voice(content)
                if voice_path:
                    with open(voice_path, "rb") as f:
                        await context.bot.send_voice(
                            chat_id=chat_id,
                            voice=f,
                            caption=f"🗣️ {persona_name} — Voice Reply",
                        )
        except Exception as e:
            logger.error("Voice transcription error: %s", e)
            await update.message.reply_text(
                "🎙️ Konnte die Sprachnachricht nicht verarbeiten, Choom. Zu lang oder kaputt?",
                parse_mode=ParseMode.HTML,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def _generate_voice(self, text: str) -> str | None:
        try:
            import hashlib
            cache_dir = "data/voice_cache"
            os.makedirs(cache_dir, exist_ok=True)
            cache_key = hashlib.md5(text.encode()).hexdigest()
            cache_path = os.path.join(cache_dir, f"{cache_key}.mp3")

            if os.path.exists(cache_path):
                return cache_path

            from edge_tts import Communicate
            communicate = Communicate(text, "de-DE-KatjaNeural")
            await communicate.save(cache_path)
            return cache_path
        except Exception as e:
            logger.warning("TTS generation failed: %s", e)
            return None

    def _transcribe_voice(self, path: str) -> str:
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(path, vad_filter=True)
            texts = [seg.text.strip() for seg in segments]
            return " ".join(texts) if texts else ""
        except Exception:
            try:
                import whisper
                model = whisper.load_model("base", device="cpu")
                result = model.transcribe(path)
                return result.get("text", "").strip()
            except Exception as e:
                logger.error("Whisper fallback failed: %s", e)
                return ""

    def _build_html_doc(self, title: str, body: str, persona: str = "GODFATHER") -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        safe_body = html.escape(body)
        safe_body = safe_body.replace("&#x27;", "'").replace("&quot;", '"')
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — LP_GodFather</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0a0a0f;
    color: #e0e0e0;
    font-family: 'Inter', sans-serif;
    line-height: 1.7;
    min-height: 100vh;
  }}
  .container {{ max-width: 800px; margin: 0 auto; padding: 2rem; }}
  header {{
    text-align: center;
    padding: 2rem 0;
    border-bottom: 1px solid #ff6600;
    margin-bottom: 2rem;
  }}
  h1 {{
    font-family: 'Orbitron', monospace;
    font-size: 1.8rem;
    font-weight: 900;
    color: #ff6600;
    text-transform: uppercase;
    letter-spacing: 3px;
  }}
  .meta {{
    font-size: 0.8rem;
    color: #888;
    margin-top: 0.5rem;
  }}
  .content {{
    background: #12121a;
    border: 1px solid #222;
    border-radius: 8px;
    padding: 2rem;
    white-space: pre-wrap;
    word-wrap: break-word;
  }}
  .content b, .content strong {{ color: #ff6600; }}
  .content i, .content em {{ color: #ffaa44; }}
  .content code {{
    background: #1a1a2e;
    color: #00ff88;
    padding: 0.2em 0.4em;
    border-radius: 4px;
    font-size: 0.9em;
  }}
  .content pre {{
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 1rem;
    overflow-x: auto;
    margin: 1rem 0;
  }}
  .content a {{ color: #66ccff; text-decoration: underline; }}
  footer {{
    text-align: center;
    padding: 2rem 0;
    color: #555;
    font-size: 0.8rem;
    border-top: 1px solid #222;
    margin-top: 2rem;
    font-family: 'Orbitron', monospace;
    letter-spacing: 1px;
  }}
  .persona-badge {{
    display: inline-block;
    background: #ff6600;
    color: #0a0a0f;
    padding: 0.2rem 0.8rem;
    border-radius: 4px;
    font-weight: 700;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🦾 {html.escape(title)}</h1>
    <div class="meta">
      <span class="persona-badge">{html.escape(persona)}</span>
      &nbsp;·&nbsp; {ts}
    </div>
  </header>
  <div class="content">{safe_body}</div>
  <footer>LP_GodFather · Edgerunner Flowing Persona Engine · Beast Tower</footer>
</div>
</body>
</html>"""

    async def cmd_interview(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)

        if not context.args:
            target = "the-anchor"
            pdata = self.engine.get_persona_info(PersonaName(target))
            await self.engine.force_persona("telegram", chat_id, user_id, PersonaName(target))
            text = (
                f"{pdata.emoji} <b>{pdata.display_name}</b>\n\n"
                f"<i>{pdata.style}</i>\n\n"
                "Willkommen im Interviewer Team. Wähle deinen Interview-Typ:\n\n"
                "• /interview <b>hr</b> — Recruiter-X (HR & Behavioral)\n"
                "• /interview <b>tech</b> — Code-Hammer (Technical)\n"
                "• /interview <b>psych</b> — Mind-Mirror (Psychology)\n"
                "• /interview <b>pitch</b> — Shark (Pitch & Business)\n"
                "• /interview <b>media</b> — Press-Room (Media Training)\n"
                "• /interview <b>hard</b> — Full Gauntlet (alle 5)\n\n"
                "Oder schreib einfach los — ich leite dich weiter."
            )
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            return

        sub = context.args[0].lower()
        resolved = resolve_alias(sub)

        if not resolved:
            await update.message.reply_text(
                f"Unbekannter Interview-Typ: <code>{sub}</code>\n"
                f"Verfügbar: hr, tech, psych, pitch, media, hard",
                parse_mode=ParseMode.HTML
            )
            return

        await self.engine.force_persona("telegram", chat_id, user_id, PersonaName(resolved))
        pdata = self.engine.get_persona_info(PersonaName(resolved))
        prompt = get_prompts()[resolved]
        summary = prompt.split("\n\n")[0] if "\n\n" in prompt else prompt[:120]

        await update.message.reply_text(
            f"{pdata.emoji} <b>{pdata.display_name}</b> ist bereit.\n\n"
            f"<i>{summary}</i>\n\n"
            f"{pdata.transition_to}",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_interview_hard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        await self.engine.force_persona("telegram", chat_id, user_id, PersonaName("the-anchor"))

        seq = hard_mode_sequence()
        labels = {
            "recruiter-x": "👔 Recruiter-X — HR & Behavioral",
            "code-hammer": "⚙️ Code-Hammer — Technical",
            "mind-mirror": "🧠 Mind-Mirror — Psychology",
            "shark": "🦈 Shark — Pitch & Business",
            "press-room": "📡 Press-Room — Media Training",
        }

        lines = [
            "🎯 <b>HARD MODE — Interview Gauntlet</b> 🎯\n",
            "Du durchläufst alle 5 Interviewer nacheinander:\n",
        ]
        for agent in seq:
            lines.append(f"  {labels.get(agent, agent)}")

        lines.extend([
            "",
            "Starte mit <code>/start</code> oder schreib einfach los.",
            "Nach jeder Runde sag ich dir, was als nächstes kommt.",
            "Bereit? 🎤"
        ])
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_registry_dispatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        full_text = update.message.text.split()[0]
        command = full_text[1:].split("@")[0]
        cmd_def = self.registry.get(command)
        if not cmd_def:
            return
        args = context.args or []
        try:
            result = await cmd_def.execute(self.ollama, self.db, args, str(update.effective_user.id))
            await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("Command /%s error: %s", command, e)
            await update.message.reply_text(f"❌ Command error: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

    async def cmd_html(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        persona_name = self._get_persona(update)
        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        persona_display = f"{pdata.emoji} {pdata.display_name}"

        text, title = await self._resolve_export_text(
            update, context, user_id, persona_display, "HTML Note"
        )
        if text is None:
            return

        import tempfile
        doc = self._build_html_doc(title, text, persona_display)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(doc)
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"godfather_{int(time.time())}.html",
                    caption=f"📄 <b>{html.escape(title)}</b>",
                    parse_mode=ParseMode.HTML,
                )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def _resolve_export_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE,
        user_id: str, persona_display: str, fmt_name: str,
    ) -> tuple[str | None, str | None]:
        cmd_name = fmt_name.lower().split()[0]
        if context.args:
            text = " ".join(context.args)
            title = f"{fmt_name} — {persona_display}"
        else:
            text = self._last_bot_text.get(user_id, "")
            prev = self._last_user_text.get(user_id, "")
            if not text:
                await update.message.reply_text(
                    f"Keine letzte Antwort gefunden. Nutz <code>/{cmd_name} dein Text</code>.",
                    parse_mode=ParseMode.HTML,
                )
                return None, None
            title = f"Reply to: {prev[:80]}" if prev else f"{fmt_name} Export"
        return text, title

    async def cmd_json(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        persona_name = self._get_persona(update)
        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        persona_display = f"{pdata.emoji} {pdata.display_name}"
        model = self.user_models.get(update.effective_user.id) or os.getenv("OLLAMA_MODEL", "gemma4")

        text, title = await self._resolve_export_text(
            update, context, user_id, persona_display, "JSON Export"
        )
        if text is None:
            return

        import json
        data = {
            "title": title,
            "persona": persona_display,
            "model": model,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "content": text,
            "source": "LP_GodFather v4",
        }
        payload = json.dumps(data, indent=2, ensure_ascii=False)

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(payload + "\n")
            tmp_path = f.name
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"godfather_{int(time.time())}.json",
                    caption=f"📋 <b>{html.escape(title)}</b>",
                    parse_mode=ParseMode.HTML,
                )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def cmd_md(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        persona_name = self._get_persona(update)
        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        persona_display = f"{pdata.emoji} {pdata.display_name}"

        text, title = await self._resolve_export_text(
            update, context, user_id, persona_display, "md Export"
        )
        if text is None:
            return

        md_body = text
        md_body = re.sub(r'<b>(.*?)</b>', r'**\1**', md_body, flags=re.DOTALL)
        md_body = re.sub(r'<i>(.*?)</i>', r'*\1*', md_body, flags=re.DOTALL)
        md_body = re.sub(r'<code>(.*?)</code>', r'`\1`', md_body, flags=re.DOTALL)
        md_body = re.sub(r'<pre>(.*?)</pre>', r'```\n\1\n```', md_body, flags=re.DOTALL)
        md_body = re.sub(r'<br\s*/?>', '\n', md_body)
        md_body = re.sub(r'<[^>]+>', '', md_body)

        md = f"# {title}\n\n"
        md += f"*Persona: {persona_display}*\n\n---\n\n"
        md += md_body
        md += f"\n\n---\n*Generated by LP\\_GodFather v4 — {time.strftime('%Y-%m-%d %H:%M:%S')}*"

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(md)
            tmp_path = f.name
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"godfather_{int(time.time())}.md",
                    caption=f"📝 <b>{html.escape(title)}</b>",
                    parse_mode=ParseMode.HTML,
                )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def cmd_csv(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id_int = update.effective_user.id
        user_id = str(user_id_int)
        import io, csv

        history = self.conversations.get(user_id_int, [])
        if not history:
            await update.message.reply_text(
                "Keine Chat-History gefunden. Schreib mir erst was.",
                parse_mode=ParseMode.HTML,
            )
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["role", "content"])
        for msg in history:
            writer.writerow([msg.get("role", ""), msg.get("content", "")])

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
            tmp_path = f.name
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"chat_history_{int(time.time())}.csv",
                    caption=f"📊 <b>Chat History</b> ({len(history)} messages)",
                    parse_mode=ParseMode.HTML,
                )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def cmd_sysinfo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import subprocess

        uptime_sec = time.time() - self.bot_start
        days, rem = divmod(int(uptime_sec), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        bot_uptime = f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"

        def sh(cmd: str) -> str:
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                return r.stdout.strip()
            except Exception:
                return "N/A"

        cpu = sh("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'") or sh("grep -c ^processor /proc/cpuinfo")
        ram_total = sh("free -h | awk '/^Mem:/{print $2}'")
        ram_used = sh("free -h | awk '/^Mem:/{print $3}'")
        disk = sh("df -h / | awk 'NR==2{print $3 \"/\" $2}'")
        load = sh("cat /proc/loadavg | awk '{print $1, $2, $3}'")
        kernel = sh("uname -r")
        hostname = sh("cat /proc/sys/kernel/hostname")
        python_v = sh("python3 --version 2>&1")

        servers = await self.ollama.check_all_servers()
        ollama_lines = []
        for srv in servers:
            status = "🟢" if srv.get("ok") else "🔴"
            ollama_lines.append(f"{status} <b>{srv.get('name', '?')}</b> ({srv.get('url', '?')})")
            if srv.get("models"):
                for m in srv["models"]:
                    ollama_lines.append(f"  · <code>{html.escape(m.get('name', m))}</code>")
            else:
                ollama_lines.append(f"  · <i>keine Models geladen</i>")

        text_parts = [
            f"<b>🦾 LP_GodFather v4 — System Dashboard</b>\n",
            f"<b>🤖 Bot</b>",
            f"  PID: {os.getpid()}",
            f"  Uptime: {bot_uptime}",
            f"  Python: {python_v}",
            f"  Host: {hostname}",
            f"",
            f"<b>💻 Server</b>",
            f"  CPU Load: {load}",
            f"  RAM: {ram_used} / {ram_total}",
            f"  Disk (/): {disk}",
            f"  Kernel: {kernel}",
            f"",
            f"<b>🧠 Ollama</b>",
            *ollama_lines, "",
        ]

        text = "\n".join(text_parts)

        if context.args and context.args[0].lower() == "json":
            json_data = {
                "bot": {"pid": os.getpid(), "uptime_sec": uptime_sec, "python": python_v, "hostname": hostname},
                "system": {"cpu_load": load, "ram": f"{ram_used}/{ram_total}", "disk": disk, "kernel": kernel},
                "ollama": [
                    {"name": s.get("name"), "url": s.get("url"), "ok": s.get("ok")} for s in servers
                ],
            }
            import json
            payload = json.dumps(json_data, indent=2)
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                f.write(payload + "\n")
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"sysinfo_{int(time.time())}.json",
                        caption=f"📊 <b>System Info JSON</b>",
                        parse_mode=ParseMode.HTML,
                    )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return

        import tempfile
        doc = self._build_html_doc("System Dashboard", text, "GODFATHER 💀")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(doc)
            tmp_path = f.name
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"sysinfo_{int(time.time())}.html",
                    caption=f"📊 <b>System Dashboard</b>",
                    parse_mode=ParseMode.HTML,
                )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if chat_id in self._voice_enabled:
            self._voice_enabled.discard(chat_id)
            await update.message.reply_text("🔇 Voice replies OFF. Text only.", parse_mode=ParseMode.HTML)
        else:
            self._voice_enabled.add(chat_id)
            await update.message.reply_text("🔊 Voice replies ON! Ich rede mit dir, Choom.", parse_mode=ParseMode.HTML)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error("Telegram error: %s", context.error)

    def build(self) -> Application:
        app = ApplicationBuilder().token(self.token).post_init(self.post_init).build()

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("persona", self.cmd_persona))
        app.add_handler(CommandHandler("personas", self.cmd_persona))
        app.add_handler(CommandHandler("flow", self.cmd_flow))
        app.add_handler(CommandHandler("vibe", self.cmd_vibe))
        app.add_handler(CommandHandler("supernova", self.cmd_supernova))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("servers", self.cmd_servers))
        app.add_handler(CommandHandler("model", self.cmd_model))
        app.add_handler(CommandHandler("models", self.cmd_models))
        app.add_handler(CommandHandler("pull", self.cmd_pull))
        app.add_handler(CommandHandler("history", self.cmd_history))
        app.add_handler(CommandHandler("clear", self.cmd_clear))
        app.add_handler(CommandHandler("html", self.cmd_html))
        app.add_handler(CommandHandler("json", self.cmd_json))
        app.add_handler(CommandHandler("md", self.cmd_md))
        app.add_handler(CommandHandler("csv", self.cmd_csv))
        app.add_handler(CommandHandler("sysinfo", self.cmd_sysinfo))
        app.add_handler(CommandHandler("voice", self.cmd_voice))
        app.add_handler(CommandHandler("about", self.cmd_about))
        app.add_handler(CommandHandler("interview", self.cmd_interview))
        app.add_handler(CommandHandler("hard", self.cmd_interview_hard))
        app.add_handler(CommandHandler("remember", self.cmd_remember))
        app.add_handler(CommandHandler("recall", self.cmd_recall))
        app.add_handler(CommandHandler("forget", self.cmd_forget))
        app.add_handler(CommandHandler("whitelist", self.cmd_whitelist))
        app.add_handler(CommandHandler("unwhitelist", self.cmd_unwhitelist))

        for cmd in self.registry.get_all():
            app.add_handler(CommandHandler(cmd.name, self.cmd_registry_dispatch))

        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))

        app.add_error_handler(self.error_handler)
        self.app = app
        return app
