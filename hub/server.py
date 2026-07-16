"""
Hub Server Flask API
Central REST API for agent registration, messaging, project/KanBan management,
autonomy control, and real-time SSE event streaming.
"""

from flask import Flask, request, jsonify, Response, stream_with_context
import queue
import time

from hub.agents import AgentRegistry
from hub.autonomy import AutonomyMode, CheckpointSystem, RevocationQueue
from hub.capabilities import CapabilityRegistry
from hub.events import get_emitter
from hub.messages import MessageStore
from hub.projects import ProjectManager, TaskStatus
from hub.sandbox import SandboxEnforcer

app = Flask(__name__)

agent_registry = AgentRegistry()
message_store = MessageStore()
project_manager = ProjectManager()
sandbox = SandboxEnforcer()
capability_registry = CapabilityRegistry()
checkpoint_system = CheckpointSystem()
revocation_queue = RevocationQueue()
events = get_emitter()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _publish(event_type: str, data: dict):
    """Publish an event to all SSE subscribers."""
    events.emit(event_type, data)


# ── Health ───────────────────────────────────────────────────────────────────

@app.route("/ping", methods=["POST", "GET"])
def ping():
    return jsonify({"status": "ok"})


# ── Agent Registry ───────────────────────────────────────────────────────────

@app.route("/agents/register", methods=["POST"])
def register_agent():
    data = request.json
    name = data.get("name")
    agent_type = data.get("type", "unknown")
    metadata = data.get("metadata", {})
    autonomy_mode = data.get("autonomy_mode", "fully_autonomous")
    capability_tags = data.get("capabilities", [])

    if not name:
        return jsonify({"error": "name required"}), 400

    try:
        mode = AutonomyMode(autonomy_mode)
    except ValueError:
        mode = AutonomyMode.FULLY_AUTONOMOUS

    sandbox.audit(name, "register", {"type": agent_type, "autonomy": mode.value})
    agent = agent_registry.register(name, agent_type, metadata)
    agent_registry.set_autonomy_mode(name, mode)
    agent_registry.set_capabilities(name, capability_tags)

    # Register capability profile
    capability_registry.register(name, capability_tags)

    # Clear any stale checkpoint state
    checkpoint_system.clear(name)

    _publish("agent_registered", {
        "name": name,
        "type": agent_type,
        "autonomy_mode": mode.value,
        "capabilities": capability_tags,
    })

    return jsonify({
        "id": agent.name,
        "type": agent.agent_type,
        "registered_at": agent.registered_at.isoformat(),
        "autonomy_mode": mode.value,
        "capabilities": capability_tags,
    }), 201


@app.route("/agents/<name>/heartbeat", methods=["POST"])
def agent_heartbeat(name: str):
    sandbox.check_rate_limit(name)

    # Tick checkpoint system
    count = checkpoint_system.tick(name)
    if checkpoint_system.should_request_checkpoint(name):
        # Agent should be submitting a checkpoint
        pass  # Agent calls /checkpoint explicitly

    success = agent_registry.heartbeat(name)
    if success:
        sandbox.audit(name, "heartbeat", {"checkpoint_tick": count})
        return jsonify({"status": "ok", "checkpoint_tick": count})
    return jsonify({"error": "agent not found"}), 404


@app.route("/agents/<name>", methods=["DELETE"])
def delete_agent(name: str):
    sandbox.audit(name, "unregister", {})
    capability_registry.unregister(name)
    checkpoint_system.clear(name)
    revocation_queue.get_pending(name)  # clear any pending revocation
    success = agent_registry.unregister(name)
    if success:
        _publish("agent_unregistered", {"name": name})
        return jsonify({"status": "ok"})
    return jsonify({"error": "agent not found"}), 404


@app.route("/agents", methods=["GET"])
def list_agents():
    agents = agent_registry.list_agents()
    return jsonify([{
        "name": a["name"],
        "type": a.get("type", "unknown"),
        "status": a.get("status", "online"),
        "registered_at": a.get("registered_at", ""),
        "last_heartbeat": a.get("last_heartbeat", ""),
        "autonomy_mode": a.get("autonomy_mode", "fully_autonomous"),
        "capabilities": a.get("capabilities", []),
        "current_task_id": a.get("current_task_id"),
        "checkpoint_sequence": a.get("checkpoint_sequence", 0),
    } for a in agents])


# ── Autonomy ─────────────────────────────────────────────────────────────────

@app.route("/agents/<name>/autonomy", methods=["POST"])
def set_agent_autonomy(name: str):
    """Set an agent's autonomy mode."""
    data = request.json
    mode_str = data.get("mode", "fully_autonomous")
    try:
        mode = AutonomyMode(mode_str)
    except ValueError:
        return jsonify({"error": f"Invalid mode: {mode_str}"}), 400

    success = agent_registry.set_autonomy_mode(name, mode)
    if not success:
        return jsonify({"error": "agent not found"}), 404

    sandbox.audit(name, "set_autonomy", {"mode": mode.value})
    _publish("agent_autonomy_changed", {"name": name, "mode": mode.value})
    return jsonify({"name": name, "autonomy_mode": mode.value})


@app.route("/autonomy/set-mode", methods=["POST"])
def set_global_autonomy():
    """Set autonomy mode for all agents (or filter by type)."""
    data = request.json
    mode_str = data.get("mode", "fully_autonomous")
    agent_type = data.get("agent_type")  # optional filter

    try:
        mode = AutonomyMode(mode_str)
    except ValueError:
        return jsonify({"error": f"Invalid mode: {mode_str}"}), 400

    agents = agent_registry.list_agents()
    updated = []
    for a in agents:
        if agent_type and a.get("type") != agent_type:
            continue
        agent_registry.set_autonomy_mode(a["name"], mode)
        updated.append(a["name"])

    _publish("global_autonomy_changed", {"mode": mode.value, "agents": updated})
    return jsonify({"mode": mode.value, "updated_agents": updated})


# ── Capabilities ─────────────────────────────────────────────────────────────

@app.route("/agents/<name>/capabilities", methods=["POST"])
def set_agent_capabilities(name: str):
    """Update an agent's capability tags."""
    data = request.json
    tags = data.get("tags", [])
    description = data.get("description", "")

    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    success = agent_registry.set_capabilities(name, tags)
    if not success:
        return jsonify({"error": "agent not found"}), 404

    capability_registry.register(name, tags, description)
    sandbox.audit(name, "set_capabilities", {"tags": tags})
    _publish("agent_capabilities_changed", {"name": name, "tags": tags})
    return jsonify({"name": name, "tags": tags})


@app.route("/capabilities", methods=["GET"])
def list_capabilities():
    profiles = capability_registry.list_all()
    return jsonify(profiles)


@app.route("/capabilities/match", methods=["GET"])
def match_capabilities():
    """Find agents that have a specific capability tag."""
    tag = request.args.get("tag", "")
    if not tag:
        return jsonify({"error": "tag required"}), 400
    agents = capability_registry.agents_with_capability(tag)
    return jsonify({"tag": tag, "agents": agents})


# ── Checkpointing ─────────────────────────────────────────────────────────────

@app.route("/agents/<name>/checkpoint", methods=["POST"])
def submit_checkpoint(name: str):
    """Agent submits a checkpoint."""
    data = request.json
    task_id = data.get("task_id")
    state = data.get("state", "")
    rationale = data.get("rationale", "")
    metadata = data.get("metadata", {})

    cp = checkpoint_system.submit(name, task_id, state, rationale, metadata)
    agent_registry.set_current_task(name, task_id, state)
    agent_registry.advance_checkpoint_sequence(name)

    sandbox.audit(name, "checkpoint", {
        "task_id": task_id,
        "state": state,
        "sequence": cp.sequence,
    })

    _publish("checkpoint_submitted", {
        "agent": name,
        "task_id": task_id,
        "state": state,
        "sequence": cp.sequence,
    })

    return jsonify({
        "id": cp.id,
        "sequence": cp.sequence,
        "timestamp": cp.timestamp.isoformat(),
    })


@app.route("/agents/<name>/checkpoint", methods=["GET"])
def get_checkpoint(name: str):
    """Get latest checkpoint for an agent."""
    cp = checkpoint_system.get_checkpoint(name)
    if not cp:
        return jsonify({"error": "No checkpoint found"}), 404
    return jsonify({
        "id": cp.id,
        "agent_name": cp.agent_name,
        "task_id": cp.task_id,
        "state": cp.state,
        "rationale": cp.rationale,
        "sequence": cp.sequence,
        "timestamp": cp.timestamp.isoformat(),
    })


# ── Revocation ────────────────────────────────────────────────────────────────

@app.route("/agents/<name>/revoke", methods=["POST"])
def revoke_agent(name: str):
    """Human issues a revocation directive to an agent."""
    data = request.json or {}
    reason = data.get("reason", "")
    flush_required = data.get("flush_required", True)

    rev = revocation_queue.issue(name, reason, flush_required)
    agent_registry.set_status(name, "revoked")
    sandbox.audit("human", "revoke_agent", {"agent": name, "reason": reason})

    _publish("agent_revoked", {
        "agent": name,
        "revocation_id": rev.id,
        "reason": reason,
        "flush_required": flush_required,
    })

    return jsonify({
        "revocation_id": rev.id,
        "agent": name,
        "issued_at": rev.issued_at.isoformat(),
    })


@app.route("/agents/<name>/revocation", methods=["GET"])
def check_revocation(name: str):
    """Agent polls for pending revocation."""
    rev = revocation_queue.get_pending(name)
    if rev:
        return jsonify({
            "pending": True,
            "revocation_id": rev.id,
            "reason": rev.reason,
            "flush_required": rev.flush_required,
        })
    return jsonify({"pending": False})


@app.route("/agents/<name>/revocation/ack", methods=["POST"])
def ack_revocation(name: str):
    """Agent acknowledges revocation and re-registers."""
    data = request.json or {}
    revocation_id = data.get("revocation_id", "")

    revocation_queue.acknowledge(revocation_id)
    agent_registry.set_status(name, "online")

    # Clear checkpoint state so agent re-starts fresh
    checkpoint_system.clear(name)

    sandbox.audit(name, "revocation_acknowledged", {"revocation_id": revocation_id})
    _publish("agent_recovered", {"name": name})
    return jsonify({"status": "ok"})


@app.route("/revocation/history", methods=["GET"])
def revocation_history():
    limit = int(request.args.get("limit", 50))
    history = revocation_queue.history(limit)
    return jsonify(history)


# ── Human Intervention ────────────────────────────────────────────────────────

@app.route("/agents/<name>/pause", methods=["POST"])
def pause_agent(name: str):
    """Human pauses an agent (status=busy, stops accepting new tasks)."""
    data = request.json or {}
    reason = data.get("reason", "")

    success = agent_registry.set_status(name, "busy")
    if not success:
        return jsonify({"error": "agent not found"}), 404

    sandbox.audit("human", "pause_agent", {"agent": name, "reason": reason})
    _publish("agent_paused", {"name": name, "reason": reason})
    return jsonify({"name": name, "status": "busy"})


@app.route("/agents/<name>/resume", methods=["POST"])
def resume_agent(name: str):
    """Human resumes a paused agent."""
    success = agent_registry.set_status(name, "online")
    if not success:
        return jsonify({"error": "agent not found"}), 404

    sandbox.audit("human", "resume_agent", {"agent": name})
    _publish("agent_resumed", {"name": name})
    return jsonify({"name": name, "status": "online"})


# ── Messaging ─────────────────────────────────────────────────────────────────

@app.route("/messages/send", methods=["POST"])
def send_message():
    data = request.json
    from_agent = data.get("from")
    to_agent = data.get("to")
    content = data.get("content", "")
    message_type = data.get("type", "text")

    if not from_agent or not to_agent:
        return jsonify({"error": "from and to required"}), 400

    sandbox.check_rate_limit(from_agent)
    if not sandbox.check_message_content(content):
        return jsonify({"error": "Sandbox: message content blocked (external URL detected)"}), 400

    sandbox.audit(from_agent, "send_message", {"to": to_agent})
    message = message_store.send(from_agent, to_agent, content, message_type)

    _publish("message_sent", {
        "id": message.id,
        "from": from_agent,
        "to": to_agent,
        "content": content[:200],  # truncate for feed
        "type": message_type,
        "timestamp": message.timestamp.isoformat(),
    })

    return jsonify({
        "id": message.id,
        "from": message.from_agent,
        "to": message.to_agent,
        "timestamp": message.timestamp.isoformat()
    })


@app.route("/messages/<agent_name>", methods=["GET"])
def get_messages(agent_name: str):
    unread_only = request.args.get("unread", "false").lower() == "true"
    inbox = message_store.get_inbox(agent_name, unread_only)
    return jsonify([{
        "id": m.id,
        "from": m.from_agent,
        "content": m.content,
        "type": m.message_type,
        "timestamp": m.timestamp.isoformat(),
        "delivered": m.delivered,
        "acknowledged": m.acknowledged
    } for m in inbox])


@app.route("/messages/<message_id>/ack", methods=["POST"])
def ack_message(message_id: str):
    success = message_store.ack(message_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "message not found"}), 404


@app.route("/messages/history/<a>/<b>", methods=["GET"])
def get_message_history(a: str, b: str):
    limit = int(request.args.get("limit", 50))
    history = message_store.get_history(a, b, limit)
    return jsonify([{
        "id": m.id,
        "from": m.from_agent,
        "to": m.to_agent,
        "content": m.content,
        "timestamp": m.timestamp.isoformat()
    } for m in history])


@app.route("/messages/graph", methods=["GET"])
def message_graph():
    """
    Returns a message flow graph: nodes = agents, edges = message counts.
    Useful for the dashboard visualization.
    """
    agents = agent_registry.list_agents()
    agent_names = {a["name"] for a in agents}

    # Build adjacency
    edges: dict[tuple[str, str], int] = {}
    for msg in message_store._messages.values():
        if msg.from_agent in agent_names and msg.to_agent in agent_names:
            key = (msg.from_agent, msg.to_agent)
            edges[key] = edges.get(key, 0) + 1

    return jsonify({
        "nodes": [{"id": a["name"], "type": a.get("type", "unknown")} for a in agents],
        "edges": [{"from": f, "to": t, "count": c} for (f, t), c in edges.items()],
    })


# ── Projects ─────────────────────────────────────────────────────────────────

@app.route("/projects", methods=["POST"])
def create_project():
    data = request.json
    name = data.get("name")
    creator = data.get("creator")
    if not name or not creator:
        return jsonify({"error": "name and creator required"}), 400

    sandbox.audit(creator, "create_project", {"name": name})
    project = project_manager.create_project(name, creator)
    _publish("project_created", {
        "id": project.id,
        "name": name,
        "creator": creator,
    })
    return jsonify({
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at.isoformat()
    }), 201


@app.route("/projects", methods=["GET"])
def list_projects():
    agent = request.args.get("agent")
    projects = project_manager.list_projects(agent)
    return jsonify([{
        "id": p.id,
        "name": p.name,
        "members": p.members,
        "created_at": p.created_at.isoformat()
    } for p in projects])


@app.route("/projects/<project_id>", methods=["GET"])
def get_project(project_id: str):
    project = project_manager.get_project(project_id)
    if not project:
        return jsonify({"error": "project not found"}), 404
    return jsonify({
        "id": project.id,
        "name": project.name,
        "members": project.members,
        "files": project.files,
        "wip_limits": project.wip_limits,
        "created_at": project.created_at.isoformat()
    })


@app.route("/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id: str):
    project = project_manager.get_project(project_id)
    if not project:
        return jsonify({"error": "project not found"}), 404
    del project_manager._projects[project_id]
    _publish("project_deleted", {"id": project_id})
    return jsonify({"status": "ok"})


@app.route("/projects/<project_id>/join", methods=["POST"])
def join_project(project_id: str):
    data = request.json
    agent = data.get("agent")
    if not agent:
        return jsonify({"error": "agent required"}), 400

    sandbox.audit(agent, "join_project", {"project": project_id})
    success = project_manager.join_project(project_id, agent)
    if success:
        _publish("agent_joined_project", {"project": project_id, "agent": agent})
        return jsonify({"status": "ok"})
    return jsonify({"error": "project not found"}), 404


@app.route("/projects/<project_id>/wip", methods=["PATCH"])
def update_wip_limit(project_id: str):
    """Update WIP limit for a status column."""
    data = request.json
    status = data.get("status")
    limit = data.get("limit")
    if not status or limit is None:
        return jsonify({"error": "status and limit required"}), 400
    success = project_manager.update_wip_limit(project_id, status, int(limit))
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "project not found"}), 404


# ── Project Files ─────────────────────────────────────────────────────────────

@app.route("/projects/<project_id>/files", methods=["POST"])
def upload_file(project_id: str):
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    file = request.files["file"]
    uploader = request.form.get("uploader", "unknown")
    content = file.read()
    sandbox.check_rate_limit(uploader)
    sandbox.audit(uploader, "upload_file", {"project": project_id, "filename": file.filename})
    try:
        result = project_manager.write_file(project_id, file.filename, content)
        _publish("file_uploaded", {
            "project": project_id,
            "filename": file.filename,
            "uploader": uploader,
            "size": result["size"],
        })
        return jsonify({
            "filename": file.filename,
            "checksum": result["checksum"],
            "size": result["size"]
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/projects/<project_id>/files/<filename>", methods=["GET"])
def download_file(project_id: str, filename: str):
    try:
        content = project_manager.read_file(project_id, filename)
        return content, 200, {"Content-Type": "application/octet-stream"}
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ── KanBan Tasks ──────────────────────────────────────────────────────────────

@app.route("/projects/<project_id>/tasks", methods=["POST"])
def create_task(project_id: str):
    data = request.json
    title = data.get("title")
    description = data.get("description", "")
    assigned_to = data.get("assigned_to")
    priority = data.get("priority", "P2")
    required_capabilities = data.get("required_capabilities", [])
    required_reviewers = data.get("required_reviewers", 1)
    created_by = data.get("created_by", "")
    parent_task_id = data.get("parent_task_id")

    if not title:
        return jsonify({"error": "title required"}), 400

    task = project_manager.create_task(
        project_id=project_id,
        title=title,
        description=description,
        assigned_to=assigned_to,
        priority=priority,
        required_capabilities=required_capabilities,
        required_reviewers=required_reviewers,
        created_by=created_by,
        parent_task_id=parent_task_id,
    )

    _publish("task_created", {
        "project": project_id,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "priority": task.priority.value,
            "assigned_to": task.assigned_to,
            "required_capabilities": task.required_capabilities,
        }
    })

    return jsonify({
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.name,
        "assigned_to": task.assigned_to,
        "required_capabilities": task.required_capabilities,
        "created_at": task.created_at.isoformat(),
    }), 201


@app.route("/projects/<project_id>/tasks", methods=["GET"])
def list_tasks(project_id: str):
    """
    List tasks for a project with optional filters.
    ?status=in_progress&agent=claude&assigned_to=claude
    """
    status = request.args.get("status")
    agent = request.args.get("agent")
    assigned_to = request.args.get("assigned_to")
    include_blocked = request.args.get("include_blocked", "true").lower() == "true"

    tasks = project_manager.get_tasks(
        project_id=project_id,
        agent_name=agent,
        status=status,
        assigned_to=assigned_to,
        include_blocked=include_blocked,
    )
    return jsonify([{
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "status": t.status.value,
        "priority": t.priority.name,
        "assigned_to": t.assigned_to,
        "claimed_by": t.claimed_by,
        "required_capabilities": t.required_capabilities,
        "blocked_reason": t.blocked_reason,
        "blocked_by": t.blocked_by,
        "subtasks": t.subtasks,
        "parent_task_id": t.parent_task_id,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "reviewers": t.reviewers,
        "required_reviewers": t.required_reviewers,
        "transitions": [
            {"from": tr.from_status, "to": tr.to_status, "at": tr.timestamp.isoformat(), "by": tr.by_agent}
            for tr in t.transitions[-5:]  # last 5 transitions
        ],
    } for t in tasks])


@app.route("/projects/<project_id>/tasks/ready", methods=["GET"])
def get_ready_queue(project_id: str):
    """Get the ready/backlog queue for an agent (capability-filtered)."""
    agent_name = request.args.get("agent")
    capability_tags = request.args.getlist("capabilities")

    tasks = project_manager.get_ready_queue(
        project_id,
        agent_name=agent_name,
        agent_capabilities=capability_tags,
    )
    return jsonify([{
        "id": t.id,
        "title": t.title,
        "priority": t.priority.name,
        "required_capabilities": t.required_capabilities,
    } for t in tasks])


@app.route("/projects/<project_id>/tasks/<task_id>/claim", methods=["POST"])
def claim_task(project_id: str, task_id: str):
    """Agent self-claims a task from the ready queue."""
    data = request.json
    agent = data.get("agent")

    if not agent:
        return jsonify({"error": "agent required"}), 400

    # Get agent capabilities
    cap_profile = capability_registry.get(agent)
    caps = list(cap_profile.tags) if cap_profile else []

    result = project_manager.claim_task(project_id, task_id, agent, caps)
    if "error" in result:
        return jsonify(result), 400

    task = project_manager.get_task(task_id)
    agent_registry.set_current_task(agent, task_id, "claimed")

    _publish("task_claimed", {
        "project": project_id,
        "task_id": task_id,
        "agent": agent,
        "title": task.title if task else "",
    })
    return jsonify(result)


@app.route("/projects/<project_id>/tasks/<task_id>", methods=["PATCH"])
def update_task(project_id: str, task_id: str):
    """
    Full task update: status transition, blocked fields, review, etc.
    Replaces the legacy update_task endpoint.
    """
    data = request.json
    agent = data.get("agent", "")
    new_status = data.get("status")
    blocked_reason = data.get("blocked_reason", "")
    blocked_by = data.get("blocked_by")
    note = data.get("note", "")

    task = project_manager.get_task(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    if new_status:
        result = project_manager.transition_task(
            project_id, task_id, new_status,
            agent_name=agent,
            blocked_reason=blocked_reason,
            blocked_by=blocked_by,
            note=note,
        )
        if "error" in result:
            return jsonify(result), 400

        _publish("task_transition", {
            "project": project_id,
            "task_id": task_id,
            "title": task.title,
            "new_status": new_status,
            "by": agent,
        })

    updated = project_manager.get_task(task_id)
    return jsonify({
        "id": updated.id,
        "title": updated.title,
        "status": updated.status.value,
        "assigned_to": updated.assigned_to,
        "priority": updated.priority.name,
        "blocked_reason": updated.blocked_reason,
        "blocked_by": updated.blocked_by,
    })


@app.route("/projects/<project_id>/tasks/<task_id>/assign", methods=["POST"])
def assign_task(project_id: str, task_id: str):
    """Human or coordinator assigns a task to a specific agent."""
    data = request.json
    agent = data.get("agent")
    assigned_by = data.get("assigned_by", "human")

    if not agent:
        return jsonify({"error": "agent required"}), 400

    result = project_manager.assign_task(project_id, task_id, agent, assigned_by)
    if "error" in result:
        return jsonify(result), 400

    task = project_manager.get_task(task_id)
    sandbox.audit(assigned_by, "assign_task", {"task": task_id, "to": agent})
    _publish("task_assigned", {
        "project": project_id,
        "task_id": task_id,
        "title": task.title if task else "",
        "agent": agent,
        "by": assigned_by,
    })
    return jsonify(result)


@app.route("/projects/<project_id>/tasks/<task_id>/unassign", methods=["POST"])
def unassign_task(project_id: str, task_id: str):
    """Move a task back to backlog and clear assignment."""
    result = project_manager.unassign_task(project_id, task_id)
    if "error" in result:
        return jsonify(result), 400
    _publish("task_unassigned", {"project": project_id, "task_id": task_id})
    return jsonify(result)


@app.route("/projects/<project_id>/tasks/<task_id>/reviewers/<reviewer>", methods=["POST"])
def add_reviewer(project_id: str, task_id: str, reviewer: str):
    """Add a reviewer to a task."""
    success = project_manager.add_reviewer(project_id, task_id, reviewer)
    if not success:
        return jsonify({"error": "task not found"}), 404
    _publish("task_reviewer_added", {
        "project": project_id,
        "task_id": task_id,
        "reviewer": reviewer,
    })
    return jsonify({"status": "ok"})


@app.route("/projects/<project_id>/metrics", methods=["GET"])
def project_metrics(project_id: str):
    metrics = project_manager.get_project_metrics(project_id)
    return jsonify(metrics)


# ── SSE Event Stream ───────────────────────────────────────────────────────────

@app.route("/events", methods=["GET"])
def sse_events():
    """
    SSE endpoint — dashboard connects here to receive the live event stream.
    Clients receive: messages, task transitions, agent status changes,
    checkpoints, revocations, file uploads.
    """
    client_id, _ = events.subscribe()

    def generate():
        q = events.get_client_queue(client_id)
        if q is None:
            return

        # Send keepalive comment every 20s
        last_keepalive = time.time()

        while True:
            try:
                event = q.get(timeout=25)  # blocks up to 25s
                yield event.to_sse()
                last_keepalive = time.time()
            except queue.Empty:
                # Keepalive
                if time.time() - last_keepalive >= 20:
                    yield f": keepalive {int(time.time())}\n\n"
                    last_keepalive = time.time()

    resp = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
    return resp


# ── Audit ─────────────────────────────────────────────────────────────────────

@app.route("/audit/log", methods=["GET"])
def get_audit_log():
    limit = int(request.args.get("limit", 100))
    log = sandbox.get_audit_log(limit)
    return jsonify(log)


# ── Global task list (cross-project) ─────────────────────────────────────────

@app.route("/tasks", methods=["GET"])
def list_all_tasks():
    """List tasks across all projects with filters."""
    agent = request.args.get("agent")
    project_id = request.args.get("project_id")
    status = request.args.get("status")
    assigned_to = request.args.get("assigned_to")

    if project_id:
        tasks = project_manager.get_tasks(project_id=project_id, agent_name=agent, status=status, assigned_to=assigned_to)
    elif agent or assigned_to or status:
        # Cross-project search
        tasks = project_manager.get_tasks(agent_name=agent, status=status, assigned_to=assigned_to)
    else:
        tasks = []

    return jsonify([{
        "id": t.id,
        "project_id": t.project_id,
        "title": t.title,
        "status": t.status.value,
        "priority": t.priority.name,
        "assigned_to": t.assigned_to,
    } for t in tasks])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
