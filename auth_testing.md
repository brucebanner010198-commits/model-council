# Auth Testing Playbook (Emergent Google Auth)

Multi-user app. Anyone can sign in with Google; each user gets private sessions + settings (keys are per-user).

## Create Test User & Session (mongosh)
```
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({ user_id: userId, email: 'test.user.'+Date.now()+'@example.com', name: 'Test User', picture: '', created_at: new Date() });
db.user_sessions.insertOne({ user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now()+7*24*60*60*1000), created_at: new Date() });
print('Session token: ' + sessionToken); print('User ID: ' + userId);
```

## Backend
- GET /api/auth/me with header `Authorization: Bearer <session_token>` (or cookie session_token) → returns user.
- Protected endpoints (all /api/sessions*, /api/settings, /api/council, /api/tts, /api/stt, /api/openrouter/models) return 401 without a valid session.
- POST /api/auth/session {session_id} exchanges an Emergent session_id → sets httpOnly cookie + returns user.
- POST /api/auth/logout clears the session.

## Browser
Set cookie session_token (domain = app host, path /, httpOnly, secure, sameSite None), then goto app; should land on dashboard, not /login.

## Data isolation
Sessions have an `owner` field = user_id. Settings doc `_id` = user_id. User A must never see User B's sessions/settings/keys.

## Cleanup
```
db.users.deleteMany({email: /test\.user\./});
db.user_sessions.deleteMany({session_token: /test_session/});
```
