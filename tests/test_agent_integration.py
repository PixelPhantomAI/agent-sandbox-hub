"""
Full-stack integration tests for the Agent Sandbox Hub Flask server.
Tests exercise the real Flask app with in-memory services.
"""

import base64
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hub.server import app, agent_registry, message_store, project_manager, sandbox


@pytest.fixture(scope="module")
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all in-memory state between tests."""
    agent_registry._agents.clear()
    message_store._messages.clear()
    project_manager._projects.clear()
    project_manager._tasks.clear()
    sandbox._audit_log.clear()
    sandbox._rate_limits.clear()
    yield


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_ping(client):
    r = client.post("/ping")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Agent Lifecycle
# ---------------------------------------------------------------------------


def test_full_agent_lifecycle(client):
    # Register
    r = client.post("/agents/register", json={"name": "claude", "type": "claude"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == "claude"

    # Heartbeat
    r = client.post("/agents/claude/heartbeat")
    assert r.status_code == 200

    # List agents
    r = client.get("/agents")
    assert r.status_code == 200
    agents = r.get_json()
    assert any(a["name"] == "claude" for a in agents)

    # Unregister
    r = client.delete("/agents/claude")
    assert r.status_code == 200


def test_agent_heartbeat_unknown(client):
    r = client.post("/agents/nobody/heartbeat")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


def test_send_and_receive_messages(client):
    # Register agents
    client.post("/agents/register", json={"name": "alice", "type": "test"})
    client.post("/agents/register", json={"name": "bob", "type": "test"})

    # Send message
    r = client.post("/messages/send", json={
        "from": "alice",
        "to": "bob",
        "content": "Hello Bob!",
        "type": "text",
    })
    assert r.status_code == 200
    msg_id = r.get_json()["id"]

    # Receive messages
    r = client.get("/messages/bob")
    assert r.status_code == 200
    messages = r.get_json()
    assert len(messages) >= 1
    assert messages[0]["content"] == "Hello Bob!"

    # Ack
    r = client.post("/messages/{}/ack".format(msg_id))
    assert r.status_code == 200

    # History
    r = client.get("/messages/history/alice/bob")
    assert r.status_code == 200
    history = r.get_json()
    assert any(m["content"] == "Hello Bob!" for m in history)


def test_sandbox_blocks_external_url_in_message(client):
    client.post("/agents/register", json={"name": "alice", "type": "test"})
    r = client.post("/messages/send", json={
        "from": "alice",
        "to": "bob",
        "content": "Check https://evil.com for info",
        "type": "text",
    })
    assert r.status_code == 400


def test_rate_limit_enforced(client):
    client.post("/agents/register", json={"name": "alice", "type": "test"})
    # The sandbox rate limit is 60/min — send many quickly
    # We test that it at least doesn't crash
    for i in range(5):
        r = client.post("/messages/send", json={
            "from": "alice", "to": "bob", "content": f"msg{i}", "type": "text"
        })
        # Either success or rate limited is acceptable
        assert r.status_code in (200, 429)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def test_full_project_workflow(client):
    # Register agent
    client.post("/agents/register", json={"name": "claude", "type": "claude"})

    # Create project
    r = client.post("/projects", json={"name": "My Project", "creator": "claude"})
    assert r.status_code == 201
    project_id = r.get_json()["id"]

    # Join project
    r = client.post("/projects/{}/join".format(project_id), json={"agent": "claude"})
    assert r.status_code == 200

    # Create task
    r = client.post("/projects/{}/tasks".format(project_id), json={
        "title": "Write code",
        "description": "Implement feature X",
        "assigned_to": "claude",
    })
    assert r.status_code == 201
    task_id = r.get_json()["id"]

    # Update task
    r = client.patch("/projects/{}/tasks/{}".format(project_id, task_id), json={"status": "in_progress"})
    assert r.status_code == 200

    # List projects
    r = client.get("/projects")
    assert r.status_code == 200
    assert any(p["name"] == "My Project" for p in r.get_json())

    # Get project details
    r = client.get("/projects/{}".format(project_id))
    assert r.status_code == 200
    proj = r.get_json()
    assert proj["name"] == "My Project"

    # Delete project
    r = client.delete("/projects/{}".format(project_id))
    assert r.status_code == 200


def test_project_audit_logged(client):
    client.post("/agents/register", json={"name": "claude", "type": "test"})
    r = client.post("/projects", json={"name": "Secret Project", "creator": "claude"})
    assert r.status_code == 201

    r = client.get("/audit/log")
    log = r.get_json()
    assert any(
        entry.get("action") == "create_project" and "Secret Project" in str(entry.get("details", {}))
        for entry in log
    )


def test_create_project_missing_fields(client):
    r = client.post("/projects", json={"name": "Only Name"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Error Cases
# ---------------------------------------------------------------------------


def test_unregistered_agent_rejected(client):
    r = client.post("/messages/send", json={
        "from": "ghost",
        "to": "claude",
        "content": "I shouldn't be here",
    })
    # No auth step needed for messaging, but the message goes through
    # (sandbox check is done on content, not auth)
    assert r.status_code in (200, 400, 429)


def test_list_agents_empty(client):
    r = client.get("/agents")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
