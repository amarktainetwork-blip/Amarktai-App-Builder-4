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
  create: (name, prompt, opts = {}) =>
    api.post("/projects", { name, prompt, ...opts }).then((r) => r.data),
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
  iterate: (id, message, opts = {}) =>
    api.post(`/projects/${id}/iterate`, { message, ...opts }).then((r) => r.data),
  cancel: (id) => api.post(`/projects/${id}/cancel`).then((r) => r.data),
  retry: (id, agent, quality_tier) =>
    api.post(`/projects/${id}/retry`, { agent, quality_tier }).then((r) => r.data),
  finalize: (id, opts = {}) => api.post(`/projects/${id}/finalize`, opts).then((r) => r.data),
  finalizeAsBranch: (id) => api.post(`/projects/${id}/finalize/branch-pr`).then((r) => r.data),
  openPR: (id, body) => api.post(`/projects/${id}/pr`, body).then((r) => r.data),
  previewToken: (id) => api.post(`/projects/${id}/preview-token`).then((r) => r.data),
  previewUrl: (id, previewToken) => {
    const params = new URLSearchParams();
    if (previewToken) params.set("preview_token", previewToken);
    return `${API}/projects/${id}/preview${params.toString() ? `?${params.toString()}` : ""}`;
  },
  repoAnalysis: (id) => api.get(`/projects/${id}/repo-analysis`).then((r) => r.data),
  coverage: (id) => api.get(`/projects/${id}/coverage`).then((r) => r.data),
  previewFallback: (id) => api.get(`/projects/${id}/preview-fallback`).then((r) => r.data),
};

export const Clarify = {
  check: (prompt, mode) => api.post("/clarify", { prompt, mode }).then((r) => r.data),
  apply: (original_prompt, answers) =>
    api.post("/clarify/apply", { original_prompt, answers }).then((r) => r.data),
};

export const Media = {
  images: (query, opts = {}) =>
    api.get("/media/images", { params: { query, ...opts } }).then((r) => r.data),
  videos: (query, opts = {}) =>
    api.get("/media/videos", { params: { query, ...opts } }).then((r) => r.data),
  styles: () => api.get("/design/styles").then((r) => r.data),
  // Media Library
  upload: (file, opts = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.project_id) fd.append("project_id", opts.project_id);
    if (opts.tags) fd.append("tags", opts.tags);
    if (opts.media_type_override) fd.append("media_type_override", opts.media_type_override);
    return api.post("/media/upload", fd, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
  },
  library: (filters = {}) => api.get("/media/library", { params: filters }).then((r) => r.data),
  get: (assetId) => api.get(`/media/${assetId}`).then((r) => r.data),
  fileUrl: (assetId) => `${API}/media/${assetId}/file?token=${encodeURIComponent(getToken() || "")}`,
  thumbnailUrl: (assetId) => `${API}/media/${assetId}/thumbnail?token=${encodeURIComponent(getToken() || "")}`,
  delete: (assetId) => api.delete(`/media/${assetId}`).then((r) => r.data),
  savePixabay: (body) => api.post("/media/save-pixabay", body).then((r) => r.data),
  saveGenerated: (body) => api.post("/media/save-generated", body).then((r) => r.data),
  generateLogo: (body) => api.post("/logo", body).then((r) => r.data),
  agentContracts: () => api.get("/agents/contracts").then((r) => r.data),
};

export const Settings = {
  get: () => api.get("/settings").then((r) => r.data),
  update: (body) => api.post("/settings", body).then((r) => r.data),
  clear: (key) => api.delete(`/settings/${key}`).then((r) => r.data),
};

export const Models = {
  list: () => api.get("/models").then((r) => r.data),
  audioStatus: () => api.get("/models/audio").then((r) => r.data),
};

export const System = {
  health: () => api.get("/health").then((r) => r.data),
  readiness: () => api.get("/readiness").then((r) => r.data),
  githubStatus: () => api.get("/integrations/github/status").then((r) => r.data),
  capabilitiesStatus: () => api.get("/capabilities/status").then((r) => r.data),
};

export const Builds = {
  list: (workspaceType) =>
    api.get("/builds", { params: workspaceType ? { workspace_type: workspaceType } : {} }).then((r) => r.data),
  storageUsage: () => api.get("/builds/storage-usage").then((r) => r.data),
  archive: (workspacePath, confirmed = true) =>
    api.post("/builds/archive", { workspace_path: workspacePath, confirmed }).then((r) => r.data),
  delete: (workspacePath, confirmed = true) =>
    api.post("/builds/delete", { workspace_path: workspacePath, confirmed }).then((r) => r.data),
  updateMeta: (workspacePath, updates) =>
    api.post("/builds/update-meta", { workspace_path: workspacePath, updates }).then((r) => r.data),
};

export const Qwen = {
  status: () => api.get("/qwen/status").then((r) => r.data),
  applyRecommendedConfig: () => api.post("/qwen/apply-recommended-config").then((r) => r.data),
};

export const Admin = {
  users: () => api.get("/admin/users").then((r) => r.data),
  createUser: (body) => api.post("/admin/users", body).then((r) => r.data),
  resetPassword: (id, password) => api.post(`/admin/users/${id}/reset-password`, { password }).then((r) => r.data),
  setStatus: (id, status) => api.patch(`/admin/users/${id}/status`, { status }).then((r) => r.data),
};

export const Assistant = {
  message: (content, project_id = null) =>
    api.post("/assistant/message", { content, project_id }).then((r) => r.data),
};

export const Stack = {
  decide: (prompt, mode, tier) =>
    api.get("/stack/decide", { params: { prompt, mode, tier } }).then((r) => r.data),
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
