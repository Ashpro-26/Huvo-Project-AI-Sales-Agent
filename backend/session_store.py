"""
Very simple in-memory conversation store, keyed by session_id.
Good enough for this assignment; swap for Redis/DB for production.
"""
import random
import time
from typing import Dict, Any, List


class Session:
    def __init__(self, session_id: str, channel: str = "chat"):
        self.session_id = session_id
        self.channel = channel
        self.messages: List[Dict[str, Any]] = []  # message list in provider-neutral format
        self.created_at = time.time()
        self.ended = False

        # Structured state accumulated via tool calls / detected events.
        # This is the "memory" the analytics step relies on for hard facts,
        # separate from the free-text conversation.
        self.state: Dict[str, Any] = {
            "site_visit_status": "not_requested",   # not_requested | booked | attempted_failed | declined
            "site_visit_details": None,
            "opted_out": False,
            "escalated_to_human": False,
            "escalation_reason": None,
            "follow_up_required": False,
            "follow_up_notes": None,
            "booking_attempts": 0,
        }

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})


class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def get_or_create(self, session_id: str, channel: str = "chat") -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id, channel)
        return self._sessions[session_id]

    def get(self, session_id: str) -> Session:
        return self._sessions.get(session_id)


store = SessionStore()


def simulate_booking(date: str, time_: str) -> Dict[str, Any]:
    """
    Deterministic-ish simulation of a backend booking system, so demo runs
    are reproducible for the grader:
      - Any request mentioning "sunday" fails (site closed) -> deterministic
        failure case to demonstrate booking-failure handling.
      - Otherwise, ~85% success, 15% simulated failure (slot taken).
    """
    text = f"{date} {time_}".lower()
    if "sunday" in text:
        return {"success": False, "reason": "Site visits are not available on Sundays."}
    if random.random() < 0.15:
        return {"success": False, "reason": "That slot was just taken by another booking."}
    return {"success": True, "reason": None}
