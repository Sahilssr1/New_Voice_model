"""Browser E2E: fake microphone -> full voice pipeline -> live transcript.

Usage:
    python e2e_call.py --lang hi --voice hi_IN-priyamvada-medium --gender female \\
        --wav fixtures/mic_hi.wav --expect-user "कैसे हैं"

Spawns headless Chromium, injects a looping WAV as the microphone via a
MediaStreamDestination, logs in, opens /calls/live/<agent>, and waits for
the user bubble and the assistant bubble to appear in the live transcript.
"""
import argparse
import base64
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BACKEND = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:5173"
EMAIL = "demo@example.com"
PASSWORD = "demo1234"


def api(method: str, path: str, token: str | None = None, body: dict | None = None):
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
    ap.add_argument("--lang", required=True, choices=["en", "hi", "hinglish"])
    ap.add_argument("--voice", required=True)
    ap.add_argument("--gender", required=True, choices=["female", "male"])
    ap.add_argument("--wav", required=True)
    ap.add_argument("--expect-user", required=True,
                    help="comma-separated substrings; PASS if any appears "
                         "(case-insensitive) in the transcribed user bubble")
    ap.add_argument("--agent-name", default=None)
    args = ap.parse_args()

    with open(args.wav, "rb") as f:
        wav_b64 = base64.b64encode(f.read()).decode()

    token = api("POST", "/api/auth/login",
                body={"email": EMAIL, "password": PASSWORD})["access_token"]
    agent = api("POST", "/api/agents", token, {
        "name": args.agent_name or f"e2e-{args.lang}-{int(time.time())}",
        "system_prompt": "You are a helpful, friendly voice assistant. Keep replies short.",
        "language": args.lang,
        "voice_gender": args.gender,
        "voice_id": args.voice,
    })
    agent_id = agent["id"]
    print(f"agent: {agent_id} ({args.lang}, {args.voice})")

    user_text, agent_text = "", ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
        ])
        ctx = browser.new_context()
        page = ctx.new_page()

        # Inject the WAV as the microphone before any page script runs.
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
                    window.__fakeMicCtx = ac;
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
        print("logged in, opening live call page")

        page.goto(f"{FRONTEND}/calls/live/{agent_id}")
        page.wait_for_selector(".transcript-live", timeout=15000)
        print("live call page opened, waiting for user transcript...")

        # Wait for the user bubble (STT through the whole pipeline).
        expects = [e.strip().lower() for e in args.expect_user.split(",")]
        page.wait_for_function(
            """(expects) => {
                const els = document.querySelectorAll('.bubble-user .bubble-text');
                return [...els].some(e => expects.some(
                    x => e.textContent.toLowerCase().includes(x)));
            }""",
            arg=expects, timeout=120000,
        )
        user_text = page.eval_on_selector(
            ".bubble-user .bubble-text", "e => e.textContent")
        print(f"USER SAID: {user_text!r}")

        print("waiting for assistant reply...")
        page.wait_for_selector(".bubble-assistant .bubble-text", timeout=180000)
        # let the assistant bubble finish streaming
        time.sleep(3)
        agent_text = page.eval_on_selector_all(
            ".bubble-assistant .bubble-text",
            "els => els.map(e => e.textContent).join(' | ')",
        )
        print(f"AGENT SAID: {agent_text!r}")
        page.screenshot(path=f"/home/hatch/workspace/voiceagent/e2e/last_call.png")
        browser.close()

    ok_user = any(e.strip().lower() in user_text.lower()
                  for e in args.expect_user.split(","))
    ok_agent = len(agent_text.strip()) > 0
    print(f"E2E RESULT: {'PASS' if (ok_user and ok_agent) else 'FAIL'} "
          f"(user_match={ok_user}, agent_replied={ok_agent})")
    return 0 if (ok_user and ok_agent) else 1


if __name__ == "__main__":
    sys.exit(main())
