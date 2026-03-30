import os
import tempfile
import pytest
from hub.projects import ProjectManager, SANDBOX_BASE, MAX_FILE_SIZE


@pytest.fixture
def temp_sandbox():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def pm(temp_sandbox):
    return ProjectManager(sandbox_base=temp_sandbox)


def test_create_project(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test Project", "claude")
    assert project.name == "Test Project"
    assert project.created_by == "claude"
    assert project.status == "active"
    assert len(project.id) == 8


def test_get_project(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    found = pm.get_project(project.id)
    assert found is not None
    assert found.name == "Test"


def test_get_project_not_found(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    assert pm.get_project("nonexistent") is None


def test_list_projects(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    pm.create_project("P1", "alice")
    pm.create_project("P2", "bob")
    projects = pm.list_projects()
    assert len(projects) == 2


def test_join_project(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    assert pm.join_project(project.id, "alice") is True
    assert "alice" in project.agents


def test_join_project_not_found(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    assert pm.join_project("nonexistent", "alice") is False


def test_write_and_read_file(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    content = b"Hello, world!"
    entry = pm.write_file(project.id, "hello.txt", content, "claude")
    assert entry.name == "hello.txt"
    assert entry.size == len(content)
    assert entry.modified_by == "claude"
    assert entry.checksum is not None

    read_content = pm.read_file(project.id, "hello.txt")
    assert read_content == content


def test_write_file_path_traversal_blocked(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    with pytest.raises(ValueError, match="path traversal"):
        pm.write_file(project.id, "../etc/passwd", b"hack", "claude")


def test_write_file_absolute_path_blocked(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    with pytest.raises(ValueError, match="Invalid filename"):
        pm.write_file(project.id, "/etc/passwd", b"hack", "claude")


def test_write_file_null_byte_blocked(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    with pytest.raises(ValueError):
        pm.write_file(project.id, "file\x00name.txt", b"hack", "claude")


def test_write_file_too_large(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    large_content = b"x" * (MAX_FILE_SIZE + 1)
    with pytest.raises(ValueError, match="too large"):
        pm.write_file(project.id, "large.bin", large_content, "claude")


def test_write_file_sanitizes_filename(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    entry = pm.write_file(project.id, "file with spaces & special.txt", b"content", "claude")
    assert "spaces" in entry.name
    assert "&" not in entry.name


def test_read_file_not_found(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    assert pm.read_file(project.id, "nonexistent.txt") is None


def test_create_and_update_task(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    task = pm.create_task(project.id, "Write tests", "Cover all cases", "claude", assigned_to="hermes")
    assert task is not None
    assert task.title == "Write tests"
    assert task.assigned_to == "hermes"
    assert task.status == "pending"

    ok = pm.update_task(project.id, task.id, "in_progress")
    assert ok is True
    assert project.tasks[task.id].status == "in_progress"


def test_create_task_project_not_found(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    task = pm.create_task("nonexistent", "title", "desc", "claude")
    assert task is None


def test_update_task_not_found(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    assert pm.update_task(project.id, "nonexistent", "done") is False


def test_delete_project(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    assert pm.delete_project(project.id, "claude") is True
    assert pm.get_project(project.id) is None


def test_delete_project_not_creator(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    project = pm.create_project("Test", "claude")
    assert pm.delete_project(project.id, "alice") is False
    assert pm.get_project(project.id) is not None


def test_delete_project_not_found(temp_sandbox):
    pm = ProjectManager(sandbox_base=temp_sandbox)
    assert pm.delete_project("nonexistent", "claude") is False
