"""
Tests for autonomy system (modes, checkpoints, revocation).
"""

import pytest
from hub.autonomy import AutonomyMode, CheckpointSystem, RevocationQueue


@pytest.fixture
def cps():
    return CheckpointSystem()


@pytest.fixture
def revq():
    return RevocationQueue()


class TestCheckpointSystem:
    def test_submit_checkpoint(self, cps):
        cp = cps.submit("claude", "task-1", "writing code", "implementing feature X")
        assert cp.agent_name == "claude"
        assert cp.task_id == "task-1"
        assert cp.state == "writing code"
        assert cp.rationale == "implementing feature X"
        assert cp.sequence == 1

    def test_submit_increments_sequence(self, cps):
        cps.submit("claude", "task-1", "step 1", "reason")
        cp2 = cps.submit("claude", "task-1", "step 2", "reason")
        assert cp2.sequence == 2

    def test_tick_accumulates(self, cps):
        for _ in range(5):
            cps.tick("claude")
        assert cps._heartbeat_counts.get("claude", 0) == 5

    def test_should_request_checkpoint(self, cps):
        # Default: 6 heartbeats per cycle
        for _ in range(5):
            cps.tick("claude")
        assert cps.should_request_checkpoint("claude") is False
        cps.tick("claude")  # 6th heartbeat
        assert cps.should_request_checkpoint("claude") is True

    def test_checkpoint_resets_tick_count(self, cps):
        for _ in range(6):
            cps.tick("claude")
        cps.submit("claude", "task-1", "done", "reason")
        assert cps._heartbeat_counts["claude"] == 0
        assert cps.should_request_checkpoint("claude") is False

    def test_stalled_after_missed_cycles(self, cps):
        cps._missed["claude"] = 2  # simulate 2 missed
        cps.mark_stalled("claude")
        assert cps.is_stalled("claude") is True

    def test_clear(self, cps):
        cps.submit("claude", "task-1", "done", "reason")
        cps.tick("claude")
        cps.clear("claude")
        assert cps.get_checkpoint("claude") is None
        assert cps._heartbeat_counts.get("claude", 0) == 0

    def test_get_stalled_agents(self, cps):
        cps.mark_stalled("claude")
        cps.mark_stalled("hermes")
        assert set(cps.get_stalled_agents()) == {"claude", "hermes"}


class TestRevocationQueue:
    def test_issue_revocation(self, revq):
        rev = revq.issue("claude", reason="policy violation", flush_required=True)
        assert rev.agent_name == "claude"
        assert rev.reason == "policy violation"
        assert rev.flush_required is True

    def test_get_pending(self, revq):
        revq.issue("claude", reason="test")
        pending = revq.get_pending("claude")
        assert pending is not None
        assert pending.agent_name == "claude"
        # Second call should be None
        assert revq.get_pending("claude") is None

    def test_has_pending(self, revq):
        revq.issue("claude", reason="test")
        assert revq.has_pending("claude") is True
        revq.get_pending("claude")
        assert revq.has_pending("claude") is False

    def test_acknowledge(self, revq):
        rev = revq.issue("claude", reason="test")
        revq.acknowledge(rev.id)
        hist = revq.history()
        assert any(h["agent"] == "claude" for h in hist)


class TestAutonomyMode:
    def test_mode_values(self):
        assert AutonomyMode.FULLY_AUTONOMOUS.value == "fully_autonomous"
        assert AutonomyMode.ADVISORY.value == "advisory"
        assert AutonomyMode.MANUAL.value == "manual"

