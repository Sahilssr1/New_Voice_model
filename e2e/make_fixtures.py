"""Generate fake-microphone WAV fixtures for browser E2E voice tests.

Each fixture: 4s leading silence (call connects first), then the test
utterance with a natural mid-sentence pause, then silence to a 40s loop.

Voices are the real Piper voices so the STT hears realistic TTS audio.
"""
import io
import wave

import numpy as np

from piper import PiperVoice

VOICES_DIR = "/home/hatch/workspace/voiceagent/backend/voices"
OUT_DIR = "/home/hatch/workspace/voiceagent/e2e/fixtures"

# (filename, voice_id, [(text, pause_after_sec)])
FIXTURES = [
    ("mic_en.wav", "en_US-amy-medium", [
        ("Hi,", 0.7),
        ("how are you doing today?", 0.0),
    ]),
    ("mic_hi.wav", "hi_IN-priyamvada-medium", [
        ("नमस्ते,", 0.7),
        ("आप कैसे हैं?", 0.0),
    ]),
    # Hinglish fixture is synthesized with the Hindi voice; the agent under
    # test is configured with language="hinglish".
    ("mic_hinglish.wav", "hi_IN-priyamvada-medium", [
        ("यार,", 0.7),
        ("तुम कैसे हो?", 0.0),
    ]),
]

SR = 16000
LEAD_SILENCE_S = 4.0
LOOP_S = 40.0


def synth(voice: PiperVoice, text: str) -> np.ndarray:
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
    if src_sr != SR:
        # simple linear resample
        idx = np.linspace(0, len(audio) - 1, int(len(audio) * SR / src_sr))
        audio = np.interp(idx, np.arange(len(audio)), audio)
    return audio.astype(np.int16)


def main() -> None:
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, voice_id, parts in FIXTURES:
        voice = PiperVoice.load(f"{VOICES_DIR}/{voice_id}.onnx")
        segs = []
        for text, pause in parts:
            segs.append(synth(voice, text))
            if pause:
                segs.append(np.zeros(int(pause * SR), dtype=np.int16))
        speech = np.concatenate(segs)
        total = np.zeros(int(LOOP_S * SR), dtype=np.int16)
        start = int(LEAD_SILENCE_S * SR)
        total[start:start + len(speech)] = speech
        path = f"{OUT_DIR}/{fname}"
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(total.tobytes())
        print(f"{path}: speech at {LEAD_SILENCE_S:.0f}s, "
              f"{len(speech)/SR:.1f}s long, {LOOP_S:.0f}s loop")


if __name__ == "__main__":
    main()
