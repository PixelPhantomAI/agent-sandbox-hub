import { useState, useCallback, useEffect } from "react";
import { api } from "./api.js";
import { useSSE } from "./hooks/useSSE.js";
import AgentList from "./components/AgentList.jsx";
import KanbanBoard from "./components/KanbanBoard.jsx";
import MessageGraph from "./components/MessageGraph.jsx";
import LiveFeed from "./components/LiveFeed.jsx";

export default function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [agents, setAgents] = useState([]);
  const [events, setEvents] = useState([]);
  const [dragKey, setDragKey] = useState(0);
  const [tab, setTab] = useState("board");

  // SSE connection
  const { connected } = useSSE(
    useCallback((ev) => {
      setEvents((prev) => [ev, ...prev].slice(0, 200));
    }, [])
  );

  const refresh = useCallback(async () => {
    try {
      const [agts, projs] = await Promise.all([api.getAgents(), api.getProjects()]);
      setAgents(agts);
      setProjects(projs);
    } catch (e) {
      console.error("Refresh failed", e);
    }
  }, []);

  useEffect(() => {
    refresh();
    // Poll agents every 10s as fallback
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  // Trigger board refresh after events that affect it
  useEffect(() => {
    if (events.length === 0) return;
    const last = events[0];
    const boardEvents = [
      "task_transition", "task_created", "task_claimed", "task_assigned",
      "task_unassigned", "project_created", "project_deleted",
    ];
    if (boardEvents.includes(last.type)) {
      setDragKey((k) => k + 1);
    }
  }, [events]);

  const handleCreateProject = async () => {
    const name = prompt("Project name:");
    if (!name) return;
    try {
      await api.createProject({ name, creator: "human" });
      refresh();
    } catch (e) {
      alert(e.message);
    }
  };

  const selectedProject = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="app">
      {/* Top bar */}
      <header className="topbar">
        <div className="topbar-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4" />
            <circle cx="7" cy="10" r="2" /><circle cx="12" cy="10" r="2" /><circle cx="17" cy="10" r="2" />
            <path d="M7 10V8M12 10V8M17 10V8" strokeWidth={1.5} />
          </svg>
          Agent Sandbox Hub
        </div>

        <div className="status-dot" style={{ marginLeft: 8 }} />

        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {connected ? (
            <span style={{ color: "var(--green)" }}>Connected</span>
          ) : (
            <span style={{ color: "var(--text-dim)" }}>Reconnecting…</span>
          )}
        </span>

        <div className="topbar-spacer" />

        {/* Project selector */}
        <select
          value={selectedProjectId || ""}
          onChange={(e) => setSelectedProjectId(e.target.value || null)}
          style={{ fontSize: 13 }}
        >
          <option value="">— Select Project —</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <button
          onClick={handleCreateProject}
          style={{ fontSize: 12, padding: "5px 12px", background: "var(--accent)", color: "white", borderRadius: 6 }}
        >
          + Project
        </button>
      </header>

      <div className="main">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-label">Views</div>
            <div
              className={`sidebar-item ${tab === "board" ? "active" : ""}`}
              onClick={() => setTab("board")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="5" height="18" rx="1" /><rect x="10" y="3" width="5" height="12" rx="1" /><rect x="17" y="3" width="4" height="8" rx="1" />
              </svg>
              KanBan Board
            </div>
            <div
              className={`sidebar-item ${tab === "comms" ? "active" : ""}`}
              onClick={() => setTab("comms")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="5" cy="12" r="3" /><circle cx="19" cy="5" r="3" /><circle cx="19" cy="19" r="3" />
                <line x1="8" y1="11" x2="16" y2="7" /><line x1="8" y1="13" x2="16" y2="17" />
              </svg>
              Communications
            </div>
            <div
              className={`sidebar-item ${tab === "agents" ? "active" : ""}`}
              onClick={() => setTab("agents")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
              </svg>
              Agent Control
            </div>
          </div>

          {tab !== "agents" && (
            <div className="sidebar-section">
              <div className="sidebar-label">Projects</div>
              {projects.map((p) => (
                <div
                  key={p.id}
                  className={`sidebar-item ${selectedProjectId === p.id ? "active" : ""}`}
                  onClick={() => { setSelectedProjectId(p.id); setTab("board"); }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 7h18M3 12h18M3 17h10" />
                  </svg>
                  {p.name}
                </div>
              ))}
              {projects.length === 0 && (
                <div style={{ fontSize: 12, color: "var(--text-dim)", padding: "4px 10px" }}>No projects</div>
              )}
            </div>
          )}

          {tab === "agents" && (
            <div className="sidebar-section">
              <div className="sidebar-label">System</div>
              <div
                className="sidebar-item"
                onClick={refresh}
                title="Refresh all data"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M23 4v6h-6M1 20v-6h6" />
                  <path d="M3.5 9a9 9 0 0114.8-4.4L23 10M1 14l4.6 4.4A9 9 0 0020.5 15" />
                </svg>
                Refresh All
              </div>
            </div>
          )}
        </aside>

        {/* Content */}
        <main className="content">
          {/* Agent cards always visible at top */}
          {agents.length > 0 && (
            <div className="agent-cards">
              {agents.slice(0, 6).map((agent) => {
                const caps = agent.capabilities || [];
                return (
                  <div key={agent.name} className="agent-card" style={{ minWidth: 180 }}>
                    <div className="agent-card-header">
                      <div
                        className="status-dot"
                        style={{
                          background: agent.status === "online" ? "var(--green)" : agent.status === "busy" ? "var(--yellow)" : agent.status === "stalled" ? "var(--red)" : "var(--text-dim)",
                          boxShadow: agent.status === "online" ? "0 0 6px var(--green)" : undefined,
                        }}
                      />
                      <span className="agent-name">{agent.name}</span>
                      <span className="agent-type">{agent.type}</span>
                    </div>
                    <div className="agent-meta">
                      <span className={`agent-status-badge ${agent.status}`}>{agent.status}</span>
                      <span style={{ fontSize: 11 }}>{agent.autonomy_mode}</span>
                    </div>
                    {caps.length > 0 && (
                      <div className="agent-capabilities">
                        {caps.map((c) => <span key={c} className="cap-tag">{c}</span>)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Tab content */}
          {tab === "board" && (
            <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
              <KanbanBoard
                projectId={selectedProjectId}
                agents={agents}
                onRefresh={refresh}
                dragKey={dragKey}
                setDragKey={setDragKey}
              />
            </div>
          )}

          {tab === "comms" && (
            <div className="panels">
              <div className="panel">
                <div className="panel-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
                    <circle cx="5" cy="12" r="3" /><circle cx="19" cy="5" r="3" /><circle cx="19" cy="19" r="3" />
                    <line x1="8" y1="11" x2="16" y2="7" /><line x1="8" y1="13" x2="16" y2="17" />
                  </svg>
                  Message Flow
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  <MessageGraph refreshKey={events.length} />
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                  </svg>
                  Live Event Feed
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)" }}>
                    {events.length} events
                  </span>
                </div>
                <div className="panel-body" style={{ padding: 0 }}>
                  <LiveFeed events={events} />
                </div>
              </div>
            </div>
          )}

          {tab === "agents" && (
            <div className="panels" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="panel">
                <div className="panel-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
                    <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                  </svg>
                  Agent Registry
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)" }}>
                    {agents.length} registered
                  </span>
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  <AgentList
                    agents={agents}
                    onRefresh={refresh}
                  />
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                  </svg>
                  Live Feed
                </div>
                <div className="panel-body" style={{ padding: 0 }}>
                  <LiveFeed events={events} />
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
