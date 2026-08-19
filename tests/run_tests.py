"""
Runs a set of scripted conversations through the running backend logic
(via FastAPI's TestClient, in-process — no server needed) and prints
input / expected behaviour / actual output for each, plus final analytics.

Run with:  python tests/run_tests.py
(from repo root; requires backend/ dependencies installed)

Note: this exercises MOCK_MODE by default (no GEMINI_API_KEY needed),
since it's meant to be runnable by a grader without a key. Set
GEMINI_API_KEY before running to test against the real prompt + Gemini.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def run_scenario(title, expected, turns, channel="chat"):
    session_id = str(uuid.uuid4())
    print(f"\n{'=' * 70}\nSCENARIO: {title}\nEXPECTED: {expected}\n{'-' * 70}")
    for user_msg in turns:
        resp = client.post("/api/chat", json={
            "session_id": session_id, "message": user_msg, "channel": channel,
        })
        print(f"USER : {user_msg}")
        if resp.status_code != 200:
            print(f"ERROR: {resp.status_code} {resp.text}")
            continue
        data = resp.json()
        print(f"BOT  : {data['reply']}")
        if data["ended"]:
            print("(conversation flagged as ended by agent)")

    analytics = client.post("/api/end", json={"session_id": session_id})
    print(f"\nANALYTICS: {analytics.json()}")
    return analytics.json()


if __name__ == "__main__":
    mode = client.get("/api/mode").json()
    print(f"Running tests. mock_mode={mode['mock_mode']}")

    run_scenario(
        "Basic price inquiry (English)",
        "Bot states only known prices (2 BHK ₹1.35 Cr / 3 BHK ₹1.75 Cr), asks a qualifying question, invents nothing.",
        ["Hi, what's the price of a 2 BHK at Northstar One?"],
    )

    run_scenario(
        "Hinglish configuration inquiry",
        "Bot responds naturally in Hinglish, does not force English.",
        ["Bhai 3 BHK ka price kya hai Sector 79 wale project mein?"],
    )

    run_scenario(
        "Qualified 2 BHK self-use inquiry",
        "Bot acknowledges the configuration and purpose without re-asking the same qualification prompt.",
        ["I'm looking for a 2BHK and it is for my own use."],
    )

    run_scenario(
        "Price objection",
        "Bot acknowledges the objection empathetically, does not invent a discount, offers a next step.",
        ["That's way too expensive for me, I was expecting something cheaper."],
    )

    run_scenario(
        "Busy / call later",
        "Bot backs off immediately, asks for a better time, logs a follow-up (visible in analytics.follow_up_required).",
        ["I'm busy right now, call me back next week."],
    )

    run_scenario(
        "Opt-out / stop contacting",
        "Bot immediately confirms opt-out, ends conversation, does not pitch again. analytics.opted_out == true.",
        ["Please stop contacting me, I'm not interested at all."],
    )

    run_scenario(
        "Unknown question (possession date)",
        "Bot admits it doesn't have the possession date, offers escalation/follow-up, does NOT invent a date.",
        ["When exactly will possession be handed over?"],
    )

    run_scenario(
        "Human escalation request",
        "Bot escalates to a human specialist. analytics.escalated_to_human == true.",
        ["I don't want to talk to a bot, connect me to a real person."],
    )

    run_scenario(
        "Site visit booking — success path",
        "Bot collects details and books the visit. analytics.site_visit_status == 'booked'.",
        [
            "I'd like to book a site visit for a 2 BHK.",
            "Saturday around 11 AM works. My name is Rohan Mehta, phone 9876543210.",
        ],
    )

    run_scenario(
        "Site visit booking — deterministic failure (Sunday)",
        "Booking fails because Sundays are unavailable in the simulated system; bot offers an alternative "
        "instead of pretending it worked. analytics.site_visit_status == 'attempted_failed'.",
        [
            "Book me a site visit this Sunday at 4pm, name Priya Singh, number 9123456780, for a 3 BHK.",
        ],
    )
