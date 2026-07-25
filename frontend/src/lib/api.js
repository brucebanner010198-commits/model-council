import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, withCredentials: true });

client.interceptors.response.use(
  (r) => r,
  (error) => {
    const url = error?.config?.url || "";
    const isAuthCheck = url.includes("/auth/me") || url.includes("/auth/session");
    if (error?.response?.status === 401 && !isAuthCheck && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);


export const exchangeSession = (session_id) => client.post("/auth/session", { session_id }).then((r) => r.data);
export const getMe = () => client.get("/auth/me").then((r) => r.data);
export const logout = () => client.post("/auth/logout").then((r) => r.data);

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
