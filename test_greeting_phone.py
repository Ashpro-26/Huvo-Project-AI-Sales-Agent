#!/usr/bin/env python3
"""Test for greeting and callback phone collection."""
import sys
sys.path.insert(0, 'backend')
from fastapi.testclient import TestClient
from backend.main import app
import uuid

client = TestClient(app)

print("=" * 70)
print("TEST 1: Greeting on first message")
print("=" * 70)
sid1 = str(uuid.uuid4())
r1 = client.post('/api/chat', json={'session_id': sid1, 'message': 'Hi there', 'channel': 'chat'})
print(f"User : Hi there")
print(f"Bot  : {r1.json()['reply']}")
if 'hello' in r1.json()['reply'].lower() or 'namaste' in r1.json()['reply'].lower():
    print("✅ PASS: Bot greeting received")
else:
    print("❌ FAIL: No greeting")
print()

print("=" * 70)
print("TEST 2: Callback with phone number flow")
print("=" * 70)
sid2 = str(uuid.uuid4())
r2 = client.post('/api/chat', json={'session_id': sid2, 'message': 'I want 3 BHK for personal use', 'channel': 'chat'})
print(f"User : I want 3 BHK for personal use")
print(f"Bot  : {r2.json()['reply']}")
print()

r3 = client.post('/api/chat', json={'session_id': sid2, 'message': 'callback please', 'channel': 'chat'})
print(f"User : callback please")
print(f"Bot  : {r3.json()['reply']}")
if 'phone' in r3.json()['reply'].lower():
    print("✅ PASS: Bot asking for phone")
else:
    print("❌ FAIL: Bot not asking for phone")
print()

r4 = client.post('/api/chat', json={'session_id': sid2, 'message': 'My number is 9876543210', 'channel': 'chat'})
print(f"User : My number is 9876543210")
print(f"Bot  : {r4.json()['reply']}")
if 'specialist' in r4.json()['reply'].lower() or 'call' in r4.json()['reply'].lower():
    print("✅ PASS: Bot confirmed callback with specialist")
else:
    print("❌ FAIL: Unexpected response")
print()

print("=" * 70)
print("TEST 3: Hinglish callback with phone")
print("=" * 70)
sid3 = str(uuid.uuid4())
r5 = client.post('/api/chat', json={'session_id': sid3, 'message': 'Main 3BHK chahta hu apne use ke liye', 'channel': 'chat'})
print(f"User : Main 3BHK chahta hu apne use ke liye")
print(f"Bot  : {r5.json()['reply']}")
print()

r6 = client.post('/api/chat', json={'session_id': sid3, 'message': 'Callback please, mera number 9123456789 hai', 'channel': 'chat'})
print(f"User : Callback please, mera number 9123456789 hai")
print(f"Bot  : {r6.json()['reply']}")
if 'specialist' in r6.json()['reply'].lower() or 'bilkul' in r6.json()['reply'].lower():
    print("✅ PASS: Bot confirmed callback (phone auto-detected)")
else:
    print("❌ FAIL: Bot not detecting phone in Hinglish message")
