"""
Tests for the KanBan task system (state machine, WIP limits, claiming).
"""

import pytest
from hub.projects import ProjectManager, TaskStatus, TaskPriority


@pytest.fixture
def pm():
    return ProjectManager(storage_path="/tmp/test-sandbox-projects")


@pytest.fixture
def proj(pm):
    return pm.create_project("Test Sprint", "creator")


class TestTaskStateMachine:
    def test_valid_transitions(self, pm, proj):
        task = pm.create_task(proj.id, "Write tests", created_by="test")
        assert task.status == TaskStatus.BACKLOG

        # backlog → ready
        r = pm.transition_task(proj.id, task.id, "ready", agent_name="test")
        assert r["ok"] is True
        assert pm.get_task(task.id).status == TaskStatus.READY

        # ready → in_progress
        task.assigned_to = "tester"
        pm._tasks[task.id] = task
        r = pm.transition_task(proj.id, task.id, "in_progress", agent_name="tester")
        assert r["ok"] is True

        # in_progress → in_review
        r = pm.transition_task(proj.id, task.id, "in_review")
        assert r["ok"] is True

        # in_review → done
        r = pm.transition_task(proj.id, task.id, "done")
        assert r["ok"] is True
        assert pm.get_task(task.id).completed_at is not None

    def test_invalid_transition_backlog_to_done(self, pm, proj):
        task = pm.create_task(proj.id, "Test", created_by="test")
        r = pm.transition_task(proj.id, task.id, "done")
        assert "error" in r

    def test_blocked_transition(self, pm, proj):
        task = pm.create_task(proj.id, "Blocked task", created_by="test")
        r = pm.transition_task(proj.id, task.id, "blocked", blocked_reason="waiting on T1")
        assert r["ok"] is True
        assert pm.get_task(task.id).blocked_reason == "waiting on T1"


class TestWipLimits:
    def test_wip_limit_respected(self, pm, proj):
        """Cannot transition to in_progress if agent already at WIP limit."""
        # Create 3 tasks: backlog→ready→in_progress (proper transitions)
        created_ids = []
        for i in range(3):
            t = pm.create_task(proj.id, f"Task {i}", assigned_to="tester", created_by="test")
            created_ids.append(t.id)
            pm.transition_task(proj.id, t.id, "ready", agent_name="tester")
            r = pm.transition_task(proj.id, t.id, "in_progress", agent_name="tester")
            assert r["ok"] is True, f"setup transition failed: {r}"

        # WIP limit for in_progress is 3 by default
        # 4th task should be rejected
        new_task = pm.create_task(proj.id, "Task 4", assigned_to="tester", created_by="test")
        r = pm.transition_task(proj.id, new_task.id, "ready", agent_name="tester")
        assert r["ok"] is True
        r2 = pm.transition_task(proj.id, new_task.id, "in_progress", agent_name="tester")
        assert "error" in r2, f"Expected WIP error, got: {r2}"
        assert "WIP limit" in r2["error"]

    def test_wip_limit_customizable(self, pm, proj):
        pm.update_wip_limit(proj.id, "in_progress", 5)
        proj = pm.get_project(proj.id)
        assert proj.wip_limits["in_progress"] == 5


class TestTaskClaiming:
    def test_claim_requires_capabilities(self, pm, proj):
        task = pm.create_task(
            proj.id, "Requires review",
            required_capabilities=["review"],
            created_by="test"
        )
        # Agent without review cap
        r = pm.claim_task(proj.id, task.id, "junior", agent_capabilities=["code"])
        assert "error" in r
        assert "Capabilities insufficient" in r["error"]

    def test_claim_with_sufficient_capabilities(self, pm, proj):
        task = pm.create_task(
            proj.id, "Write code",
            required_capabilities=["code"],
            created_by="test"
        )
        r = pm.claim_task(proj.id, task.id, "senior", agent_capabilities=["code", "review"])
        assert r["ok"] is True
        assert pm.get_task(task.id).assigned_to == "senior"
        assert pm.get_task(task.id).claimed_by == "senior"

    def test_claim_only_from_backlog_or_ready(self, pm, proj):
        task = pm.create_task(proj.id, "In progress task", created_by="test")
        task.status = TaskStatus.IN_PROGRESS
        pm._tasks[task.id] = task

        r = pm.claim_task(proj.id, task.id, "agent", agent_capabilities=[])
        assert "error" in r
        assert "Cannot claim" in r["error"]


class TestCycleTimeTracking:
    def test_started_at_set_on_in_progress(self, pm, proj):
        task = pm.create_task(proj.id, "Track me", assigned_to="dev", created_by="test")
        assert task.started_at is None
        # Must go through ready first
        pm.transition_task(proj.id, task.id, "ready", agent_name="dev")
        pm.transition_task(proj.id, task.id, "in_progress", agent_name="dev")
        updated = pm.get_task(task.id)
        assert updated.started_at is not None

    def test_completed_at_set_on_done(self, pm, proj):
        task = pm.create_task(proj.id, "Track me", assigned_to="dev", created_by="test")
        pm.transition_task(proj.id, task.id, "ready", agent_name="dev")
        pm.transition_task(proj.id, task.id, "in_progress", agent_name="dev")
        pm.transition_task(proj.id, task.id, "in_review", agent_name="dev")
        pm.transition_task(proj.id, task.id, "done", agent_name="dev")

        updated = pm.get_task(task.id)
        assert updated.completed_at is not None
        assert updated.started_at is not None


class TestPriorityAndReadyQueue:
    def test_higher_priority_first(self, pm, proj):
        pm.create_task(proj.id, "Low", priority="P3", created_by="test")
        pm.create_task(proj.id, "Critical", priority="P0", created_by="test")
        pm.create_task(proj.id, "Medium", priority="P2", created_by="test")

        queue = pm.get_ready_queue(proj.id)
        assert queue[0].priority == TaskPriority.P0
        assert queue[1].priority == TaskPriority.P2
        assert queue[2].priority == TaskPriority.P3

    def test_capability_filter(self, pm, proj):
        t1 = pm.create_task(proj.id, "Needs code", required_capabilities=["code"], created_by="test")
        t2 = pm.create_task(proj.id, "Needs review", required_capabilities=["review"], created_by="test")
        t3 = pm.create_task(proj.id, "No reqs", created_by="test")

        # Filter by agent with code only
        queue = pm.get_ready_queue(proj.id, agent_name="dev", agent_capabilities=["code"])
        ids = [t.id for t in queue]
        assert t1.id in ids
        assert t3.id in ids
        assert t2.id not in ids  # review cap required


class TestProjectMetrics:
    def test_metrics(self, pm, proj):
        pm.create_task(proj.id, "T1", created_by="test")
        pm.create_task(proj.id, "T2", created_by="test")
        pm.create_task(proj.id, "T3", created_by="test")

        metrics = pm.get_project_metrics(proj.id)
        assert metrics["total_tasks"] == 3
        assert metrics["by_status"]["backlog"] == 3
