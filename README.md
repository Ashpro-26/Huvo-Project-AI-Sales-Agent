# Northstar Homes — AI Sales Agent (Huvo AI FDE Assignment)

An AI conversational sales agent for a fictional real-estate project (**Northstar One**,
Sector 79, Gurugram), built as: a channel-agnostic system prompt (works for chat and voice),
a FastAPI backend with tool-use for site-visit booking/escalation/follow-up/opt-out, a simple
web chat UI, and post-conversation analytics generation.

## Project structure

```
northstar-bot/
├── system_prompt.txt          # The final prompt source of truth, loaded at runtime
├── backend/
│   ├── main.py                # FastAPI app: /api/chat, /api/end, static UI
│   ├── agent.py               # Prompt loading, Gemini tool-use loop, MOCK_MODE fallback
│   ├── analytics.py           # Post-conversation analytics extraction
│   ├── session_store.py       # In-memory session/conversation memory + simulated booking system
│   ├── models.py              # Pydantic request/response/analytics schemas
│   ├── config.py              # Env config (API key, model, mock-mode flag)
│   ├── requirements.txt
│   └── static/index.html     # Premium landing-page chat UI
├── tests/
│   ├── run_tests.py          # Scripted scenarios run in-process against the app
│   ├── test_results.txt      # Captured output from the last run
│   └── TEST_CASES.md         # Input / expected / actual summary table
├── .env.example
└── README.md
```

## How to run

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp ../.env.example .env
# Edit .env and set GEMINI_API_KEY=... to use the real agent.
# Leave it empty to run in MOCK_MODE (see "Mock mode" below).

python3 main.py
# or: uvicorn main:app --reload
```

Then open **http://localhost:8000** — a simple chat UI is served directly by FastAPI
(no separate frontend build/server needed). Pick "Chat" or "Voice (simulated)" from the
channel dropdown to see the same prompt adapt its style (voice replies avoid
markdown/bullets/emoji and stay in short spoken sentences).

Click **"End conversation & view analytics"** at any point to close the session and see the
generated analytics JSON in the panel below the chat.

### Running the test scenarios

```bash
cd .. # repo root
python3 tests/run_tests.py
```

This runs 9 scripted scenarios in-process (via FastAPI's `TestClient`) and prints
input/output/analytics for each — see `tests/TEST_CASES.md` for the curated table and
`tests/test_results.txt` for full captured output. It works with or without an API key
(mock mode auto-detected).

## The prompt (Part 1)

The full final prompt is in [system_prompt.txt](system_prompt.txt). Design choices worth calling out:

- **One prompt, two channels.** The backend prepends `CHANNEL=chat` or `CHANNEL=voice` to the
  system prompt at request time. The prompt itself contains a "Channel Awareness" section
  telling the model exactly how to adapt (no markdown/bullets/emoji on voice, shorter
  single-idea sentences, confirm-back critical details since voice STT can mishear).
- **Hard-scoped project knowledge.** Only the facts given in the assignment (project,
  location, configurations, starting prices) are listed as things the agent may state. It is
  explicitly told what it does *not* know (possession date, amenities, RERA, discounts, etc.)
  and instructed to never invent, estimate, or round toward an answer — this directly
  satisfies the "should not invent prices/discounts/availability" requirement.
- **Tool-use instead of free-text promises.** Booking, follow-up scheduling, escalation, and
  opt-out are modeled as actual tool calls (`book_site_visit`, `schedule_followup`,
  `escalate_to_human`, `opt_out`) rather than letting the model just say a booking succeeded.
  The backend simulates a real booking system behind the tool (see
  `session_store.simulate_booking`) and returns success/failure, so the prompt has explicit
  instructions for handling booking failure without looping or over-apologizing.
- **Opt-out is treated as an absolute override** — the prompt states this explicitly so it
  takes priority over every other goal (qualification, booking, etc.), and the backend also
  enforces it structurally (`ended: true` is returned and the session should stop).
- **Objection handling, busy/uninterested, and "call later"** each get their own short
  playbook: acknowledge → respond with real facts only → offer one low-friction next step,
  without pressure tactics or fabricated urgency.

## Simple bot (Part 2)

- **Backend:** FastAPI (`backend/main.py`), as required. Two endpoints: `POST /api/chat`
  (send a message, get a reply) and `POST /api/end` (close the session, get analytics).
- **Memory:** each `session_id` accumulates the full message history plus a structured
  `state` dict updated by tool calls (booking status, opt-out, escalation, follow-up) —
  see `session_store.py`. This is intentionally simple in-memory storage per the assignment's
  "keep implementation simple" guidance; swapping in Redis/Postgres would be a small change.
- **Web interface:** a single static `index.html` (vanilla JS, no build step) served by
  FastAPI itself, with a channel selector and a premium real-estate landing-page layout that
  embeds the conversation flow and shows analytics when the session is ended.
- **Languages:** the prompt asks the model to detect and mirror English/Hindi/Hinglish
  per-turn; the mock fallback agent does a lightweight version of the same (Devanagari
  detection + Hinglish keyword heuristics) purely so the pipeline is testable without a key.
- **Booking simulation + failure handling:** `session_store.simulate_booking()` deterministically
  fails any visit requested for "Sunday" (site closed) and randomly fails ~15% of other
  requests (slot taken), so both the happy path and the failure path are exercised. The
  agent is prompted to handle failure by proposing an alternative rather than retrying blindly
  or apologizing repeatedly.
- **Analytics:** generated on `POST /api/end`. Hard facts (site-visit status/details,
  opt-out, escalation, follow-up) come directly from the tool-call-derived session state —
  no guessing. Softer, judgement-based fields (interest level, budget signal, purpose,
  timeline, language mix, objections, summary) come from one extra structured-JSON extraction
  call over the transcript (`analytics.py`), with a keyword-based fallback in mock mode. See
  `models.Analytics` for the full schema.

## Mock mode

If `GEMINI_API_KEY` is not set in `.env`, the app automatically runs in `MOCK_MODE`: a
small rule-based responder stands in for the LLM (see `agent._mock_reply` and
`analytics._mock_extraction`) so the whole app — UI, session memory, booking simulation,
analytics — is runnable and gradeable without any credentials. It is **not** a substitute for
the real prompt; it exists purely so the structure/behaviour of the system can be verified
without an API key. The banner in the web UI makes this visible, and `GET /api/mode` reports
`mock_mode` explicitly.

## Key assumptions

- Only the facts given in the assignment brief are "real" project knowledge; everything else
  (possession date, amenities, exact floor plans, discounts, loan tie-ups) is deliberately
  treated as unknown, per the "do not invent" requirement.
- One session = one conversation = one lead. No cross-session lead merging/dedup is
  implemented (out of scope for "keep it simple").
- "Voice" is simulated at the prompt-style level (the agent avoids visual-only formatting and
  speaks in short confirm-back sentences); no actual speech-to-text/text-to-speech pipeline is
  wired up, since the assignment asks for a text-based bot for Part 2 with a prompt that's
  *suitable* for voice, not a live voice integration.
- Booking "success/failure" is simulated (see above) rather than hitting a real CRM/calendar,
  since no such backend was specified.
- CORS is left wide open (`*`) since this is a local demo, not a production deployment.

## Known limitations

- In-memory session store: restarting the server loses all conversations (fine for a demo;
  would move to a persistent store for production).
- `MOCK_MODE`'s rule-based responder is intentionally simplistic (keyword matching) — it's a
  fallback for running without an API key, not a demonstration of prompt quality. The real
  behaviour should be evaluated via the live LLM path.
- No authentication/rate-limiting on the API — not needed for this assignment's scope.
- Analytics extraction via a second LLM call adds one extra API round-trip per `end` call;
  fine for a demo, would likely be batched/cached differently at scale.
- No persistent lead database — analytics are computed on demand and returned in the API
  response, not stored anywhere durable.

## AI tools used

- Gemini is the primary LLM powering the agent at runtime.
- The project also keeps a mock fallback path for local development and testing without credentials.
