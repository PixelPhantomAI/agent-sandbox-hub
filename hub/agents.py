import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

from hub.autonomy import AutonomyMode


@dataclass
class Agent:
    name: str
    agent_type: str  # e.g., "claude", "openclaw", "hermes"
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    status: str = "online"  # online, busy, offline, stalled, revoked
    metadata: dict = field(default_factory=dict)
    # Autonomy
    autonomy_mode: AutonomyMode = AutonomyMode.FULLY_AUTONOMOUS
    # Capabilities
    capability_tags: List[str] = field(default_factory=list)
    # Checkpoint tracking
    current_task_id: Optional[str] = None
    current_task_state: str = ""
    checkpoint_sequence: int = 0


class AgentRegistry:
    def __init__(self, heartbeat_timeout: int = 30):
        self._agents: Dict[str, Agent] = {}
        self._lock = threading.Lock()
        self._heartbeat_timeout = heartbeat_timeout

    def register(self, name: str, agent_type: str, metadata: dict = None) -> Agent:
        with self._lock:
            agent = Agent(name=name, agent_type=agent_type, metadata=metadata or {})
            self._agents[name] = agent
        return agent

    def heartbeat(self, name: str) -> bool:
        with self._lock:
            if name in self._agents:
                self._agents[name].last_heartbeat = datetime.utcnow()
                self._agents[name].status = "online"
                return True
        return False

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name in self._agents:
                del self._agents[name]
                return True
        return False

    def get_agent(self, name: str) -> Optional[Agent]:
        return self._agents.get(name)

    def list_agents(self, status: str = None) -> List[dict]:
        with self._lock:
            agents = list(self._agents.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return [
            {
                "name": a.name,
                "type": a.agent_type,
                "status": a.status,
                "registered_at": a.registered_at.isoformat(),
                "last_heartbeat": a.last_heartbeat.isoformat(),
                "autonomy_mode": a.autonomy_mode.value,
                "capabilities": a.capability_tags,
                "current_task_id": a.current_task_id,
                "checkpoint_sequence": a.checkpoint_sequence,
            }
            for a in agents
        ]

    def set_autonomy_mode(self, name: str, mode: AutonomyMode) -> bool:
        """Set autonomy mode for an agent."""
        with self._lock:
            if name not in self._agents:
                return False
            self._agents[name].autonomy_mode = mode
            return True

    def set_capabilities(self, name: str, tags: List[str]) -> bool:
        """Update capability tags for an agent."""
        with self._lock:
            if name not in self._agents:
                return False
            self._agents[name].capability_tags = tags
            return True

    def set_current_task(self, name: str, task_id: str, state: str = "") -> bool:
        """Update the task an agent is currently working on."""
        with self._lock:
            if name not in self._agents:
                return False
            self._agents[name].current_task_id = task_id
            self._agents[name].current_task_state = state
            return True

    def set_status(self, name: str, status: str) -> bool:
        """Set agent status (online, busy, stalled, revoked, offline)."""
        with self._lock:
            if name not in self._agents:
                return False
            self._agents[name].status = status
            return True

    def advance_checkpoint_sequence(self, name: str) -> int:
        """Increment and return the checkpoint sequence number."""
        with self._lock:
            if name not in self._agents:
                return 0
            self._agents[name].checkpoint_sequence += 1
            return self._agents[name].checkpoint_sequence

    def cleanup_stale(self) -> List[str]:
        """Remove agents that have missed heartbeats."""
        now = datetime.utcnow()
        with self._lock:
            stale = [
                name
                for name, a in self._agents.items()
                if (now - a.last_heartbeat).total_seconds() > self._heartbeat_timeout
            ]
            for name in stale:
                del self._agents[name]
        return stale
