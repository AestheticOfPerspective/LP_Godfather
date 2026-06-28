"""Antigravity CLI integration — /antigravity command handler."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS

logger = logging.getLogger(__name__)


async def cmd_antigravity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if not context.args:
        await update.message.reply_text(
            "🤖 <b>Antigravity CLI Agent</b>\n\n"
            "Nutzung:\n"
            "<code>/antigravity &lt;aufgabe&gt;</code> — Führe eine komplexe Aufgabe aus\n"
            "<code>/antigravity setup</code> — Antigravity authentifizieren (Admin)\n\n"
            "Der Agent kann: Multi-Step Reasoning, Code ausführen, Dateien bearbeiten, Web-Recherche.",
            parse_mode=ParseMode.HTML,
        )
        return

    if context.args[0].lower() == "setup":
        if not user or user.id not in ADMIN_IDS:
            await update.message.reply_text("🚫 Nur Admins.")
            return
        await update.message.reply_text("🔄 Starte Antigravity Auth...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "agy", "--prompt", "auth test",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            output = stderr.decode() if stderr else "(no output)"
            if "https://" in output:
                import re
                urls = re.findall(r"https?://\S+", output)
                auth_url = urls[0] if urls else None
                if auth_url:
                    await update.message.reply_text(
                        f"🔑 Auth-URL:\n{auth_url}\n\n"
                        "Öffne den Link im Browser und logge dich ein. "
                        "Danach ist Antigravity bereit.",
                    )
                    return
            await update.message.reply_text(
                f"❌ Konnte keine Auth-URL finden.\n<pre>{output[:1000]}</pre>",
                parse_mode=ParseMode.HTML,
            )
        except FileNotFoundError:
            await update.message.reply_text("❌ `agy` ist nicht installiert. Admin muss Container neu bauen.")
        except asyncio.TimeoutError:
            await update.message.reply_text("⏱️ Timeout.")
        except Exception as e:
            logger.error("antigravity setup error: %s", e)
            await update.message.reply_text(f"❌ Fehler: {e}")
        return

    prompt = " ".join(context.args)
    msg = await update.message.reply_text("🤖 Antigravity Agent denkt nach...")

    try:
        proc = await asyncio.create_subprocess_exec(
            "agy", "--prompt", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode == 0:
            result = stdout.decode().strip()
            if result:
                await msg.edit_text(
                    f"🤖 <b>Antigravity:</b>\n\n{result[:3000]}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await msg.edit_text("✅ Antigravity erledigt (keine Ausgabe).")
        else:
            error = stderr.decode().strip()[:500]
            if "auth" in error.lower() or "sign" in error.lower():
                await msg.edit_text("🔑 Antigravity nicht authentifiziert. Admin: `/antigravity setup`")
            else:
                await msg.edit_text(f"❌ Fehler ({proc.returncode}): {error}")
    except FileNotFoundError:
        await msg.edit_text("❌ `agy` nicht installiert. Admin muss Container neu bauen.")
    except asyncio.TimeoutError:
        await msg.edit_text("⏱️ Antigravity hat zu lange gebraucht (Limit 120s).")
    except Exception as e:
        logger.error("antigravity error: %s", e)
        await msg.edit_text(f"❌ Fehler: {e}")
