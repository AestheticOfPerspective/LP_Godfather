"""
handlers/products.py — Life.Play Produkt-Katalog
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

PRODUCTS = {
    "creator": {
        "title": "🎨 Creator Economy Track",
        "items": [
            ("📦 OBS Starter Pack", "29€", "Komplettes OBS-Profil, Audio-Ducking, 3 Overlays"),
            ("📦 OBS Pro Pack", "79€", "Advanced Audio-Chain, 10+ Overlays, Support-Call"),
            ("📦 OBS Ultimate Bundle", "149€", "Alles + Stream Deck, VoiceMeeter, 3 Monate Updates"),
            ("🎓 Streaming Fundamentals", "49€", "8 Module, OBS bis Advanced, Audio-Engineering"),
            ("🎓 Content Creation Masterclass", "129€", "15 Module, Audience-Building, Monetarisierung"),
        ]
    },
    "ai": {
        "title": "🤖 KI Developer Track",
        "items": [
            ("🤖 Single Persona License", "39€", "Vollständiges Persona-Konzept + System-Prompt + Commercial License"),
            ("🤖 Persona Collection (3er)", "99€", "3 Personas + Cross-Persona Guide + Extended License"),
            ("🤖 Complete Universe", "299€", "Alle Personas + Lore + API-Examples + Lifetime Updates"),
            ("🛠️ Basic AI-Agent", "750€", "Custom Agent Development, 30 Tage Support"),
            ("🛠️ Advanced AI-Agent", "2.500€", "Multi-Tool, RAG, 90 Tage Support"),
        ]
    },
    "membership": {
        "title": "🌟 Membership",
        "items": [
            ("⚡ Supporter", "5€/Monat", "Exclusive Discord, Early Access, Mini-Tutorials"),
            ("🔥 Creator", "15€/Monat", "Wöchentliche Live-Sessions, 10% Rabatt, Resource-Library"),
            ("💎 VIP", "50€/Monat", "1:1 Coaching (1h/Monat), Beta-Zugang, Private Reviews"),
        ]
    }
}


def get_products_menu(category: str) -> tuple[str, InlineKeyboardMarkup]:
    """Gibt Text und Keyboard für die gewählte Produktkategorie zurück."""

    if category == "all":
        text = (
            "📦 <b>Life.Play Produkte</b>\n\n"
            "Wähle eine Kategorie:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎨 Creator Tools", callback_data="products_creator"),
             InlineKeyboardButton("🤖 KI Packs", callback_data="products_ai")],
            [InlineKeyboardButton("🌟 Membership", callback_data="products_membership")],
        ])
        return text, keyboard

    cat = PRODUCTS.get(category)
    if not cat:
        return "❌ Kategorie nicht gefunden.", InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Zurück", callback_data="products_back")
        ]])

    lines = [f"<b>{cat['title']}</b>\n"]
    for name, price, desc in cat["items"]:
        lines.append(f"{name} — <b>{price}</b>")
        lines.append(f"  <i>{desc}</i>\n")

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Zurück", callback_data="products_back")
    ]])
    return text, keyboard
