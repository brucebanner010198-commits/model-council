import { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from "react";
import { exchangeSession, verifyMagicLink, getMe, logout as apiLogout, setStoredToken } from "../lib/api";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
const AUTH_URL = "https://auth.emergentagent.com/";

const AuthContext = createContext(null);

// Small helper. Prefix log lines so they're easy to spot in devtools.
const log = (...args) => console.info("[auth]", ...args);

// Emergent normally puts the session_id in the URL *fragment* (#session_id=…)
// but some redirect chains have been seen putting it in the *query string*
// (?session_id=…). We support both, defensively.
const readSessionIdFromUrl = () => {
  const hash = window.location.hash || "";
  const search = window.location.search || "";
  const hashMatch = hash.match(/session_id=([^&]+)/);
  if (hashMatch) return { sid: decodeURIComponent(hashMatch[1]), where: "fragment" };
  const params = new URLSearchParams(search);
  const q = params.get("session_id");
  if (q) return { sid: q, where: "query" };
  return null;
};

const readMagicTokenFromUrl = () => {
  const hash = window.location.hash || "";
  const m = hash.match(/magic=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  // Guard against React 18 StrictMode double-invocation. The Emergent OAuth
  // session_id and magic-link tokens are single-use. Running bootstrap twice
  // makes the second call 401 and can race with the first, nulling the user.
  const bootstrapped = useRef(false);

  const bootstrap = useCallback(async () => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    log("bootstrap start; href=", window.location.href);

    // 1a) Emergent Google redirect: session_id in fragment or query
    const found = readSessionIdFromUrl();
    if (found) {
      const { sid, where } = found;
      log(`session_id found in ${where} (len=${sid.length}, prefix=${sid.slice(0, 8)}...)`);
      // Clear the URL FIRST so a soft-remount can't see the token again.
      window.history.replaceState(null, "", window.location.pathname);
      try {
        const u = await exchangeSession(sid);
        log("session exchange OK, user=", u.email);
        setUser(u);
      } catch (e) {
        const detail = e?.response?.data?.detail || e?.message || String(e);
        console.warn("[auth] Google session exchange failed:", detail, e);
        setAuthError(`Google sign-in failed: ${detail}`);
        setUser(null);
      } finally {
        setLoading(false);
      }
      return;
    }

    // 1b) Magic link redirect
    const magicToken = readMagicTokenFromUrl();
    if (magicToken) {
      log(`magic token found (len=${magicToken.length})`);
      window.history.replaceState(null, "", window.location.pathname);
      try {
        const u = await verifyMagicLink(magicToken);
        log("magic verify OK, user=", u.email);
        setUser(u);
      } catch (e) {
        const detail = e?.response?.data?.detail || e?.message || String(e);
        console.warn("[auth] magic verify failed:", detail, e);
        setAuthError(`Sign-in link failed: ${detail}`);
        setUser(null);
      } finally {
        setLoading(false);
      }
      return;
    }

    // 2) Restore existing session (cookie or Bearer)
    try {
      const u = await getMe();
      log("existing session restored, user=", u.email);
      setUser(u);
    } catch (e) {
      const status = e?.response?.status;
      if (status && status !== 401) {
        console.warn("[auth] /auth/me failed with unexpected status", status, e);
      } else {
        log("no existing session (401)");
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  const login = useCallback(() => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    log("Google sign-in redirect →", redirectUrl);
    window.location.href = `${AUTH_URL}?redirect=${encodeURIComponent(redirectUrl)}`;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch (e) {
      console.warn("[auth] server logout failed (clearing local state anyway):", e);
    }
    setStoredToken("");
    setUser(null);
    window.location.href = "/login";
  }, []);

  // Called by the Login page after a successful password login / register.
  const signInWithUser = useCallback((u) => {
    setUser(u);
    setAuthError(null);
    setLoading(false);
  }, []);

  const value = useMemo(
    () => ({ user, loading, authError, login, logout, signInWithUser, setAuthError }),
    [user, loading, authError, login, logout, signInWithUser]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
