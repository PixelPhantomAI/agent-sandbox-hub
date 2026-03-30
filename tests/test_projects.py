"""
Project Manager Tests
"""

import os
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from hub.projects import ProjectManager, Task

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB, must match ProjectManager.MAX_FILE_SIZE


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def pm(temp_storage):
    return ProjectManager(storage_path=temp_storage)


def test_create_project(pm):
    project = pm.create_project("Test Project", "claude")
    assert project.name == "Test Project"
    assert "claude" in project.members
    assert project.id is not None


def test_get_project(pm):
    project = pm.create_project("Test", "claude")
    found = pm.get_project(project.id)
    assert found is not None
    assert found.name == "Test"


def test_get_project_not_found(pm):
    assert pm.get_project("nonexistent") is None


def test_list_projects(pm):
    pm.create_project("P1", "alice")
    pm.create_project("P2", "bob")
    projects = pm.list_projects()
    assert len(projects) == 2


def test_join_project(pm):
    project = pm.create_project("Test", "claude")
    assert pm.join_project(project.id, "alice") is True
    assert "alice" in project.members


def test_join_project_not_found(pm):
    assert pm.join_project("nonexistent", "alice") is False


def test_write_and_read_file(pm, temp_storage):
    project = pm.create_project("Test", "claude")
    content = b"Hello, world!"
    result = pm.write_file(project.id, "hello.txt", content)
    assert result["checksum"] is not None
    assert result["size"] == len(content)

    read_content = pm.read_file(project.id, "hello.txt")
    assert read_content == content


def test_write_file_invalid_path(pm):
    project = pm.create_project("Test", "claude")
    with pytest.raises(ValueError, match="Invalid filename"):
        pm.write_file(project.id, "../etc/passwd", b"hack")


def test_write_file_too_large(pm):
    project = pm.create_project("Test", "claude")
    large_content = b"x" * (MAX_FILE_SIZE + 1)
    with pytest.raises(ValueError, match="too large"):
        pm.write_file(project.id, "large.bin", large_content)


def test_read_file_not_found(pm):
    project = pm.create_project("Test", "claude")
    with pytest.raises(ValueError, match="not found"):
        pm.read_file(project.id, "nonexistent.txt")


def test_create_and_update_task(pm):
    project = pm.create_project("Test", "claude")
    task = pm.create_task(project.id, "Write tests", "Cover all cases", assigned_to="hermes")
    assert task is not None
    assert task.title == "Write tests"
    assert task.assigned_to == "hermes"
    assert task.status == "pending"

    ok = pm.update_task(project.id, task.id, "in_progress")
    assert ok is True
    assert pm.get_tasks(project.id)[0].status == "in_progress"


def test_create_task_project_not_found(pm):
    with pytest.raises(ValueError, match="not found"):
        pm.create_task("nonexistent", "title", "desc")


def test_update_task_not_found(pm):
    project = pm.create_project("Test", "claude")
    assert pm.update_task(project.id, "nonexistent", "done") is False


def test_get_tasks(pm):
    project = pm.create_project("Test", "claude")
    pm.create_task(project.id, "Task 1", "desc1")
    pm.create_task(project.id, "Task 2", "desc2", assigned_to="alice")
    tasks = pm.get_tasks(project.id)
    assert len(tasks) == 2


def test_task_assignment(pm):
    project = pm.create_project("Test", "claude")
    task = pm.create_task(project.id, "Review PR", "Check code quality", assigned_to="hermes")
    assert task.assigned_to == "hermes"
    assert task.status == "pending"
