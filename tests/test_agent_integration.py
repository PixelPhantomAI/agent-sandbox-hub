"""
Full-stack integration tests for the Agent Sandbox Hub.
These tests exercise the Flask server with real service instances.
"""

import base64
import json
import time
import threading
import pytest
import requests

# We need to start the server in a background thread for integration tests
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hub.server import app


@pytest.fixture(scope="module")
def client():
    """Start the Flask test client against the real app."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all in-memory state between tests."""
    from hub.server import agent_registry, message_store, project_manager, sandbox_enforcer
    # Clear agents
    agent_registry._agents.clear()
    # Clear messages
    message_store._messages.clear()
    message_store._inbox.clear()
    # Clear projects
    project_manager._projects.clear()
    # Clear audit log
    sandbox_enforcer._audit_log.clear()
    # Clear rate limits
    sandbox_enforcer._message_counts.clear()
    yield


# ---------------------------------------------------------------------------
# Agent Lifecycle
# ---------------------------------------------------------------------------


def test_full_agent_lifecycle(client):
    # Register
    r = client.post("/agents/register", json={"name": "claude", "agent_type": "claude"})
    assert r.status_code == 201
    data = r.get_json()
    assert data["agent"] == "claude"

    # Heartbeat
    r = client.post("/agents/claude/heartbeat")
    assert r.status_code == 200

    # List agents
    r = client.get("/agents")
    assert r.status_code == 200
    agents = r.get_json()["agents"]
    assert any(a["name"] == "claude" for a in agents)

    # Unregister
    r = client.delete("/agents/claude")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


def test_send_and_receive_messages(client):
    # Register agents
    client.post("/agents/register", json={"name": "alice", "agent_type": "test"})
    client.post("/agents/register", json={"name": "bob", "agent_type": "test"})

    # Send message
    r = client.post("/messages/send", json={
        "from_agent": "alice",
        "to_agent": "bob",
        "content": "Hello Bob!",
        "message_type": "text",
    })
    assert r.status_code == 201
    msg_id = r.get_json()["id"]

    # Receive message
    r = client.get("/messages/bob")
    messages = r.get_json()["messages"]
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello Bob!"
    assert messages[0]["delivered"] is True

    # Ack
    r = client.post(f"/messages/{msg_id}/ack")
    assert r.status_code == 200

    # History
    r = client.get("/messages/history/alice/bob")
    history = r.get_json()["history"]
    assert len(history) == 1
    assert history[0]["content"] == "Hello Bob!"


def test_sandbox_blocks_external_url_in_message(client):
    client.post("/agents/register", json={"name": "alice", "agent_type": "test"})
    r = client.post("/messages/send", json={
        "from_agent": "alice",
        "to_agent": "bob",
        "content": "Check https://evil.com for info",
        "message_type": "text",
    })
    assert r.status_code == 400
    assert "Sandbox violation" in r.get_json()["error"]


def test_rate_limit_enforced(client):
    client.post("/agents/register", json={"name": "alice", "agent_type": "test"})
    # Override rate limit to 2 for this test
    from hub.server import sandbox_enforcer
    sandbox_enforcer._rate_limit = 2
    sandbox_enforcer._message_counts.clear()

    client.post("/messages/send", json={"from_agent": "alice", "to_agent": "bob", "content": "msg1"})
    client.post("/messages/send", json={"from_agent": "alice", "to_agent": "bob", "content": "msg2"})
    r = client.post("/messages/send", json={"from_agent": "alice", "to_agent": "bob", "content": "msg3"})
    assert r.status_code == 429
    assert "rate limit" in r.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def test_full_project_workflow(client):
    # Register agent
    client.post("/agents/register", json={"name": "claude", "agent_type": "claude"})

    # Create project
    r = client.post("/projects", json={"name": "My Project", "created_by": "claude"})
    assert r.status_code == 201
    project_id = r.get_json()["id"]

    # Join project
    client.post("/projects/{}/join".format(project_id), json={"agent_name": "claude"})

    # Create task
    r = client.post("/projects/{}/tasks".format(project_id), json={
        "title": "Write code",
        "description": "Implement feature X",
        "created_by": "claude",
        "assigned_to": "claude",
    })
    assert r.status_code == 201
    task_id = r.get_json()["id"]

    # Update task
    r = client.patch("/projects/{}/tasks/{}".format(project_id, task_id), json={"status": "in_progress"})
    assert r.status_code == 200

    # Upload file
    content = b"print('hello world')"
    content_b64 = base64.b64encode(content).decode()
    r = client.post("/projects/{}/files".format(project_id), json={
        "filename": "hello.py",
        "content": content_b64,
        "modified_by": "claude",
    })
    assert r.status_code == 201
    entry = r.get_json()
    assert entry["name"] == "hello.py"
    assert entry["size"] == len(content)

    # Download file
    r = client.get("/projects/{}/files/hello.py".format(project_id))
    assert r.status_code == 200
    assert base64.b64decode(r.text.encode()).decode() == "print('hello world')"

    # List projects
    r = client.get("/projects")
    assert r.status_code == 200
    assert len(r.get_json()["projects"]) == 1

    # Get project details
    r = client.get("/projects/{}".format(project_id))
    assert r.status_code == 200
    proj = r.get_json()
    assert proj["name"] == "My Project"
    assert len(proj["tasks"]) == 1
    assert len(proj["files"]) == 1

    # Delete project
    r = client.delete("/projects/{}".format(project_id), json={"requester": "claude"})
    assert r.status_code == 200


def test_project_audit_logged(client):
    client.post("/agents/register", json={"name": "claude", "agent_type": "test"})
    r = client.post("/projects", json={"name": "Secret Project", "created_by": "claude"})
    project_id = r.get_json()["id"]

    r = client.get("/audit/log")
    log = r.get_json()["audit_log"]
    assert any(entry["action"] == "project_created" and entry["details"].get("name") == "Secret Project"
               for entry in log)


# ---------------------------------------------------------------------------
# Webhook / Health
# ---------------------------------------------------------------------------


def test_ping(client):
    r = client.post("/ping")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_unregistered_agent_rejected(client):
    r = client.post("/messages/send", json={
        "from_agent": "ghost",
        "to_agent": "claude",
        "content": "I shouldn't be here",
    })
    assert r.status_code == 403
    assert "not registered" in r.get_json()["error"]
