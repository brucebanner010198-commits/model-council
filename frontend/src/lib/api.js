import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });

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

export const transcribe = (blob) => {
  const fd = new FormData();
  fd.append("audio", blob, "recording.webm");
  return client.post("/stt", fd, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
};
