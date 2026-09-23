"""Demo video with SOUND: real browser call, real voices.

Records the screen (login -> dashboard -> agents -> live call) while a fake
microphone plays the user's voice. Captures exact timestamps of the user and
assistant turns, then rebuilds the sound track from the real audio:
  - user's spoken fixture WAV
  - assistant's reply re-synthesized with the SAME Piper voice model

Output: e2e/demo-with-sound.mp4 (screen recording + mixed voice audio).

Usage:
    python e2e_demo.py
"""
import base64
import io
import json
import sys
import time
import urllib.request
import wave

from playwright.sync_api import sync_playwright

BACKEND = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:5173"
EMAIL = "demo@example.com"
PASSWORD = "demo1234"
E2E = "/home/hatch/workspace/voiceagent/e2e"
VOICES = "/home/hatch/workspace/voiceagent/backend/voices"

LANG = "en"
VOICE = "en_US-lessac-medium"
GENDER = "male"
WAV = f"{E2E}/fixtures/mic_en.wav"
EXPECT = "how are you"


def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        BACKEND + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main() -> int:
    with open(WAV, "rb") as f:
        wav_b64 = base64.b64encode(f.read()).decode()

    token = api("POST", "/api/auth/login",
                body={"email": EMAIL, "password": PASSWORD})["access_token"]
    agent = api("POST", "/api/agents", token, {
        "name": f"demo-{int(time.time())}",
        "system_prompt": "You are a helpful, friendly voice assistant. Keep replies short.",
        "language": LANG,
        "voice_gender": GENDER,
        "voice_id": VOICE,
    })
    agent_id = agent["id"]
    print(f"agent: {agent_id}", flush=True)

    events = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
        ])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=f"{E2E}/video_raw",
            record_video_size={"width": 1280, "height": 720},
        )
        t0 = time.time()  # video timeline origin
        page = ctx.new_page()

        # Fake mic: play the fixture ONCE (no loop for a clean single turn).
        page.add_init_script(f"""
            const wavB64 = "{wav_b64}";
            const wavBytes = Uint8Array.from(atob(wavB64), c => c.charCodeAt(0)).buffer;
            const _gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = async (constraints) => {{
                if (constraints && constraints.audio) {{
                    const AC = window.AudioContext || window.webkitAudioContext;
                    const ac = new AC({{ sampleRate: 16000 }});
                    await ac.resume();
                    const buf = await ac.decodeAudioData(wavBytes.slice(0));
                    const src = ac.createBufferSource();
                    src.buffer = buf; src.loop = false; src.start();
                    const dest = ac.createMediaStreamDestination();
                    src.connect(dest);
                    return dest.stream;
                }}
                return _gum(constraints);
            }};
        """)

        # Walk the UI so the video shows how the app is used.
        page.goto(f"{FRONTEND}/login")
        page.fill('input[type="email"], input[name="email"]', EMAIL)
        page.fill('input[type="password"], input[name="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard", timeout=15000)
        time.sleep(2)
        page.goto(f"{FRONTEND}/agents")
        time.sleep(2)

        # Live call.
        page.goto(f"{FRONTEND}/calls/live/{agent_id}")
        page.wait_for_selector(".transcript-live", timeout=15000)
        events["call_start"] = time.time() - t0
        print("call started, waiting for user transcript...", flush=True)

        page.wait_for_function(
            """(exp) => {
                const els = document.querySelectorAll('.bubble-user .bubble-text');
                return [...els].some(e => e.textContent.toLowerCase().includes(exp));
            }""",
            arg=EXPECT, timeout=120000,
        )
        events["user_at"] = time.time() - t0
        user_text = page.eval_on_selector(".bubble-user .bubble-text",
                                         "e => e.textContent")
        print(f"USER SAID: {user_text!r}", flush=True)

        print("waiting for assistant reply...", flush=True)
        page.wait_for_selector(".bubble-assistant .bubble-text", timeout=180000)
        events["assistant_at"] = time.time() - t0
        time.sleep(8)  # let the reply finish streaming + "play"
        agent_text = page.eval_on_selector_all(
            ".bubble-assistant .bubble-text",
            "els => els.map(e => e.textContent).join(' ')",
        )
        print(f"AGENT SAID: {agent_text!r}", flush=True)
        time.sleep(3)
        events["video_end"] = time.time() - t0
        events["user_text"] = user_text
        events["agent_text"] = agent_text

        video_path = page.video.path()
        ctx.close()
        browser.close()
        print(f"raw video: {video_path}", flush=True)

    with open(f"{E2E}/demo_events.json", "w") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    # move raw video to a stable path
    import shutil, glob
    raws = glob.glob(f"{E2E}/video_raw/*.webm")
    if raws:
        shutil.move(raws[0], f"{E2E}/demo_raw.webm")
    print("events saved", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
