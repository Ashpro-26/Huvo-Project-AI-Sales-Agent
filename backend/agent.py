"""
Core agent logic: loads the final system prompt from the repository root,
then calls the configured LLM with tool use for site-visit booking,
follow-up scheduling, escalation, and opt-out — so those events are
structured and reliable rather than guessed from free text.

If no API key is set, it falls back to a small rule-based MOCK agent so the
app remains runnable end-to-end without a key (see config.MOCK_MODE).
"""
import json
import re
from pathlib import Path
from typing import Dict, Any

import requests

from config import AI_PROVIDER, API_KEY, MODEL_NAME, MOCK_MODE
from session_store import Session, simulate_booking

PROMPT_PATH = Path(__file__).resolve().parent.parent / "system_prompt.txt"


def _load_base_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Extract the fenced prompt block between the first ``` pair.
    match = re.search(r"```\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text


BASE_SYSTEM_PROMPT = _load_base_prompt()

TOOLS = [
    {
        "name": "book_site_visit",
        "description": (
            "Attempt to book a site visit for the customer once they have "
            "confirmed a date, time, and their contact details. The system "
            "will simulate checking availability and return success or "
            "failure — do not assume success before calling this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Customer name"},
                "phone": {"type": "string", "description": "Customer phone number"},
                "date": {"type": "string", "description": "Requested visit date, as stated by customer"},
                "time": {"type": "string", "description": "Requested visit time, as stated by customer"},
                "configuration": {"type": "string", "description": "2 BHK, 3 BHK, or undecided"},
            },
            "required": ["name", "phone", "date", "time"],
        },
    },
    {
        "name": "schedule_followup",
        "description": (
            "Log that the customer asked to be contacted later / at a "
            "specific future time, instead of continuing now."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_time": {"type": "string", "description": "When the customer wants to be contacted"},
                "reason": {"type": "string", "description": "Why, if stated (busy, thinking it over, etc.)"},
            },
            "required": ["preferred_time"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand off the conversation to a human Northstar Homes specialist. "
            "Call this when the customer asks for a human, when a question "
            "needs a definitive answer outside known project facts, when "
            "booking has failed more than once, or the customer is "
            "frustrated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why escalation is needed"},
            },
            "required": ["reason"],
        },
    },
    {
        "name": "opt_out",
        "description": (
            "Record that the customer asked to not be contacted again. "
            "Call this immediately whenever the customer requests this, "
            "and do not continue pitching afterward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Optional context"},
            },
            "required": [],
        },
    },
]


def _system_prompt_for(channel: str) -> str:
    return f"CHANNEL={channel}\n\n{BASE_SYSTEM_PROMPT}"


def _execute_tool(session: Session, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "book_site_visit":
        session.state["booking_attempts"] += 1
        result = simulate_booking(tool_input.get("date", ""), tool_input.get("time", ""))
        if result["success"]:
            session.state["site_visit_status"] = "booked"
            session.state["site_visit_details"] = {
                "name": tool_input.get("name"),
                "phone": tool_input.get("phone"),
                "date": tool_input.get("date"),
                "time": tool_input.get("time"),
                "configuration": tool_input.get("configuration"),
            }
        else:
            session.state["site_visit_status"] = "attempted_failed"
        return result

    if tool_name == "schedule_followup":
        session.state["follow_up_required"] = True
        session.state["follow_up_notes"] = (
            f"Contact at: {tool_input.get('preferred_time')}"
            + (f" — {tool_input.get('reason')}" if tool_input.get("reason") else "")
        )
        return {"logged": True}

    if tool_name == "escalate_to_human":
        session.state["escalated_to_human"] = True
        session.state["escalation_reason"] = tool_input.get("reason")
        return {"logged": True}

    if tool_name == "opt_out":
        session.state["opted_out"] = True
        session.state["site_visit_status"] = (
            "declined" if session.state["site_visit_status"] == "not_requested"
            else session.state["site_visit_status"]
        )
        return {"logged": True}

    return {"error": f"unknown tool {tool_name}"}


def _gemini_tool_response(system_prompt: str, messages: list, tools: list) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"
    history = []
    for message in messages:
        role = "user" if message["role"] == "user" else "model"
        content = message["content"]
        if isinstance(content, str):
            history.append({"role": role, "parts": [{"text": content}]})
        else:
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    parts.append({"text": json.dumps({"tool_result": block.get("content")})})
                elif hasattr(block, "type") and block.type == "text":
                    parts.append({"text": block.text})
                elif hasattr(block, "type") and block.type == "tool_use":
                    parts.append({"text": json.dumps({"tool_call": {"name": block.name, "args": block.input}})})
            history.append({"role": role, "parts": parts})

    payload = {
        "system_instruction": [{"parts": [{"text": system_prompt}]}],
        "tools": [{
            "function_declarations": [{
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            } for tool in tools]
        }],
        "contents": history,
    }
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def _extract_gemini_text(response: Dict[str, Any]) -> str:
    candidates = response.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts if "text" in part).strip()


def _extract_gemini_tool_calls(response: Dict[str, Any]) -> list:
    candidates = response.get("candidates", [])
    if not candidates:
        return []
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    tool_calls = []
    for part in parts:
        if "functionCall" in part:
            fn = part["functionCall"]
            tool_calls.append({
                "name": fn.get("name"),
                "args": fn.get("args", {}),
            })
    return tool_calls


def get_reply(session: Session, user_message: str) -> str:
    session.add_user_message(user_message)

    if MOCK_MODE:
        reply = _mock_reply(session, user_message)
        session.add_assistant_message(reply)
        return reply

    system_prompt = _system_prompt_for(session.channel)
    messages = list(session.messages)

    for _ in range(5):
        if AI_PROVIDER == "gemini":
            response = _gemini_tool_response(system_prompt, messages, TOOLS)
            tool_calls = _extract_gemini_tool_calls(response)
            if not tool_calls:
                final_text = _extract_gemini_text(response)
                session.add_assistant_message(final_text)
                return final_text or "..."

            assistant_content = []
            for tool_call in tool_calls:
                name = tool_call["name"]
                args = tool_call.get("args", {})
                assistant_content.append({"type": "tool_use", "name": name, "input": args, "id": f"call_{name}_{len(assistant_content)}"})
            messages.append({"role": "assistant", "content": assistant_content})
            tool_results = []
            for block in assistant_content:
                result = _execute_tool(session, block["name"], block["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": str(result),
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        import anthropic
        client = anthropic.Anthropic(api_key=API_KEY)
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=600,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            session.add_assistant_message(final_text)
            return final_text or "..."

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool(session, block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })
        messages.append({"role": "user", "content": tool_results})

    return "Sorry, I'm having trouble processing that — let me connect you with a human specialist."


# =====================================================================
# MOCK AGENT — used when no live API key is configured. This rule-based
# stand-in keeps the UI, session logic, booking simulation, and analytics
# runnable for testing/demo purposes while matching the same core intents
# at a simplified level.
# =====================================================================

def _mock_reply(session: Session, msg: str) -> str:
    m = msg.lower()

    def is_hindi(text):
        return any("\u0900" <= ch <= "\u097f" for ch in text)

    hinglish_markers = ["hai", "kya", "nahi", "kaise", "kitna", "aap", "mujhe", "bhai", "mein", "se", "aur", "bolte", "bolti"]
    lang = "Hindi" if is_hindi(msg) else ("Hinglish" if any(w in m for w in hinglish_markers) else "English")
    
    # Track language used in this conversation; respect user's language preference
    if session.state["language_used"] is None:
        session.state["language_used"] = lang
    elif lang != "English":
        session.state["language_used"] = lang

    # Extract phone number if present (10-digit pattern)
    phone_match = re.search(r'\b(\d{10})\b', msg)
    if phone_match:
        session.state["customer_phone"] = phone_match.group(1)
    
    # Extract name if it looks like a name (capitalize pattern)
    if any(word in m for word in ["name", "i'm", "im", "mera naam", "my name", "call me"]):
        # Try to extract name: look for patterns like "name is XYZ" or "I'm XYZ"
        name_match = re.search(r'(?:name\s+is|i[\'s]*m|call me)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)', msg, re.IGNORECASE)
        if name_match:
            session.state["customer_name"] = name_match.group(1).strip()

    # GREETING: Only greet if it's a simple greeting message (short and primarily a greeting)
    is_greeting = any(w in m for w in ["hi", "hello", "hey", "namaste", "haan", "how are", "how do", "kaise", "kya haal", "sup", "yo", "greetings"])
    is_simple_greeting = len(m) < 30 and is_greeting  # Short message + greeting keyword = likely a simple greeting
    if len(session.messages) == 1 and is_simple_greeting:
        responses = {
            "English": "Hello! How can I help you?",
            "Hinglish": "Namaste! Main aapki kaise madad kar sakti hoon?",
            "Hindi": "नमस्ते! मैं आपकी कैसे मदद कर सकती हूँ?"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["stop", "don't contact", "do not contact", "remove me", "band karo"]):
        session.state["opted_out"] = True
        responses = {
            "English": "Understood — I won't contact you again. Thank you for your time.",
            "Hinglish": "Theek hai, ab aapko dobara contact nahi kiya jayega. Dhanyavaad.",
            "Hindi": "ठीक है, अब आपको दोबारा contact नहीं किया जाएगा। धन्यवाद।"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["not interested", "no interest", "nahi chahiye"]):
        responses = {
            "English": "No problem at all, thanks for letting me know. If anything changes, feel free to reach out.",
            "Hinglish": "Koi baat nahi, batane ke liye dhanyavaad. Agar kabhi interest ho to zaroor batayega.",
            "Hindi": "कोई बात नहीं, बताने के लिए धन्यवाद। अगर कभी interest हो तो जरूर बताइएगा।"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["busy", "later", "call back", "baad me", "abhi nahi"]):
        session.state["follow_up_required"] = True
        session.state["follow_up_notes"] = "Customer asked to be contacted later (exact time not captured in mock mode)."
        responses = {
            "English": "No worries — when would be a better time to reach you?",
            "Hinglish": "Koi baat nahi — kis time par baat karna theek rahega?",
            "Hindi": "कोई बात नहीं — किस समय पर बात करना ठीक रहेगा?"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["human", "agent", "manager", "real person", "insaan"]):
        session.state["escalated_to_human"] = True
        session.state["escalation_reason"] = "Customer requested human agent"
        responses = {
            "English": "Sure, I'm connecting you with a Northstar Homes specialist who will follow up shortly.",
            "Hinglish": "Bilkul, main aapko Northstar Homes ke specialist se connect kar rahi hoon, woh jald follow up karenge.",
            "Hindi": "बिलकुल, मैं आपको Northstar Homes के specialist से connect कर रही हूँ, वो जल्द follow up करेंगे।"
        }
        return responses.get(lang, responses["English"])

    # Extract and track configuration and purpose from user message
    if any(w in m for w in ["2bhk", "2 bhk", "2 b h k"]):
        session.state["configuration_interest"] = "2 BHK"
    elif any(w in m for w in ["3bhk", "3 bhk", "3 b h k"]):
        session.state["configuration_interest"] = "3 BHK"
    
    if any(w in m for w in ["own use", "for my own use", "self use", "family", "rehne", "apne liye", "own", "apne", "personal use", "khud", "khud ke liye", "mera use"]):
        session.state["purpose"] = "self-use"
    elif any(w in m for w in ["investment", "sirf invest", "invest karna", "sirf paisa", "profit"]):
        session.state["purpose"] = "investment"

    if any(w in m for w in ["price", "cost", "kitna", "budget", "crore", "lakh"]):
        responses = {
            "English": ("Northstar One has 2 BHK starting at ₹1.35 crore and 3 BHK starting at ₹1.75 crore, "
                        "in Sector 79, Gurugram. Which configuration are you leaning towards?"),
            "Hinglish": ("Northstar One mein 2 BHK ₹1.35 crore se shuru hai aur 3 BHK ₹1.75 crore se, Sector 79 Gurugram mein. "
                         "Aapko kaunsa configuration pasand aayega?"),
            "Hindi": ("Northstar One में 2 BHK ₹1.35 crore से शुरू है और 3 BHK ₹1.75 crore से, Sector 79 Gurugram में। "
                     "आपको कौनसा configuration पसंद आयेगा?")
        }
        return responses.get(lang, responses["English"])

    if (("2bhk" in m or "2 bhk" in m or "2 b h k" in m or "3bhk" in m or "3 bhk" in m or "3 b h k" in m) and 
        ("own use" in m or "for my own use" in m or "self use" in m or "family" in m or "rehne" in m or "own" in m or "apne" in m or "personal use" in m or "khud" in m)):
        config = "2 BHK" if any(w in m for w in ["2bhk", "2 bhk", "2 b h k"]) else "3 BHK"
        responses = {
            "English": f"Thanks, that helps. A {config} for self-use is a good fit for this project. I can help with the next step if you'd like a site visit or a callback.",
            "Hinglish": f"Shukriya, yeh clear hai. {config} self-use ke liye project bahut suitable hai. Agar aap site visit ya callback chahte hain, main madad kar sakti hoon.",
            "Hindi": f"धन्यवाद, यह स्पष्ट है। {config} self-use के लिए project बहुत suitable है। अगर आप site visit या callback चाहते हैं, मैं मदद कर सकती हूँ।"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["visit", "site visit", "dekhna", "book", "booking", "book karna"]):
        session.state["booking_attempts"] += 1
        if "sunday" in m:
            session.state["site_visit_status"] = "attempted_failed"
            responses = {
                "English": "I checked, but site visits aren't available on Sundays. Could another day work — maybe Saturday or a weekday?",
                "Hinglish": "Check kiya, lekin Sunday ko site visit available nahi hai. Koi aur din theek rahega, jaise Saturday?",
                "Hindi": "चेक किया, लेकिन Sunday को site visit available नहीं है। कोई और दिन ठीक रहेगा, जैसे Saturday?"
            }
            return responses.get(lang, responses["English"])
        session.state["site_visit_status"] = "booked"
        session.state["site_visit_details"] = {"date": "as discussed", "time": "as discussed"}
        responses = {
            "English": "Great, I'll set that up. Could you share your name and phone number to confirm the visit?",
            "Hinglish": "Bahut badhiya, main visit set kar deti hoon. Apna naam aur phone number bata dijiye confirm karne ke liye.",
            "Hindi": "बहुत बढ़िया, मैं visit set कर देती हूँ। अपना नाम और phone number बता दिजिए confirm करने के लिए।"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["amenities", "possession", "rera", "loan", "emi", "discount", "offer"]):
        responses = {
            "English": "I don't have that exact detail on hand — I can have a specialist confirm it for you. Would that work?",
            "Hinglish": "Yeh exact detail mere paas abhi nahi hai — main specialist se confirm karwa deti hoon. Theek hai?",
            "Hindi": "यह exact detail मेरे पास अभी नहीं है — मैं specialist से confirm करा देती हूँ। ठीक है?"
        }
        return responses.get(lang, responses["English"])

    if any(w in m for w in ["bye", "thanks", "thank you", "dhanyavaad", "shukriya"]):
        responses = {
            "English": "Thank you for your time — have a great day!",
            "Hinglish": "Aapke time ke liye dhanyavaad — aapka din shubh ho!",
            "Hindi": "आपके time के लिए धन्यवाद — आपका दिन शुभ हो!"
        }
        return responses.get(lang, responses["English"])

    # Handle phone number when we're waiting for it (after callback request)
    if session.state["phone_asked_for_callback"] and session.state["customer_phone"]:
        session.state["follow_up_required"] = True
        session.state["callback_requested"] = True
        session.state["follow_up_notes"] = f"Customer requested callback from specialist. Phone: {session.state['customer_phone']}"
        responses = {
            "English": "Perfect! A specialist will reach out to you shortly with more details. Thank you!",
            "Hinglish": "Bilkul! Ek specialist aapko jald hi call karenge aur details batayenge. Dhanyavaad!",
            "Hindi": "बिलकुल! एक specialist आपको जल्द ही call करेंगे और details बताएंगे। धन्यवाद!"
        }
        return responses.get(lang, responses["English"])

    # Handle callback preference (after site visit/callback question)
    if any(w in m for w in ["callback", "kripya callback", "callback please", "specialist se", "koi specialist", "kripya specialist", "ok", "theek hai", "yes", "haan", "bilkul"]):
        # If phone not yet captured, ask for it
        if not session.state["customer_phone"]:
            responses = {
                "English": "Great! To send you a callback, could you please share your phone number?",
                "Hinglish": "Bahut badhiya! Callback bhejne ke liye, kripya apna phone number bata dijiye.",
                "Hindi": "बहुत बढ़िया! Callback भेजने के लिए, कृपया अपना phone number बता दिजिए।"
            }
            session.state["phone_asked_for_callback"] = True
            return responses.get(lang, responses["English"])
        
        # If we already have phone, confirm callback
        session.state["follow_up_required"] = True
        session.state["callback_requested"] = True
        session.state["follow_up_notes"] = f"Customer requested callback from specialist. Phone: {session.state['customer_phone']}"
        responses = {
            "English": "Perfect! A specialist will reach out to you shortly with more details. Thank you!",
            "Hinglish": "Bilkul! Ek specialist aapko jald hi call karenge aur details batayenge. Dhanyavaad!",
            "Hindi": "बिलकुल! एक specialist आपको जल्द ही call करेंगे और details बताएंगे। धन्यवाद!"
        }
        return responses.get(lang, responses["English"])

    # Default response: check what we already know to avoid redundant re-asking
    if session.state["configuration_interest"] is not None and session.state["purpose"] is not None:
        # Already know config and purpose, move to next step
        responses = {
            "English": "Got it! Would you like to book a site visit or would you prefer a callback from one of our specialists?",
            "Hinglish": "Samjh gaya! Kya aap site visit book karna chahte hain ya kisi specialist se callback prefer karenge?",
            "Hindi": "समझ गया! क्या आप site visit book करना चाहते हैं या किसी specialist से callback prefer करेंगे?"
        }
        return responses.get(lang, responses["English"])
    elif session.state["configuration_interest"] is not None:
        # Already know config, ask about purpose
        config = session.state["configuration_interest"]
        responses = {
            "English": f"Great, {config} is a good choice. Is this for your own use or investment?",
            "Hinglish": f"Bahut badhiya, {config} bilkul sahi choice hai. Yeh apne liye hai ya investment ke liye?",
            "Hindi": f"बहुत बढ़िया, {config} बिलकुल सही choice है। यह अपने लिए है या investment के लिए?"
        }
        return responses.get(lang, responses["English"])
    elif session.state["purpose"] is not None:
        # Already know purpose, ask about config
        purpose = session.state["purpose"]
        responses = {
            "English": f"Good to know. For {purpose}, are you interested in a 2 BHK or 3 BHK?",
            "Hinglish": f"Acha, samjh gaya. {purpose} ke liye, aap 2 BHK ya 3 BHK mein interested hain?",
            "Hindi": f"अच्छा, समझ गया। {purpose} के लिए, आप 2 BHK या 3 BHK में interested हैं?"
        }
        return responses.get(lang, responses["English"])
    else:
        # Don't know anything yet, ask everything
        responses = {
            "English": "Thanks for sharing that! Are you looking at a 2 BHK or 3 BHK, and is this for your own use or investment?",
            "Hinglish": "Bataane ke liye dhanyavaad! Aap 2 BHK dekh rahe hain ya 3 BHK, aur yeh khud rehne ke liye hai ya investment ke liye?",
            "Hindi": "बताने के लिए धन्यवाद! आप 2 BHK देख रहे हैं या 3 BHK, और यह खुद रहने के लिए है या investment के लिए?"
        }
        return responses.get(lang, responses["English"])
