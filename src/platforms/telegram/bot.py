from __future__ import annotations
import os
import time
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

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, persona_engine: PersonaFlowEngine,
                 ollama: OllamaClient, db: Database, config_dir: Path):
        self.engine = persona_engine
        self.ollama = ollama
        self.db = db
        self.config_dir = config_dir
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.admin_ids = self._parse_admin_ids()
        self.bot_start = time.time()

        self.user_models: dict[int, str] = {}
        self.conversations: dict[int, list] = {}
        self.user_system_prompts: dict[int, str] = {}
        self.app: Optional[Application] = None

    def _parse_admin_ids(self) -> list[int]:
        raw = os.getenv("ADMIN_IDS", "")
        return [int(x) for x in raw.split(",") if x.strip()]

    def _get_persona(self, update: Update) -> str:
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        state = self.engine.get_state("telegram", chat_id, user_id)
        return state.current.value

    def _build_system_prompt(self, persona_name: str, user_id: int) -> str:
        custom = self.user_system_prompts.get(user_id)
        if custom:
            return custom

        pdata = self.engine.get_persona_info(PersonaName(persona_name))
        return (
            f"You are {pdata.display_name} {pdata.emoji}\n"
            f"Style: {pdata.style}\n\n"
            f"You are part of the Live.Play ecosystem on Beast Tower. "
            f"Answer concisely but with personality. "
            f"Use Telegram MarkdownV2: *bold*, _italic_, `code`. "
            f"Keep messages under 4000 characters. "
            f"Stay in character as {pdata.display_name}."
        )

    async def post_init(self, app: Application):
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
            BotCommand("about", "Bot info & credits"),
        ]
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
                "<i>💡 Tip: Personas flow automatically based on your vibe!</i>"
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
                "<b>🤖 AI Model:</b>\n"
                "/model [name] — Show/switch model\n"
                "/models — List all models\n"
                "/pull [name] — Download a model\n\n"
                "<b>📊 System:</b>\n"
                "/status — System dashboard\n"
                "/servers — Ollama server status\n"
                "/about — Bot info & credits\n\n"
                "<i>9 personas flow naturally. No command needed!</i>"
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
                msg, switched = self.engine.force_persona(
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
        target, msg = self.engine.set_vibe("telegram", chat_id, uid, vibe)

        if target is None:
            await update.message.reply_text(msg)
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
        msg, switched = self.engine.force_persona("telegram", chat_id, uid, target)
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
                    f"Switched to: <code>{html.escape(new_model)}</code>",
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
        count = len(self.conversations.get(user_id, []))
        self.conversations[user_id] = []
        await update.message.reply_text(f"Cleared {count} messages. Fresh start, choom!")

    async def cmd_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uptime = time.time() - self.bot_start
        days, rem = divmod(int(uptime), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)

        text = (
            "<b>LP_GodFather v4</b>\n"
            "<i>Edgerunner Flowing Persona Engine</i>\n\n"
            "9 personas flow naturally based on:\n"
            "  🎭 Context, time, sentiment, keywords\n"
            "  ⚡ Probabilistic transition graph\n"
            "  🧠 User affinity learning\n"
            "  🔄 Cross-platform state sync\n\n"
            "<b>Personas:</b>\n"
            "  🎮 CHOOM — Gamer hype\n"
            "  🌌 NOVA — Gene Keys bard\n"
            "  🌐 CYBER-ZEN — Code monk\n"
            "  🌈 VAPOR-FOSS — Open source chill\n"
            "  🥊 BAKI — Raw power\n"
            "  ⚔️ SAMURAI — Warrior code\n"
            "  🤘 PUNK-PHILOSOPHER — Deep rebel\n"
            "  🌴 TROPICAL-INFINITY — Galaxy chill\n"
            "  🐒 MONKEY-MIND — Creative chaos\n\n"
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

        self.db.upsert_user(user_id, "telegram", user.username)

        respond = not is_group
        if is_group:
            text_lower = text.lower()
            triggers = ["godfather", "choom", "nova", "baki", "vibe",
                        "hey bot", "lp_", "edgerunner", "/persona", "/vibe", "/flow"]
            if any(t in text_lower for t in triggers):
                respond = True
            if update.message.reply_to_message and update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.is_bot:
                respond = True

        if not respond:
            return

        persona_name = self._get_persona(update)
        next_persona, did_transition = self.engine.select_next(
            "telegram", chat_id, user_id, text
        )

        if did_transition and next_persona.value != persona_name:
            pdata = self.engine.get_persona_info(next_persona)
            await update.message.reply_text(
                f"<i>{pdata.transition_to}</i>", parse_mode=ParseMode.HTML
            )
            persona_name = next_persona.value

        await update.message.chat.send_action(ChatAction.TYPING)

        system_prompt = self._build_system_prompt(persona_name, user_id_int)
        history = self.conversations.get(user_id_int, [])[-10:]
        history_dicts = history if history else []

        response = await self.ollama.chat(
            user_id=user_id,
            user_message=text,
            system_prompt=system_prompt,
            history=history_dicts,
        )

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

        if user_id_int not in self.conversations:
            self.conversations[user_id_int] = []
        self.conversations[user_id_int].append({"role": "user", "content": text})
        self.conversations[user_id_int].append({"role": "assistant", "content": response.content})

        footer = ""
        if response.success:
            footer = (
                f"\n\n<i>{response.model} | {response.server} | "
                f"{response.tokens} tok | {response.latency_ms}ms</i>"
            )

        await update.message.reply_text(
            html.escape(response.content) + footer,
            parse_mode=ParseMode.HTML,
        )

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

        footer = ""
        if response.success:
            footer = f"\n\n<i>{response.model} | {response.server} | {response.latency_ms}ms</i>"

        await update.message.reply_text(
            html.escape(response.content) + footer,
            parse_mode=ParseMode.HTML,
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error("Telegram error: %s", context.error)

    def build(self) -> Application:
        app = ApplicationBuilder().token(self.token).post_init(self.post_init).build()

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("persona", self.cmd_persona))
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
        app.add_handler(CommandHandler("about", self.cmd_about))

        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        app.add_error_handler(self.error_handler)
        self.app = app
        return app
