import { useState } from "react";
import { api } from "../api.js";

const AUTONOMY_LABELS = {
  fully_autonomous: "Auto",
  advisory: "Advisory",
  manual: "Manual",
};

export default function AgentList({ agents, onRefresh, onIntervene }) {
  const [filter, setFilter] = useState("all");

  const filtered = agents.filter((a) => {
    if (filter === "all") return true;
    if (filter === "online") return a.status === "online";
    if (filter === "busy") return a.status === "busy";
    if (filter === "stalled") return a.status === "stalled";
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Agents</span>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ marginLeft: "auto", fontSize: 12 }}
        >
          <option value="all">All</option>
          <option value="online">Online</option>
          <option value="busy">Busy</option>
          <option value="stalled">Stalled</option>
        </select>
      </div>

      {filtered.length === 0 && (
        <div className="empty-state">
          <span>No agents</span>
        </div>
      )}

      {filtered.map((agent) => (
        <AgentCard
          key={agent.name}
          agent={agent}
          onRefresh={onRefresh}
          onIntervene={onIntervene}
        />
      ))}
    </div>
  );
}

function AgentCard({ agent, onRefresh, onIntervene }) {
  const [settingMode, setSettingMode] = useState(false);
  const [showActions, setShowActions] = useState(false);

  const handleSetMode = async (mode) => {
    setSettingMode(true);
    try {
      await api.setAutonomy(agent.name, mode);
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setSettingMode(false);
      setShowActions(false);
    }
  };

  const mode = agent.autonomy_mode || "fully_autonomous";
  const caps = agent.capabilities || [];

  return (
    <div className="agent-card">
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
        <span className={`agent-status-badge ${agent.status}`}>{agent.status}</span>
      </div>

      <div className="agent-meta">
        <span>{AUTONOMY_LABELS[mode] || mode}</span>
        {agent.current_task_id && (
          <span style={{ color: "var(--yellow)", fontSize: 11 }}>
            Task: {agent.current_task_id.slice(0, 8)}…
          </span>
        )}
        {agent.checkpoint_sequence > 0 && (
          <span style={{ fontSize: 11 }}>cp:{agent.checkpoint_sequence}</span>
        )}
      </div>

      {caps.length > 0 && (
        <div className="agent-capabilities">
          {caps.map((c) => (
            <span key={c} className="cap-tag">{c}</span>
          ))}
        </div>
      )}

      <div className="agent-actions">
        <button
          onClick={() => setShowActions((v) => !v)}
          title="Agent actions"
        >
          Actions ▾
        </button>
        <select
          value={mode}
          onChange={(e) => handleSetMode(e.target.value)}
          disabled={settingMode}
          style={{ fontSize: 11, padding: "3px 6px" }}
        >
          <option value="fully_autonomous">Auto</option>
          <option value="advisory">Advisory</option>
          <option value="manual">Manual</option>
        </select>
      </div>

      {showActions && (
        <div
          style={{
            marginTop: 6,
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
          }}
        >
          <button
            className="agent-actions"
            style={{ fontSize: 11, padding: "4px 8px", borderRadius: 4, background: "var(--surface2)", color: "var(--yellow)", border: "1px solid rgba(234,179,8,.3)" }}
            onClick={async () => {
              await api.pauseAgent(agent.name, "Human paused");
              onRefresh();
              setShowActions(false);
            }}
          >
            Pause
          </button>
          <button
            style={{ fontSize: 11, padding: "4px 8px", borderRadius: 4, background: "var(--surface2)", color: "var(--green)", border: "1px solid rgba(34,197,94,.3)" }}
            onClick={async () => {
              await api.resumeAgent(agent.name);
              onRefresh();
              setShowActions(false);
            }}
          >
            Resume
          </button>
          <button
            className="agent-actions danger"
            onClick={async () => {
              await api.revokeAgent(agent.name, "Human revoked");
              onRefresh();
              setShowActions(false);
            }}
          >
            Revoke
          </button>
        </div>
      )}
    </div>
  );
}
