#!/usr/bin/env python3
"""
Spot-check for synthesize endpoint - verify no UnboundLocalError on txt variable
"""

import requests
import time
from pymongo import MongoClient
from datetime import datetime, timedelta

BASE_URL = "https://c55e4954-05f1-4ce6-9454-c92edf151524.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
MONGO_URI = "mongodb://localhost:27017/council"

# MongoDB connection
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.council

# Test data
user_id = f"synth-test-{int(time.time())}"
token = f"synth_{int(time.time() * 1000)}"
email = f"synth.{int(time.time())}@x.dev"

print("\n" + "="*80)
print("SYNTHESIZE ENDPOINT SPOT-CHECK")
print("="*80 + "\n")

# Seed test user
try:
    db.users.insert_one({
        "user_id": user_id,
        "email": email,
        "name": "Synthesize Test User",
        "picture": "",
        "created_at": datetime.utcnow()
    })
    
    expires_at = datetime.utcnow() + timedelta(hours=1)
    db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": expires_at,
        "created_at": datetime.utcnow()
    })
    
    print(f"✅ Seeded test user: {user_id}")
except Exception as e:
    print(f"❌ Failed to seed user: {e}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# Create a session with 2+ participants
session_id = None
try:
    payload = {
        "title": "Synthesize test session",
        "participant_ids": ["gpt", "claude", "gemini"]
    }
    resp = requests.post(f"{API_BASE}/sessions", headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        session_id = resp.json().get("id")
        print(f"✅ Created session: {session_id}")
    else:
        print(f"❌ Failed to create session: {resp.status_code} - {resp.text}")
        exit(1)
except Exception as e:
    print(f"❌ Exception creating session: {e}")
    exit(1)

# Call synthesize endpoint
print("\n[Testing synthesize endpoint]")
print("Expected: Should fail gracefully with provider error (no API keys)")
print("NOT expected: UnboundLocalError on 'txt' variable\n")

try:
    payload = {
        "chairman_id": "gpt",
        "question": "What is 2+2?"
    }
    resp = requests.post(f"{API_BASE}/sessions/{session_id}/synthesize", 
                        headers=headers, json=payload, timeout=120)
    
    print(f"Response status: {resp.status_code}")
    
    if resp.status_code == 500:
        # Check if it's an UnboundLocalError
        response_text = resp.text.lower()
        if "unboundlocalerror" in response_text and "txt" in response_text:
            print(f"❌ REGRESSION DETECTED: UnboundLocalError on 'txt' variable!")
            print(f"Response: {resp.text[:500]}")
            exit(1)
        else:
            # Some other 500 error (likely provider error, which is expected)
            print(f"✅ Got 500 but NOT UnboundLocalError (likely provider error, which is expected)")
            print(f"Response snippet: {resp.text[:200]}")
    elif resp.status_code == 502:
        print(f"✅ Got 502 Bad Gateway (provider error, which is expected without API keys)")
        print(f"Response: {resp.json()}")
    elif resp.status_code == 400:
        print(f"✅ Got 400 Bad Request (provider error, which is expected without API keys)")
        print(f"Response: {resp.json()}")
    elif resp.status_code == 200:
        print(f"⚠️  Unexpected: Got 200 OK (should fail without provider keys)")
        print(f"Response: {resp.json()}")
    else:
        print(f"⚠️  Got unexpected status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
    
    print("\n✅ SPOT-CHECK PASSED: No UnboundLocalError detected")
    
except Exception as e:
    print(f"❌ Exception during synthesize call: {e}")
    exit(1)

# Cleanup
try:
    db.users.delete_one({"user_id": user_id})
    db.user_sessions.delete_one({"session_token": token})
    db.sessions.delete_one({"id": session_id})
    db.settings.delete_one({"_id": user_id})
    print("\n✅ Cleanup completed")
except Exception as e:
    print(f"⚠️  Cleanup warning: {e}")

print("\n" + "="*80)
print("SPOT-CHECK COMPLETE")
print("="*80 + "\n")
