FROM python:3.11-slim

WORKDIR /app

# System-Dependencies fuer faster-whisper, edge-tts und agy
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Google Antigravity CLI (agy)
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash && \
    ln -sf /root/.local/bin/agy /usr/local/bin/agy

COPY . .

RUN groupadd -r godfather && useradd -r -g godfather -d /app -s /sbin/nologin godfather \
    && mkdir -p /app/data \
    && chown -R godfather:godfather /app

USER godfather

CMD ["python", "bot.py"]
