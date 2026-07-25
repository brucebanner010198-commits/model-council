#!/usr/bin/env python3
"""
Comprehensive backend test suite for The Council API
Tests new username/password auth endpoints and regression tests
"""
import requests
import json
import time
from datetime import datetime

# Backend URL
BASE_URL = "https://c55e4954-05f1-4ce6-9454-c92edf151524.preview.emergentagent.com/api"

# Test data
TIMESTAMP = int(time.time())
TEST_USER1_EMAIL = f"qatest-user1-{TIMESTAMP}@example.com"
TEST_USER1_PASSWORD = "SecurePass123!"
TEST_USER1_NAME = "QA Test User 1"

TEST_USER2_EMAIL = f"qatest-user2-{TIMESTAMP}@example.com"
TEST_USER2_PASSWORD = "AnotherPass456!"
TEST_USER2_NAME = "QA Test User 2"

# Test results
test_results = []
user1_session_token = None
user2_session_token = None
user1_session_id = None
user2_session_id = None


def log_test(test_name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    result = {"test": test_name, "passed": passed, "details": details}
    test_results.append(result)
    print(f"{status}: {test_name}")
    if details:
        print(f"   Details: {details}")


def test_1_public_api_endpoint():
    """Test 1: GET /api/ returns 200 with correct message"""
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        if r.status_code == 200 and r.json().get("message") == "AI Model Council API":
            log_test("Public API endpoint", True, "GET /api/ returns 200 with correct message")
        else:
            log_test("Public API endpoint", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("Public API endpoint", False, str(e))


def test_2_auth_debug_unauthenticated():
    """Test 2: GET /api/auth/debug without auth"""
    try:
        r = requests.get(f"{BASE_URL}/auth/debug", timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Verify it returns expected keys
            required_keys = ["server_time", "origin", "referer", "cookie_present", "cookie_prefix",
                           "bearer_present", "bearer_prefix", "session_found", "session_expires_at",
                           "emergent_llm_key_configured", "resend_configured"]
            missing_keys = [k for k in required_keys if k not in data]
            if missing_keys:
                log_test("GET /api/auth/debug (unauthenticated)", False, f"Missing keys: {missing_keys}")
            elif data["cookie_present"] or data["bearer_present"] or data["session_found"]:
                log_test("GET /api/auth/debug (unauthenticated)", False, 
                        f"Should show no auth: cookie_present={data['cookie_present']}, bearer_present={data['bearer_present']}, session_found={data['session_found']}")
            else:
                log_test("GET /api/auth/debug (unauthenticated)", True, 
                        "Returns all required keys, no auth detected")
        else:
            log_test("GET /api/auth/debug (unauthenticated)", False, f"Status: {r.status_code}")
    except Exception as e:
        log_test("GET /api/auth/debug (unauthenticated)", False, str(e))


def test_3_register_user1():
    """Test 3: POST /api/auth/register - Create user1"""
    global user1_session_token
    try:
        payload = {
            "email": TEST_USER1_EMAIL,
            "password": TEST_USER1_PASSWORD,
            "name": TEST_USER1_NAME
        }
        r = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Verify response structure
            required_keys = ["user_id", "email", "name", "picture", "session_token"]
            missing_keys = [k for k in required_keys if k not in data]
            if missing_keys:
                log_test("POST /api/auth/register (user1)", False, f"Missing keys: {missing_keys}")
            elif data["email"] != TEST_USER1_EMAIL:
                log_test("POST /api/auth/register (user1)", False, f"Email mismatch: {data['email']}")
            else:
                user1_session_token = data["session_token"]
                # Verify cookie is set
                cookie = r.cookies.get("session_token")
                if not cookie:
                    log_test("POST /api/auth/register (user1)", False, "No session_token cookie set")
                elif cookie != user1_session_token:
                    log_test("POST /api/auth/register (user1)", False, 
                            f"Cookie value mismatch: cookie={cookie[:8]}..., body={user1_session_token[:8]}...")
                else:
                    log_test("POST /api/auth/register (user1)", True, 
                            f"User created, session_token in response matches cookie, user_id={data['user_id']}")
        elif r.status_code == 422:
            log_test("POST /api/auth/register (user1)", False, f"Validation error: {r.text}")
        else:
            log_test("POST /api/auth/register (user1)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/register (user1)", False, str(e))


def test_4_register_duplicate_email():
    """Test 4: POST /api/auth/register with duplicate email returns 409"""
    try:
        payload = {
            "email": TEST_USER1_EMAIL,
            "password": "DifferentPass789!",
            "name": "Duplicate User"
        }
        r = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=10)
        if r.status_code == 409:
            log_test("POST /api/auth/register (duplicate email)", True, "Returns 409 as expected")
        else:
            log_test("POST /api/auth/register (duplicate email)", False, 
                    f"Expected 409, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/register (duplicate email)", False, str(e))


def test_5_register_short_password():
    """Test 5: POST /api/auth/register with password < 8 chars returns 422"""
    try:
        payload = {
            "email": f"qatest-short-{TIMESTAMP}@example.com",
            "password": "short",
            "name": "Short Pass User"
        }
        r = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=10)
        if r.status_code == 422:
            log_test("POST /api/auth/register (short password)", True, "Returns 422 as expected")
        else:
            log_test("POST /api/auth/register (short password)", False, 
                    f"Expected 422, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/register (short password)", False, str(e))


def test_6_login_user1():
    """Test 6: POST /api/auth/login with correct credentials"""
    global user1_session_token
    try:
        payload = {
            "email": TEST_USER1_EMAIL,
            "password": TEST_USER1_PASSWORD
        }
        r = requests.post(f"{BASE_URL}/auth/login", json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            required_keys = ["user_id", "email", "name", "picture", "session_token"]
            missing_keys = [k for k in required_keys if k not in data]
            if missing_keys:
                log_test("POST /api/auth/login (correct credentials)", False, f"Missing keys: {missing_keys}")
            else:
                # Update session token (password rehash test - bcrypt roundtrip works)
                user1_session_token = data["session_token"]
                cookie = r.cookies.get("session_token")
                if cookie != user1_session_token:
                    log_test("POST /api/auth/login (correct credentials)", False, 
                            "Cookie value doesn't match response body")
                else:
                    log_test("POST /api/auth/login (correct credentials)", True, 
                            f"Login successful, bcrypt roundtrip works, user_id={data['user_id']}")
        else:
            log_test("POST /api/auth/login (correct credentials)", False, 
                    f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/login (correct credentials)", False, str(e))


def test_7_login_wrong_password():
    """Test 7: POST /api/auth/login with wrong password returns 401"""
    try:
        payload = {
            "email": TEST_USER1_EMAIL,
            "password": "WrongPassword123!"
        }
        r = requests.post(f"{BASE_URL}/auth/login", json=payload, timeout=10)
        if r.status_code == 401:
            detail = r.json().get("detail", "")
            if "Incorrect email or password" in detail:
                log_test("POST /api/auth/login (wrong password)", True, "Returns 401 with correct message")
            else:
                log_test("POST /api/auth/login (wrong password)", False, f"Wrong error message: {detail}")
        else:
            log_test("POST /api/auth/login (wrong password)", False, 
                    f"Expected 401, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/login (wrong password)", False, str(e))


def test_8_login_nonexistent_user():
    """Test 8: POST /api/auth/login with non-existent email returns 401"""
    try:
        payload = {
            "email": f"nonexistent-{TIMESTAMP}@example.com",
            "password": "SomePassword123!"
        }
        r = requests.post(f"{BASE_URL}/auth/login", json=payload, timeout=10)
        if r.status_code == 401:
            detail = r.json().get("detail", "")
            if "Incorrect email or password" in detail:
                log_test("POST /api/auth/login (non-existent user)", True, 
                        "Returns 401 with same message (security requirement)")
            else:
                log_test("POST /api/auth/login (non-existent user)", False, f"Wrong error message: {detail}")
        else:
            log_test("POST /api/auth/login (non-existent user)", False, 
                    f"Expected 401, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/login (non-existent user)", False, str(e))


def test_9_auth_debug_with_bearer():
    """Test 9: GET /api/auth/debug with Bearer token"""
    if not user1_session_token:
        log_test("GET /api/auth/debug (with Bearer)", False, "No user1_session_token available")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        r = requests.get(f"{BASE_URL}/auth/debug", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if not data.get("bearer_present"):
                log_test("GET /api/auth/debug (with Bearer)", False, "bearer_present should be true")
            elif not data.get("session_found"):
                log_test("GET /api/auth/debug (with Bearer)", False, "session_found should be true")
            elif not data.get("session_expires_at"):
                log_test("GET /api/auth/debug (with Bearer)", False, "session_expires_at should be present")
            else:
                # Verify token is truncated (only first 8 chars + ...)
                bearer_prefix = data.get("bearer_prefix", "")
                if len(bearer_prefix) > 12:  # Should be 8 chars + "..."
                    log_test("GET /api/auth/debug (with Bearer)", False, 
                            f"bearer_prefix too long (should be 8 chars + ...): {bearer_prefix}")
                else:
                    log_test("GET /api/auth/debug (with Bearer)", True, 
                            f"Bearer detected, session found, token truncated to {bearer_prefix}")
        else:
            log_test("GET /api/auth/debug (with Bearer)", False, f"Status: {r.status_code}")
    except Exception as e:
        log_test("GET /api/auth/debug (with Bearer)", False, str(e))


def test_10_auth_me_bearer():
    """Test 10: GET /api/auth/me with Bearer token"""
    if not user1_session_token:
        log_test("GET /api/auth/me (Bearer)", False, "No user1_session_token available")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        r = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("email") == TEST_USER1_EMAIL:
                log_test("GET /api/auth/me (Bearer)", True, f"Returns correct user data: {data.get('user_id')}")
            else:
                log_test("GET /api/auth/me (Bearer)", False, f"Email mismatch: {data.get('email')}")
        else:
            log_test("GET /api/auth/me (Bearer)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/auth/me (Bearer)", False, str(e))


def test_11_auth_me_cookie():
    """Test 11: GET /api/auth/me with cookie"""
    if not user1_session_token:
        log_test("GET /api/auth/me (Cookie)", False, "No user1_session_token available")
        return
    try:
        cookies = {"session_token": user1_session_token}
        r = requests.get(f"{BASE_URL}/auth/me", cookies=cookies, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("email") == TEST_USER1_EMAIL:
                log_test("GET /api/auth/me (Cookie)", True, f"Returns correct user data: {data.get('user_id')}")
            else:
                log_test("GET /api/auth/me (Cookie)", False, f"Email mismatch: {data.get('email')}")
        else:
            log_test("GET /api/auth/me (Cookie)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/auth/me (Cookie)", False, str(e))


def test_12_auth_me_unauthenticated():
    """Test 12: GET /api/auth/me without credentials returns 401"""
    try:
        r = requests.get(f"{BASE_URL}/auth/me", timeout=10)
        if r.status_code == 401:
            log_test("GET /api/auth/me (unauthenticated)", True, "Returns 401 as expected")
        else:
            log_test("GET /api/auth/me (unauthenticated)", False, 
                    f"Expected 401, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/auth/me (unauthenticated)", False, str(e))


def test_13_council_bearer():
    """Test 13: GET /api/council with Bearer token"""
    if not user1_session_token:
        log_test("GET /api/council (Bearer)", False, "No user1_session_token available")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        r = requests.get(f"{BASE_URL}/council", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if len(data.get("members", [])) == 5 and data.get("notetaker"):
                log_test("GET /api/council (Bearer)", True, "Returns 5 members and notetaker")
            else:
                log_test("GET /api/council (Bearer)", False, 
                        f"Expected 5 members, got {len(data.get('members', []))}")
        else:
            log_test("GET /api/council (Bearer)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/council (Bearer)", False, str(e))


def test_14_council_unauthenticated():
    """Test 14: GET /api/council without credentials returns 401"""
    try:
        r = requests.get(f"{BASE_URL}/council", timeout=10)
        if r.status_code == 401:
            log_test("GET /api/council (unauthenticated)", True, "Returns 401 as expected")
        else:
            log_test("GET /api/council (unauthenticated)", False, 
                    f"Expected 401, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/council (unauthenticated)", False, str(e))


def test_15_sessions_unauthenticated():
    """Test 15: GET /api/sessions without credentials returns 401"""
    try:
        r = requests.get(f"{BASE_URL}/sessions", timeout=10)
        if r.status_code == 401:
            log_test("GET /api/sessions (unauthenticated)", True, "Returns 401 as expected")
        else:
            log_test("GET /api/sessions (unauthenticated)", False, 
                    f"Expected 401, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/sessions (unauthenticated)", False, str(e))


def test_16_settings_unauthenticated():
    """Test 16: GET /api/settings without credentials returns 401"""
    try:
        r = requests.get(f"{BASE_URL}/settings", timeout=10)
        if r.status_code == 401:
            log_test("GET /api/settings (unauthenticated)", True, "Returns 401 as expected")
        else:
            log_test("GET /api/settings (unauthenticated)", False, 
                    f"Expected 401, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/settings (unauthenticated)", False, str(e))


def test_17_create_session_user1():
    """Test 17: POST /api/sessions - Create session for user1"""
    global user1_session_id
    if not user1_session_token:
        log_test("POST /api/sessions (user1)", False, "No user1_session_token available")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        payload = {
            "title": f"QA Test Session User1 {TIMESTAMP}",
            "participant_ids": ["gpt", "claude", "gemini", "deepseek", "kimi"]
        }
        r = requests.post(f"{BASE_URL}/sessions", json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("id") and len(data.get("participant_ids", [])) == 5:
                user1_session_id = data["id"]
                log_test("POST /api/sessions (user1)", True, f"Session created: {user1_session_id}")
            else:
                log_test("POST /api/sessions (user1)", False, f"Invalid response: {data}")
        else:
            log_test("POST /api/sessions (user1)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/sessions (user1)", False, str(e))


def test_18_get_session_user1():
    """Test 18: GET /api/sessions/{id} - Get user1's session"""
    if not user1_session_token or not user1_session_id:
        log_test("GET /api/sessions/{id} (user1)", False, "Missing user1_session_token or user1_session_id")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        r = requests.get(f"{BASE_URL}/sessions/{user1_session_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("id") == user1_session_id:
                log_test("GET /api/sessions/{id} (user1)", True, "Returns correct session")
            else:
                log_test("GET /api/sessions/{id} (user1)", False, f"Session ID mismatch: {data.get('id')}")
        else:
            log_test("GET /api/sessions/{id} (user1)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("GET /api/sessions/{id} (user1)", False, str(e))


def test_19_add_message_user1():
    """Test 19: POST /api/sessions/{id}/message - Add message to user1's session"""
    if not user1_session_token or not user1_session_id:
        log_test("POST /api/sessions/{id}/message (user1)", False, 
                "Missing user1_session_token or user1_session_id")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        payload = {"text": "Hello council, this is a test message"}
        r = requests.post(f"{BASE_URL}/sessions/{user1_session_id}/message", 
                         json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("speaker_id") == "human" and data.get("text"):
                log_test("POST /api/sessions/{id}/message (user1)", True, "Message added successfully")
            else:
                log_test("POST /api/sessions/{id}/message (user1)", False, f"Invalid response: {data}")
        else:
            log_test("POST /api/sessions/{id}/message (user1)", False, 
                    f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/sessions/{id}/message (user1)", False, str(e))


def test_20_register_user2():
    """Test 20: POST /api/auth/register - Create user2 for isolation test"""
    global user2_session_token
    try:
        payload = {
            "email": TEST_USER2_EMAIL,
            "password": TEST_USER2_PASSWORD,
            "name": TEST_USER2_NAME
        }
        r = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            user2_session_token = data["session_token"]
            log_test("POST /api/auth/register (user2)", True, f"User2 created: {data['user_id']}")
        else:
            log_test("POST /api/auth/register (user2)", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/register (user2)", False, str(e))


def test_21_user_isolation():
    """Test 21: User isolation - user2 cannot access user1's session"""
    if not user2_session_token or not user1_session_id:
        log_test("User isolation test", False, "Missing user2_session_token or user1_session_id")
        return
    try:
        headers = {"Authorization": f"Bearer {user2_session_token}"}
        r = requests.get(f"{BASE_URL}/sessions/{user1_session_id}", headers=headers, timeout=10)
        if r.status_code == 404:
            log_test("User isolation test", True, "User2 cannot access user1's session (404)")
        else:
            log_test("User isolation test", False, 
                    f"Expected 404, got {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_test("User isolation test", False, str(e))


def test_22_settings_write():
    """Test 22: POST /api/settings - Update OpenRouter key (security check)"""
    if not user1_session_token:
        log_test("POST /api/settings (security check)", False, "No user1_session_token available")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        payload = {"openrouter_key": "sk-or-test-key-12345"}
        r = requests.post(f"{BASE_URL}/settings", json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            # Now GET settings and verify key is NOT exposed
            r2 = requests.get(f"{BASE_URL}/settings", headers=headers, timeout=10)
            if r2.status_code == 200:
                data = r2.json()
                # Check that the actual key is not in the response
                response_str = json.dumps(data)
                if "sk-or-test-key-12345" in response_str:
                    log_test("POST /api/settings (security check)", False, 
                            "SECURITY ISSUE: API key exposed in GET /api/settings response")
                elif data.get("openrouter_configured") == True:
                    log_test("POST /api/settings (security check)", True, 
                            "Key stored, openrouter_configured=true, key NOT exposed")
                else:
                    log_test("POST /api/settings (security check)", False, 
                            f"openrouter_configured should be true: {data}")
            else:
                log_test("POST /api/settings (security check)", False, 
                        f"GET /api/settings failed: {r2.status_code}")
        else:
            log_test("POST /api/settings (security check)", False, 
                    f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/settings (security check)", False, str(e))


def test_23_logout():
    """Test 23: POST /api/auth/logout - Delete session"""
    if not user1_session_token:
        log_test("POST /api/auth/logout", False, "No user1_session_token available")
        return
    try:
        headers = {"Authorization": f"Bearer {user1_session_token}"}
        r = requests.post(f"{BASE_URL}/auth/logout", headers=headers, timeout=10)
        if r.status_code == 200:
            # Now try to access /auth/me with the same token - should fail
            r2 = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
            if r2.status_code == 401:
                log_test("POST /api/auth/logout", True, "Session deleted, subsequent /auth/me returns 401")
            else:
                log_test("POST /api/auth/logout", False, 
                        f"After logout, /auth/me should return 401, got {r2.status_code}")
        else:
            log_test("POST /api/auth/logout", False, f"Status: {r.status_code}, Body: {r.text[:200]}")
    except Exception as e:
        log_test("POST /api/auth/logout", False, str(e))


def test_24_delete_session():
    """Test 24: DELETE /api/sessions/{id} - Delete session (using user2's token)"""
    global user2_session_id
    if not user2_session_token:
        log_test("DELETE /api/sessions/{id}", False, "No user2_session_token available")
        return
    try:
        # First create a session for user2
        headers = {"Authorization": f"Bearer {user2_session_token}"}
        payload = {
            "title": f"QA Test Session User2 {TIMESTAMP}",
            "participant_ids": ["gpt", "claude"]
        }
        r = requests.post(f"{BASE_URL}/sessions", json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            log_test("DELETE /api/sessions/{id}", False, f"Failed to create session: {r.status_code}")
            return
        
        user2_session_id = r.json()["id"]
        
        # Now delete it
        r2 = requests.delete(f"{BASE_URL}/sessions/{user2_session_id}", headers=headers, timeout=10)
        if r2.status_code == 200:
            # Verify it's deleted
            r3 = requests.get(f"{BASE_URL}/sessions/{user2_session_id}", headers=headers, timeout=10)
            if r3.status_code == 404:
                log_test("DELETE /api/sessions/{id}", True, "Session deleted, subsequent GET returns 404")
            else:
                log_test("DELETE /api/sessions/{id}", False, 
                        f"After delete, GET should return 404, got {r3.status_code}")
        else:
            log_test("DELETE /api/sessions/{id}", False, f"Status: {r2.status_code}, Body: {r2.text[:200]}")
    except Exception as e:
        log_test("DELETE /api/sessions/{id}", False, str(e))


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for t in test_results if t["passed"])
    failed = sum(1 for t in test_results if not t["passed"])
    total = len(test_results)
    
    print(f"\nTotal: {total} tests")
    print(f"Passed: {passed} tests")
    print(f"Failed: {failed} tests")
    print(f"Success rate: {(passed/total*100):.1f}%\n")
    
    if failed > 0:
        print("FAILED TESTS:")
        print("-" * 80)
        for t in test_results:
            if not t["passed"]:
                print(f"❌ {t['test']}")
                if t["details"]:
                    print(f"   {t['details']}")
        print()
    
    print("="*80)


def main():
    """Run all tests"""
    print("="*80)
    print("The Council Backend API Test Suite")
    print("Testing new username/password auth endpoints and regression tests")
    print("="*80)
    print(f"\nBackend URL: {BASE_URL}")
    print(f"Test User 1: {TEST_USER1_EMAIL}")
    print(f"Test User 2: {TEST_USER2_EMAIL}")
    print(f"Timestamp: {TIMESTAMP}\n")
    print("="*80)
    print("RUNNING TESTS")
    print("="*80 + "\n")
    
    # Run all tests in order
    test_1_public_api_endpoint()
    test_2_auth_debug_unauthenticated()
    test_3_register_user1()
    test_4_register_duplicate_email()
    test_5_register_short_password()
    test_6_login_user1()
    test_7_login_wrong_password()
    test_8_login_nonexistent_user()
    test_9_auth_debug_with_bearer()
    test_10_auth_me_bearer()
    test_11_auth_me_cookie()
    test_12_auth_me_unauthenticated()
    test_13_council_bearer()
    test_14_council_unauthenticated()
    test_15_sessions_unauthenticated()
    test_16_settings_unauthenticated()
    test_17_create_session_user1()
    test_18_get_session_user1()
    test_19_add_message_user1()
    test_20_register_user2()
    test_21_user_isolation()
    test_22_settings_write()
    test_23_logout()
    test_24_delete_session()
    
    print_summary()


if __name__ == "__main__":
    main()
