FROM python:3.11-slim

WORKDIR /app

# System-Dependencies fuer faster-whisper und edge-tts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data-Verzeichnis fuer SQLite
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
