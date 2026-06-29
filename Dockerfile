FROM python:3.12-slim

# ffmpeg is required for MP3 extraction and video/audio merging.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Long-polling bot; the health server binds $PORT (set by Render) for keep-alive.
CMD ["python", "-m", "bot.main"]
