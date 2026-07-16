"""
Autonomy System
Implements autonomy modes, checkpointing, and revocation for safe agent operation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import threading
import uuid


class AutonomyMode(Enum):
    """
    fully_autonomous  — agents self-assign, self-progress, no human approval needed
    advisory         — agents propose actions; human must approve before execution
    manual           — humans assign all tasks; agents only execute what's assigned
    """
    FULLY_AUTONOMOUS = "fully_autonomous"
    ADVISORY = "advisory"
    MANUAL = "manual"


@dataclass
class Checkpoint:
    id: str
    agent_name: str
    task_id: Optional[str]
    state: str  # what the agent is doing
    rationale: str  # why it's doing it
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sequence: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class Revocation:
    id: str
    agent_name: str
    issued_at: datetime = field(default_factory=datetime.utcnow)
    reason: str = ""
    acknowledged: bool = False
    flush_required: bool = True


class CheckpointSystem:
    """
    Tracks agent checkpoints to detect drift and stalled agents.

    Agents must emit a checkpoint every N heartbeat cycles.
    If an agent misses N consecutive checkpoint windows, it's marked stalled.
    """

    MAX_MISSED_CHECKPOINTS = 3
    HEARTBEATS_PER_CYCLE = 6  # e.g. 6 × 10s heartbeat = 1 checkpoint/min

    def __init__(self):
        self._checkpoints: dict[str, Checkpoint] = {}
        self._sequences: dict[str, int] = {}
        self._heartbeat_counts: dict[str, int] = {}
        self._missed: dict[str, int] = {}
        self._stalled: dict[str, bool] = {}
        self._lock = threading.RLock()

    def tick(self, agent_name: str) -> int:
        """
        Called on each heartbeat. Returns current heartbeat count within cycle.
        When count reaches HEARTBEATS_PER_CYCLE, caller should request a checkpoint.
        """
        with self._lock:
            count = self._heartbeat_counts.get(agent_name, 0) + 1
            self._heartbeat_counts[agent_name] = count
            return count

    def submit(self, agent_name: str, task_id: str, state: str, rationale: str, metadata: dict = None) -> Checkpoint:
        """
        Agent submits a checkpoint. Resets missed count, advances sequence.
        """
        with self._lock:
            self._heartbeat_counts[agent_name] = 0
            self._missed[agent_name] = 0
            self._stalled[agent_name] = False

            seq = self._sequences.get(agent_name, 0) + 1
            self._sequences[agent_name] = seq

            checkpoint = Checkpoint(
                id=str(uuid.uuid4()),
                agent_name=agent_name,
                task_id=task_id or None,
                state=state,
                rationale=rationale,
                sequence=seq,
                metadata=metadata or {}
            )
            self._checkpoints[agent_name] = checkpoint
            return checkpoint

    def is_stalled(self, agent_name: str) -> bool:
        """Returns True if agent has missed too many checkpoint windows."""
        with self._lock:
            return self._stalled.get(agent_name, False)

    def mark_stalled(self, agent_name: str):
        """Mark an agent as stalled (called when missed checkpoints exceed threshold)."""
        with self._lock:
            self._stalled[agent_name] = True

    def get_checkpoint(self, agent_name: str) -> Optional[Checkpoint]:
        """Get latest checkpoint for an agent."""
        with self._lock:
            return self._checkpoints.get(agent_name)

    def get_stalled_agents(self) -> list[str]:
        """List all stalled agents."""
        with self._lock:
            return [name for name, s in self._stalled.items() if s]

    def should_request_checkpoint(self, agent_name: str) -> bool:
        """Returns True when the agent's heartbeat count has reached the cycle threshold."""
        with self._lock:
            return self._heartbeat_counts.get(agent_name, 0) >= self.HEARTBEATS_PER_CYCLE

    def clear(self, agent_name: str):
        """Clear all checkpoint state for an agent."""
        with self._lock:
            self._checkpoints.pop(agent_name, None)
            self._sequences.pop(agent_name, None)
            self._heartbeat_counts.pop(agent_name, None)
            self._missed.pop(agent_name, None)
            self._stalled.pop(agent_name, None)


class RevocationQueue:
    """
    Issues revocation directives to agents.
    When an agent is revoked it must: halt, flush pending work, re-register.
    """

    def __init__(self):
        self._pending: dict[str, Revocation] = {}
        self._history: list[Revocation] = []
        self._lock = threading.RLock()

    def issue(self, agent_name: str, reason: str = "", flush_required: bool = True) -> Revocation:
        """Issue a revocation for an agent."""
        with self._lock:
            rev = Revocation(
                id=str(uuid.uuid4()),
                agent_name=agent_name,
                reason=reason,
                flush_required=flush_required
            )
            self._pending[agent_name] = rev
            return rev

    def get_pending(self, agent_name: str) -> Optional[Revocation]:
        """Get pending revocation for an agent (clears it)."""
        with self._lock:
            return self._pending.pop(agent_name, None)

    def has_pending(self, agent_name: str) -> bool:
        """Check if agent has a pending revocation."""
        with self._lock:
            return agent_name in self._pending

    def history(self, limit: int = 50) -> list[dict]:
        """Get revocation history."""
        with self._lock:
            hist = self._history[-limit:]
            return [
                {"id": r.id, "agent": r.agent_name, "reason": r.reason,
                 "issued_at": r.issued_at.isoformat(), "acknowledged": r.acknowledged}
                for r in hist
            ]

    def acknowledge(self, revocation_id: str):
        """Mark a revocation as acknowledged."""
        with self._lock:
            for rev in self._pending.values():
                if rev.id == revocation_id:
                    rev.acknowledged = True
                    self._history.append(rev)
                    self._pending.pop(rev.agent_name, None)
                    break
