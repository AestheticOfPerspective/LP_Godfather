"""Memory handler — User-Facts speichern, suchen, verwalten.

Commands:
  /remember <fact>  – Speichert einen Fakt über dich
  /recall <topic>   – Durchsucht deine gespeicherten Fakten
  /forget <id>      – Löscht einen bestimmten Fakt
  /mymemories       – Listet alle deine Fakten auf
"""

from html import escape

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.storage import db


async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/remember Dein Fakt hier</code>\n\n"
            "Beispiel: <code>/remember Ich mag starken Kaffee zum Coden</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    fact = " ".join(context.args).strip()
    if len(fact) > 500:
        await update.message.reply_text("❌ Maximal 500 Zeichen, Choom.")
        return

    uid = str(user.id)
    count = db.count_user_facts(uid)
    if count >= 50:
        await update.message.reply_text(
            "❌ Maximal 50 Fakten pro User. Lösche alte mit <code>/forget</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    fact_id = db.add_user_fact(uid, fact)
    await update.message.reply_text(
        f"🧠 <b>Fakt gespeichert!</b> (ID #{fact_id})\n"
        f"„{escape(fact)}“\n\n"
        "Ich merke mir das für unsere Gespräche, Choom.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_recall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/recall Suchbegriff</code>\n\n"
            "Durchsucht deine gespeicherten Fakten nach dem Begriff.",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args).strip()
    uid = str(user.id)
    results = db.search_user_facts(uid, query)

    if not results:
        await update.message.reply_text(
            f"🔍 Keine Fakten zu „{escape(query)}“ gefunden.\n"
            "Nutze <code>/remember</code> um mir etwas über dich beizubringen.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"🧠 Fakten zu „{escape(query)}“:\n"]
    for fid, fact_text, created_at in results[:10]:
        lines.append(f"  #{fid}  {escape(fact_text)}")
    if len(results) > 10:
        lines.append(f"\n… und {len(results) - 10} weitere.")
    lines.append("\nDetails mit <code>/mymemories</code> oder löschen mit <code>/forget</code>.")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    if not context.args:
        await update.message.reply_text(
            "❓ Nutzung: <code>/forget 3</code>\n\n"
            "Löscht den Fakt mit der angegebenen ID.\n"
            "IDs findest du mit <code>/mymemories</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        fact_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Bitte eine gültige ID-Nummer angeben.")
        return

    uid = str(user.id)
    if db.delete_user_fact(fact_id, uid):
        await update.message.reply_text(
            f"🧹 Fakt #{fact_id} gelöscht, Choom.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "❌ Kein Fakt mit dieser ID gefunden (oder er gehört dir nicht).",
            parse_mode=ParseMode.HTML,
        )


async def cmd_mymemories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    uid = str(user.id)
    facts = db.get_user_facts(uid)

    if not facts:
        await update.message.reply_text(
            "🧠 Du hast noch keine gespeicherten Fakten.\n"
            "Nutze <code>/remember</code> um mir etwas über dich beizubringen!",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = ["🧠 <b>Deine gespeicherten Fakten</b>\n"]
    for fid, fact_text, created_at in facts:
        lines.append(f"  #{fid}  {escape(fact_text)}")
    lines.append(f"\nGesamt: {len(facts)} Fakten\nLöschen mit <code>/forget &lt;ID&gt;</code>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
