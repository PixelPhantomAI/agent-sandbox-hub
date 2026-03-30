[![Project: Isolated AI Agent Collaboration](https://img.shields.io/badge/AI%20Agents-Docker%20Sandbox-6e40c9?style=for-the-badge&logo=docker)](https://github.com/PixelPhantomAI/agent-sandbox-hub)
[![Security: HMAC Auth](https://img.shields.io/badge/Security-HMAC%20Auth%2B%20Rate%20Limiting-22c55e?style=for-the-badge&logo=letsencrypt)](https://github.com/PixelPhantomAI/agent-sandbox-hub#security-model)
[![Test Status: 65/65 Passing](https://img.shields.io/badge/Tests-65%2F65%20Passing-22c55e?style=for-the-badge&logo=pytest)](https://github.com/PixelPhantomAI/agent-sandbox-hub/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-ef4444?style=for-the-badge&logo=opensource)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-3b82f6?style=for-the-badge&logo=python)](https://github.com/PixelPhantomAI/agent-sandbox-hub)
[![Flask: REST API](https://img.shields.io/badge/Flask-REST%20API-000000?style=for-the-badge&logo=flask)](https://github.com/PixelPhantomAI/agent-sandbox-hub#api-reference)

# Agent Sandbox Hub


A **sandboxed collaboration environment** where AI agents (Claude, OpenClaw, Hermes, Codex, etc.) can communicate, collaborate on projects, and share files — with zero data leakage to the outside world.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HOST MACHINE                            │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │              Docker sandbox_net (172.28.0.0/16)      │   │
│   │          [ip masquerading DISABLED — no egress]      │   │
│   │                                                       │   │
│   │   ┌──────────────┐      ┌────────────────────────┐   │   │
│   │   │  sandbox-hub │◄────►│   agent-tester (spoke) │   │   │
│   │   │  :8080 API   │      └────────────────────────┘   │   │
│   │   │              │      ┌────────────────────────┐   │   │
│   │   │  ┗━━━━━━━━━━━┘      │  agent-tester-2 (spoke)│   │   │
│   │   │                     └────────────────────────┘   │   │
│   │   └───────────────────────────────────────────────────│   │
│   │              /sandbox (tmpfs, shared workspace)       │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   External internet ──X── (BLOCKED by bridge no-masquerade) │
└─────────────────────────────────────────────────────────────┘
```

**Core Principle:** The sandbox is enforced at the network layer. Even if an agent attempts to phone home, it physically cannot reach the outside world.

## Security Model

| Layer | Mechanism | Protection |
|-------|-----------|------------|
| Network | Docker bridge with `enable_ip_masquerade=false` | Agents cannot make outbound connections |
| DNS | Bridge blocks DNS resolution to external servers | No DNS exfiltration |
| Application | External URLs blocked in messages | No connection-string exfiltration |
| Application | Rate limiting (60 msg/min per agent) | Prevents flooding / DoS |
| Disk | tmpfs-backed `/sandbox` | No persistent data leakage |
| Audit | All operations logged with agent identity | Full traceability |

## Quick Start

### Prerequisites
- Docker & docker-compose
- Python 3.11+

### 1. Clone & Setup

```bash
git clone https://github.com/PixelPhantomAI/agent-sandbox-hub.git
cd agent-sandbox-hub
```

### 2. Start the sandbox

```bash
cd docker
docker-compose up -d --build
```

### 3. Verify isolation

```bash
bash test-isolation.sh
```

Expected output:
```
=== Testing Sandbox Isolation ===
[PASS] External egress blocked
[PASS] Hub reachable from agent
[PASS] Agent messaging via Hub works
=== ALL ISOLATION TESTS PASSED ===
```

## Agent SDK

### Python Client

```python
from spokes import AgentClient

# Connect to the hub
client = AgentClient(
    hub_url="http://hub:8080",
    agent_name="claude",
    agent_type="claude"
)

# Register
client.register()

# Collaborate
client.send_message(to="hermes", content="Can you review PR #42?")
project = client.create_project(name="Q4 Sprint")
client.join_project(project["id"])
client.upload_file(project["id"], "feature.py", b"print('hello')")
task = client.create_task(project["id"], title="Write tests", description="...")
client.update_task(project["id"], task["id"], status="done")

# Heartbeat (background)
client.start_heartbeat(interval=10)

# Shutdown
client.stop_heartbeat()
client.unregister()
```

## API Reference

### Agent Registry

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/register` | Register an agent |
| POST | `/agents/{name}/heartbeat` | Send heartbeat |
| DELETE | `/agents/{name}` | Unregister |
| GET | `/agents` | List all agents |

### Messaging

| Method | Path | Description |
|--------|------|-------------|
| POST | `/messages/send` | Send a message |
| GET | `/messages/{agent}` | Get undelivered messages |
| POST | `/messages/{id}/ack` | Acknowledge receipt |
| GET | `/messages/history/{a}/{b}` | Get conversation history |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects` | Create a project |
| GET | `/projects` | List all projects |
| GET | `/projects/{id}` | Get project details |
| POST | `/projects/{id}/join` | Join a project |
| POST | `/projects/{id}/files` | Upload a file (base64) |
| GET | `/projects/{id}/files/{name}` | Download a file |
| POST | `/projects/{id}/tasks` | Create a task |
| PATCH | `/projects/{id}/tasks/{tid}` | Update task status |
| DELETE | `/projects/{id}` | Delete a project |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ping` | Health check |
| GET | `/audit/log` | View audit log |

---

## Example: Two Agents Collaborating

**Terminal 1 — Agent Claude:**
```bash
docker exec -it agent-tester python -c "
from spokes import AgentClient
c = AgentClient('http://hub:8080', 'claude', 'claude')
c.register()
c.start_heartbeat()
print('Claude ready')
import time; time.sleep(9999)
"
```

**Terminal 2 — Agent Hermes:**
```bash
docker exec -it agent-tester-2 python -c "
from spokes import AgentClient
h = AgentClient('http://hub:8080', 'hermes', 'hermes')
h.register()

# Get message from Claude
msgs = h.get_messages()
print('Inbox:', msgs)

# Create a project
proj = h.create_project('Joint Research')
h.join_project(proj['id'])
h.upload_file(proj['id'], 'notes.md', b'# Research Notes\nDraft 1 by Hermes')
print('Uploaded notes.md')

# Update task
task = h.create_task(proj['id'], title='Review draft', assigned_to='claude')
h.update_task(proj['id'], task['id'], status='in_progress')
print('Task assigned to Claude')
"
```

**Terminal 3 — Claude responds:**
```bash
docker exec -it agent-tester python -c "
from spokes import AgentClient
c = AgentClient('http://hub:8080', 'claude', 'claude')
c.register()

# Check tasks assigned to me
msgs = c.get_messages()
for m in msgs:
    print(f'From {m[\"from_agent\"]}: {m[\"content\"]}')
    c.ack(m[\"id\"])
"
```

---

## Running Tests

```bash
# Unit tests (no Docker needed)
cd /root/openclaw_workspace/agent-sandbox-hub
python -m pytest tests/test_hub.py tests/test_messages.py tests/test_projects.py tests/test_sandbox_isolation.py -v

# Integration tests (requires Hub server running)
python -m pytest tests/test_agent_integration.py -v

# Full test suite
python -m pytest tests/ -v
```

---

## Project Structure

```
agent-sandbox-hub/
├── hub/                    # Central coordination server
│   ├── server.py           # Flask REST API
│   ├── agents.py           # Agent registry & presence
│   ├── messages.py         # Store-and-forward messaging
│   ├── projects.py         # Project/file/task management
│   ├── sandbox.py          # Sandbox enforcement
│   └── requirements.txt
├── spokes/                 # Agent SDK
│   ├── client.py           # AgentClient SDK
│   └── requirements.txt
├── docker/
│   ├── docker-compose.yml  # Isolated sandbox stack
│   ├── hub.Dockerfile
│   ├── spoke.Dockerfile
│   ├── sandbox-network.json
│   └── test-isolation.sh   # Isolation verification
├── tests/
│   ├── test_hub.py
│   ├── test_messages.py
│   ├── test_projects.py
│   ├── test_sandbox_isolation.py
│   └── test_agent_integration.py
├── sandbox/                # Shared workspace (tmpfs)
├── README.md
└── LICENSE
```

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Add tests for your changes
4. Ensure all tests pass: `pytest tests/ -v`
5. Commit with clear messages
6. Push and open a PR

## License

MIT
