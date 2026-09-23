"""Generate memory + barge-in test fixtures."""
import io
import wave

import numpy as np

from piper import PiperVoice

VOICES_DIR = "/home/hatch/workspace/voiceagent/backend/voices"
OUT_DIR = "/home/hatch/workspace/voiceagent/e2e/fixtures"
SR = 16000


def synth(voice, text):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(voice.config.sample_rate)
        voice.synthesize_wav(text, w)
    buf.seek(0)
    with wave.open(buf, "rb") as w:
        raw = w.readframes(w.getnframes())
        src_sr = w.getframerate()
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    idx = np.linspace(0, len(audio) - 1, int(len(audio) * SR / src_sr))
    return np.interp(idx, np.arange(len(audio)), audio).astype(np.int16)


def save(path, segments, total_s):
    """segments: list of (start_sec, audio)."""
    total = np.zeros(int(total_s * SR), dtype=np.int16)
    for start, audio in segments:
        i = int(start * SR)
        total[i:i + len(audio)] = audio
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(total.tobytes())
    print(f"{path}: {total_s}s")


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    voice = PiperVoice.load(f"{VOICES_DIR}/hi_IN-priyamvada-medium.onnx")

    # Memory test: name in turn 1, recall question in turn 2.
    # Turn 1 at 4s, turn 2 at 30s (after turn 1's full response).
    t1 = synth(voice, "मेरा नाम साहिल है।")
    t2 = synth(voice, "मेरा नाम क्या है?")
    save(f"{OUT_DIR}/mic_hi_memory.wav",
         [(4, t1), (30, t2)], 70)

    # Barge-in test: speech every 8s; one will land during agent TTS.
    # Turn 1 at 4s, then interruptions at 12s, 20s, 28s.
    speech = synth(voice, "रुको, एक मिनट।")
    save(f"{OUT_DIR}/mic_hi_barge.wav",
         [(4, synth(voice, "नमस्ते, आप कैसे हैं?")),
          (12, speech), (20, speech), (28, speech)], 60)


if __name__ == "__main__":
    main()
