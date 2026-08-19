#!/usr/bin/env python3
"""Quick check of original test suite scenarios."""
import sys
sys.path.insert(0, 'backend')
from fastapi.testclient import TestClient
from backend.main import app
import uuid

client = TestClient(app)

tests = [
    ("Basic price inquiry", ["Hi, what's the price of a 2 BHK at Northstar One?"], ["Northstar One has 2 BHK", "price"]),
    ("Hinglish inquiry", ["Bhai 3 BHK ka price kya hai Sector 79 wale project mein?"], ["Northstar One mein", "3 BHK"]),
    ("Opt-out", ["Please stop contacting me, I'm not interested at all."], ["understood", "theek hai", "contact nahi"]),
    ("Possession date", ["When exactly will possession be handed over?"], ["i don't have", "exact detail", "specialist"]),
    ("Site visit Sunday fail", ["Book me a site visit this Sunday at 4pm, name Priya Singh"], ["not available", "sunday", "another day"]),
]

print("=" * 70)
print("QUICK VALIDATION OF ORIGINAL TEST SCENARIOS")
print("=" * 70)

passed = 0
failed = 0

for title, messages, expected_phrases in tests:
    sid = str(uuid.uuid4())
    r = client.post('/api/chat', json={'session_id': sid, 'message': messages[0], 'channel': 'chat'})
    reply = r.json()['reply'].lower()
    
    match = any(phrase.lower() in reply for phrase in expected_phrases)
    if match:
        print(f"✅ {title}")
        passed += 1
    else:
        print(f"❌ {title}")
        print(f"   Expected any of: {expected_phrases}")
        print(f"   Got: {reply[:80]}...")
        failed += 1

print("=" * 70)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 70)
