import { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from "react";
import { exchangeSession, verifyMagicLink, getMe, logout as apiLogout } from "../lib/api";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
const AUTH_URL = "https://auth.emergentagent.com/";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Guard against React 18 StrictMode double-invocation. The Emergent OAuth
  // session_id and magic-link tokens are single-use — running bootstrap twice
  // makes the second call 401 and can race with the first, nulling the user.
  const bootstrapped = useRef(false);

  const bootstrap = useCallback(async () => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    const hash = window.location.hash || "";

    // 1a) Emergent Google redirect: session_id in fragment
    const gMatch = hash.match(/session_id=([^&]+)/);
    if (gMatch) {
      const sid = decodeURIComponent(gMatch[1]);
      // Clear the hash FIRST so a soft-remount can't see the token again
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      try {
        const u = await exchangeSession(sid);
        setUser(u);
      } catch (e) {
        console.warn("Google session exchange failed:", e);
        setUser(null);
      } finally {
        setLoading(false);
      }
      return;
    }

    // 1b) Magic link redirect: magic token in fragment
    const mMatch = hash.match(/magic=([^&]+)/);
    if (mMatch) {
      const tok = decodeURIComponent(mMatch[1]);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      try {
        const u = await verifyMagicLink(tok);
        setUser(u);
      } catch (e) {
        console.warn("Magic-link verification failed:", e);
        setUser(null);
      } finally {
        setLoading(false);
      }
      return;
    }

    // 2) Restore existing session
    try {
      const u = await getMe();
      setUser(u);
    } catch (e) {
      // 401 here is expected when signed-out; only log unexpected shapes
      if (e?.response?.status && e.response.status !== 401) {
        console.warn("Auth bootstrap failed:", e);
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
    window.location.href = `${AUTH_URL}?redirect=${encodeURIComponent(redirectUrl)}`;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch (e) {
      console.warn("Server logout failed (clearing local state anyway):", e);
    }
    setUser(null);
    window.location.href = "/login";
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
