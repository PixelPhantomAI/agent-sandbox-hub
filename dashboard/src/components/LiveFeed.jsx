import { useRef, useEffect } from "react";

const EVENT_LABELS = {
  message_sent: "message",
  task_transition: "transition",
  task_created: "task+",
  task_claimed: "claimed",
  task_assigned: "assigned",
  task_unassigned: "unassigned",
  agent_registered: "joined",
  agent_unregistered: "left",
  agent_paused: "paused",
  agent_resumed: "resumed",
  agent_revoked: "revoked",
  agent_recovered: "recovered",
  checkpoint_submitted: "checkpoint",
  agent_capabilities_changed: "caps",
  agent_autonomy_changed: "autonomy",
  global_autonomy_changed: "g.autonomy",
  project_created: "project+",
  project_deleted: "project-",
  agent_joined_project: "joined project",
  file_uploaded: "uploaded",
};

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}:${d.getSeconds().toString().padStart(2, "0")}`;
}

function EventLabel({ type, data }) {
  const label = EVENT_LABELS[type] || type;

  switch (type) {
    case "message_sent":
      return (
        <span>
          <strong>{data.from}</strong> → <strong>{data.to}</strong>: {data.content?.slice(0, 80)}
        </span>
      );
    case "task_transition":
      return (
        <span>
          <strong>{data.title?.slice(0, 40)}</strong> → <strong>{data.new_status}</strong>
          {data.by && <span style={{ color: "var(--text-dim)" }}> by {data.by}</span>}
        </span>
      );
    case "task_created":
      return (
        <span>
          New task: <strong>{data.task?.title?.slice(0, 50)}</strong>
        </span>
      );
    case "task_claimed":
      return (
        <span>
          <strong>{data.agent}</strong> claimed <strong>{data.title?.slice(0, 40)}</strong>
        </span>
      );
    case "task_assigned":
      return (
        <span>
          <strong>{data.by === "human" ? "Human" : data.by}</strong> assigned <strong>{data.title?.slice(0, 40)}</strong> to <strong>{data.agent}</strong>
        </span>
      );
    case "agent_registered":
      return (
        <span>
          <strong>{data.name}</strong> ({data.type}) joined — {data.autonomy_mode}
        </span>
      );
    case "agent_unregistered":
      return <span><strong>{data.name}</strong> left</span>;
    case "agent_paused":
      return <span><strong>{data.name}</strong> paused{data.reason && `: ${data.reason}`}</span>;
    case "agent_resumed":
      return <span><strong>{data.name}</strong> resumed</span>;
    case "agent_revoked":
      return <span><strong>{data.agent}</strong> revoked{data.reason && `: ${data.reason}`}</span>;
    case "agent_recovered":
      return <span><strong>{data.name}</strong> recovered from revocation</span>;
    case "checkpoint_submitted":
      return (
        <span>
          <strong>{data.agent}</strong> checkpoint {data.sequence}{data.task_id && ` on ${data.task_id.slice(0, 8)}…`}
        </span>
      );
    case "project_created":
      return <span>Project <strong>{data.name}</strong> created</span>;
    default:
      return <span>{JSON.stringify(data).slice(0, 80)}</span>;
  }
}

export default function LiveFeed({ events }) {
  const listRef = useRef(null);

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [events]);

  return (
    <ul className="feed-list" ref={listRef}>
      {events.length === 0 && (
        <li className="feed-item" style={{ justifyContent: "center", color: "var(--text-dim)", fontSize: 12 }}>
          Waiting for events…
        </li>
      )}
      {events.map((ev) => (
        <li key={ev.id} className="feed-item">
          <span className="feed-time">{formatTime(ev.timestamp)}</span>
          <span className={`feed-content feed-event-${ev.type}`}>
            <EventLabel type={ev.type} data={ev.data} />
          </span>
        </li>
      ))}
    </ul>
  );
}
