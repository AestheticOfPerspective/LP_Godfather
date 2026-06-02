"""
handlers/hermes_router.py — Telegram-first Hermes Primary Router bridge.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from config import (
    ADMIN_IDS,
    HERMES_ALLOWED_CHAT_IDS,
    HERMES_ALLOWED_CHAT_TITLES,
    HERMES_DEFAULT_DJ_MODE,
    HERMES_DEFAULT_PHASE,
    HERMES_ROUTER_ENABLED,
    HERMES_ROUTER_TIMEOUT,
    HERMES_ROUTER_TOKEN,
    HERMES_ROUTER_URL,
)

logger = logging.getLogger(__name__)

PHASES = ("prep", "live", "post", "archive")

NAMESPACE_COMMANDS: dict[str, set[str]] = {
    "live": {"preflight", "go", "checkpoint", "brb", "panic", "outro", "state"},
    "dj": {"mode", "drop", "switch8", "recover", "lock", "state"},
    "ops": {"status", "diag", "fallback", "queue", "state", "chatid"},
    "chronik": {"log", "recap", "extract", "next", "state"},
}

ADMIN_ONLY_COMMANDS: set[tuple[str, str]] = {
    ("live", "preflight"),
    ("live", "go"),
    ("live", "panic"),
    ("live", "outro"),
    ("dj", "mode"),
    ("dj", "drop"),
    ("dj", "switch8"),
    ("dj", "recover"),
    ("dj", "lock"),
    ("ops", "diag"),
    ("ops", "fallback"),
    ("ops", "queue"),
    ("chronik", "extract"),
    ("chronik", "next"),
}

STATE_TRANSITIONS: dict[tuple[str, str, str], str] = {
    ("live", "preflight", "prep"): "prep",
    ("live", "go", "prep"): "live",
    ("live", "checkpoint", "live"): "live",
    ("live", "brb", "live"): "live",
    ("live", "panic", "live"): "prep",
    ("live", "panic", "post"): "prep",
    ("live", "outro", "live"): "post",
    ("chronik", "recap", "post"): "archive",
    ("chronik", "next", "archive"): "prep",
}

ROUTER_STATE: dict[str, str] = {
    "phase": HERMES_DEFAULT_PHASE if HERMES_DEFAULT_PHASE in PHASES else "prep",
    "dj_mode": HERMES_DEFAULT_DJ_MODE,
    "last_namespace": "",
    "last_subcommand": "",
    "last_error": "",
}


def _phase_gate(namespace: str, subcommand: str, phase: str) -> bool:
    if subcommand == "state":
        return True
    if namespace == "live" and subcommand == "go" and phase != "prep":
        return False
    if namespace == "live" and subcommand in {"checkpoint", "brb", "outro"} and phase != "live":
        return False
    if namespace == "chronik" and subcommand == "recap" and phase != "post":
        return False
    if namespace == "chronik" and subcommand == "next" and phase != "archive":
        return False
    return True


async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return False
    if user.id in ADMIN_IDS:
        return True
    if not chat or chat.type not in ("group", "supergroup"):
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
    except Exception:
        logger.exception("Admin check failed for user=%s chat=%s", user.id, getattr(chat, "id", "?"))
        return False
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


def _allowed_chat(update: Update) -> bool:
    if not HERMES_ALLOWED_CHAT_IDS and not HERMES_ALLOWED_CHAT_TITLES:
        return True
    chat = update.effective_chat
    if not chat:
        return False
    if chat.id in HERMES_ALLOWED_CHAT_IDS:
        return True
    title = (chat.title or "").strip().lower()
    if title and title in HERMES_ALLOWED_CHAT_TITLES:
        return True
    return False


def _usage(namespace: str) -> str:
    examples = {
        "live": "/live preflight | /live go | /live checkpoint | /live brb | /live panic | /live outro",
        "dj": "/dj mode cyber-zen | /dj drop | /dj switch8 | /dj recover | /dj lock",
        "ops": "/ops status | /ops diag | /ops fallback | /ops queue | /ops chatid",
        "chronik": "/chronik log <text> | /chronik recap | /chronik extract | /chronik next",
    }
    return examples.get(namespace, "")


def _normalize_route(namespace: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, list[str]]:
    args = [a.strip() for a in (context.args or []) if a.strip()]
    if not args:
        return "", []
    subcommand = args[0].lower()
    rest = args[1:]
    return subcommand, rest


def _apply_transition(namespace: str, subcommand: str) -> str:
    current = ROUTER_STATE["phase"]
    nxt = STATE_TRANSITIONS.get((namespace, subcommand, current), current)
    ROUTER_STATE["phase"] = nxt
    ROUTER_STATE["last_namespace"] = namespace
    ROUTER_STATE["last_subcommand"] = subcommand
    return nxt


def _router_status_text() -> str:
    return (
        "🛰️ <b>Hermes Router Status</b>\n"
        f"Phase: <b>{ROUTER_STATE['phase']}</b>\n"
        f"DJ Mode: <b>{ROUTER_STATE['dj_mode']}</b>\n"
        f"Last: <code>{ROUTER_STATE['last_namespace']} {ROUTER_STATE['last_subcommand']}</code>\n"
        f"Hermes Forwarding: <b>{'ON' if HERMES_ROUTER_ENABLED else 'OFF'}</b>"
    )


async def _forward_to_hermes(
    namespace: str,
    subcommand: str,
    args: list[str],
    update: Update,
) -> tuple[bool, str]:
    if not HERMES_ROUTER_ENABLED:
        return True, "forwarding disabled"
    if not HERMES_ROUTER_URL:
        return False, "HERMES_ROUTER_URL fehlt"

    payload = {
        "namespace": namespace,
        "subcommand": subcommand,
        "args": args,
        "phase": ROUTER_STATE["phase"],
        "dj_mode": ROUTER_STATE["dj_mode"],
        "chat": {
            "id": update.effective_chat.id if update.effective_chat else None,
            "type": update.effective_chat.type if update.effective_chat else None,
        },
        "user": {
            "id": update.effective_user.id if update.effective_user else None,
            "username": update.effective_user.username if update.effective_user else None,
        },
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    headers = {"Content-Type": "application/json"}
    if HERMES_ROUTER_TOKEN:
        headers["Authorization"] = f"Bearer {HERMES_ROUTER_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=HERMES_ROUTER_TIMEOUT) as client:
            resp = await client.post(HERMES_ROUTER_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            message = data.get("message", "ok") if isinstance(data, dict) else "ok"
            return True, message
    except Exception as exc:
        logger.exception("Hermes forwarding failed")
        return False, str(exc)


async def handle_namespace_command(
    namespace: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message:
        return

    subcommand, args = _normalize_route(namespace, context)
    if not subcommand:
        await update.message.reply_text(_usage(namespace), parse_mode="HTML")
        return

    if not _allowed_chat(update):
        if not (namespace == "ops" and subcommand == "chatid"):
            await update.message.reply_text("🚫 Dieser Chat ist nicht für Hermes Routing freigeschaltet.")
            return

    allowed = NAMESPACE_COMMANDS.get(namespace, set())
    if subcommand not in allowed:
        await update.message.reply_text(
            f"❓ Unbekannter Subcommand: <code>{subcommand}</code>\n{_usage(namespace)}",
            parse_mode="HTML",
        )
        return

    if (namespace, subcommand) in ADMIN_ONLY_COMMANDS and not await _is_admin(update, context):
        await update.message.reply_text("🚫 Nur Admins duerfen diesen Command ausführen.")
        return

    phase = ROUTER_STATE["phase"]
    if not _phase_gate(namespace, subcommand, phase):
        await update.message.reply_text(
            f"⛔ Command aktuell gesperrt im Phase-State <b>{phase}</b>.",
            parse_mode="HTML",
        )
        return

    if namespace == "dj" and subcommand == "mode":
        if not args:
            await update.message.reply_text("🎚️ Nutzung: <code>/dj mode cyber-zen</code>", parse_mode="HTML")
            return
        ROUTER_STATE["dj_mode"] = args[0].lower()

    if namespace == "ops" and subcommand == "status":
        await update.message.reply_text(_router_status_text(), parse_mode="HTML")
        return

    if namespace == "ops" and subcommand == "chatid":
        chat = update.effective_chat
        title = chat.title if chat and chat.title else "(no title)"
        cid = chat.id if chat else "?"
        await update.message.reply_text(
            "🧭 <b>Telegram Chat Context</b>\n"
            f"Title: <b>{title}</b>\n"
            f"Chat ID: <code>{cid}</code>\n"
            "Add this ID to <code>HERMES_ALLOWED_CHAT_IDS</code> in .env",
            parse_mode="HTML",
        )
        return

    if subcommand == "state":
        await update.message.reply_text(_router_status_text(), parse_mode="HTML")
        return

    next_phase = _apply_transition(namespace, subcommand)
    ok, detail = await _forward_to_hermes(namespace, subcommand, args, update)
    if not ok:
        ROUTER_STATE["last_error"] = detail
        await update.message.reply_text(
            "⚠️ Hermes nicht erreichbar — Local Guard State bleibt aktiv.\n"
            f"Command: <code>/{namespace} {subcommand}</code>\n"
            f"Phase: <b>{next_phase}</b>",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        f"✅ <b>Hermes Route OK</b>\n"
        f"Command: <code>/{namespace} {subcommand}</code>\n"
        f"Phase: <b>{next_phase}</b>\n"
        f"Detail: <code>{detail}</code>",
        parse_mode="HTML",
    )


async def cmd_live(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_namespace_command("live", update, context)


async def cmd_dj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_namespace_command("dj", update, context)


async def cmd_ops(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_namespace_command("ops", update, context)


async def cmd_chronik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_namespace_command("chronik", update, context)
