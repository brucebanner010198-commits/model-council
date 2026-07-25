import axios from "axios";

// Resolve the backend base URL. In this Kubernetes environment the ingress
// always routes `/api/*` on whatever preview URL the frontend is served from
// to the same backend pod, so a same-origin request always works. If the
// build-time REACT_APP_BACKEND_URL matches the current browser origin, use it
// as-is; otherwise fall back to same-origin so a rotated preview URL doesn't
// wedge every request behind a cross-origin CORS-with-credentials block.
const _ENV_URL = process.env.REACT_APP_BACKEND_URL || "";
const _resolveBase = () => {
  if (typeof window === "undefined") return _ENV_URL;
  const origin = window.location.origin;
  if (!_ENV_URL) return origin;
  try {
    const envHost = new URL(_ENV_URL).origin;
    return envHost === origin ? _ENV_URL : origin;
  } catch {
    return origin;
  }
};
const BACKEND_URL = _resolveBase();
export const API = `${BACKEND_URL}/api`;

// ---- Bearer-token fallback -------------------------------------------------
// The primary auth mechanism is the HttpOnly cookie set by the backend.
// However some browsers / embedded webviews strip SameSite=None cookies,
// so on every successful auth response we also stash the returned
// session_token in localStorage and attach it as `Authorization: Bearer …`
// on every request. The backend's get_current_user() accepts both.
const TOKEN_KEY = "council_session_token";

export const getStoredToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
};

export const setStoredToken = (t) => {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* localStorage may be unavailable in private mode */ }
};

const client = axios.create({ baseURL: API, withCredentials: true });

client.interceptors.request.use((config) => {
  const t = getStoredToken();
  if (t) {
    config.headers = config.headers || {};
    if (!config.headers.Authorization && !config.headers.authorization) {
      config.headers.Authorization = `Bearer ${t}`;
    }
  }
  return config;
});

client.interceptors.response.use(
  (r) => r,
  (error) => {
    const url = error?.config?.url || "";
    const isAuthCheck = url.includes("/auth/me") || url.includes("/auth/session")
      || url.includes("/auth/login") || url.includes("/auth/register");
    if (error?.response?.status === 401 && !isAuthCheck && window.location.pathname !== "/login") {
      setStoredToken("");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// Small helper: after any successful auth response, stash the token so a
// blocked cookie doesn't wedge the user out of the app.
const stashTokenFromResponse = (data) => {
  if (data && data.session_token) setStoredToken(data.session_token);
  return data;
};

// ---- Auth ----
export const exchangeSession = (session_id) =>
  client.post("/auth/session", { session_id }).then((r) => stashTokenFromResponse(r.data));
export const registerAccount = (body) =>
  client.post("/auth/register", body).then((r) => stashTokenFromResponse(r.data));
export const loginPassword = (body) =>
  client.post("/auth/login", body).then((r) => stashTokenFromResponse(r.data));
// legacy magic-link (kept for compatibility with existing routes / emails)
export const requestMagicLink = (email) => client.post("/auth/magic/request", { email }).then((r) => r.data);
export const verifyMagicLink = (token) =>
  client.post("/auth/magic/verify", { token }).then((r) => stashTokenFromResponse(r.data));
export const getMe = () => client.get("/auth/me").then((r) => r.data);
export const authDebug = () => client.get("/auth/debug").then((r) => r.data);
export const logout = () =>
  client.post("/auth/logout").then((r) => { setStoredToken(""); return r.data; })
    .catch((e) => { setStoredToken(""); throw e; });

// ---- App ----
export const getCouncil = () => client.get("/council").then((r) => r.data);
export const getSettings = () => client.get("/settings").then((r) => r.data);
export const saveSettings = (body) => client.post("/settings", body).then((r) => r.data);
export const listOpenRouterModels = () => client.get("/openrouter/models").then((r) => r.data);

export const listSessions = () => client.get("/sessions").then((r) => r.data);
export const createSession = (body) => client.post("/sessions", body).then((r) => r.data);
export const getSession = (id) => client.get(`/sessions/${id}`).then((r) => r.data);
export const deleteSession = (id) => client.delete(`/sessions/${id}`).then((r) => r.data);

export const sendMessage = (id, text) => client.post(`/sessions/${id}/message`, { text }).then((r) => r.data);
export const respond = (id, model_id, directive) =>
  client.post(`/sessions/${id}/respond`, { model_id, directive }).then((r) => r.data);
export const refreshNotes = (id) => client.post(`/sessions/${id}/notes`).then((r) => r.data);
export const concludeSession = (id, drafter_id) =>
  client.post(`/sessions/${id}/conclude`, { drafter_id }).then((r) => r.data);
export const reviewSession = (id) => client.post(`/sessions/${id}/review`).then((r) => r.data);
export const synthesize = (id, chairman_id, question) =>
  client.post(`/sessions/${id}/synthesize`, { chairman_id, question }).then((r) => r.data);
export const ttsSpeak = (text, member_id) =>
  client.post(`/tts`, { text, member_id }).then((r) => r.data);
export const exportUrl = (id) => `${API}/sessions/${id}/export`;

export const transcribe = (blob) => {
  const fd = new FormData();
  fd.append("audio", blob, "recording.webm");
  return client.post("/stt", fd, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
};
