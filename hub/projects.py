"""
Project State Manager
Manages projects, file storage, and tasks with security protections.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import os
import threading
import uuid


@dataclass
class Project:
    id: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    members: list = field(default_factory=list)
    files: dict = field(default_factory=dict)


@dataclass
class Task:
    id: str
    project_id: str
    title: str
    description: str
    status: str = "pending"
    assigned_to: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class ProjectManager:
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/.")

    def __init__(self, storage_path: str = "/tmp/sandbox-projects"):
        self._projects: dict[str, Project] = {}
        self._tasks: dict[str, Task] = {}
        self._lock = threading.RLock()
        self._storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _validate_path(self, path: str) -> bool:
        """Prevent path traversal attacks."""
        normalized = os.path.normpath(path)
        if ".." in path or normalized.startswith(".."):
            return False
        for c in path:
            if c not in self.ALLOWED_CHARS and c != ".":
                return False
        return True

    def _compute_checksum(self, data: bytes) -> str:
        """Compute SHA256 checksum of file data."""
        return hashlib.sha256(data).hexdigest()

    def create_project(self, name: str, creator: str) -> Project:
        """Create a new project."""
        with self._lock:
            project_id = str(uuid.uuid4())
            project = Project(id=project_id, name=name, members=[creator])
            self._projects[project_id] = project
            return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        with self._lock:
            return self._projects.get(project_id)

    def list_projects(self, agent_name: str = None) -> list[Project]:
        """List projects, optionally filtered by agent membership."""
        with self._lock:
            if agent_name:
                return [p for p in self._projects.values() if agent_name in p.members]
            return list(self._projects.values())

    def join_project(self, project_id: str, agent_name: str) -> bool:
        """Add an agent to a project."""
        with self._lock:
            if project_id not in self._projects:
                return False
            project = self._projects[project_id]
            if agent_name not in project.members:
                project.members.append(agent_name)
            return True

    def write_file(self, project_id: str, filename: str, content: bytes) -> dict:
        """Write a file to a project with size limit and checksum."""
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
        """Read a file from a project with checksum verification."""
        with self._lock:
            if project_id not in self._projects:
                raise ValueError("Project not found")
            file_path = os.path.join(self._storage_path, project_id, filename)
            if not os.path.exists(file_path):
                raise ValueError("File not found")
            with open(file_path, "rb") as f:
                content = f.read()
            if project_id in self._projects:
                file_info = self._projects[project_id].files.get(filename)
                if file_info:
                    expected = file_info["checksum"]
                    actual = self._compute_checksum(content)
                    if expected != actual:
                        raise ValueError("Checksum mismatch")
            return content

    def create_task(self, project_id: str, title: str, description: str, assigned_to: str = None) -> Task:
        """Create a task in a project."""
        with self._lock:
            if project_id not in self._projects:
                raise ValueError("Project not found")
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project_id,
                title=title,
                description=description,
                assigned_to=assigned_to
            )
            self._tasks[task.id] = task
            return task

    def update_task(self, project_id: str, task_id: str, status: str) -> bool:
        """Update task status."""
        with self._lock:
            if task_id not in self._tasks:
                return False
            task = self._tasks[task_id]
            if task.project_id != project_id:
                return False
            task.status = status
            return True

    def get_tasks(self, project_id: str) -> list[Task]:
        """Get all tasks for a project."""
        with self._lock:
            return [t for t in self._tasks.values() if t.project_id == project_id]
