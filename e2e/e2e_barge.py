"""Barge-in E2E: user interrupts the agent mid-response.

Usage:
    python e2e_barge.py --lang hi --voice hi_IN-priyamvada-medium --gender female \\
        --wav fixtures/mic_hi_barge.wav

PASS if the DB shows an 'agent_interrupted' event for the call AND the
interrupting utterance was transcribed and answered.
"""
import argparse
import base64
import json
import os
import sqlite3
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BACKEND = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:5173"
EMAIL = "demo@example.com"
PASSWORD = "demo1234"
DB = os.path.expanduser("~/workspace/voiceagent/backend/voiceagent.db")


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
    args = ap.parse_args()

    with open(args.wav, "rb") as f:
        wav_b64 = base64.b64encode(f.read()).decode()

    token = api("POST", "/api/auth/login",
                body={"email": EMAIL, "password": PASSWORD})["access_token"]
    agent = api("POST", "/api/agents", token, {
        "name": f"e2e-barge-{int(time.time())}",
        # Force a long reply so TTS playback lasts long enough to barge in.
        "system_prompt": (
            "You are a helpful voice assistant. IMPORTANT: Always give a "
            "very long, detailed response of at least 6 full sentences. "
            "Never give a short reply."
        ),
        "language": args.lang,
        "voice_gender": args.gender,
        "voice_id": args.voice,
    })
    agent_id = agent["id"]
    print(f"agent: {agent_id}")

    call_id = None
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

        # Wait for at least 2 user turns (initial + interruption).
        print("waiting for interruption turn...")
        try:
            page.wait_for_function(
                """() => document.querySelectorAll('.bubble-user .bubble-text').length >= 2""",
                timeout=120000,
            )
        except Exception as e:
            print(f"only one user turn seen: {e}")
        time.sleep(5)
        users = page.eval_on_selector_all(
            ".bubble-user .bubble-text", "els => els.map(e => e.textContent)")
        agents = page.eval_on_selector_all(
            ".bubble-assistant .bubble-text",
            "els => els.map(e => e.textContent)")
        for i, u in enumerate(users):
            print(f"USER {i+1}: {u!r}")
        for i, a in enumerate(agents):
            print(f"AGENT {i+1}: {a!r}")

        # Grab the call id from the page URL or the latest call via API.
        calls = api("GET", "/api/calls?limit=5", token)
        items = calls if isinstance(calls, list) else calls.get("items", [])
        call_id = items[0]["id"] if items else None
        print(f"call: {str(call_id)[:8] if call_id else None}")
        browser.close()

    if not call_id:
        print("BARGE RESULT: FAIL (no call found)")
        return 1

    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(
        "SELECT event_type, substr(payload, 1, 100) FROM call_events "
        "WHERE call_id = ? ORDER BY created_at",
        (call_id,),
    )
    events = cur.fetchall()
    con.close()
    interrupted = [e for e in events if e[0] == "agent_interrupted"]
    print(f"agent_interrupted events: {len(interrupted)}")
    for e in interrupted[:3]:
        print(f"  {e[0]} {e[1]}")

    ok = len(interrupted) > 0 and len(users) >= 2
    print(f"BARGE RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
