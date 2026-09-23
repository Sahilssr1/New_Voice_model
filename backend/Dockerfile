FROM python:3.12-slim

WORKDIR /app

# espeak-ng is required by piper-tts at runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Best-effort voice download at build time; never fail the build if offline.
RUN mkdir -p /app/voices \
    && (python -m piper.download_voices en_US-amy-medium en_US-ryan-medium hi_IN-priyamvada-medium --download-dir /app/voices || true)

COPY . .

ENV TTS_VOICES_DIR=/app/voices \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
