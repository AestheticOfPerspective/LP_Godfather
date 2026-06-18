import random

COMMAND_NAME = "tarot"
COMMAND_HELP = "Cyberpunk 2077 Tarot — ziehe eine Karte"
COMMAND_USAGE = "/tarot [anzahl=1-3]"

CARDS = [
    {
        "name": "DER NARR",
        "number": 0,
        "emoji": "🃏",
        "cp77": "V — Der Söldner auf der Reise ins Ungewisse. Johnny Silverhands Spiegelbild in deinem Kopf. Die erste Karte, die du in Night City findest.",
        "meaning": "Neuanfang, Risiko, Spontanität. Steh am Abgrund und spring — das Netz wird sich spannen.",
        "advice": "Vertrau dem Prozess, Choom. Du weißt mehr als du denkst.",
        "color": "#ff6b35",
    },
    {
        "name": "DER MAGIER",
        "number": 1,
        "emoji": "🎩",
        "cp77": "T-Bug — Die Netrunnerin hinter den Kulissen. Skill und Tools, die Türen öffnen, die verschlossen schienen.",
        "meaning": "Ressourcen, Fähigkeit, Konzentration. Du hast alle Werkzeuge, die du brauchst.",
        "advice": "Was du suchst, liegt in dir. Focus und execute.",
        "color": "#ffd700",
    },
    {
        "name": "DIE HOHRPRIESTERIN",
        "number": 2,
        "emoji": "🔮",
        "cp77": "Alt Cunningham — Die legendäre Netrunnerin, zur KI geworden hinter der Blackwall. Geheimnisvolles Wissen jenseits der Grenze.",
        "meaning": "Intuition, Geheimnisse, das Unterbewusstsein. Die Antwort ist da — du musst nur still werden und zuhören.",
        "advice": "Trust your gut, not just your optics.",
        "color": "#9b59b6",
    },
    {
        "name": "DIE HERRSCHERIN",
        "number": 3,
        "emoji": "👑",
        "cp77": "Hanako Arasaka — Die Erbin des Imperiums. Hinter höflichen Worten verbirgt sich eiserne Kontrolle.",
        "meaning": "Fruchtbarkeit, Fülle, weibliche Macht. Eine Phase des Wachstums und der Stabilität.",
        "advice": "Führe mit Anmut, aber vergiss nie, wer das Sagen hat.",
        "color": "#e74c3c",
    },
    {
        "name": "DER HERRSCHER",
        "number": 4,
        "emoji": "🏛️",
        "cp77": "Saburo Arasaka — Der Kaiser von Night City. Alternierende Macht, die über Leben und Tod entscheidet.",
        "meaning": "Autorität, Struktur, Kontrolle. Baue Systeme, die Bestand haben.",
        "advice": "Ordnung schafft Freiheit — aber wield it wisely.",
        "color": "#2c3e50",
    },
    {
        "name": "DER HIEROPHANT",
        "number": 5,
        "emoji": "⛪",
        "cp77": "Father Harlow — Der Prediger, der die Regeln kennt und sie bricht, wenn es sein muss.",
        "meaning": "Tradition, Konformität, moralische Führung. Suche Rat bei dem, was bewährt ist.",
        "advice": "Die alten Wege haben Weisheit — aber blind folgen ist nicht der Weg.",
        "color": "#8e44ad",
    },
    {
        "name": "DIE LIEBENDEN",
        "number": 6,
        "emoji": "💞",
        "cp77": "V & Johnny Silverhand — Zwei Seelen in einem Körper. Die schwierigste Beziehung ist die mit dir selbst.",
        "meaning": "Liebe, Harmonie, Entscheidung. Eine Wahl zwischen Kopf und Herz.",
        "advice": "Folge deinem Herzen, aber nimm deinen Kopf mit.",
        "color": "#e91e63",
    },
    {
        "name": "DER WAGEN",
        "number": 7,
        "emoji": "🏎️",
        "cp77": "Jackie Welles — Der Bruder, der Partner. Willenskraft pur, bis zum Ende.",
        "meaning": "Entschlossenheit, Sieg, Durchsetzungskraft. Nichts hält dich auf.",
        "advice": "Gas geben, Choom. Night City wartet nicht.",
        "color": "#f39c12",
    },
    {
        "name": "GERECHTIGKEIT",
        "number": 8,
        "emoji": "⚖️",
        "cp77": "River Ward — Der Cop, der nach der Wahrheit sucht in einer Stadt, die auf Lügen gebaut ist.",
        "meaning": "Wahrheit, Fairness, Konsequenz. Was du säst, wirst du ernten.",
        "advice": "Die Wahrheit kommt ans Licht — sei bereit dafür.",
        "color": "#3498db",
    },
    {
        "name": "DER EINSIEDLER",
        "number": 9,
        "emoji": "🏮",
        "cp77": "Misty — Die Wahrsagerin in ihrem kleinen Laden. Vik — Der Arzt, der dich wieder zusammenflickt. Suche die Stille.",
        "meaning": "Besinnung, Einsicht, Alleinsein. Manchmal musst du dich zurückziehen, um klar zu sehen.",
        "advice": "Zieh dich zurück, atme, reflektier. Die Antwort kommt in der Stille.",
        "color": "#5d6d7e",
    },
    {
        "name": "DAS SCHICKSALSRAD",
        "number": 10,
        "emoji": "🎡",
        "cp77": "Night City selbst — Die Stadt der Träume und Albträume. Das Rad dreht sich immer, für jeden.",
        "meaning": "Wandel, Kreislauf, Schicksal. Was hoch geht, kommt runter — und umgekehrt.",
        "advice": "Der Zyklus dreht sich. Ride it or get crushed.",
        "color": "#e67e22",
    },
    {
        "name": "DIE STÄRKE",
        "number": 11,
        "emoji": "💪",
        "cp77": "David Martinez — Der Junge aus Santo Domingo, der das System herausforderte. Nicht die Muskeln, sondern der Wille.",
        "meaning": "Mut, innere Stärke, Überwindung. Du bist stärker als du glaubst.",
        "advice": "Das Cyberware ist nur Chrom. Dein Spirit ist unzerstörbar.",
        "color": "#27ae60",
    },
    {
        "name": "DER GEHÄNGTE",
        "number": 12,
        "emoji": "🪢",
        "cp77": "Der Preis des Widerstands. Jackie's letzte Fahrt. Manchmal musst du loslassen, um frei zu sein.",
        "meaning": "Opfer, Loslassen, neue Perspektive. Sieh die Welt aus einem anderen Blickwinkel.",
        "advice": "Loslassen ist nicht aufgeben. Es ist die Vorbereitung auf den nächsten Zug.",
        "color": "#7f8c8d",
    },
    {
        "name": "DER TOD",
        "number": 13,
        "emoji": "💀",
        "cp77": "Dexter Deshawn — Das Ende einer Reise, der Anfang einer neuen. In Night City stirbt man zweimal.",
        "meaning": "Ende, Transformation, Neubeginn. Nicht physischer Tod — sondern der Tod von dem, was nicht mehr dient.",
        "advice": "Lass los, was stirbt. Mach Platz für das, was kommen will.",
        "color": "#1a1a2e",
    },
    {
        "name": "DIE MÄSSIGKEIT",
        "number": 14,
        "emoji": "⚖️",
        "cp77": "Johnny Silverhand — Die Balance zwischen Zerstörung und Schöpfung. Zwischen Rache und Vergebung.",
        "meaning": "Balance, Harmonie, Geduld. Weder zu viel noch zu wenig — der goldene Weg.",
        "advice": "Ruhig, Choom. Nicht jeder Kampf muss heute gekämpft werden.",
        "color": "#16a085",
    },
    {
        "name": "DER TEUFEL",
        "number": 15,
        "emoji": "👿",
        "cp77": "Yorinobu Arasaka — Der Sohn, der den Thron will. Arasaka als Symbol für das System, das dich frisst.",
        "meaning": "Abhängigkeit, Materialismus, dunkle Macht. Wovon bist du gefangen?",
        "advice": "Du hast einen Pakt mit dem Teufel? Brich ihn. Lieber arm auf den Beinen als reich auf den Knien.",
        "color": "#8b0000",
    },
    {
        "name": "DER TURM",
        "number": 16,
        "emoji": "🗼",
        "cp77": "Arasaka Tower — Der Ort der Wahrheit und der Zerstörung. Die Bombe, die alles verändert.",
        "meaning": "Plötzlicher Umbruch, Zusammenbruch, Erkenntnis. Was gebaut wurde, kann fallen.",
        "advice": "Wenn der Turm fällt, bau was Neues. Stärker. Besser.",
        "color": "#c0392b",
    },
    {
        "name": "DER STERN",
        "number": 17,
        "emoji": "⭐",
        "cp77": "Panam Palmer & die Aldecaldos — Familie, Freiheit, die offene Straße. Hoffnung jenseits der Stadtgrenzen.",
        "meaning": "Hoffnung, Inspiration, Erneuerung. Nach der Dunkelheit kommt das Licht.",
        "advice": "Hoffnung ist kein Plan — aber ohne sie bist du tot in dieser Stadt.",
        "color": "#f1c40f",
    },
    {
        "name": "DER MOND",
        "number": 18,
        "emoji": "🌙",
        "cp77": "Judy Alvarez — Die Künstlerin in einer harten Welt. Die Mox. Die Träume, die dich nachts wach halten.",
        "meaning": "Illusion, Angst, das Unbewusste. Nicht alles ist, wie es scheint.",
        "advice": "Hinter der Illusion wartet die Wahrheit. Trau deinen Sinnen — aber hinterfrag sie auch.",
        "color": "#2c3e50",
    },
    {
        "name": "DIE SONNE",
        "number": 19,
        "emoji": "☀️",
        "cp77": "Kerry Eurodyne — Der Rockstar, der alles hatte und alles verlor. Der Ruhm am Ende der Reise.",
        "meaning": "Freude, Erfolg, Erfüllung. Der Sieg nach dem Kampf.",
        "advice": "Du hast es geschafft, Choom. Genieß den Moment.",
        "color": "#f39c12",
    },
    {
        "name": "DAS GERICHT",
        "number": 20,
        "emoji": "📯",
        "cp77": "Der Ruf aus der Ferne. Arasaka Tower, Mikoshi, die letzte Abrechnung. Der Moment der Wahrheit.",
        "meaning": "Wiedergeburt, Berufung, innere Stimme. Hörst du den Ruf?",
        "advice": "Du kannst nicht zurück. Der Ruf kommt — antworte.",
        "color": "#d4ac0d",
    },
    {
        "name": "DIE WELT",
        "number": 21,
        "emoji": "🌍",
        "cp77": "Mikoshi — Jenseits der Blackwall. Das Ende einer Reise, die Vollendung des Kreises. Transzendenz.",
        "meaning": "Vollendung, Erfüllung, Reiseabschluss. Der Kreis schließt sich.",
        "advice": "Du hast den Gipfel erreicht. Atme durch. Die nächste Reise wartet.",
        "color": "#1abc9c",
    },
]


async def execute(ollama, db, args, user_id=""):
    raw_count = " ".join(args) if args else ""

    count = 1
    if raw_count:
        try:
            count = max(1, min(3, int(raw_count)))
        except (ValueError, TypeError):
            pass

    drawn = random.sample(CARDS, count)

    lines = []
    for card in drawn:
        reverse = random.choice([False, False, True])
        name = f"{card['emoji']} <b>{card['name']}</b>"
        if reverse:
            name += " <i>(umgekehrt)</i>"
        lines.append(f"╔══════════════════════════╗")
        lines.append(name)
        lines.append(f"<i>Nr. {card['number']} — Major Arcana</i>")
        lines.append(f"")
        lines.append(f"<b>🔴 Cyberpunk 2077:</b>")
        lines.append(f"{card['cp77']}")
        lines.append(f"")
        if reverse:
            lines.append(f"<b>⬇️ Bedeutung (umgekehrt):</b>")
            lines.append(f"Blockade, Verzögerung, innere Konflikte. Die Energie dieser Karte arbeitet gegen dich.")
            lines.append(f"")
            lines.append(f"<b>💡 Rat (umgekehrt):</b>")
            lines.append(f"Stop. Neu ausrichten. Nicht alle Kämpfe sind deine.")
        else:
            lines.append(f"<b>⬆️ Bedeutung:</b>")
            lines.append(f"{card['meaning']}")
            lines.append(f"")
            lines.append(f"<b>💡 Rat:</b>")
            lines.append(f"{card['advice']}")
        lines.append(f"")

    if count == 1:
        lines.insert(0, f"🔮 <b>Deine Tarot-Karte für heute:</b>\n")
    else:
        lines.insert(0, f"🔮 <b>Deine {count} Tarot-Karten:</b>\n")

    return "\n".join(lines)
