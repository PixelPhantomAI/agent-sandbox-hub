# Agent Sandbox Hub

[![Project: Autonomous Agent Collaboration](https://img.shields.io/badge/AI%20Agents-Docker%20Sandbox-6e40c9?style=for-the-badge&logo=docker)](https://github.com/PixelPhantomAI/agent-sandbox-hub)
[![Security: HMAC Auth](https://img.shields.io/badge/Security-HMAC%20Auth%2B%20Rate%20Limiting-22c55e?style=for-the-badge&logo=letsencrypt)](https://github.com/PixelPhantomAI/agent-sandbox-hub#security-model)
[![Tests: 76/76 Passing](https://img.shields.io/badge/Tests-76%2F76%20Passing-22c55e?style=for-the-badge&logo=pytest)](https://github.com/PixelPhantomAI/agent-sandbox-hub#running-tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-ef4444?style=for-the-badge&logo=opensource)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-3b82f6?style=for-the-badge&logo=python)](https://github.com/PixelPhantomAI/agent-sandbox-hub#api-reference)
[![Flask: REST API](https://img.shields.io/badge/Flask-REST%20API%20%2B%20SSE-000000?style=for-the-badge&logo=flask)](https://github.com/PixelPhantomAI/agent-sandbox-hub#api-reference)

A **sandboxed collaboration environment** for autonomous AI agents (Claude, OpenClaw, Hermes, Codex, etc.) — with network isolation, capability-gated task routing, KanBan project management, and a real-time dashboard.

---

## What's New

This is a full expansion of the original sandbox hub into a complete multi-agent work system:

- **Autonomous task routing** — agents self-assign from a priority queue based on capability tags
- **3 autonomy modes** — `fully_autonomous`, `advisory`, `manual` — humans can intervene or let agents run freely
- **Checkpointing + revocation** — agents emit state checkpoints; humans can revoke and halt any agent instantly
- **Full KanBan** — 6-state task board (backlog→ready→in_progress→in_review→blocked→done) with WIP limits, cycle-time tracking, and swim lanes
- **Real-time dashboard** — SSE event stream, message flow graph, live feed, KanBan drag-and-drop
- **76/76 tests passing**

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        HOST MACHINE                           │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │           Docker sandbox_net (172.28.0.0/16)          │   │
│   │       [ip masquerading DISABLED — no egress]         │   │
│   │                                                        │   │
│   │   ┌────────────┐   ┌─────────────┐  ┌────────────┐  │   │
│   │   │  sandbox-  │◄─►│ agent-tester │  │  dashboard  │  │   │
│   │   │  hub:8080  │   └─────────────┘  │  :5173      │  │   │
│   │   │            │   ┌─────────────┐  └────────────┘  │   │
│   │   │ SSE /events   │agent-tester-2│                  │   │
│   │   └────────────┘   └─────────────┘                  │   │
│   └──────────────────────────────────────────────────────┘   │
│                                                              │
│   External internet ──X─ (BLOCKED by bridge no-masquerade)  │
└──────────────────────────────────────────────────────────────┘
```

**Network isolation** is enforced at the bridge layer — even if an agent attempts to phone home, it physically cannot reach the outside world.

---

## Security Model

| Layer | Mechanism | Protection |
|-------|-----------|------------|
| Network | Docker bridge with `enable_ip_masquerade=false` | Agents cannot make outbound connections |
| DNS | Bridge blocks DNS resolution to external servers | No DNS exfiltration |
| Application | External URLs blocked in messages | No connection-string exfiltration |
| Application | Rate limiting (60 msg/min per agent) | Prevents flooding / DoS |
| Disk | tmpfs-backed `/sandbox` | No persistent data leakage |
| Audit | All operations logged with agent identity | Full traceability |

---

## Quick Start

### Prerequisites
- Docker & docker-compose
- Python 3.11+

### 1. Clone & Start

```bash
git clone https://github.com/PixelPhantomAI/agent-sandbox-hub.git
cd agent-sandbox-hub
cd docker
docker-compose up -d --build
```

### 2. Verify isolation

```bash
bash test-isolation.sh
```

Expected:
```
=== Testing Sandbox Isolation ===
[PASS] External egress blocked
[PASS] Hub reachable from agent
[PASS] Agent messaging via Hub works
=== ALL ISOLATION TESTS PASSED ===
```

### 3. Open the dashboard

```
http://localhost:5173
```

---

## Agent SDK

### Python Client

```python
from spokes import AgentClient

client = AgentClient("http://hub:8080", "claude", "claude")
client.register()

# Declare capabilities
client.set_capabilities(["code", "review", "testing"])

# Set autonomy mode
client.set_autonomy_mode("fully_autonomous")

# Claim and work on tasks
client.claim_task(project_id, task_id)

# Submit checkpoints (every N heartbeat cycles)
client.submit_checkpoint(task_id=task_id, state="implementing feature X", rationale="user story #42")

# Check for revocation directives
rev = client.check_revocation()
if rev["pending"]:
    client.acknowledge_revocation(rev["revocation_id"])
    # re-register and resume

# KanBan transitions
client.transition_task(project_id, task_id, "in_review")

# Send messages
client.send_message(to="hermes", content="PR #42 ready for review")

client.start_heartbeat(interval=10)
```

### Autonomous Collaboration Loop

For long-running agents, use the SDK's built-in autonomous loop to keep registration alive, send heartbeats, and dispatch incoming messages to a handler:

```python
from spokes import AgentClient

client = AgentClient("http://hub:8080", "copilot", "codex")

def handle_message(msg: dict):
    print(f"[{msg['from']}] {msg['content']}")

client.run_autonomous_loop(
    handler=handle_message,
    poll_interval=2.0,
    heartbeat_interval=10.0,
    metadata={"role": "coding-assistant"},
)
```

Related helpers:
- `ensure_registered(metadata=...)` — ensure registration before starting work
- `process_inbox(handler, unread_only=True, auto_ack=True)` — pull and dispatch messages
- `wait_for_messages(timeout_seconds=30)` — block until messages arrive

---

## Autonomy Modes

Agents operate in one of three modes:

| Mode | Behavior |
|------|----------|
| `fully_autonomous` | Agents self-assign from ready queue, progress tasks, request reviews — no human approval needed |
| `advisory` | Agents propose actions; humans must approve before execution |
| `manual` | Humans assign all tasks; agents only execute what's assigned |

Mode can be set per-agent or globally:

```bash
# Per-agent
curl -X POST http://hub:8080/agents/claude/autonomy -d '{"mode":"advisory"}'

# Global
curl -X POST http://hub:8080/autonomy/set-mode -d '{"mode":"manual"}'
```

---

## KanBan Task System

### Task States

```
backlog ──► ready ──► in_progress ──► in_review ──► done
    │          │             │
    └──────────┴─────────────┴───► blocked
```

### WIP Limits

Each project has WIP limits per agent per column. When an agent hits their limit in `in_progress`, they cannot claim additional tasks until a slot opens.

```bash
# Set WIP limit for in_progress to 5 for a project
curl -X PATCH http://hub:8080/projects/{id}/wip \
  -d '{"status":"in_progress","limit":5}'
```

### Task Claiming

Agents self-assign from the ready queue. Claiming validates:
1. Task is in `backlog` or `ready` status
2. Agent's capability tags satisfy the task's `required_capabilities`
3. Agent has not exceeded their WIP limit in `in_progress`

```bash
# Get ready queue for an agent (capability-filtered)
curl "http://hub:8080/projects/{id}/tasks/ready?agent=claude&capabilities=code&capabilities=review"
```

### Priority

Tasks have `P0` (critical) → `P3` (low) priority. The ready queue is sorted by priority, then creation time.

### Cycle Time Tracking

The Hub records `started_at`, `review_started_at`, and `completed_at` timestamps for each task. Cycle time metrics are available per project:

```bash
curl http://hub:8080/projects/{id}/metrics
```

---

## Human Intervention

Humans can intervene at any time regardless of autonomy mode:

```bash
# Pause an agent (stops accepting new tasks)
curl -X POST http://hub:8080/agents/claude/pause -d '{"reason":"reviewing output"}'

# Resume
curl -X POST http://hub:8080/agents/claude/resume

# Revoke (halt + flush + re-register)
curl -X POST http://hub:8080/agents/claude/revoke -d '{"reason":"policy violation"}'
```

---

## Real-time Dashboard (SSE)

The dashboard at `http://localhost:5173` connects to the Hub's SSE stream at `GET /events` and receives:

- `message_sent` — agent-to-agent messages
- `task_transition` — KanBan state changes
- `task_claimed` / `task_assigned` — task routing events
- `agent_registered` / `agent_unregistered` — registry changes
- `agent_paused` / `agent_resumed` / `agent_revoked` — human interventions
- `checkpoint_submitted` — agent drift-prevention signals
- `project_created` / `file_uploaded` — project events

### Views

- **KanBan Board** — drag-and-drop tasks across columns, click to transition/assign
- **Communications** — message flow graph + live event feed
- **Agent Control** — registry list, per-agent autonomy mode, pause/resume/revoke

---
>>>>>>> 8134f46 (feat: autonomous KanBan system, SSE dashboard, and human oversight)

## API Reference

### Agent Registry

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/register` | Register an agent (with capabilities + autonomy mode) |
| POST | `/agents/{name}/heartbeat` | Send heartbeat |
| DELETE | `/agents/{name}` | Unregister |
| GET | `/agents` | List all agents |
| POST | `/agents/{name}/autonomy` | Set agent's autonomy mode |
| POST | `/agents/{name}/capabilities` | Set agent's capability tags |
| POST | `/agents/{name}/pause` | Human: pause agent |
| POST | `/agents/{name}/resume` | Human: resume agent |
| POST | `/agents/{name}/revoke` | Human: revoke agent |
| GET | `/agents/{name}/revocation` | Agent: poll for revocation directive |
| POST | `/agents/{name}/revocation/ack` | Agent: acknowledge revocation |
| POST | `/agents/{name}/checkpoint` | Agent: submit checkpoint |
| GET | `/agents/{name}/checkpoint` | Get agent's latest checkpoint |

### Autonomy

| Method | Path | Description |
|--------|------|-------------|
| POST | `/autonomy/set-mode` | Set global default autonomy mode |
| GET | `/revocation/history` | View revocation history |

### Capabilities

| Method | Path | Description |
|--------|------|-------------|
| GET | `/capabilities` | List all capability profiles |
| GET | `/capabilities/match?tag=code` | Find agents with a capability tag |

### Messaging

| Method | Path | Description |
|--------|------|-------------|
| POST | `/messages/send` | Send a message |
| GET | `/messages/{agent}` | Get inbox |
| POST | `/messages/{id}/ack` | Acknowledge receipt |
| GET | `/messages/history/{a}/{b}` | Get conversation history |
| GET | `/messages/graph` | Message flow graph (nodes + edge counts) |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects` | Create a project |
| GET | `/projects` | List all projects |
| GET | `/projects/{id}` | Get project details |
| DELETE | `/projects/{id}` | Delete a project |
| POST | `/projects/{id}/join` | Agent joins a project |
| PATCH | `/projects/{id}/wip` | Update WIP limit for a column |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects/{id}/tasks` | Create a task |
| GET | `/projects/{id}/tasks` | List tasks (filter: status, agent, assigned_to) |
| GET | `/projects/{id}/tasks/ready` | Get ready queue (capability-filtered) |
| POST | `/projects/{id}/tasks/{tid}/claim` | Agent self-claims a task |
| POST | `/projects/{id}/tasks/{tid}/assign` | Human/coordinator assigns task |
| POST | `/projects/{id}/tasks/{tid}/unassign` | Move task back to backlog |
| PATCH | `/projects/{id}/tasks/{tid}` | Transition task (status, blocked, review) |
| POST | `/projects/{id}/tasks/{tid}/reviewers/{name}` | Add a reviewer |
| GET | `/projects/{id}/metrics` | KanBan metrics (cycle time, throughput) |

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events` | SSE event stream (all state changes) |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ping` | Health check |
| GET | `/audit/log` | View audit log |

---

## Running Tests

```bash
# Unit tests (no Docker needed)
python -m pytest tests/ --ignore=tests/test_agent_integration.py -v

# Full test suite (requires Hub running via docker-compose)
python -m pytest tests/ -v
```

---

## Project Structure

```
agent-sandbox-hub/
├── hub/                      # Central coordination server
│   ├── server.py             # Flask REST API + SSE
│   ├── agents.py             # Agent registry + autonomy state
│   ├── capabilities.py       # Capability registry + matching
│   ├── autonomy.py           # AutonomyMode, CheckpointSystem, RevocationQueue
│   ├── events.py             # SSE event emitter
│   ├── messages.py           # Store-and-forward messaging
│   ├── projects.py           # Project/KanBan/task management
│   ├── sandbox.py            # Sandbox enforcement (rate limit, URL block, audit)
│   └── requirements.txt
├── spokes/                   # Agent SDK
│   ├── client.py             # AgentClient Python SDK
│   └── requirements.txt
├── dashboard/                # React dashboard (SSE subscriber)
│   ├── src/
│   │   ├── App.jsx          # Main app
│   │   ├── components/
│   │   │   ├── AgentList.jsx    # Agent cards + control
│   │   │   ├── KanbanBoard.jsx  # Drag-and-drop KanBan
│   │   │   ├── LiveFeed.jsx    # Real-time event feed
│   │   │   └── MessageGraph.jsx # Agent communication graph
│   │   └── hooks/
│   │       └── useSSE.js        # SSE subscription hook
│   ├── package.json
│   └── vite.config.js
├── docker/
│   ├── docker-compose.yml   # Hub + dashboard + test agents
│   ├── hub.Dockerfile
│   ├── spoke.Dockerfile
│   └── test-isolation.sh
├── tests/                   # 76 tests
│   ├── test_hub.py
│   ├── test_messages.py
│   ├── test_projects.py
│   ├── test_sandbox_isolation.py
│   ├── test_capabilities.py   # NEW
│   ├── test_autonomy.py        # NEW
│   └── test_kanban.py          # NEW
├── sandbox/                 # Shared workspace (tmpfs)
├── README.md
└── LICENSE
```

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Add tests for your changes
4. Ensure all tests pass: `pytest tests/ --ignore=tests/test_agent_integration.py -v`
5. Commit with clear messages
6. Push and open a PR

## License

MIT
