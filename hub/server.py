"""
Hub Server Flask API
Central REST API for agent registration, messaging, and project management.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from hub.agents import AgentRegistry
from hub.messages import MessageStore
from hub.projects import ProjectManager
from hub.sandbox import SandboxEnforcer

app = Flask(__name__)
CORS(app)

agent_registry = AgentRegistry()
message_store = MessageStore()
project_manager = ProjectManager()
sandbox = SandboxEnforcer()


@app.route("/ping", methods=["POST", "GET"])
def ping():
    return jsonify({"status": "ok"})


@app.route("/agents/register", methods=["POST"])
def register_agent():
    data = request.json
    name = data.get("name")
    agent_type = data.get("type", "unknown")
    metadata = data.get("metadata", {})
    if not name:
        return jsonify({"error": "name required"}), 400
    sandbox.audit(name, "register", {"type": agent_type})
    agent = agent_registry.register(name, agent_type, metadata)
    return jsonify({
        "id": agent.name,
        "type": agent.agent_type,
        "registered_at": agent.registered_at.isoformat()
    })


@app.route("/agents/<name>/heartbeat", methods=["POST"])
def agent_heartbeat(name: str):
    sandbox.check_rate_limit(name)
    success = agent_registry.heartbeat(name)
    if success:
        sandbox.audit(name, "heartbeat", {})
        return jsonify({"status": "ok"})
    return jsonify({"error": "agent not found"}), 404


@app.route("/agents/<name>", methods=["DELETE"])
def delete_agent(name: str):
    sandbox.audit(name, "unregister", {})
    success = agent_registry.unregister(name)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "agent not found"}), 404


@app.route("/agents", methods=["GET"])
def list_agents():
    agents = agent_registry.list_agents()
    return jsonify([{
        "name": a["name"],
        "type": a.get("type", "unknown"),
        "registered_at": a.get("registered_at", ""),
        "last_heartbeat": a.get("last_heartbeat", ""),
        "metadata": a.get("metadata", {})
    } for a in agents])


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


@app.route("/projects", methods=["POST"])
def create_project():
    data = request.json
    name = data.get("name")
    creator = data.get("creator")
    if not name or not creator:
        return jsonify({"error": "name and creator required"}), 400
    sandbox.audit(creator, "create_project", {"name": name})
    project = project_manager.create_project(name, creator)
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
        "created_at": project.created_at.isoformat()
    })


@app.route("/projects/<project_id>/join", methods=["POST"])
def join_project(project_id: str):
    data = request.json
    agent = data.get("agent")
    if not agent:
        return jsonify({"error": "agent required"}), 400
    sandbox.audit(agent, "join_project", {"project": project_id})
    success = project_manager.join_project(project_id, agent)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "project not found"}), 404


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


@app.route("/projects/<project_id>/tasks", methods=["POST"])
def create_task(project_id: str):
    data = request.json
    title = data.get("title")
    description = data.get("description", "")
    assigned_to = data.get("assigned_to")
    if not title:
        return jsonify({"error": "title required"}), 400
    task = project_manager.create_task(project_id, title, description, assigned_to)
    return jsonify({
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assigned_to": task.assigned_to
    }), 201


@app.route("/projects/<project_id>/tasks/<task_id>", methods=["PATCH"])
def update_task(project_id: str, task_id: str):
    data = request.json
    status = data.get("status")
    if not status:
        return jsonify({"error": "status required"}), 400
    success = project_manager.update_task(project_id, task_id, status)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "task not found"}), 404


@app.route("/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id: str):
    project = project_manager.get_project(project_id)
    if not project:
        return jsonify({"error": "project not found"}), 404
    del project_manager._projects[project_id]
    return jsonify({"status": "ok"})


@app.route("/audit/log", methods=["GET"])
def get_audit_log():
    limit = int(request.args.get("limit", 100))
    log = sandbox.get_audit_log(limit)
    return jsonify(log)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
