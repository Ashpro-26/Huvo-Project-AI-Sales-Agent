"""
Generates analytics for a finished conversation.

Hard facts (booking status, opt-out, escalation, follow-up) come straight
from session.state, which was populated by actual tool calls during the
conversation — no guessing there.

Softer fields (budget signal, interest level, configuration interest,
purpose, timeline, language mix, objections, summary) are derived with a
single extra LLM call over the transcript (structured JSON output), since
these require judgement/interpretation. In MOCK_MODE, a lightweight
keyword-based heuristic fills these instead.
"""
import json
import re
from typing import Any, Dict

import requests

from config import AI_PROVIDER, API_KEY, MODEL_NAME, MOCK_MODE
from models import Analytics
from session_store import Session

EXTRACTION_SYSTEM_PROMPT = """You extract structured analytics from a real-estate sales conversation
transcript (Northstar Homes / Northstar One project). Read the transcript and return ONLY a JSON
object (no markdown, no commentary) with exactly these fields:

{
  "configuration_interest": "2 BHK" | "3 BHK" | "undecided" | null,
  "budget_signal": string or null (brief factual note on what the customer indicated about budget/price reaction, do not invent numbers they didn't say),
  "purpose": "self-use" | "investment" | null,
  "timeline": string or null (brief, e.g. "within 3 months", "just researching"),
  "interest_level": "hot" | "warm" | "cold",
  "language_used": "English" | "Hindi" | "Hinglish" | "mixed",
  "objections_raised": array of short strings (e.g. "price too high"), empty array if none,
  "summary": string, 1-3 sentences summarizing the conversation and outcome
}

Only use information actually present in the transcript. Use null / empty values where the
transcript doesn't give enough signal. Do not fabricate anything."""


def _transcript_text(session: Session) -> str:
    lines = []
    for msg in session.messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            text = content
        else:
            # LLM provider content blocks (text / tool_use / tool_result)
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_result":
                        continue  # internal, skip from transcript
                elif getattr(block, "type", None) == "text":
                    parts.append(block.text)
            text = " ".join(parts)
        if text.strip():
            lines.append(f"{role.upper()}: {text.strip()}")
    return "\n".join(lines)


def _mock_extraction(transcript: str) -> Dict[str, Any]:
    t = transcript.lower()
    config = "3 BHK" if "3 bhk" in t else ("2 BHK" if "2 bhk" in t else "undecided" if "bhk" in t else None)
    purpose = "investment" if "investment" in t else ("self-use" if any(w in t for w in ["own use", "family", "rehne"]) else None)
    lang = "Hindi" if re.search(r"[\u0900-\u097f]", transcript) else \
           ("Hinglish" if any(w in t for w in ["hai", "kya", "nahi", "kaise"]) else "English")
    objections = []
    if any(w in t for w in ["expensive", "too high", "mehenga"]):
        objections.append("price too high")
    if "think" in t or "soch" in t:
        objections.append("wants to think it over")
    if "not interested" in t:
        interest = "cold"
    elif "book" in t or "visit" in t:
        interest = "hot"
    elif "price" in t or "bhk" in t:
        interest = "warm"
    else:
        interest = "cold"
    return {
        "configuration_interest": config,
        "budget_signal": "Discussed starting prices; no explicit budget stated by customer." if "price" in t else None,
        "purpose": purpose,
        "timeline": None,
        "interest_level": interest,
        "language_used": lang,
        "objections_raised": objections,
        "summary": "Mock-mode summary: conversation covered project details based on customer's messages.",
    }


def _gemini_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def _llm_extraction(transcript: str) -> Dict[str, Any]:
    if AI_PROVIDER == "gemini":
        payload = {
            "system_instruction": [{"parts": [{"text": EXTRACTION_SYSTEM_PROMPT}]}],
            "contents": [{
                "role": "user",
                "parts": [{"text": transcript or "(empty conversation)"}],
            }],
        }
        data = _gemini_response(payload)
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if "text" in part).strip()
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=API_KEY)
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=500,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript or "(empty conversation)"}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()

    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def build_analytics(session: Session) -> Analytics:
    transcript = _transcript_text(session)
    extracted = _mock_extraction(transcript) if MOCK_MODE else _llm_extraction(transcript)

    return Analytics(
        session_id=session.session_id,
        configuration_interest=extracted.get("configuration_interest"),
        budget_signal=extracted.get("budget_signal"),
        purpose=extracted.get("purpose"),
        timeline=extracted.get("timeline"),
        interest_level=extracted.get("interest_level", "unknown") or "unknown",
        language_used=extracted.get("language_used"),
        site_visit_status=session.state["site_visit_status"],
        site_visit_details=session.state["site_visit_details"],
        follow_up_required=session.state["follow_up_required"],
        follow_up_notes=session.state["follow_up_notes"],
        opted_out=session.state["opted_out"],
        escalated_to_human=session.state["escalated_to_human"],
        escalation_reason=session.state["escalation_reason"],
        objections_raised=extracted.get("objections_raised", []) or [],
        summary=extracted.get("summary"),
        turn_count=len([m for m in session.messages if m["role"] == "user"]),
    )
