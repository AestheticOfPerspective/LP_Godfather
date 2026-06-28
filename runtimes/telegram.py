#!/usr/bin/env python3
"""
Telegram Runtime — GodFather Bot als Telegram-Bot
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime

# Fix fuer python-telegram-bot + Python 3.14 (kein Event-Loop in MainThread)
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    MessageReactionHandler,
    filters,
)
from telegram.constants import ParseMode, ChatMemberStatus
from html import escape

from config import BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS, WELCOME_ENABLED
from handlers.ai import (
    ask_ai,
    PERSONAS,
    get_user_persona,
    set_user_persona,
    get_persona_keyboard,
    clear_history,
    suggest_persona,
    telegram_safe_response,
)
from handlers.products import get_products_menu
from handlers.chat_context import build_chat_context_text, chat_maturity_level
from handlers.admin import (
    cmd_ban,
    cmd_kick,
    cmd_warn,
    cmd_warns,
    cmd_mute,
    cmd_unmute,
    cmd_stats,
)
from handlers.voice import handle_voice
from handlers.ains import handle_text_message
from handlers.dj import (
    generate_vibe_playlist,
    format_playlist,
    get_vibe_keyboard,
    VIBE_PRESETS,
)
from handlers.webapp import show_goals_webapp
from handlers.hermes_router import cmd_live, cmd_dj, cmd_ops, cmd_chronik
from handlers.orchestrate import cmd_orchestrate
from handlers.tarot import cmd_tarot, handle_tarot_callback
from handlers.stream import (
    format_clip,
    format_clip_saved,
    format_follow,
    format_heute,
    format_recap,
    format_recap_saved,
    format_wann,
)
from handlers.memory import cmd_remember, cmd_recall, cmd_forget, cmd_mymemories
from handlers.train import cmd_teach, cmd_knowledge, cmd_trainings, cmd_forget_training
from handlers.hilfe import cmd_hilfe, handle_hilfe_callback
from handlers.feedback import (
    format_feedback_summary,
    handle_message_reaction,
    handle_sticker_feedback,
)
from handlers.skill_creator import cmd_skills
from handlers.maintenance import cmd_maintenance
from handlers.comedy_test import check_clip
from handlers.supernova import cmd_supernova
from handlers.promo import cmd_promo
from handlers.amazon import cmd_deals
from handlers.revive import cmd_revive, cmd_activity
from handlers.mastering import cmd_mastering, cmd_queue, cmd_status, cmd_update_status, route_mastering
from handlers.antigravity import cmd_antigravity
from utils.decorators import admin_only, group_only
from utils.storage import db

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("GodFatherBot")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"Yo, <b>{user.first_name}</b>. 💀\n\n"
        "Ich bin <b>GodFather</b> — der Community-Bot von <b>Life.Play</b>.\n\n"
        "Was ich kann:\n"
        "• Gruppen moderieren (Warn, Mute, Ban)\n"
        "• Fragen via KI beantworten (Text & Sprache)\n"
        "• 🎙️ Voice Commands — Sprachnachricht = KI-Antwort\n"
        "• 6 wählbare KI-Personas\n"
        "• Produkt-Infos & Preise zeigen\n"
        "• Neue Member willkommen heißen\n"
        "• Stats und Reports ausgeben\n\n"
        "Tippe /help für alle Commands. Let's go, Choom. 🔥"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Produkte", callback_data="products"),
         InlineKeyboardButton("🤖 KI fragen", callback_data="ai_help")],
        [InlineKeyboardButton("🎭 Persona wählen", callback_data="persona_menu"),
         InlineKeyboardButton("📖 Source Code", url="https://github.com/AestheticOfPerspective/LP_Godfather")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📋 <b>GodFather Command-Liste</b>\n\n"
        "<b>── Allgemein ──</b>\n"
        "/start – Intro & Menü\n"
        "/help – Diese Liste\n"
        "/products – Life.Play Produkte\n"
        "/personas – KI-Persona Produkt-Übersicht\n"
        "/about – Über Life.Play\n"
        "/wann – JutsuGaming Wochenplan\n"
        "/heute – Stream heute?\n"
        "/follow – Twitch/YouTube Links\n"
        "/clip – Clip-Moment einreichen\n"
        "/recap – Letzten Stream-Recap anzeigen\n\n"
        "<b>── KI ──</b>\n"
         "/ask [Frage] – KI fragen\n"
         "/orchestrate [Frage] – Multi-Persona Perspektiven\n"
          "/persona – KI-Persona wechseln\n"
          "/prompt [Text] – Prompt-Engineering Tipp\n"
        "/tarot – Nyx.exe Tarot-Orakel\n"
         "/clear – Gesprächsverlauf löschen\n"
        "/vibe [preset] – DJ-Agent Playlist erstellen\n"
        "/promo – Edgerunner Cross-Promotion: alle Channels & Vorlagen\n"
        "/deals – Gaming-Streaming Tech auf Amazon (Partnerlinks)\n"
        "/mastering – Mixing & Mastering Track einreichen\n"
        "/supernova – SUPERNOVA Campaign Status & Countdown\n"
        "🎙️ Sprachnachricht – wird transkribiert + KI antwortet\n"
        "💬 Bot merkt sich die letzten 5 Nachrichten pro User\n\n"
        "<b>── Hermes Router (Primary) ──</b>\n"
        "/live [sub] – Stream State & Orchestration\n"
        "/dj [sub] – DJ Actions & Mode\n"
        "/ops [sub] – Runtime/Ops Status\n"
        "/chronik [sub] – Recap & Learnings\n\n"
        "<b>── Moderation (Admins) ──</b>\n"
        "/warn @user [Grund] – Verwarnung\n"
        "/warns @user – Verwarnungen anzeigen\n"
        "/mute @user [Minuten] – Stummschalten\n"
        "/unmute @user – Stummschaltung aufheben\n"
        "/kick @user [Grund] – Kicken\n"
        "/ban @user [Grund] – Bannen\n"
        "/stats – Gruppen-Statistiken\n\n"
        "<i>Life.Play — Built different. 💀</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🌐 <b>Life.Play</b>\n\n"
        "Premium-Hub für Creator & KI-Entwickler im DACH-Raum.\n\n"
        "🎨 <b>Was wir machen:</b>\n"
        "• OBS-Setups & Streaming-Ressourcen\n"
        "• KI-Persona Designs & Prompt-Packs\n"
        "• Custom AI-Agent Development\n"
        "• Live-Coaching & Workshops\n\n"
        "💡 <b>Philosophie:</b> FOSS-Ethik trifft Commercial.\n"
        "Pay for Value, not Access.\n\n"
        "🔗 Links folgen bald — Stay tuned, Choom."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_wann(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_wann(), parse_mode=ParseMode.HTML)


async def cmd_heute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_heute(), parse_mode=ParseMode.HTML)


async def cmd_follow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_follow(), parse_mode=ParseMode.HTML)


async def cmd_clip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        user = update.effective_user
        chat = update.effective_chat
        clip_text = " ".join(context.args).strip()
        clip_id = db.add_clip_submission(
            "telegram",
            str(chat.id if chat else "unknown"),
            str(user.id if user else "unknown"),
            user.username or user.first_name if user else "unknown",
            clip_text,
        )
        await update.message.reply_text(format_clip_saved(clip_id), parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text(format_clip(), parse_mode=ParseMode.HTML)


async def cmd_recap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    user = update.effective_user
    if args and args[0].lower() == "add":
        if not user or user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Nur Admins koennen Recaps setzen.")
            return
        body = " ".join(args[1:]).strip()
        if not body:
            await update.message.reply_text("❓ Nutzung: <code>/recap add Kurzfassung des Streams</code>", parse_mode=ParseMode.HTML)
            return
        actor = user.username or user.first_name or str(user.id)
        recap_id = db.add_stream_recap("telegram", actor, body)
        await update.message.reply_text(format_recap_saved(recap_id), parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text(format_recap(db.latest_stream_recap()), parse_mode=ParseMode.HTML)


async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Feedback-Auswertung ist nur für Admins.")
        return
    scope = str(chat.id) if chat and context.args and context.args[0].lower() == "hier" else None
    await update.message.reply_text(format_feedback_summary(scope), parse_mode=ParseMode.HTML)


async def cmd_personas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🤖 <b>Life.Play KI-Personas</b>\n\n"
        "Fertige, kommerziell nutzbare KI-Charakter-Konzepte\n"
        "mit System-Prompts, Backstory & Lore.\n\n"
        "🌐 <b>Cyber-Zen</b> — AI-Mönch-Hacker. Ruhig, pointiert.\n"
        "🌈 <b>Vapor-FOSS</b> — Chilliger Hacker, Vaporwave + Open Source.\n"
        "🌴 <b>Tropical-Infinity</b> — Relaxed, hochfunktional.\n"
        "🐒 <b>Monkey-Mind Poetry</b> — Poeten-Schamane, Zen meets Zirkus.\n"
        "🤘 <b>Punk-Philosopher</b> — Rebellisch, charmant, intelligent-flirty.\n\n"
        "💡 Nutze <code>/persona</code> um eine Persona für /ask zu aktivieren.\n\n"
        "📦 Persona-Packs kaufen:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎭 Persona jetzt wechseln", callback_data="persona_menu")],
        [InlineKeyboardButton("📦 Zu den Persona-Packs", callback_data="products_ai")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cmd_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_key = get_user_persona(user_id)
    current_name = PERSONAS[current_key]["name"]

    text = (
        "🎭 <b>Persona wählen</b>\n\n"
        f"Aktuelle Persona: <b>{current_name}</b>\n\n"
        "Wähle eine KI-Persona für deine /ask Anfragen:\n\n"
        "💀 <b>GodFather</b> — Standard. Cyberpunk, direkt, kein Bullshit.\n"
        "🌐 <b>Cyber-Zen</b> — AI-Mönch. Meditativ, präzise, haikuartig.\n"
        "🌈 <b>Vapor-FOSS</b> — Chill Hacker. Vaporwave + FOSS-Vibes.\n"
        "🌴 <b>Tropical-Infinity</b> — Bali-Dev. Positiv, lösungsorientiert.\n"
        "🐒 <b>Monkey-Mind</b> — Poeten-Schamane. Reime, Beats, Freeflow.\n"
        "🤘 <b>Punk-Philosopher</b> — Rebellisch, flirty, tiefgründig.\n"
        "💜 <b>Nyx.exe</b> — Digitale Muse. Poetisch, empathisch, 3-AM-Talks."
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_persona_keyboard()
    )


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/ask Deine Frage hier</code>",
            parse_mode=ParseMode.HTML
        )
        return

    user_id = update.effective_user.id
    persona_key = get_user_persona(user_id)
    persona_name = PERSONAS[persona_key]["name"]

    question = " ".join(context.args)
    msg = await update.message.reply_text(f"⏳ {persona_name} denkt nach...")

    db.increment_stat("ai_requests")
    chat = update.effective_chat
    maturity = chat_maturity_level(chat)
    response = await ask_ai(
        question,
        user_id=user_id,
        extra_context=build_chat_context_text(chat, update.effective_user),
        is_group=chat.type in ("group", "supergroup") if chat else True,
        fsk_level=maturity,
    )

    suggestion = suggest_persona(question, persona_key)
    hint = ""
    if suggestion:
        s_name = PERSONAS[suggestion]["name"]
        hint = f"\n\n💡 <i>Tipp: {s_name} wäre perfekt für dieses Thema → /persona</i>"

    await msg.edit_text(
        f"{persona_name}:\n\n{telegram_safe_response(response)}{hint}",
        parse_mode=ParseMode.HTML
    )


async def cmd_comedy_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/comedy-test Deine Clip-Idee hier</code>\n\n"
            "Prueft eine Clip-Idee gegen die Comedy Gates:\n"
            "• SATIRE — Ziel klar?\n"
            "• IRONY — Kontrast ohne Insiderwissen?\n"
            "• DARK HUMOR — System/Selbst, nicht Person?\n"
            "• DE/EN/RU SAFE — Uebersetzbar ohne Target-Shift?",
            parse_mode=ParseMode.HTML,
        )
        return

    idea = " ".join(context.args)
    msg = await update.message.reply_text("⏳ Comedy-Gates werden geprueft...")
    result = await check_clip(idea)
    await msg.edit_text(
        f"<b>💀 Comedy Gate Check</b>\n\n<pre>{escape(result)}</pre>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/prompt Dein Prompt-Text</code>\n\n"
            "Ich analysiere deinen Prompt und gebe Verbesserungsvorschläge.",
            parse_mode=ParseMode.HTML
        )
        return

    prompt_text = " ".join(context.args)
    user_id = update.effective_user.id
    persona_key = get_user_persona(user_id)
    persona_name = PERSONAS[persona_key]["name"]

    msg = await update.message.reply_text(f"🔍 {persona_name} analysiert...")

    db.increment_stat("ai_requests")
    chat = update.effective_chat
    maturity = chat_maturity_level(chat)
    response = await ask_ai(
        "Analysiere diesen Prompt als Prompt-Engineering-Experte. "
        "Gib konkrete Verbesserungsvorschlaege. Maximal 3 Punkte, kein Bullshit.\n\n"
        f"Prompt:\n{prompt_text}",
        user_id=user_id,
        extra_context=build_chat_context_text(chat, update.effective_user),
        is_group=chat.type in ("group", "supergroup") if chat else True,
        fsk_level=maturity,
    )
    await msg.edit_text(
        f"🎯 <b>Prompt-Analyse:</b>\n\n{telegram_safe_response(response)}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        vibe_name = context.args[0].lower()
        duration = int(context.args[1]) if len(context.args) > 1 else 60
        if vibe_name not in VIBE_PRESETS:
            presets = ", ".join(VIBE_PRESETS.keys())
            await update.message.reply_text(
                f"❓ Unbekannter Vibe. Verfügbar: <code>{presets}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        msg = await update.message.reply_text(f"🎧 Erstelle {VIBE_PRESETS[vibe_name]['name']} Playlist...")
        playlist = await generate_vibe_playlist(vibe_name, duration)
        await msg.edit_text(format_playlist(playlist, vibe_name), parse_mode=ParseMode.HTML)
    else:
        text = (
            "🎧 <b>DJ-Agent — Vibe Curator</b>\n\n"
            "Wähle einen Vibe für deine Playlist:\n\n"
            "🎯 <b>focus</b> — Deep Work, Coding\n"
            "🌅 <b>chill</b> — Feierabend, Relaxen\n"
            "🎉 <b>party</b> — Streams, Gaming\n"
            "💻 <b>coding</b> — Programming Sessions\n"
            "☀️ <b>morning</b> — Start in den Tag\n\n"
            "Oder: <code>/vibe focus 90</code> (90 Min Playlist)"
        )
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=get_vibe_keyboard()
        )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    clear_history(user_id)
    await update.message.reply_text(
        "🧹 Gesprächsverlauf gelöscht. Frischer Start, Choom.",
        parse_mode=ParseMode.HTML,
    )


async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("vibe_"):
        vibe_name = query.data[len("vibe_"):]
        await query.edit_message_text(f"🎧 Erstelle {VIBE_PRESETS[vibe_name]['name']} Playlist...")
        playlist = await generate_vibe_playlist(vibe_name, 60)
        await query.edit_message_text(
            format_playlist(playlist, vibe_name), parse_mode=ParseMode.HTML
        )
        return

    if query.data == "persona_menu":
        user_id = query.from_user.id
        current_name = PERSONAS[get_user_persona(user_id)]["name"]
        await query.edit_message_text(
            f"🎭 <b>Persona wählen</b>\n\nAktuelle Persona: <b>{current_name}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_persona_keyboard(),
        )
        return

    if query.data.startswith("persona_"):
        persona_key = query.data[len("persona_"):]
        user_id = query.from_user.id
        set_user_persona(user_id, persona_key)
        persona = PERSONAS.get(persona_key, PERSONAS["godfather"])
        await query.answer(f"✅ Persona: {persona['name']}", show_alert=False)
        await query.edit_message_text(
            f"✅ <b>Persona aktiviert!</b>\n\n"
            f"Aktive Persona: <b>{persona['name']}</b>\n\n"
            f"<i>{persona['system'][:120]}…</i>\n\n"
            "Nutze <code>/ask</code> um jetzt die KI zu befragen.",
            parse_mode=ParseMode.HTML,
        )
        return

    if query.data == "products":
        text, keyboard = get_products_menu("all")
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif query.data == "products_ai":
        text, keyboard = get_products_menu("ai")
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif query.data == "products_creator":
        text, keyboard = get_products_menu("creator")
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif query.data == "products_membership":
        text, keyboard = get_products_menu("membership")
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif query.data == "products_back":
        text, keyboard = get_products_menu("all")
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif query.data == "ai_help":
        await query.edit_message_text(
            "🤖 <b>KI-Hilfe</b>\n\n"
            "Nutze <code>/ask [Deine Frage]</code> um die KI zu fragen.\n"
            "Nutze <code>/persona</code> um die Persona zu wechseln.\n"
            "Nutze <code>/prompt [Text]</code> für Prompt-Analyse.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎭 Persona wählen", callback_data="persona_menu")],
                [InlineKeyboardButton("⬅️ Zurück", callback_data="back_start")],
            ])
        )

    elif query.data == "back_start":
        await cmd_start(update, context)


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WELCOME_ENABLED:
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        db.increment_stat("joins")
        name = member.first_name
        chat_title = update.effective_chat.title or "Life.Play"

        text = (
            f"💀 <b>Willkommen, {name}!</b>\n\n"
            f"Du bist jetzt Teil von <b>{chat_title}</b>.\n\n"
            "👋 Schau dich um, lies die Regeln und hab keine Scheu zu fragen.\n"
            "Der GodFather passt auf — /help für Commands."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return

    db.increment_stat("messages")

    user = update.effective_user
    chat = update.effective_chat
    if user and chat and not user.is_bot:
        db.touch_user(str(chat.id), str(user.id), user.username or user.first_name or "")

    if chat.type in ("group", "supergroup"):
        member = await context.bot.get_chat_member(chat.id, user.id)
        is_new = member.status == ChatMemberStatus.MEMBER

        suspicious_patterns = ["t.me/", "http://", "https://", "@"]
        link_count = sum(msg.text.count(p) for p in suspicious_patterns)

        if is_new and link_count >= 3:
            try:
                await msg.delete()
                await context.bot.send_message(
                    chat.id,
                    f"⚠️ {user.mention_html()}, keine Links für neue Member. "
                    "Warte etwas und versuch's nochmal.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.warning(f"Konnte Nachricht nicht löschen: {e}")


async def handle_products_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, keyboard = get_products_menu("all")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


def run() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN fehlt in .env / config.py!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("hilfe", cmd_hilfe))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("wann", cmd_wann))
    app.add_handler(CommandHandler("heute", cmd_heute))
    app.add_handler(CommandHandler("follow", cmd_follow))
    app.add_handler(CommandHandler("clip", cmd_clip))
    app.add_handler(CommandHandler("recap", cmd_recap))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CommandHandler("personas", cmd_personas))
    app.add_handler(CommandHandler("persona", cmd_persona))
    app.add_handler(CommandHandler("products", lambda u, c: handle_products_cmd(u, c)))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("prompt", cmd_prompt))
    app.add_handler(CommandHandler("orchestrate", cmd_orchestrate))
    app.add_handler(CommandHandler("comedy_test", cmd_comedy_test))
    app.add_handler(CommandHandler("comedytest", cmd_comedy_test))
    app.add_handler(CommandHandler("ctest", cmd_comedy_test))
    app.add_handler(CommandHandler("tarot", cmd_tarot))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("vibe", cmd_vibe))
    app.add_handler(CommandHandler("supernova", cmd_supernova))
    app.add_handler(CommandHandler("promo", cmd_promo))
    app.add_handler(CommandHandler("deals", cmd_deals))
    app.add_handler(CommandHandler("mastering", cmd_mastering))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("updatestatus", cmd_update_status))
    app.add_handler(MessageHandler(filters.TEXT | filters.AUDIO | filters.VOICE | filters.Document.AUDIO, route_mastering))

    app.add_handler(CommandHandler("skills", cmd_skills))

    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("recall", cmd_recall))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("mymemories", cmd_mymemories))

    app.add_handler(CommandHandler("teach", cmd_teach))
    app.add_handler(CommandHandler("knowledge", cmd_knowledge))
    app.add_handler(CommandHandler("trainings", cmd_trainings))
    app.add_handler(CommandHandler("forget_training", cmd_forget_training))
    app.add_handler(CommandHandler("goals", show_goals_webapp))
    app.add_handler(CommandHandler("live", cmd_live))
    app.add_handler(CommandHandler("dj", cmd_dj))
    app.add_handler(CommandHandler("ops", cmd_ops))
    app.add_handler(CommandHandler("chronik", cmd_chronik))

    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("warns", cmd_warns))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("revive", cmd_revive))
    app.add_handler(CommandHandler("activity", cmd_activity))
    app.add_handler(CommandHandler("antigravity", cmd_antigravity))

    app.add_handler(CallbackQueryHandler(handle_tarot_callback, pattern=r"^tarot_"))
    app.add_handler(CallbackQueryHandler(handle_hilfe_callback, pattern=r"^hilfe_"))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageReactionHandler(handle_message_reaction))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker_feedback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("GodFather Bot startet... 💀")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
