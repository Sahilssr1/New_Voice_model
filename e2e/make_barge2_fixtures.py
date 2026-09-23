"""Targeted barge-in fixtures: long agent reply, dense interruptions."""
import wave

import numpy as np

from piper import PiperVoice

VOICES_DIR = "/home/hatch/workspace/voiceagent/backend/voices"
OUT = "/home/hatch/workspace/voiceagent/e2e/fixtures"
SR = 16000
VOICE = "hi_IN-priyamvada-medium"


def synth(voice, text):
    import io
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


def save(name, voice, segments, total_s):
    buf = np.zeros(int(total_s * SR), dtype=np.float32)
    for start, text in segments:
        pcm = synth(voice, text).astype(np.float32) / 32768.0
        i = int(start * SR)
        j = min(len(buf), i + len(pcm))
        buf[i:j] += pcm[: j - i]
    buf = np.clip(buf, -1, 1)
    with wave.open(f"{OUT}/{name}", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())
    print(f"{OUT}/{name}: {total_s}s")


if __name__ == "__main__":
    voice = PiperVoice.load(f"{VOICES_DIR}/{VOICE}.onnx")
    # Initial short request, then "रुको" every 3s from 8s to 50s.
    segs = [(4.0, "नमस्ते।")]
    for t in range(8, 51, 3):
        segs.append((float(t), "रुको, एक मिनट।"))
    save("mic_hi_barge2.wav", voice, segs, 60)
