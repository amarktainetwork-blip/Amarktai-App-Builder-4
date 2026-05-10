import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "amarktai.token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

export const api = axios.create({ baseURL: API, headers: { "Content-Type": "application/json" } });

api.interceptors.request.use((config) => {
  const t = getToken();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      setToken(null);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  },
);

export const Auth = {
  login: (email, password) =>
    api.post("/auth/login", { email, password }).then((r) => {
      setToken(r.data.token);
      return r.data;
    }),
  me: () => api.get("/auth/me").then((r) => r.data),
  logout: () => { setToken(null); },
};

export const Projects = {
  list: () => api.get("/projects").then((r) => r.data),
  create: (name, prompt) => api.post("/projects", { name, prompt }).then((r) => r.data),
  fromRepo: (repo_url, branch, github_pat) =>
    api.post("/projects/from-repo", { repo_url, branch, github_pat }).then((r) => r.data),
  get: (id) => api.get(`/projects/${id}`).then((r) => r.data),
  remove: (id) => api.delete(`/projects/${id}`).then((r) => r.data),
  messages: (id) => api.get(`/projects/${id}/messages`).then((r) => r.data),
  events: (id) => api.get(`/projects/${id}/events`).then((r) => r.data),
  files: (id) => api.get(`/projects/${id}/files`).then((r) => r.data),
  fileContent: (id, path) =>
    api.get(`/projects/${id}/files/content`, { params: { path } }).then((r) => r.data),
  send: (id, content) => api.post(`/projects/${id}/messages`, { content }).then((r) => r.data),
  finalize: (id) => api.post(`/projects/${id}/finalize`).then((r) => r.data),
  openPR: (id, body) => api.post(`/projects/${id}/pr`, body).then((r) => r.data),
  previewUrl: (id) => `${API}/projects/${id}/preview`,
};

export const Settings = {
  get: () => api.get("/settings").then((r) => r.data),
  update: (body) => api.post("/settings", body).then((r) => r.data),
};

export const Models = {
  list: () => api.get("/models").then((r) => r.data),
};

export const Contact = {
  send: (body) => api.post("/contact", body).then((r) => r.data),
};

/** Open a WebSocket subscribed to a project's live event stream. */
export function openProjectSocket(projectId, onMessage) {
  const wsBase = (BACKEND_URL || "").replace(/^http/, "ws");
  const t = getToken();
  const ws = new WebSocket(`${wsBase}/api/ws/${projectId}?token=${encodeURIComponent(t || "")}`);
  ws.onmessage = (evt) => {
    try { onMessage(JSON.parse(evt.data)); } catch { /* ignore */ }
  };
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 25000);
  ws.addEventListener("close", () => clearInterval(ping));
  return ws;
}
