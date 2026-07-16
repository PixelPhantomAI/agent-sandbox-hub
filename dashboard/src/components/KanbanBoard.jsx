import { useState, useCallback, useEffect } from "react";
import { api } from "../api.js";

const COLUMNS = [
  { key: "backlog", label: "Backlog" },
  { key: "ready", label: "Ready" },
  { key: "in_progress", label: "In Progress" },
  { key: "in_review", label: "In Review" },
  { key: "blocked", label: "Blocked" },
  { key: "done", label: "Done" },
];

export default function KanbanBoard({ projectId, agents, onRefresh, dragKey, setDragKey }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [wipLimits, setWipLimits] = useState({});

  const loadTasks = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const data = await api.getProjectTasks(projectId);
      setTasks(data);
      const proj = await api.getProject(projectId);
      setWipLimits(proj.wip_limits || {});
    } catch (e) {
      console.error("Failed to load tasks", e);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Reload when dragKey changes (signals a task was moved)
  useEffect(() => {
    if (dragKey >= 0) loadTasks();
  }, [dragKey, loadTasks]);

  if (!projectId) {
    return (
      <div className="empty-state">
        <span>Select a project to view the KanBan board</span>
      </div>
    );
  }

  const countInCol = (status) => tasks.filter((t) => t.status === status).length;

  const tasksByCol = {};
  for (const col of COLUMNS) {
    tasksByCol[col.key] = tasks.filter((t) => t.status === col.key);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div className="kanban-controls">
        <span style={{ fontWeight: 600, fontSize: 13 }}>KanBan Board</span>
        <button
          onClick={loadTasks}
          style={{ fontSize: 12, padding: "4px 10px", background: "var(--surface2)", color: "var(--text)", borderRadius: 4, border: "1px solid var(--border)" }}
        >
          Refresh
        </button>
        <button
          onClick={async () => {
            const title = prompt("Task title:");
            if (!title) return;
            await api.createTask(projectId, { title, created_by: "human" });
            loadTasks();
            onRefresh();
          }}
          style={{ fontSize: 12, padding: "4px 10px", background: "var(--accent)", color: "white", borderRadius: 4 }}
        >
          + New Task
        </button>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)" }}>
          {tasks.length} tasks
        </span>
      </div>

      <div className="kanban-board">
        {COLUMNS.map((col) => (
          <KanbanColumn
            key={col.key}
            col={col}
            tasks={tasksByCol[col.key]}
            wipLimit={wipLimits[col.key]}
            agents={agents}
            projectId={projectId}
            onTaskMoved={loadTasks}
            onTaskClick={(task) => {
              // Show task detail / transition dialog
              showTaskDialog(task, projectId, loadTasks, onRefresh);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function KanbanColumn({ col, tasks, wipLimit, projectId, onTaskMoved, onTaskClick }) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);
    const { taskId, fromStatus } = JSON.parse(e.dataTransfer.getData("text/plain"));
    if (fromStatus === col.key) return; // Same column

    try {
      await api.updateTask(projectId, taskId, { status: col.key });
      onTaskMoved();
    } catch (err) {
      alert(err.message);
    }
  };

  const atLimit = wipLimit && count >= wipLimit;
  const count = tasks.length;
  const overLimit = atLimit && count >= wipLimit;

  return (
    <div
      className={`kanban-col ${dragOver ? "drag-over" : ""}`}
      data-status={col.key}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="kanban-col-header">
        <span>{col.label}</span>
        {wipLimit && (
          <span
            style={{
              marginLeft: 4,
              fontSize: 10,
              color: overLimit ? "var(--red)" : "var(--text-dim)",
            }}
          >
            {count}/{wipLimit}
          </span>
        )}
        <span className="kanban-count">{count}</span>
      </div>

      <div className="kanban-col-body">
        {tasks.length === 0 && (
          <div className="kanban-empty">No tasks</div>
        )}
        {tasks.map((task) => (
          <KanbanCard
            key={task.id}
            task={task}
            onTaskClick={onTaskClick}
          />
        ))}
      </div>
    </div>
  );
}

function KanbanCard({ task, onTaskClick }) {
  const [dragging, setDragging] = useState(false);

  const onDragStart = (e) => {
    setDragging(true);
    e.dataTransfer.setData("text/plain", JSON.stringify({ taskId: task.id, fromStatus: task.status }));
    e.dataTransfer.effectAllowed = "move";
  };
  const onDragEnd = () => setDragging(false);

  return (
    <div
      className={`kanban-card ${dragging ? "dragging" : ""}`}
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={() => onTaskClick(task)}
    >
      <div className={`kanban-card-priority priority-${task.priority}`}>
        {task.priority} {task.required_capabilities?.length > 0 && "· cap"}
      </div>
      <div className="kanban-card-title">{task.title}</div>

      {task.assigned_to && (
        <div className="kanban-card-meta">
          <span className="kanban-card-agent">{task.assigned_to}</span>
        </div>
      )}

      {task.blocked_reason && (
        <div className="kanban-card-blocked">Blocked: {task.blocked_reason}</div>
      )}

      {task.required_capabilities?.length > 0 && (
        <div>
          {task.required_capabilities.map((c) => (
            <span key={c} className="kanban-card-cap">{c}</span>
          ))}
        </div>
      )}

      {task.transitions?.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 10, color: "var(--text-dim)" }}>
          {task.transitions[task.transitions.length - 1].to} · {new Date(task.transitions[task.transitions.length - 1].at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

function showTaskDialog(task, projectId, loadTasks, onRefresh) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:200;backdrop-filter:blur(4px)";

  const modal = document.createElement("div");
  modal.className = "modal";

  const statusOptions = ["backlog", "ready", "in_progress", "in_review", "blocked", "done"];
  const capsStr = (task.required_capabilities || []).join(", ");

  modal.innerHTML = `
    <h3 style="margin-bottom:4px">${task.title.slice(0, 60)}</h3>
    <p style="color:var(--text-dim);font-size:12px;margin-bottom:12px">
      ${task.description?.slice(0, 120) || "No description"}
      ${capsStr ? `<br>Capabilities required: ${capsStr}` : ""}
    </p>
    <div class="modal-row">
      <label>Transition to</label>
      <select id="task-status-select">
        ${statusOptions.map((s) => `<option value="${s}" ${task.status === s ? "selected" : ""}>${s}</option>`).join("")}
      </select>
    </div>
    <div class="modal-row">
      <label>Assign to</label>
      <input id="task-assign-input" placeholder="agent name (leave blank to unassign)" value="${task.assigned_to || ""}" />
    </div>
    <div class="modal-row">
      <label>Note</label>
      <input id="task-note-input" placeholder="optional note" />
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" id="task-cancel-btn">Cancel</button>
      <button class="btn-primary" id="task-save-btn">Save</button>
    </div>
  `;

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const close = () => {
    document.body.removeChild(overlay);
  };

  modal.querySelector("#task-cancel-btn").onclick = close;
  overlay.onclick = (e) => { if (e.target === overlay) close(); };

  modal.querySelector("#task-save-btn").onclick = async () => {
    const newStatus = modal.querySelector("#task-status-select").value;
    const newAssign = modal.querySelector("#task-assign-input").value.trim();
    const note = modal.querySelector("#task-note-input").value.trim();

    try {
      await api.updateTask(projectId, task.id, { status: newStatus, agent: newAssign || task.assigned_by, note });
      if (newAssign && newAssign !== task.assigned_to) {
        await api.assignTask(projectId, task.id, newAssign);
      }
      loadTasks();
      onRefresh();
    } catch (err) {
      alert(err.message);
    }
    close();
  };
}
