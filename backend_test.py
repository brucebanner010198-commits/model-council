#!/usr/bin/env python3
"""
Subscription OAuth backend test suite for The Council
Tests subscription persistence, token privacy, and observability
"""
import requests
import json
import time
import sys
from datetime import datetime

# Backend URL
BASE_URL = "https://docs-ready-1.preview.emergentagent.com/api"

# Test results tracking
test_results = []
failed_tests = []

def log_test(step, description, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    result = f"Step {step}: {status} - {description}"
    if details:
        result += f"\n    Details: {details}"
    print(result)
    test_results.append({
        "step": step,
        "description": description,
        "passed": passed,
        "details": details
    })
    if not passed:
        failed_tests.append(f"Step {step}: {description}")

def check_token_leak(response_body, forbidden_strings, step):
    """Check if any forbidden token strings appear in response"""
    body_str = json.dumps(response_body) if isinstance(response_body, dict) else str(response_body)
    leaked = []
    for token in forbidden_strings:
        if token in body_str:
            leaked.append(token)
    return leaked

def main():
    print("=" * 80)
    print("SUBSCRIPTION OAUTH BACKEND TEST SUITE")
    print("=" * 80)
    print()

    # Setup: Register a fresh test user
    timestamp = int(time.time())
    test_email = f"qasub-{timestamp}@example.com"
    test_password = "TestPass123!"
    
    print(f"SETUP: Registering test user {test_email}")
    register_resp = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": test_email, "password": test_password, "name": "QA Sub Test"}
    )
    
    if register_resp.status_code != 200:
        print(f"❌ SETUP FAILED: Could not register user. Status: {register_resp.status_code}")
        print(f"Response: {register_resp.text}")
        sys.exit(1)
    
    register_data = register_resp.json()
    bearer_token = register_data.get("session_token")
    user_id = register_data.get("user_id")
    
    if not bearer_token:
        print("❌ SETUP FAILED: No session_token in registration response")
        sys.exit(1)
    
    print(f"✅ SETUP: User registered successfully. user_id={user_id}")
    print(f"    Bearer token: {bearer_token[:16]}...")
    print()
    
    headers = {"Authorization": f"Bearer {bearer_token}"}
    
    # ========================================================================
    # SECTION A — Anthropic subscription persistence
    # ========================================================================
    print("=" * 80)
    print("SECTION A — Anthropic subscription persistence")
    print("=" * 80)
    print()
    
    # Step 1: POST /api/settings with Anthropic token
    print("Step 1: POST /api/settings with Anthropic subscription token")
    anthropic_token = "sk-ant-oat01-FAKETOKEN123XYZ"
    settings_resp = requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"anthropic": {"access_token": anthropic_token}}}
    )
    
    if settings_resp.status_code == 200:
        settings_data = settings_resp.json()
        # Check response structure
        has_ok = settings_data.get("ok") == True
        has_openrouter = "openrouter_configured" in settings_data
        has_providers = "providers_configured" in settings_data
        has_subs = "subscriptions_configured" in settings_data
        anthropic_configured = settings_data.get("subscriptions_configured", {}).get("anthropic") == True
        openai_not_configured = settings_data.get("subscriptions_configured", {}).get("openai") == False
        
        all_checks = has_ok and has_openrouter and has_providers and has_subs and anthropic_configured and openai_not_configured
        
        log_test(1, "POST /settings with Anthropic token", all_checks,
                f"ok={has_ok}, anthropic_configured={anthropic_configured}, openai_configured={not openai_not_configured}")
    else:
        log_test(1, "POST /settings with Anthropic token", False,
                f"Status {settings_resp.status_code}: {settings_resp.text}")
    
    # Step 2: GET /api/settings - verify token NOT exposed
    print("\nStep 2: GET /api/settings - verify Anthropic token NOT exposed")
    get_settings_resp = requests.get(f"{BASE_URL}/settings", headers=headers)
    
    if get_settings_resp.status_code == 200:
        settings_data = get_settings_resp.json()
        anthropic_configured = settings_data.get("subscriptions_configured", {}).get("anthropic") == True
        
        # CRITICAL: Check for token leaks
        forbidden = ["sk-ant-oat01", "FAKETOKEN", "FAKETOKEN123XYZ"]
        leaked = check_token_leak(settings_data, forbidden, 2)
        
        if leaked:
            log_test(2, "GET /settings token privacy", False,
                    f"❌ CRITICAL: Token leaked! Found: {leaked}")
        elif anthropic_configured:
            log_test(2, "GET /settings token privacy", True,
                    "anthropic_configured=true, token NOT exposed ✅")
        else:
            log_test(2, "GET /settings token privacy", False,
                    "anthropic_configured should be true")
    else:
        log_test(2, "GET /settings token privacy", False,
                f"Status {get_settings_resp.status_code}")
    
    # Step 3: GET /api/council - verify subscription_configured flags
    print("\nStep 3: GET /api/council - verify subscription flags")
    council_resp = requests.get(f"{BASE_URL}/council", headers=headers)
    
    if council_resp.status_code == 200:
        council_data = council_resp.json()
        providers = council_data.get("providers", [])
        
        # Find anthropic provider
        anthropic_provider = next((p for p in providers if p["id"] == "anthropic"), None)
        
        if anthropic_provider:
            has_sub_supported = anthropic_provider.get("subscription_supported") == True
            has_sub_configured = anthropic_provider.get("subscription_configured") == True
            
            # Check for token leaks
            forbidden = ["sk-ant-oat01", "FAKETOKEN"]
            leaked = check_token_leak(council_data, forbidden, 3)
            
            if leaked:
                log_test(3, "GET /council subscription flags", False,
                        f"❌ CRITICAL: Token leaked! Found: {leaked}")
            elif has_sub_supported and has_sub_configured:
                log_test(3, "GET /council subscription flags", True,
                        "anthropic: subscription_supported=true, subscription_configured=true, token NOT exposed ✅")
            else:
                log_test(3, "GET /council subscription flags", False,
                        f"subscription_supported={has_sub_supported}, subscription_configured={has_sub_configured}")
        else:
            log_test(3, "GET /council subscription flags", False,
                    "anthropic provider not found in response")
    else:
        log_test(3, "GET /council subscription flags", False,
                f"Status {council_resp.status_code}")
    
    # Step 4: Clear Anthropic subscription
    print("\nStep 4: POST /settings to clear Anthropic subscription")
    clear_resp = requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"anthropic": {}}}
    )
    
    if clear_resp.status_code == 200:
        clear_data = clear_resp.json()
        anthropic_cleared = clear_data.get("subscriptions_configured", {}).get("anthropic") == False
        
        log_test(4, "Clear Anthropic subscription", anthropic_cleared,
                f"anthropic_configured={not anthropic_cleared}")
    else:
        log_test(4, "Clear Anthropic subscription", False,
                f"Status {clear_resp.status_code}")
    
    # Step 5: Verify cleared
    print("\nStep 5: GET /settings - verify Anthropic subscription cleared")
    verify_clear_resp = requests.get(f"{BASE_URL}/settings", headers=headers)
    
    if verify_clear_resp.status_code == 200:
        verify_data = verify_clear_resp.json()
        anthropic_cleared = verify_data.get("subscriptions_configured", {}).get("anthropic") == False
        
        log_test(5, "Verify Anthropic cleared", anthropic_cleared,
                f"anthropic_configured={not anthropic_cleared}")
    else:
        log_test(5, "Verify Anthropic cleared", False,
                f"Status {verify_clear_resp.status_code}")
    
    # ========================================================================
    # SECTION B — OpenAI Codex subscription persistence
    # ========================================================================
    print()
    print("=" * 80)
    print("SECTION B — OpenAI Codex subscription persistence")
    print("=" * 80)
    print()
    
    # Step 6: POST /settings with OpenAI Codex tokens
    print("Step 6: POST /settings with OpenAI Codex subscription")
    openai_blob = {
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": "eyJraWQ...FAKE",
            "access_token": "ACCESSFAKE12345",
            "refresh_token": "REFRESHFAKE99999",
            "account_id": "acc_test_1"
        },
        "last_refresh": "2026-07-25T00:00:00Z"
    }
    
    openai_resp = requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"openai": openai_blob}}
    )
    
    if openai_resp.status_code == 200:
        openai_data = openai_resp.json()
        openai_configured = openai_data.get("subscriptions_configured", {}).get("openai") == True
        
        log_test(6, "POST /settings with OpenAI Codex", openai_configured,
                f"openai_configured={openai_configured}")
    else:
        log_test(6, "POST /settings with OpenAI Codex", False,
                f"Status {openai_resp.status_code}: {openai_resp.text}")
    
    # Step 7: GET /settings - verify OpenAI tokens NOT exposed
    print("\nStep 7: GET /settings - verify OpenAI tokens NOT exposed")
    get_openai_resp = requests.get(f"{BASE_URL}/settings", headers=headers)
    
    if get_openai_resp.status_code == 200:
        openai_settings = get_openai_resp.json()
        openai_configured = openai_settings.get("subscriptions_configured", {}).get("openai") == True
        
        # CRITICAL: Check for token leaks
        forbidden = ["ACCESSFAKE", "REFRESHFAKE", "acc_test_1", "id_token", "OPENAI_API_KEY", "eyJraWQ"]
        leaked = check_token_leak(openai_settings, forbidden, 7)
        
        if leaked:
            log_test(7, "GET /settings OpenAI token privacy", False,
                    f"❌ CRITICAL: Token leaked! Found: {leaked}")
        elif openai_configured:
            log_test(7, "GET /settings OpenAI token privacy", True,
                    "openai_configured=true, tokens NOT exposed ✅")
        else:
            log_test(7, "GET /settings OpenAI token privacy", False,
                    "openai_configured should be true")
    else:
        log_test(7, "GET /settings OpenAI token privacy", False,
                f"Status {get_openai_resp.status_code}")
    
    # Step 8: GET /api/council - verify OpenAI subscription_configured
    print("\nStep 8: GET /api/council - verify OpenAI subscription_configured")
    council_openai_resp = requests.get(f"{BASE_URL}/council", headers=headers)
    
    if council_openai_resp.status_code == 200:
        council_openai_data = council_openai_resp.json()
        providers = council_openai_data.get("providers", [])
        
        openai_provider = next((p for p in providers if p["id"] == "openai"), None)
        
        if openai_provider:
            has_sub_configured = openai_provider.get("subscription_configured") == True
            
            log_test(8, "GET /council OpenAI subscription_configured", has_sub_configured,
                    f"openai subscription_configured={has_sub_configured}")
        else:
            log_test(8, "GET /council OpenAI subscription_configured", False,
                    "openai provider not found")
    else:
        log_test(8, "GET /council OpenAI subscription_configured", False,
                f"Status {council_openai_resp.status_code}")
    
    # Step 9: Clear OpenAI subscription
    print("\nStep 9: POST /settings to clear OpenAI subscription")
    clear_openai_resp = requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"openai": {}}}
    )
    
    if clear_openai_resp.status_code == 200:
        clear_openai_data = clear_openai_resp.json()
        openai_cleared = clear_openai_data.get("subscriptions_configured", {}).get("openai") == False
        
        log_test(9, "Clear OpenAI subscription", openai_cleared,
                f"openai_configured={not openai_cleared}")
    else:
        log_test(9, "Clear OpenAI subscription", False,
                f"Status {clear_openai_resp.status_code}")
    
    # ========================================================================
    # SECTION C — Structured logging (observability)
    # ========================================================================
    print()
    print("=" * 80)
    print("SECTION C — Structured logging (observability)")
    print("=" * 80)
    print()
    
    # Re-set both subscriptions for logging test
    print("Setting up subscriptions for logging test...")
    requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"anthropic": {"access_token": anthropic_token}}}
    )
    time.sleep(0.5)
    
    requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"openai": openai_blob}}
    )
    time.sleep(0.5)
    
    # Clear both
    requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"anthropic": {}}}
    )
    time.sleep(0.5)
    
    requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"subscription_tokens": {"openai": {}}}
    )
    time.sleep(0.5)
    
    # Step 10: Check backend logs
    print("\nStep 10: Checking backend logs for structured logging")
    print("    Reading /var/log/supervisor/backend.err.log...")
    
    try:
        with open("/var/log/supervisor/backend.err.log", "r") as f:
            log_lines = f.readlines()[-200:]  # Last 200 lines
        
        log_content = "".join(log_lines)
        
        # Expected log patterns
        expected_logs = [
            "[settings] subscription set for anthropic",
            "[settings] subscription cleared for anthropic",
            "[settings] subscription set for openai",
            "[settings] subscription cleared for openai"
        ]
        
        found_logs = []
        missing_logs = []
        
        for expected in expected_logs:
            if expected in log_content:
                found_logs.append(expected)
            else:
                missing_logs.append(expected)
        
        # Check for token leaks in logs
        log_leaks = []
        forbidden_in_logs = ["FAKETOKEN123XYZ", "ACCESSFAKE12345", "REFRESHFAKE99999"]
        for token in forbidden_in_logs:
            if token in log_content:
                log_leaks.append(token)
        
        # Check that prefixes ARE present (but not full tokens)
        has_anthropic_prefix = "prefix=sk-ant-oat" in log_content
        has_openai_prefix = "prefix=ACCESSFAKE" in log_content
        has_refresh_flag = "has_refresh=True" in log_content
        
        if log_leaks:
            log_test(10, "Backend structured logging", False,
                    f"❌ CRITICAL: Full tokens leaked in logs! Found: {log_leaks}")
        elif missing_logs:
            log_test(10, "Backend structured logging", False,
                    f"Missing expected log lines: {missing_logs}")
        elif not (has_anthropic_prefix and has_openai_prefix and has_refresh_flag):
            log_test(10, "Backend structured logging", False,
                    f"Missing token prefixes in logs. anthropic_prefix={has_anthropic_prefix}, openai_prefix={has_openai_prefix}, has_refresh={has_refresh_flag}")
        else:
            log_test(10, "Backend structured logging", True,
                    f"All 4 expected log lines found. Token prefixes present, full tokens NOT leaked ✅")
            print(f"    Found logs: {found_logs}")
    
    except Exception as e:
        log_test(10, "Backend structured logging", False,
                f"Error reading logs: {str(e)}")
    
    # ========================================================================
    # SECTION D — Routing preference validation
    # ========================================================================
    print()
    print("=" * 80)
    print("SECTION D — Routing preference validation")
    print("=" * 80)
    print()
    
    # Step 11: POST /settings with subscription routing
    print("Step 11: POST /settings with subscription routing preferences")
    routing_resp = requests.post(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"routing": {"claude": "subscription", "gpt": "subscription", "gemini": "subscription"}}
    )
    
    if routing_resp.status_code == 200:
        log_test(11, "POST /settings with subscription routing", True,
                "Accepted subscription routing preferences")
    else:
        log_test(11, "POST /settings with subscription routing", False,
                f"Status {routing_resp.status_code}")
    
    # Step 12: GET /settings - verify routing persisted
    print("\nStep 12: GET /settings - verify routing persisted")
    routing_get_resp = requests.get(f"{BASE_URL}/settings", headers=headers)
    
    if routing_get_resp.status_code == 200:
        routing_data = routing_get_resp.json()
        routing = routing_data.get("routing", {})
        claude_routing = routing.get("claude") == "subscription"
        
        log_test(12, "GET /settings routing persistence", claude_routing,
                f"routing.claude={routing.get('claude')}")
    else:
        log_test(12, "GET /settings routing persistence", False,
                f"Status {routing_get_resp.status_code}")
    
    # ========================================================================
    # SECTION E — Regression checks
    # ========================================================================
    print()
    print("=" * 80)
    print("SECTION E — Regression checks")
    print("=" * 80)
    print()
    
    # Step 13: Auth gating - all endpoints should return 401 without auth
    print("Step 13: Auth gating regression - verify 401 without credentials")
    
    endpoints_to_check = [
        "/auth/me",
        "/council",
        "/sessions",
        "/settings"
    ]
    
    all_gated = True
    gating_details = []
    
    for endpoint in endpoints_to_check:
        resp = requests.get(f"{BASE_URL}{endpoint}")
        if resp.status_code == 401:
            gating_details.append(f"{endpoint}: 401 ✅")
        else:
            gating_details.append(f"{endpoint}: {resp.status_code} ❌")
            all_gated = False
    
    log_test(13, "Auth gating regression", all_gated,
            "\n    " + "\n    ".join(gating_details))
    
    # Step 14: User isolation - create second user and verify isolation
    print("\nStep 14: User isolation - verify per-user subscription isolation")
    
    # Register second user
    test_email2 = f"qasub-{timestamp}-2@example.com"
    register2_resp = requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": test_email2, "password": test_password, "name": "QA Sub Test 2"}
    )
    
    if register2_resp.status_code == 200:
        bearer_token2 = register2_resp.json().get("session_token")
        headers2 = {"Authorization": f"Bearer {bearer_token2}"}
        
        # User2 should see empty subscriptions (not user1's)
        user2_settings_resp = requests.get(f"{BASE_URL}/settings", headers=headers2)
        
        if user2_settings_resp.status_code == 200:
            user2_settings = user2_settings_resp.json()
            user2_subs = user2_settings.get("subscriptions_configured", {})
            
            # User2 should have no subscriptions configured
            no_anthropic = user2_subs.get("anthropic") == False
            no_openai = user2_subs.get("openai") == False
            
            if no_anthropic and no_openai:
                log_test(14, "User isolation", True,
                        "User2 sees empty subscriptions (not User1's) ✅")
            else:
                log_test(14, "User isolation", False,
                        f"User2 should have no subscriptions. Got: {user2_subs}")
        else:
            log_test(14, "User isolation", False,
                    f"User2 GET /settings failed: {user2_settings_resp.status_code}")
    else:
        log_test(14, "User isolation", False,
                f"Could not register user2: {register2_resp.status_code}")
    
    # Step 15: GET /auth/debug - verify only prefixes, no full tokens
    print("\nStep 15: GET /auth/debug - verify token prefix truncation")
    
    debug_resp = requests.get(f"{BASE_URL}/auth/debug", headers=headers)
    
    if debug_resp.status_code == 200:
        debug_data = debug_resp.json()
        
        # Check that bearer_prefix is truncated (should be first 8 chars + ...)
        bearer_prefix = debug_data.get("bearer_prefix", "")
        has_ellipsis = bearer_prefix.endswith("...")
        is_truncated = len(bearer_prefix) <= 12  # 8 chars + "..."
        
        # Check for full token leak
        full_token_leaked = bearer_token in json.dumps(debug_data)
        
        if full_token_leaked:
            log_test(15, "GET /auth/debug token truncation", False,
                    "❌ CRITICAL: Full bearer token leaked in /auth/debug")
        elif has_ellipsis and is_truncated:
            log_test(15, "GET /auth/debug token truncation", True,
                    f"bearer_prefix truncated correctly: {bearer_prefix} ✅")
        else:
            log_test(15, "GET /auth/debug token truncation", False,
                    f"bearer_prefix not properly truncated: {bearer_prefix}")
    else:
        log_test(15, "GET /auth/debug token truncation", False,
                f"Status {debug_resp.status_code}")
    
    # ========================================================================
    # CLEANUP
    # ========================================================================
    print()
    print("=" * 80)
    print("CLEANUP")
    print("=" * 80)
    print()
    
    print("Cleaning up test data from MongoDB...")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio
        import os
        from dotenv import load_dotenv
        
        load_dotenv("/app/backend/.env")
        mongo_url = os.environ['MONGO_URL']
        
        async def cleanup():
            client = AsyncIOMotorClient(mongo_url)
            db = client[os.environ['DB_NAME']]
            
            # Delete test users
            users_result = await db.users.delete_many({"email": {"$regex": "^qasub-"}})
            sessions_result = await db.user_sessions.delete_many({})
            settings_result = await db.settings.delete_many({"_id": {"$regex": "^user_"}})
            
            print(f"    Deleted {users_result.deleted_count} test users")
            print(f"    Deleted {sessions_result.deleted_count} sessions")
            print(f"    Deleted {settings_result.deleted_count} settings")
            
            client.close()
        
        asyncio.run(cleanup())
        print("✅ Cleanup completed")
    except Exception as e:
        print(f"⚠️  Cleanup error (non-critical): {str(e)}")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    
    total_tests = len(test_results)
    passed_tests = sum(1 for t in test_results if t["passed"])
    failed_count = total_tests - passed_tests
    
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_count}")
    print(f"Success rate: {(passed_tests/total_tests*100):.1f}%")
    print()
    
    if failed_tests:
        print("FAILED TESTS:")
        for failed in failed_tests:
            print(f"  ❌ {failed}")
        print()
        sys.exit(1)
    else:
        print("✅ ALL TESTS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
