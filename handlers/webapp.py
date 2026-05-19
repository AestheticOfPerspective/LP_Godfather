from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

async def show_goals_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows the Goal Tracker web app.
    """
    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Goal Tracker öffnen",
                web_app=WebAppInfo(url="https://65f889d533b79a0008420653--lifeplay-goal-tracker.netlify.app/")
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Klicke, um deine Ziele zu verwalten:",
        reply_markup=reply_markup
    )
