import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { exchangeSession, verifyMagicLink, getMe, logout as apiLogout } from "../lib/api";

const AuthContext = createContext(null);

const AUTH_URL = "https://auth.emergentagent.com/";

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    const hash = window.location.hash || "";
    // 1a) Emergent Google redirect: session_id in fragment
    const gMatch = hash.match(/session_id=([^&]+)/);
    if (gMatch) {
      try {
        const u = await exchangeSession(decodeURIComponent(gMatch[1]));
        setUser(u);
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        setLoading(false);
        return;
      } catch (e) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
    // 1b) Magic link redirect: magic token in fragment
    const mMatch = hash.match(/magic=([^&]+)/);
    if (mMatch) {
      try {
        const u = await verifyMagicLink(decodeURIComponent(mMatch[1]));
        setUser(u);
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        setLoading(false);
        return;
      } catch (e) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
    // 2) Restore existing session
    try {
      const u = await getMe();
      setUser(u);
    } catch (e) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  const login = () => {
    const redirect = window.location.origin + "/";
    window.location.href = `${AUTH_URL}?redirect=${encodeURIComponent(redirect)}`;
  };

  const logout = async () => {
    try { await apiLogout(); } catch (e) {}
    setUser(null);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
