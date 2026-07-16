"""
Agent Capability Registry
Tracks agent capabilities/tags and matches them against task requirements.
"""

from dataclasses import dataclass, field
from typing import Optional
import threading


@dataclass
class CapabilityProfile:
    tags: set[str] = field(default_factory=set)
    description: str = ""
    max_concurrent_tasks: int = 3


class CapabilityRegistry:
    """
    Registry mapping agent names to their capability profiles.
    Capabilities are free-form tags. Tasks declare required capabilities;
    agents can only claim tasks where their capabilities superset the requirements.
    """

    # Built-in capability tags
    BUILTIN_TAGS = {
        "code", "review", "research", "coordinator",
        "executor", "data", "planning", "testing", "debugging",
        "writing", "analysis", "deployment"
    }

    def __init__(self):
        self._profiles: dict[str, CapabilityProfile] = {}
        self._lock = threading.RLock()

    def register(self, agent_name: str, tags: list[str] = None, description: str = "") -> CapabilityProfile:
        """Register (or update) a capability profile for an agent."""
        with self._lock:
            resolved_tags = set(t.lower().strip() for t in (tags or []))
            self._profiles[agent_name] = CapabilityProfile(
                tags=resolved_tags,
                description=description
            )
            return self._profiles[agent_name]

    def get(self, agent_name: str) -> Optional[CapabilityProfile]:
        """Get capability profile for an agent."""
        with self._lock:
            return self._profiles.get(agent_name)

    def list_all(self) -> list[dict]:
        """List all registered profiles."""
        with self._lock:
            return [
                {"agent": name, "tags": list(p.tags), "description": p.description}
                for name, p in self._profiles.items()
            ]

    def agents_with_capability(self, required_tag: str) -> list[str]:
        """Find all agents that have a given capability tag."""
        with self._lock:
            tag = required_tag.lower()
            return [
                name for name, p in self._profiles.items()
                if tag in p.tags
            ]

    def can_claim(self, agent_name: str, required_tags: list[str]) -> bool:
        """
        Check if an agent's capabilities satisfy a task's required tags.
        Empty required_tags means any agent can claim it.
        """
        with self._lock:
            profile = self._profiles.get(agent_name)
            if not profile:
                return False
            if not required_tags:
                return True
            required = set(t.lower() for t in required_tags)
            return required.issubset(profile.tags)

    def unregister(self, agent_name: str):
        """Remove capability profile when agent unregisters."""
        with self._lock:
            self._profiles.pop(agent_name, None)
