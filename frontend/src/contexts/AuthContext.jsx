import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { exchangeSession, getMe, logout as apiLogout } from "../lib/api";

const AuthContext = createContext(null);

const AUTH_URL = "https://auth.emergentagent.com/";

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    // 1) Handle redirect from Emergent auth: session_id lives in the URL fragment
    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (match) {
      try {
        const u = await exchangeSession(decodeURIComponent(match[1]));
        setUser(u);
        // strip the fragment without reloading
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        setLoading(false);
        return;
      } catch (e) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
    // 2) Otherwise try to restore an existing session
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
