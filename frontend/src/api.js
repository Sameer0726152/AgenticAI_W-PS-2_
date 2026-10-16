const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (HTTP ${res.status})`);
  return body;
}

export const api = {
  health: () => request("/api/health"),
  listJobs: () => request("/api/jobs"),
  getJob: (id) => request(`/api/jobs/${id}`),
  createJob: (url, text) =>
    request("/api/jobs", { method: "POST", body: JSON.stringify({ url, text: text || null }) }),
  deleteJob: (id) => request(`/api/jobs/${id}`, { method: "DELETE" }),
  listRepos: () => request("/api/repos"),
  connectRepo: (fullName, branch) =>
    request("/api/repos", { method: "POST", body: JSON.stringify({ full_name: fullName, branch: branch || null }) }),
  deleteRepo: (id) => request(`/api/repos/${id}`, { method: "DELETE" }),
};
