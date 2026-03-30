"""
Agent Client SDK
Provides a client for agents to interact with the Hub API.
"""

import requests
import threading
import time


class AgentClient:
    def __init__(self, hub_url: str, agent_name: str, agent_type: str):
        self.hub_url = hub_url.rstrip("/")
        self.agent_name = agent_name
        self.agent_type = agent_type
        self._session = requests.Session()
        self._heartbeat_thread = None
        self._heartbeat_running = False

    def register(self) -> dict:
        """Register this agent with the hub."""
        response = self._session.post(
            f"{self.hub_url}/agents/register",
            json={"name": self.agent_name, "type": self.agent_type}
        )
        response.raise_for_status()
        return response.json()

    def unregister(self) -> bool:
        """Unregister this agent from the hub."""
        try:
            response = self._session.delete(
                f"{self.hub_url}/agents/{self.agent_name}"
            )
            return response.status_code == 200
        except:
            return False

    def heartbeat(self) -> bool:
        """Send a heartbeat to the hub."""
        try:
            response = self._session.post(
                f"{self.hub_url}/agents/{self.agent_name}/heartbeat"
            )
            return response.status_code == 200
        except:
            return False

    def send_message(self, to: str, content: str, message_type: str = "text") -> dict:
        """Send a message to another agent."""
        response = self._session.post(
            f"{self.hub_url}/messages/send",
            json={
                "from": self.agent_name,
                "to": to,
                "content": content,
                "type": message_type
            }
        )
        response.raise_for_status()
        return response.json()

    def get_messages(self, unread_only: bool = False) -> list:
        """Get inbox messages."""
        params = {"unread": "true"} if unread_only else {}
        response = self._session.get(
            f"{self.hub_url}/messages/{self.agent_name}",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def ack(self, message_id: str) -> bool:
        """Acknowledge message receipt."""
        response = self._session.post(
            f"{self.hub_url}/messages/{message_id}/ack"
        )
        return response.status_code == 200

    def create_project(self, name: str) -> dict:
        """Create a new project."""
        response = self._session.post(
            f"{self.hub_url}/projects",
            json={"name": name, "creator": self.agent_name}
        )
        response.raise_for_status()
        return response.json()

    def list_projects(self, agent: str = None) -> list:
        """List projects."""
        params = {"agent": agent} if agent else {}
        response = self._session.get(
            f"{self.hub_url}/projects",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def join_project(self, project_id: str) -> bool:
        """Join a project."""
        response = self._session.post(
            f"{self.hub_url}/projects/{project_id}/join",
            json={"agent": self.agent_name}
        )
        return response.status_code == 200

    def upload_file(self, project_id: str, filename: str, content: bytes) -> dict:
        """Upload a file to a project."""
        files = {"file": (filename, content)}
        data = {"uploader": self.agent_name}
        response = self._session.post(
            f"{self.hub_url}/projects/{project_id}/files",
            files=files,
            data=data
        )
        response.raise_for_status()
        return response.json()

    def download_file(self, project_id: str, filename: str) -> bytes:
        """Download a file from a project."""
        response = self._session.get(
            f"{self.hub_url}/projects/{project_id}/files/{filename}"
        )
        response.raise_for_status()
        return response.content

    def create_task(self, project_id: str, title: str, description: str, assigned_to: str = None) -> dict:
        """Create a task in a project."""
        json_data = {"title": title, "description": description}
        if assigned_to:
            json_data["assigned_to"] = assigned_to
        response = self._session.post(
            f"{self.hub_url}/projects/{project_id}/tasks",
            json=json_data
        )
        response.raise_for_status()
        return response.json()

    def update_task(self, project_id: str, task_id: str, status: str) -> bool:
        """Update task status."""
        response = self._session.patch(
            f"{self.hub_url}/projects/{project_id}/tasks/{task_id}",
            json={"status": status}
        )
        return response.status_code == 200

    def start_heartbeat(self, interval: int = 10):
        """Start periodic heartbeat in a background thread."""
        self._heartbeat_running = True

        def _heartbeat_loop():
            while self._heartbeat_running:
                self.heartbeat()
                time.sleep(interval)

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        """Stop the heartbeat thread."""
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1)
