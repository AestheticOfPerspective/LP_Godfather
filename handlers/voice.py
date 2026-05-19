"""
handlers/voice.py — Voice Command Handler
Sprachnachrichten via faster-whisper transkribieren (lokal, CUDA),
dann durch die aktive Persona jagen. Antwort als Text + Voice (TTS).
"""

import logging
import tempfile
import os
import asyncio
from functools import partial

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.ai import ask_ai, PERSONAS, get_user_persona

logger = logging.getLogger(__name__)

# ── TTS Stimmen pro Persona ──────────────────────────────────────────────────
_PERSONA_VOICES: dict[str, str] = {
    "godfather": "de-DE-ConradNeural",       # Tief, autoritaer
    "cyber_zen": "de-DE-KillianNeural",       # Ruhig, klar
    "vapor_foss": "de-DE-FlorianMultilingualNeural",  # Chill, modern
    "tropical_infinity": "de-DE-FlorianMultilingualNeural",
    "monkey_mind": "de-DE-ConradNeural",      # Energisch
    "punk_philosopher": "de-DE-KillianNeural",
    "nyx": "de-DE-KatjaNeural",              # Warm, feminin, poetisch
}

# ── Whisper Modell (lazy-loaded beim ersten Voice) ───────────────────────────

_whisper_model = None


def _load_whisper():
    """Laedt das Whisper-Modell einmalig. CUDA wenn vorhanden, sonst CPU."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    from faster_whisper import WhisperModel

    whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
    compute = "float16" if whisper_device == "cuda" else "int8"

    for device, ctype in [(whisper_device, compute), ("cpu", "int8")]:
        try:
            _whisper_model = WhisperModel("base", device=device, compute_type=ctype)
            logger.info(f"Whisper geladen: base ({device.upper()})")
            return _whisper_model
        except Exception as e:
            logger.warning(f"Whisper {device.upper()} fehlgeschlagen: {e}")

    raise RuntimeError("Whisper konnte weder mit CUDA noch CPU geladen werden.")


def _transcribe_sync(file_path: str) -> str:
    """Synchrone Transkription — wird im Thread-Pool ausgefuehrt."""
    model = _load_whisper()
    segments, info = model.transcribe(file_path, beam_size=3)
    text = " ".join(seg.text.strip() for seg in segments)
    return text.strip()


async def _tts_generate(text: str, voice: str, output_path: str) -> bool:
    """Generiert eine MP3-Datei via edge-tts. Gibt True bei Erfolg zurueck."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except ImportError:
        logger.warning("edge-tts nicht installiert — kein Voice-Reply.")
        return False
    except Exception as e:
        logger.warning(f"TTS fehlgeschlagen: {e}")
        return False


# ── Voice Handler ────────────────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Empfaengt Sprachnachrichten, transkribiert sie und antwortet via KI + TTS."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    user = update.effective_user
    user_id = user.id
    persona_key = get_user_persona(user_id)
    persona_name = PERSONAS[persona_key]["name"]

    msg = await update.message.reply_text("🎙️ Hoere zu...")

    tmp_path = None
    tts_path = None
    try:
        # Voice-Datei herunterladen
        file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        # Transkription im Thread-Pool (blockiert nicht den Bot)
        await msg.edit_text("🎙️ Transkribiere...")
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, partial(_transcribe_sync, tmp_path))

        if not text:
            await msg.edit_text("🎙️ Konnte nichts verstehen — versuch's nochmal.")
            return

        # Transkription zeigen, KI-Antwort holen
        await msg.edit_text(
            f"🎙️ <i>{text}</i>\n\n⏳ {persona_name} denkt nach...",
            parse_mode=ParseMode.HTML,
        )

        from utils.storage import db
        db.increment_stat("ai_requests")
        db.increment_stat("voice_messages")

        response = await ask_ai(text, user_id=user_id)

        # Text-Antwort senden
        await msg.edit_text(
            f"🎙️ <i>{text}</i>\n\n{persona_name}:\n\n{response}",
            parse_mode=ParseMode.HTML,
        )

        # TTS: Antwort als Sprachnachricht zuruecksenden
        tts_voice = _PERSONA_VOICES.get(persona_key, "de-DE-ConradNeural")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tts_tmp:
            tts_path = tts_tmp.name

        if await _tts_generate(response, tts_voice, tts_path):
            with open(tts_path, "rb") as audio_file:
                await update.message.reply_voice(voice=audio_file)

    except ImportError:
        await msg.edit_text(
            "❌ <b>faster-whisper nicht installiert.</b>\n\n"
            "<code>pip install faster-whisper</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Voice-Fehler: {e}")
        await msg.edit_text(f"❌ Voice-Fehler: {e}")
    finally:
        for path in (tmp_path, tts_path):
            if path and os.path.exists(path):
                os.unlink(path)
