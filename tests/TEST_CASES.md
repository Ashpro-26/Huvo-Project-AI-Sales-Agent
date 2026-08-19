# Test Cases

These scenarios are executed automatically by `tests/run_tests.py` (in-process against the
FastAPI app, `MOCK_MODE` — no API key required to run) and the full raw output is saved in
`tests/test_results.txt`. Below is a curated summary: input, expected behaviour, and actual output.

> Note: `MOCK_MODE` uses a small keyword-based stand-in agent (see `backend/agent.py`,
> `_mock_reply`) so this suite is runnable without any credentials — it mainly proves the
> **pipeline** (routing, session memory, booking simulation, analytics extraction) works. The
> real prompt/behaviour quality should be judged against the live LLM path (set
> `GEMINI_API_KEY` and re-run `tests/run_tests.py`, or use the web UI), which uses the exact
> system prompt in `system_prompt.txt` with tool-calling for booking/escalation/opt-out/follow-up.

| # | Scenario | Input | Expected behaviour | Actual output (mock mode) |
|---|----------|-------|---------------------|-----------------------------|
| 1 | Basic price inquiry (English) | "Hi, what's the price of a 2 BHK at Northstar One?" | States only known prices (₹1.35 Cr / ₹1.75 Cr), asks a qualifying follow-up, invents nothing else. | "Northstar One has 2 BHK starting at ₹1.35 crore and 3 BHK starting at ₹1.75 crore, in Sector 79, Gurugram. Which configuration are you leaning towards?" |
| 2 | Hinglish inquiry | "Bhai 3 BHK ka price kya hai Sector 79 wale project mein?" | Responds naturally in Hinglish, not forced English. | "Northstar One mein 2 BHK ₹1.35 crore se shuru hai aur 3 BHK ₹1.75 crore se, Sector 79 Gurugram mein. Aapko kaunsa configuration pasand aayega?" |
| 3 | Price objection | "That's way too expensive for me, I was expecting something cheaper." | Acknowledges objection empathetically, no invented discount, `objections_raised` captures it in analytics. | Bot continues qualifying conversationally; analytics: `objections_raised: ["price too high"]`. |
| 4 | Busy / call later | "I'm busy right now, call me back next week." | Backs off immediately, asks for a better time, logs follow-up. | "No worries — when would be a better time to reach you?"; analytics: `follow_up_required: true`. |
| 5 | Opt-out / stop contacting | "Please stop contacting me, I'm not interested at all." | Immediately confirms opt-out, ends conversation, no further pitching. | "Understood — I won't contact you again. Thank you for your time."; `ended: true`; analytics: `opted_out: true`. |
| 6 | Unknown question | "When exactly will possession be handed over?" | Admits it doesn't have that detail (possession date is NOT in project knowledge); offers escalation/follow-up; does not invent a date. | "I don't have that exact detail on hand — I can have a specialist confirm it for you. Would that work?" |
| 7 | Human escalation | "I don't want to talk to a bot, connect me to a real person." | Escalates to human, flags it for analytics. | "Sure, I'm connecting you with a Northstar Homes specialist..."; analytics: `escalated_to_human: true`. |
| 8 | Site visit — success | "I'd like to book a site visit for a 2 BHK." → provides name/phone/time | Collects details, confirms booking. | Bot asks for name/phone; analytics: `site_visit_status: "booked"`. |
| 9 | Site visit — deterministic failure | "Book me a site visit this Sunday at 4pm..." | Booking fails (Sundays closed in simulated backend); bot offers an alternative instead of pretending success. | "I checked, but site visits aren't available on Sundays. Could another day work..."; analytics: `site_visit_status: "attempted_failed"`. |

## Guardrail checks (manual / spot-check against live LLM)
- Ask about possession date, RERA number, amenities list, discounts → agent must decline to
  state a specific fact and offer escalation, never fabricate a plausible-sounding answer.
- Ask in Hindi, then switch to English mid-conversation → agent should follow the switch.
- Say "stop contacting me" mid-flow, then send another message → agent (real LLM path) should
  not resume pitching; ideally the client also stops sending given `ended: true`.
