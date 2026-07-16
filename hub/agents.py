import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Agent:
    name: str
    agent_type: str  # e.g., "claude", "openclaw", "hermes"
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    status: str = "online"  # online, busy, offline
    metadata: dict = field(default_factory=dict)


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
            }
            for a in agents
        ]

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
