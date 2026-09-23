"""Memory E2E: turn 1 gives a name, turn 2 asks for it back.

Usage:
    python e2e_memory.py --lang hi --voice hi_IN-priyamvada-medium --gender female \\
        --wav fixtures/mic_hi_memory.wav

PASS if the agent's reply to turn 2 contains the name from turn 1.
"""
import argparse
import base64
import json
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BACKEND = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:5173"
EMAIL = "demo@example.com"
PASSWORD = "demo1234"


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--gender", required=True)
    ap.add_argument("--wav", required=True)
    ap.add_argument("--name-word", default=None,
                    help="name the agent must recall; defaults to the word "
                         "after 'मेरा नाम' in turn 1's transcript")
    args = ap.parse_args()

    with open(args.wav, "rb") as f:
        wav_b64 = base64.b64encode(f.read()).decode()

    token = api("POST", "/api/auth/login",
                body={"email": EMAIL, "password": PASSWORD})["access_token"]
    agent = api("POST", "/api/agents", token, {
        "name": f"e2e-memory-{int(time.time())}",
        "system_prompt": "You are a helpful, friendly voice assistant. Keep replies short.",
        "language": args.lang,
        "voice_gender": args.gender,
        "voice_id": args.voice,
    })
    agent_id = agent["id"]
    print(f"agent: {agent_id}")

    replies = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
        ])
        page = browser.new_context().new_page()
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
                    src.buffer = buf; src.loop = true; src.start();
                    const dest = ac.createMediaStreamDestination();
                    src.connect(dest);
                    return dest.stream;
                }}
                return _gum(constraints);
            }};
        """)
        page.goto(f"{FRONTEND}/login")
        page.fill('input[type="email"], input[name="email"]', EMAIL)
        page.fill('input[type="password"], input[name="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard", timeout=15000)
        page.goto(f"{FRONTEND}/calls/live/{agent_id}")
        page.wait_for_selector(".transcript-live", timeout=15000)
        print("waiting for two user turns...")

        # Wait until two user bubbles are present.
        page.wait_for_function(
            """() => document.querySelectorAll('.bubble-user .bubble-text').length >= 2""",
            timeout=180000,
        )
        users = page.eval_on_selector_all(
            ".bubble-user .bubble-text", "els => els.map(e => e.textContent)")
        print(f"TURN 1 USER: {users[0]!r}")
        print(f"TURN 2 USER: {users[1]!r}")

        # Wait for the second assistant reply, then let it finish.
        page.wait_for_function(
            """() => document.querySelectorAll('.bubble-assistant .bubble-text').length >= 2""",
            timeout=180000,
        )
        time.sleep(3)
        replies = page.eval_on_selector_all(
            ".bubble-assistant .bubble-text",
            "els => els.map(e => e.textContent)")
        print(f"TURN 1 AGENT: {replies[0]!r}")
        print(f"TURN 2 AGENT: {replies[1]!r}")
        browser.close()

    # The name is whatever Whisper heard after "मेरा नाम" in turn 1.
    name_word = args.name_word
    if not name_word:
        m = re.search(r"मेरा नाम\s+(\S+)", users[0])
        name_word = m.group(1) if m else "साहिल"
    print(f"remembered name: {name_word!r}")
    remembered = name_word.lower() in replies[1].lower()
    print(f"MEMORY RESULT: {'PASS' if remembered else 'FAIL'} "
          f"(turn-2 reply mentions {name_word!r}: {remembered})")
    return 0 if remembered else 1


if __name__ == "__main__":
    sys.exit(main())
