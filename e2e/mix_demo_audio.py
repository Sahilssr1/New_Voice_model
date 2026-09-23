"""Build the demo sound track and mux it with the screen recording.

Reads e2e/demo_events.json, synthesizes the assistant's reply with the same
Piper voice used in the call, mixes it with the user's fixture audio at the
exact timestamps, and muxes over e2e/demo_raw.webm.

Output: e2e/demo-with-sound.mp4
"""
import json
import subprocess
import sys
import wave

E2E = "/home/hatch/workspace/voiceagent/e2e"
VOICES = "/home/hatch/workspace/voiceagent/backend/voices"
VENV_PY = "/home/hatch/workspace/voiceagent/backend/.venv/bin/python"


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def synthesize(text: str, voice_id: str, out_wav: str):
    code = (
        "import sys, wave\n"
        "from piper import PiperVoice, SynthesisConfig\n"
        f"v = PiperVoice.load('{VOICES}/{voice_id}.onnx')\n"
        "text = sys.stdin.read()\n"
        "chunks = []\n"
        "sr = 22050\n"
        "syn = SynthesisConfig()\n"
        "for chunk in v.synthesize(text, syn_config=syn):\n"
        "    chunks.append(chunk.audio_int16_bytes)\n"
        "    sr = int(getattr(chunk, 'sample_rate', sr) or sr)\n"
        "pcm = b''.join(chunks)\n"
        f"w = wave.open('{out_wav}', 'wb')\n"
        "w.setnchannels(1)\n"
        "w.setsampwidth(2)\n"
        "w.setframerate(sr)\n"
        "w.writeframes(pcm)\n"
        "w.close()\n"
        "print('synth ok', len(pcm), sr, flush=True)\n"
    )
    p = subprocess.run([VENV_PY, "-c", code], input=text.encode(),
                       capture_output=True)
    if p.returncode != 0:
        print(p.stderr.decode()[-2000:])
        raise RuntimeError("piper synthesis failed")


def main() -> int:
    with open(f"{E2E}/demo_events.json") as f:
        ev = json.load(f)

    call_start = ev["call_start"]
    user_at = ev["user_at"]
    assistant_at = ev["assistant_at"]
    agent_text = ev["agent_text"].strip()
    print(f"call_start={call_start:.1f}s user_at={user_at:.1f}s "
          f"assistant_at={assistant_at:.1f}s", flush=True)
    print(f"assistant text: {agent_text!r}", flush=True)

    assistant_wav = f"{E2E}/demo_assistant.wav"
    synthesize(agent_text, "en_US-lessac-medium", assistant_wav)

    # Mix: user fixture at call_start, assistant TTS at assistant_at.
    # adelay expects milliseconds; pad the shorter track with apad.
    mixed = f"{E2E}/demo_mixed.m4a"
    run([
        "ffmpeg", "-y",
        "-i", f"{E2E}/fixtures/mic_en.wav",
        "-i", assistant_wav,
        "-filter_complex",
        f"[0:a]adelay={int(call_start * 1000)}|{int(call_start * 1000)},apad[a0];"
        f"[1:a]adelay={int(assistant_at * 1000)}|{int(assistant_at * 1000)},apad[a1];"
        "[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[a]",
        "-map", "[a]", "-c:a", "aac", "-b:a", "128k",
        "-t", str(ev["video_end"] + 2),
        mixed,
    ])

    # Mux with the screen recording.
    out = f"{E2E}/demo-with-sound.mp4"
    run([
        "ffmpeg", "-y",
        "-i", f"{E2E}/demo_raw.webm",
        "-i", mixed,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        out,
    ])
    print(f"DONE: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
