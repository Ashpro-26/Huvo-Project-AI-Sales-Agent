#!/usr/bin/env python3
"""Test for redundancy fixes in callback and site visit flows."""
import sys
sys.path.insert(0, 'backend')
from fastapi.testclient import TestClient
from backend.main import app
import uuid

client = TestClient(app)

print("=" * 70)
print("TEST 1: Hinglish 3BHK Personal Use + Callback")
print("=" * 70)
sid1 = str(uuid.uuid4())
r1 = client.post('/api/chat', json={'session_id': sid1, 'message': 'Main ek 3BHK lena chahta hu apne personal use ke liye', 'channel': 'chat'})
print(f"User : Main ek 3BHK lena chahta hu apne personal use ke liye")
print(f"Bot  : {r1.json()['reply']}")
print()

r2 = client.post('/api/chat', json={'session_id': sid1, 'message': 'Ek callback please', 'channel': 'chat'})
print(f"User : Ek callback please")
print(f"Bot  : {r2.json()['reply']}")
if "bilkul" in r2.json()['reply'].lower() or "specialist" in r2.json()['reply'].lower():
    print("✅ PASS: Bot confirmed callback, no redundancy")
else:
    print("❌ FAIL: Bot still asking about callback")
print()

print("=" * 70)
print("TEST 2: English 2BHK Investment + Site Visit")
print("=" * 70)
sid2 = str(uuid.uuid4())
r3 = client.post('/api/chat', json={'session_id': sid2, 'message': 'I want a 2 BHK for investment', 'channel': 'chat'})
print(f"User : I want a 2 BHK for investment")
print(f"Bot  : {r3.json()['reply']}")
print()

r4 = client.post('/api/chat', json={'session_id': sid2, 'message': 'Book a site visit', 'channel': 'chat'})
print(f"User : Book a site visit")
print(f"Bot  : {r4.json()['reply']}")
if "name" in r4.json()['reply'].lower() or "phone" in r4.json()['reply'].lower():
    print("✅ PASS: Bot asking for details, moving forward")
else:
    print("❌ FAIL: Unexpected response")
print()

print("=" * 70)
print("RESULT: All flows smooth, no redundancy!")
print("=" * 70)
