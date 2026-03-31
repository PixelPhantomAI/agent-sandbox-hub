const HUB_URL = import.meta.env.VITE_HUB_URL || "http://localhost:8080";

async function request(path, opts = {}) {
  const res = await fetch(`${HUB_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Agents
  getAgents: () => request("/agents"),
  registerAgent: (body) => request("/agents/register", { method: "POST", body: JSON.stringify(body) }),
  deleteAgent: (name) => request(`/agents/${encodeURIComponent(name)}`, { method: "DELETE" }),
  pauseAgent: (name, reason) => request(`/agents/${encodeURIComponent(name)}/pause`, { method: "POST", body: JSON.stringify({ reason }) }),
  resumeAgent: (name) => request(`/agents/${encodeURIComponent(name)}/resume`, { method: "POST" }),
  revokeAgent: (name, reason) => request(`/agents/${encodeURIComponent(name)}/revoke`, { method: "POST", body: JSON.stringify({ reason }) }),
  setAutonomy: (name, mode) => request(`/agents/${encodeURIComponent(name)}/autonomy`, { method: "POST", body: JSON.stringify({ mode }) }),
  setCapabilities: (name, tags) => request(`/agents/${encodeURIComponent(name)}/capabilities`, { method: "POST", body: JSON.stringify({ tags }) }),

  // Projects
  getProjects: () => request("/projects"),
  createProject: (body) => request("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id) => request(`/projects/${id}`),
  getProjectMetrics: (id) => request(`/projects/${id}/metrics`),
  getProjectTasks: (id, params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/projects/${id}/tasks${q ? "?" + q : ""}`);
  },
  getReadyQueue: (projectId, agent) => {
    const q = new URLSearchParams({ agent }.filter(([,v]) => v)).toString();
    return request(`/projects/${projectId}/tasks/ready${q ? "?" + q : ""}`);
  },
  createTask: (projectId, body) => request(`/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(body) }),
  updateTask: (projectId, taskId, body) =>
    request(`/projects/${projectId}/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(body) }),
  claimTask: (projectId, taskId, agent) =>
    request(`/projects/${projectId}/tasks/${taskId}/claim`, { method: "POST", body: JSON.stringify({ agent }) }),
  assignTask: (projectId, taskId, agent) =>
    request(`/projects/${projectId}/tasks/${taskId}/assign`, { method: "POST", body: JSON.stringify({ agent }) }),
  updateWip: (projectId, status, limit) =>
    request(`/projects/${projectId}/wip`, { method: "PATCH", body: JSON.stringify({ status, limit }) }),

  // Capabilities
  getCapabilities: () => request("/capabilities"),
  matchCapabilities: (tag) => request(`/capabilities/match?tag=${encodeURIComponent(tag)}`),

  // Audit
  getAuditLog: (limit = 100) => request(`/audit/log?limit=${limit}`),

  // Message graph
  getMessageGraph: () => request("/messages/graph"),
};
