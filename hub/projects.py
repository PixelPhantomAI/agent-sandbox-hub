"""
Project State Manager
Manages projects, files, and the full KanBan task system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import os
import threading
import uuid


class TaskStatus(Enum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"

    @classmethod
    def can_transition_from(cls, from_status: "TaskStatus", to_status: "TaskStatus") -> bool:
        """Define valid KanBan transitions."""
        valid = {
            cls.BACKLOG: {cls.READY, cls.BLOCKED},
            cls.READY: {cls.IN_PROGRESS, cls.BLOCKED, cls.BACKLOG},
            cls.IN_PROGRESS: {cls.IN_REVIEW, cls.BLOCKED, cls.READY},
            cls.IN_REVIEW: {cls.DONE, cls.IN_PROGRESS},
            cls.BLOCKED: {cls.READY, cls.BACKLOG},
            cls.DONE: {cls.BACKLOG},  # allow rework
        }
        return to_status in valid.get(from_status, set())


class TaskPriority(Enum):
    P0 = 0  # critical
    P1 = 1  # high
    P2 = 2  # medium
    P3 = 3  # low


# WIP limits per agent per KanBan column (None = unlimited)
DEFAULT_WIP_LIMITS = {
    str(TaskStatus.IN_PROGRESS): 3,
    str(TaskStatus.IN_REVIEW): 5,
}


@dataclass
class TaskTransition:
    from_status: str
    to_status: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    by_agent: str = ""
    note: str = ""


@dataclass
class Task:
    id: str
    project_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.P2
    assigned_to: Optional[str] = None
    claimed_by: Optional[str] = None  # agent that self-claimed
    required_capabilities: list = field(default_factory=list)
    blocked_reason: str = ""
    blocked_by: Optional[str] = None  # task ID that is blocking this one
    subtasks: list = field(default_factory=list)  # list of task IDs
    parent_task_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    transitions: list = field(default_factory=list)
    created_by: str = ""
    reviewers: list = field(default_factory=list)
    required_reviewers: int = 1

    # Cycle-time tracking
    started_at: Optional[datetime] = None
    review_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class Project:
    id: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    members: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    # KanBan config
    wip_limits: dict = field(default_factory=dict)  # {status: limit}
    default_wip: int = 3


class ProjectManager:
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/.")

    def __init__(self, storage_path: str = "/tmp/sandbox-projects"):
        self._projects: dict[str, Project] = {}
        self._tasks: dict[str, Task] = {}
        self._lock = threading.RLock()
        self._storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    # ── Path validation ────────────────────────────────────────────────

    def _validate_path(self, path: str) -> bool:
        normalized = os.path.normpath(path)
        if ".." in path or normalized.startswith(".."):
            return False
        for c in path:
            if c not in self.ALLOWED_CHARS and c != ".":
                return False
        return True

    def _compute_checksum(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    # ── Project CRUD ───────────────────────────────────────────────────

    def create_project(self, name: str, creator: str) -> Project:
        with self._lock:
            project_id = str(uuid.uuid4())
            project = Project(
                id=project_id,
                name=name,
                members=[creator],
                wip_limits=dict(DEFAULT_WIP_LIMITS),
            )
            self._projects[project_id] = project
            return project

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._lock:
            return self._projects.get(project_id)

    def list_projects(self, agent_name: str = None) -> list[Project]:
        with self._lock:
            if agent_name:
                return [p for p in self._projects.values() if agent_name in p.members]
            return list(self._projects.values())

    def join_project(self, project_id: str, agent_name: str) -> bool:
        with self._lock:
            if project_id not in self._projects:
                return False
            project = self._projects[project_id]
            if agent_name not in project.members:
                project.members.append(agent_name)
            return True

    def update_wip_limit(self, project_id: str, status: str, limit: int) -> bool:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return False
            project.wip_limits[status] = limit
            return True

    # ── File operations ────────────────────────────────────────────────

    def write_file(self, project_id: str, filename: str, content: bytes) -> dict:
        with self._lock:
            if project_id not in self._projects:
                raise ValueError("Project not found")
            if not self._validate_path(filename):
                raise ValueError("Invalid filename")
            if len(content) > self.MAX_FILE_SIZE:
                raise ValueError(f"File too large (max {self.MAX_FILE_SIZE} bytes)")
            checksum = self._compute_checksum(content)
            project = self._projects[project_id]
            project.files[filename] = {
                "checksum": checksum,
                "size": len(content),
                "updated_at": datetime.utcnow().isoformat()
            }
            file_path = os.path.join(self._storage_path, project_id, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(content)
            return {"checksum": checksum, "size": len(content)}

    def read_file(self, project_id: str, filename: str) -> bytes:
        with self._lock:
            if project_id not in self._projects:
                raise ValueError("Project not found")
            file_path = os.path.join(self._storage_path, project_id, filename)
            if not os.path.exists(file_path):
                raise ValueError("File not found")
            with open(file_path, "rb") as f:
                content = f.read()
            project = self._projects[project_id]
            file_info = project.files.get(filename)
            if file_info:
                expected = file_info["checksum"]
                actual = self._compute_checksum(content)
                if expected != actual:
                    raise ValueError("Checksum mismatch")
            return content

    # ── Task lifecycle ─────────────────────────────────────────────────

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str = "",
        assigned_to: str = None,
        priority: str = "P2",
        required_capabilities: list = None,
        required_reviewers: int = 1,
        created_by: str = "",
        parent_task_id: str = None,
    ) -> Task:
        with self._lock:
            if project_id not in self._projects:
                raise ValueError("Project not found")
            try:
                pri = TaskPriority[priority.upper()]
            except KeyError:
                pri = TaskPriority.P2
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project_id,
                title=title,
                description=description,
                assigned_to=assigned_to,
                priority=pri,
                required_capabilities=required_capabilities or [],
                required_reviewers=required_reviewers,
                created_by=created_by,
                parent_task_id=parent_task_id,
            )
            self._tasks[task.id] = task
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_tasks(
        self,
        project_id: str = None,
        agent_name: str = None,
        status: str = None,
        assigned_to: str = None,
        include_blocked: bool = True,
    ) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        filters = []
        if project_id:
            filters.append(lambda t: t.project_id == project_id)
        if agent_name:
            filters.append(lambda t: t.assigned_to == agent_name or t.claimed_by == agent_name)
        if status:
            filters.append(lambda t: t.status.value == status)
        if assigned_to:
            filters.append(lambda t: t.assigned_to == assigned_to)
        if not include_blocked:
            filters.append(lambda t: t.status != TaskStatus.BLOCKED)

        for f in filters:
            tasks = [t for t in tasks if f(t)]

        # Sort by priority then created_at
        tasks.sort(key=lambda t: (t.priority.value, t.created_at))
        return tasks

    def _wip_count(self, project_id: str, agent_name: str, status: TaskStatus) -> int:
        """Count how many tasks this agent has in a given status."""
        return sum(
            1 for t in self._tasks.values()
            if t.project_id == project_id
            and t.assigned_to == agent_name
            and t.status == status
        )

    def transition_task(
        self,
        project_id: str,
        task_id: str,
        new_status: str,
        agent_name: str = "",
        blocked_reason: str = "",
        blocked_by: str = None,
        note: str = "",
    ) -> dict:
        """
        Transition a task to a new status.
        Returns {"ok": True} or {"error": "reason"}.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.project_id != project_id:
                return {"error": "Task not found"}

            try:
                new = TaskStatus(new_status)
            except ValueError:
                return {"error": f"Invalid status: {new_status}"}

            if not TaskStatus.can_transition_from(task.status, new):
                return {"error": f"Invalid transition: {task.status.value} → {new_status}"}

            # WIP limit check when entering IN_PROGRESS
            project = self._projects.get(project_id)
            if new == TaskStatus.IN_PROGRESS and task.assigned_to and project:
                limit = project.wip_limits.get(str(TaskStatus.IN_PROGRESS), self._DEFAULT_WIP)
                count = self._wip_count(project_id, task.assigned_to, TaskStatus.IN_PROGRESS)
                if count >= limit:
                    return {"error": f"WIP limit reached for {task.assigned_to} in in_progress (limit: {limit})"}

            # Record transition
            task.transitions.append(TaskTransition(
                from_status=task.status.value,
                to_status=new_status,
                by_agent=agent_name,
                note=note,
            ))

            old_status = task.status
            task.status = new
            task.updated_at = datetime.utcnow()

            # Track cycle-time timestamps
            now = datetime.utcnow()
            if new == TaskStatus.IN_PROGRESS and not task.started_at:
                task.started_at = now
            elif new == TaskStatus.IN_REVIEW and not task.review_started_at:
                task.review_started_at = now
            elif new == TaskStatus.DONE:
                task.completed_at = now

            if blocked_reason:
                task.blocked_reason = blocked_reason
            if blocked_by:
                task.blocked_by = blocked_by

            return {"ok": True, "from": old_status.value, "to": new.value}

    _DEFAULT_WIP = 3

    def claim_task(
        self,
        project_id: str,
        task_id: str,
        agent_name: str,
        agent_capabilities: list[str] = None,
    ) -> dict:
        """
        Agent self-claims a task from the ready queue.
        Validates: capabilities match, WIP not exceeded, task is in READY or BACKLOG.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.project_id != project_id:
                return {"error": "Task not found"}

            if task.status not in (TaskStatus.BACKLOG, TaskStatus.READY):
                return {"error": f"Cannot claim task in {task.status.value} status"}

            # Capability check
            if task.required_capabilities and agent_capabilities:
                required = set(c.lower() for c in task.required_capabilities)
                available = set(c.lower() for c in agent_capabilities)
                if not required.issubset(available):
                    return {"error": f"Capabilities insufficient. Required: {required}, have: {available}"}

            # WIP limit
            project = self._projects.get(project_id)
            if project:
                limit = project.wip_limits.get(str(TaskStatus.IN_PROGRESS), self._DEFAULT_WIP)
                count = self._wip_count(project_id, agent_name, TaskStatus.IN_PROGRESS)
                if count >= limit:
                    return {"error": f"WIP limit reached for {agent_name} (limit: {limit})"}

            task.assigned_to = agent_name
            task.claimed_by = agent_name
            task.status = TaskStatus.READY
            task.updated_at = datetime.utcnow()
            return {"ok": True, "task_id": task_id}

    def assign_task(
        self,
        project_id: str,
        task_id: str,
        agent_name: str,
        assigned_by: str = "",
    ) -> dict:
        """Human (or coordinator) directly assigns a task to an agent."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.project_id != project_id:
                return {"error": "Task not found"}

            # WIP limit check
            project = self._projects.get(project_id)
            if project:
                limit = project.wip_limits.get(str(TaskStatus.IN_PROGRESS), self._DEFAULT_WIP)
                count = self._wip_count(project_id, agent_name, TaskStatus.IN_PROGRESS)
                if count >= limit:
                    return {"error": f"WIP limit reached for {agent_name} (limit: {limit})"}

            task.assigned_to = agent_name
            task.status = TaskStatus.READY
            task.updated_at = datetime.utcnow()
            return {"ok": True}

    def unassign_task(self, project_id: str, task_id: str) -> dict:
        """Move a task back to backlog and clear assignment."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.project_id != project_id:
                return {"error": "Task not found"}
            task.assigned_to = None
            task.claimed_by = None
            task.status = TaskStatus.BACKLOG
            task.updated_at = datetime.utcnow()
            return {"ok": True}

    def add_reviewer(self, project_id: str, task_id: str, reviewer: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.project_id != project_id:
                return False
            if reviewer not in task.reviewers:
                task.reviewers.append(reviewer)
            return True

    def get_ready_queue(self, project_id: str, agent_name: str = None, agent_capabilities: list = None) -> list[Task]:
        """
        Get tasks in BACKLOG or READY that an agent can claim.
        Filtered by capability match if agent_name provided.
        Sorted by priority.
        """
        with self._lock:
            tasks = [
                t for t in self._tasks.values()
                if t.project_id == project_id
                and t.status in (TaskStatus.BACKLOG, TaskStatus.READY)
            ]
        # Filter by capability
        if agent_name and agent_capabilities:
            available = set(c.lower() for c in agent_capabilities)
            tasks = [
                t for t in tasks
                if not t.required_capabilities
                or set(c.lower() for c in t.required_capabilities).issubset(available)
            ]
        tasks.sort(key=lambda t: (t.priority.value, t.created_at))
        return tasks

    # ── Legacy backward-compatible update_task ─────────────────────────

    def update_task(self, project_id: str, task_id: str, status: str) -> bool:
        """
        Legacy backward-compatible update_task.
        Calls transition_task and returns True on success, False on failure.
        """
        result = self.transition_task(project_id, task_id, status)
        return result.get("ok", False)

    # ── Metrics ─────────────────────────────────────────────────────────

    def get_project_metrics(self, project_id: str) -> dict:
        """Calculate KanBan metrics for a project."""
        with self._lock:
            tasks = [t for t in self._tasks.values() if t.project_id == project_id]

        total = len(tasks)
        by_status = {}
        for s in TaskStatus:
            by_status[s.value] = sum(1 for t in tasks if t.status == s)

        # Cycle times
        cycle_times = []
        for t in tasks:
            if t.started_at and t.completed_at:
                delta = (t.completed_at - t.started_at).total_seconds() / 60
                cycle_times.append(delta)

        avg_cycle = sum(cycle_times) / len(cycle_times) if cycle_times else 0

        # Per-agent throughput (done tasks)
        agent_throughput = {}
        for t in tasks:
            if t.status == TaskStatus.DONE and t.assigned_to:
                agent_throughput[t.assigned_to] = agent_throughput.get(t.assigned_to, 0) + 1

        return {
            "total_tasks": total,
            "by_status": by_status,
            "avg_cycle_time_minutes": round(avg_cycle, 1),
            "completed_count": len(cycle_times),
            "agent_throughput": agent_throughput,
        }
