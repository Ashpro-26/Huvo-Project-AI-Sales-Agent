import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

if AI_PROVIDER == "gemini":
    API_KEY = GEMINI_API_KEY
elif AI_PROVIDER == "anthropic":
    API_KEY = ANTHROPIC_API_KEY
else:
    API_KEY = GEMINI_API_KEY or ANTHROPIC_API_KEY

# If no API key is configured, the app runs in MOCK_MODE: a small rule-based
# stand-in for the LLM so the end-to-end app (UI, session memory, booking
# simulation, analytics) can still be run and graded without a key.
# Set GEMINI_API_KEY in .env to use the real agent + prompt.
MOCK_MODE = API_KEY == ""
