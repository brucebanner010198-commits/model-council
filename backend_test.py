#!/usr/bin/env python3
"""
Smoke test for The Council FastAPI backend
Launch-readiness test - does NOT test provider/LLM calls requiring real API keys
"""

import requests
import json
import time
from datetime import datetime
from pymongo import MongoClient

# Configuration
BASE_URL = "https://c55e4954-05f1-4ce6-9454-c92edf151524.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
MONGO_URI = "mongodb://localhost:27017/council"

# Test results tracking
results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def log_pass(test_name, details=""):
    results["passed"].append(f"✅ {test_name}: {details}")
    print(f"✅ {test_name}: {details}")

def log_fail(test_name, details=""):
    results["failed"].append(f"❌ {test_name}: {details}")
    print(f"❌ {test_name}: {details}")

def log_warning(test_name, details=""):
    results["warnings"].append(f"⚠️  {test_name}: {details}")
    print(f"⚠️  {test_name}: {details}")

# MongoDB connection
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.council

# Test data
user1_id = f"smoke-user-{int(time.time())}"
user1_token = f"smoke_{int(time.time() * 1000)}"
user1_email = f"smoke.{int(time.time())}@x.dev"

user2_id = f"smoke-user-{int(time.time())}-2"
user2_token = f"smoke_{int(time.time() * 1000)}_2"
user2_email = f"smoke.{int(time.time())}.2@x.dev"

session_id = None

print("\n" + "="*80)
print("THE COUNCIL - BACKEND SMOKE TEST")
print("="*80 + "\n")

# ============================================================================
# 1. PUBLIC ENDPOINT
# ============================================================================
print("\n[1] Testing Public Endpoint...")
try:
    resp = requests.get(f"{API_BASE}/", timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("message") == "AI Model Council API":
            log_pass("GET /api/", f"200 OK, message: {data.get('message')}")
        else:
            log_fail("GET /api/", f"200 but unexpected message: {data}")
    else:
        log_fail("GET /api/", f"Expected 200, got {resp.status_code}")
except Exception as e:
    log_fail("GET /api/", f"Exception: {e}")

# ============================================================================
# 2. AUTH GATING (401 without credentials)
# ============================================================================
print("\n[2] Testing Auth Gating (401 without credentials)...")

endpoints_requiring_auth = [
    "/auth/me",
    "/council",
    "/sessions",
    "/settings"
]

for endpoint in endpoints_requiring_auth:
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", timeout=10)
        if resp.status_code == 401:
            log_pass(f"GET /api{endpoint} without auth", "401 Unauthorized as expected")
        else:
            log_fail(f"GET /api{endpoint} without auth", f"Expected 401, got {resp.status_code}")
    except Exception as e:
        log_fail(f"GET /api{endpoint} without auth", f"Exception: {e}")

# ============================================================================
# 3. SEED USERS & SESSIONS IN MONGODB
# ============================================================================
print("\n[3] Seeding test users and sessions in MongoDB...")

try:
    # Seed user 1
    db.users.insert_one({
        "user_id": user1_id,
        "email": user1_email,
        "name": "Smoke Test User 1",
        "picture": "",
        "created_at": datetime.utcnow()
    })
    
    # Calculate expiry (1 hour from now)
    expires_at = datetime.utcnow()
    expires_at = expires_at.replace(microsecond=0)
    from datetime import timedelta
    expires_at = expires_at + timedelta(hours=1)
    
    db.user_sessions.insert_one({
        "user_id": user1_id,
        "session_token": user1_token,
        "expires_at": expires_at,
        "created_at": datetime.utcnow()
    })
    
    log_pass("Seed User 1", f"user_id={user1_id}, token={user1_token[:20]}...")
    
    # Seed user 2 for isolation testing
    db.users.insert_one({
        "user_id": user2_id,
        "email": user2_email,
        "name": "Smoke Test User 2",
        "picture": "",
        "created_at": datetime.utcnow()
    })
    
    db.user_sessions.insert_one({
        "user_id": user2_id,
        "session_token": user2_token,
        "expires_at": expires_at,
        "created_at": datetime.utcnow()
    })
    
    log_pass("Seed User 2", f"user_id={user2_id}, token={user2_token[:20]}...")
    
except Exception as e:
    log_fail("Seed users", f"Exception: {e}")

# ============================================================================
# 4. SIGNED-IN READS
# ============================================================================
print("\n[4] Testing Signed-in Reads with Bearer token...")

headers = {"Authorization": f"Bearer {user1_token}"}

# Test /auth/me
try:
    resp = requests.get(f"{API_BASE}/auth/me", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("user_id") == user1_id and data.get("email") == user1_email:
            log_pass("GET /api/auth/me with Bearer", f"200 OK, user_id={data.get('user_id')}, email={data.get('email')}")
        else:
            log_fail("GET /api/auth/me with Bearer", f"200 but unexpected data: {data}")
    else:
        log_fail("GET /api/auth/me with Bearer", f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("GET /api/auth/me with Bearer", f"Exception: {e}")

# Test /council
try:
    resp = requests.get(f"{API_BASE}/council", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        members = data.get("members", [])
        notetaker = data.get("notetaker")
        providers = data.get("providers", [])
        openrouter_configured = data.get("openrouter_configured")
        any_provider_configured = data.get("any_provider_configured")
        
        if len(members) == 5 and notetaker and len(providers) == 5:
            log_pass("GET /api/council with Bearer", 
                    f"200 OK, members={len(members)}, providers={len(providers)}, "
                    f"openrouter_configured={openrouter_configured}, any_provider_configured={any_provider_configured}")
        else:
            log_fail("GET /api/council with Bearer", 
                    f"200 but unexpected structure: members={len(members)}, providers={len(providers)}")
    else:
        log_fail("GET /api/council with Bearer", f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("GET /api/council with Bearer", f"Exception: {e}")

# Test /settings
try:
    resp = requests.get(f"{API_BASE}/settings", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        openrouter_configured = data.get("openrouter_configured")
        providers_configured = data.get("providers_configured")
        
        if openrouter_configured is not None and providers_configured is not None:
            log_pass("GET /api/settings with Bearer", 
                    f"200 OK, openrouter_configured={openrouter_configured}, providers_configured={providers_configured}")
        else:
            log_fail("GET /api/settings with Bearer", f"200 but missing expected fields: {data}")
    else:
        log_fail("GET /api/settings with Bearer", f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("GET /api/settings with Bearer", f"Exception: {e}")

# ============================================================================
# 5. SESSIONS CRUD
# ============================================================================
print("\n[5] Testing Sessions CRUD...")

# Create session
try:
    payload = {
        "title": "Smoke test session",
        "participant_ids": ["gpt", "claude", "gemini", "deepseek", "kimi"]
    }
    resp = requests.post(f"{API_BASE}/sessions", headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        session_id = data.get("id")
        owner = data.get("owner")
        participant_ids = data.get("participant_ids", [])
        turns = data.get("turns", [])
        notes = data.get("notes", [])
        status = data.get("status")
        
        if (session_id and owner == user1_id and len(participant_ids) == 5 and 
            len(turns) == 0 and len(notes) == 0 and status == "active"):
            log_pass("POST /api/sessions", 
                    f"200 OK, session_id={session_id}, owner={owner}, participants={len(participant_ids)}, status={status}")
        else:
            log_fail("POST /api/sessions", f"200 but unexpected data: {data}")
    else:
        log_fail("POST /api/sessions", f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("POST /api/sessions", f"Exception: {e}")

# List sessions
try:
    resp = requests.get(f"{API_BASE}/sessions", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and any(s.get("id") == session_id for s in data):
            log_pass("GET /api/sessions", f"200 OK, found newly created session in list")
        else:
            log_fail("GET /api/sessions", f"200 but session not found in list")
    else:
        log_fail("GET /api/sessions", f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("GET /api/sessions", f"Exception: {e}")

# Get specific session
if session_id:
    try:
        resp = requests.get(f"{API_BASE}/sessions/{session_id}", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("id") == session_id:
                log_pass(f"GET /api/sessions/{session_id}", f"200 OK, retrieved session")
            else:
                log_fail(f"GET /api/sessions/{session_id}", f"200 but wrong session: {data.get('id')}")
        else:
            log_fail(f"GET /api/sessions/{session_id}", f"Expected 200, got {resp.status_code}: {resp.text}")
    except Exception as e:
        log_fail(f"GET /api/sessions/{session_id}", f"Exception: {e}")

# Add message to session
if session_id:
    try:
        payload = {"text": "Hello council"}
        resp = requests.post(f"{API_BASE}/sessions/{session_id}/message", 
                           headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("text") == "Hello council" and data.get("speaker_id") == "human":
                log_pass(f"POST /api/sessions/{session_id}/message", 
                        f"200 OK, turn added: {data.get('text')}")
            else:
                log_fail(f"POST /api/sessions/{session_id}/message", f"200 but unexpected turn: {data}")
        else:
            log_fail(f"POST /api/sessions/{session_id}/message", 
                    f"Expected 200, got {resp.status_code}: {resp.text}")
    except Exception as e:
        log_fail(f"POST /api/sessions/{session_id}/message", f"Exception: {e}")

# Delete session
if session_id:
    try:
        resp = requests.delete(f"{API_BASE}/sessions/{session_id}", headers=headers, timeout=10)
        if resp.status_code == 200:
            log_pass(f"DELETE /api/sessions/{session_id}", "200 OK, session deleted")
        else:
            log_fail(f"DELETE /api/sessions/{session_id}", 
                    f"Expected 200, got {resp.status_code}: {resp.text}")
    except Exception as e:
        log_fail(f"DELETE /api/sessions/{session_id}", f"Exception: {e}")

# Verify session is deleted (404)
if session_id:
    try:
        resp = requests.get(f"{API_BASE}/sessions/{session_id}", headers=headers, timeout=10)
        if resp.status_code == 404:
            log_pass(f"GET /api/sessions/{session_id} after delete", "404 Not Found as expected")
        else:
            log_fail(f"GET /api/sessions/{session_id} after delete", 
                    f"Expected 404, got {resp.status_code}")
    except Exception as e:
        log_fail(f"GET /api/sessions/{session_id} after delete", f"Exception: {e}")

# ============================================================================
# 6. SETTINGS WRITE
# ============================================================================
print("\n[6] Testing Settings Write...")

# Update settings with personas and routing
try:
    payload = {
        "personas": {"gpt": "very sceptical"},
        "routing": {"gpt": "auto"}
    }
    resp = requests.post(f"{API_BASE}/settings", headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        log_pass("POST /api/settings (personas/routing)", "200 OK")
    else:
        log_fail("POST /api/settings (personas/routing)", 
                f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("POST /api/settings (personas/routing)", f"Exception: {e}")

# Verify settings were applied
try:
    resp = requests.get(f"{API_BASE}/settings", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        personas = data.get("personas", {})
        routing = data.get("routing", {})
        
        if personas.get("gpt") == "very sceptical" and routing.get("gpt") == "auto":
            log_pass("GET /api/settings (verify personas/routing)", 
                    f"200 OK, personas and routing applied correctly")
        else:
            log_fail("GET /api/settings (verify personas/routing)", 
                    f"200 but settings not applied: personas={personas}, routing={routing}")
    else:
        log_fail("GET /api/settings (verify personas/routing)", 
                f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("GET /api/settings (verify personas/routing)", f"Exception: {e}")

# Update settings with OpenRouter key
try:
    payload = {"openrouter_key": "sk-or-fake-key-for-test"}
    resp = requests.post(f"{API_BASE}/settings", headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        log_pass("POST /api/settings (openrouter_key)", "200 OK")
    else:
        log_fail("POST /api/settings (openrouter_key)", 
                f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("POST /api/settings (openrouter_key)", f"Exception: {e}")

# Verify OpenRouter key is configured but NOT in response
try:
    resp = requests.get(f"{API_BASE}/settings", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        openrouter_configured = data.get("openrouter_configured")
        response_text = json.dumps(data)
        
        if openrouter_configured is True:
            if "sk-or-fake-key-for-test" not in response_text:
                log_pass("GET /api/settings (verify openrouter_configured)", 
                        "200 OK, openrouter_configured=True and key NOT in response (secure)")
            else:
                log_fail("GET /api/settings (verify openrouter_configured)", 
                        "200 but SECURITY ISSUE: API key exposed in response!")
        else:
            log_fail("GET /api/settings (verify openrouter_configured)", 
                    f"200 but openrouter_configured={openrouter_configured}, expected True")
    else:
        log_fail("GET /api/settings (verify openrouter_configured)", 
                f"Expected 200, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("GET /api/settings (verify openrouter_configured)", f"Exception: {e}")

# ============================================================================
# 7. MAGIC-LINK WHEN NOT CONFIGURED
# ============================================================================
print("\n[7] Testing Magic-link when not configured...")

try:
    payload = {"email": "test@example.com"}
    resp = requests.post(f"{API_BASE}/auth/magic/request", json=payload, timeout=10)
    if resp.status_code == 503:
        log_pass("POST /api/auth/magic/request (no RESEND_API_KEY)", 
                "503 Service Unavailable as expected")
    else:
        log_fail("POST /api/auth/magic/request (no RESEND_API_KEY)", 
                f"Expected 503, got {resp.status_code}: {resp.text}")
except Exception as e:
    log_fail("POST /api/auth/magic/request (no RESEND_API_KEY)", f"Exception: {e}")

# ============================================================================
# 8. AUTH REJECTION
# ============================================================================
print("\n[8] Testing Auth Rejection...")

# Test with invalid token
try:
    invalid_headers = {"Authorization": "Bearer invalidtoken"}
    resp = requests.get(f"{API_BASE}/auth/me", headers=invalid_headers, timeout=10)
    if resp.status_code == 401:
        log_pass("GET /api/auth/me with invalid token", "401 Unauthorized as expected")
    else:
        log_fail("GET /api/auth/me with invalid token", 
                f"Expected 401, got {resp.status_code}")
except Exception as e:
    log_fail("GET /api/auth/me with invalid token", f"Exception: {e}")

# Test DELETE with random UUID (should be 200 idempotent or 404)
try:
    import uuid
    random_uuid = str(uuid.uuid4())
    resp = requests.delete(f"{API_BASE}/sessions/{random_uuid}", headers=headers, timeout=10)
    if resp.status_code in [200, 404]:
        log_pass(f"DELETE /api/sessions/{random_uuid} (random UUID)", 
                f"{resp.status_code} (idempotent delete)")
    else:
        log_warning(f"DELETE /api/sessions/{random_uuid} (random UUID)", 
                   f"Got {resp.status_code}, expected 200 or 404")
except Exception as e:
    log_fail(f"DELETE /api/sessions/{random_uuid} (random UUID)", f"Exception: {e}")

# ============================================================================
# 9. ISOLATION (User 2 cannot access User 1's session)
# ============================================================================
print("\n[9] Testing User Isolation...")

# First, create a session for user 1
user1_session_id = None
try:
    payload = {
        "title": "User 1 private session",
        "participant_ids": ["gpt", "claude"]
    }
    resp = requests.post(f"{API_BASE}/sessions", headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        user1_session_id = data.get("id")
        log_pass("Create session for User 1", f"session_id={user1_session_id}")
    else:
        log_fail("Create session for User 1", f"Expected 200, got {resp.status_code}")
except Exception as e:
    log_fail("Create session for User 1", f"Exception: {e}")

# Try to access User 1's session with User 2's token
if user1_session_id:
    try:
        user2_headers = {"Authorization": f"Bearer {user2_token}"}
        resp = requests.get(f"{API_BASE}/sessions/{user1_session_id}", 
                          headers=user2_headers, timeout=10)
        if resp.status_code == 404:
            log_pass("User 2 access User 1's session", 
                    "404 Not Found as expected (proper isolation)")
        else:
            log_fail("User 2 access User 1's session", 
                    f"Expected 404, got {resp.status_code} - SECURITY ISSUE: User isolation broken!")
    except Exception as e:
        log_fail("User 2 access User 1's session", f"Exception: {e}")

# ============================================================================
# 10. CLEANUP
# ============================================================================
print("\n[10] Cleaning up test data...")

try:
    # Delete test users
    result = db.users.delete_many({"user_id": {"$regex": "^smoke-user-"}})
    log_pass("Cleanup users", f"Deleted {result.deleted_count} test users")
    
    # Delete test sessions
    result = db.user_sessions.delete_many({"session_token": {"$regex": "^smoke_"}})
    log_pass("Cleanup user_sessions", f"Deleted {result.deleted_count} test sessions")
    
    # Delete test council sessions
    result = db.sessions.delete_many({"owner": {"$regex": "^smoke-user-"}})
    log_pass("Cleanup sessions", f"Deleted {result.deleted_count} test council sessions")
    
    # Delete test settings
    result = db.settings.delete_many({"_id": {"$regex": "^smoke-user-"}})
    log_pass("Cleanup settings", f"Deleted {result.deleted_count} test settings")
    
except Exception as e:
    log_fail("Cleanup", f"Exception: {e}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*80)
print("TEST SUMMARY")
print("="*80)

print(f"\n✅ PASSED: {len(results['passed'])}")
for item in results["passed"]:
    print(f"  {item}")

if results["warnings"]:
    print(f"\n⚠️  WARNINGS: {len(results['warnings'])}")
    for item in results["warnings"]:
        print(f"  {item}")

if results["failed"]:
    print(f"\n❌ FAILED: {len(results['failed'])}")
    for item in results["failed"]:
        print(f"  {item}")
else:
    print("\n🎉 ALL TESTS PASSED!")

print("\n" + "="*80)
print(f"Total: {len(results['passed'])} passed, {len(results['failed'])} failed, {len(results['warnings'])} warnings")
print("="*80 + "\n")

# Exit with appropriate code
exit(0 if len(results["failed"]) == 0 else 1)
