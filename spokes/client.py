"""
Agent Client SDK
Provides a client for agents to interact with the Hub API.
"""

import requests
import threading
import time
from typing import Callable, Optional


class AgentClient:
    def __init__(self, hub_url: str, agent_name: str, agent_type: str):
        self.hub_url = hub_url.rstrip("/")
        self.agent_name = agent_name
        self.agent_type = agent_type
        self._session = requests.Session()
        self._heartbeat_thread = None
        self._heartbeat_running = False

    def register(self, metadata: Optional[dict] = None) -> dict:
        """Register this agent with the hub."""
        payload = {
            "name": self.agent_name,
            "type": self.agent_type,
        }
        if metadata:
            payload["metadata"] = metadata
        response = self._session.post(
            f"{self.hub_url}/agents/register",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def ensure_registered(self, metadata: Optional[dict] = None) -> bool:
        """Ensure this agent is known by the hub.

        If heartbeat succeeds, registration already exists. Otherwise register now.
        """
        if self.heartbeat():
            return True
        try:
            self.register(metadata=metadata)
            return True
        except Exception:
            return False

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

    def process_inbox(
        self,
        handler: Callable[[dict], None],
        unread_only: bool = True,
        auto_ack: bool = True,
        max_messages: Optional[int] = None,
    ) -> int:
        """Pull inbox messages and dispatch each message to handler.

        Returns the number of processed messages.
        """
        messages = self.get_messages(unread_only=unread_only)
        processed = 0
        for message in messages:
            handler(message)
            if auto_ack:
                self.ack(message["id"])
            processed += 1
            if max_messages is not None and processed >= max_messages:
                break
        return processed

    def wait_for_messages(
        self,
        timeout_seconds: float = 30.0,
        poll_interval: float = 1.0,
        unread_only: bool = True,
    ) -> list:
        """Poll until messages arrive or timeout expires."""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            messages = self.get_messages(unread_only=unread_only)
            if messages:
                return messages
            time.sleep(poll_interval)
        return []

    def run_autonomous_loop(
        self,
        handler: Callable[[dict], None],
        poll_interval: float = 2.0,
        heartbeat_interval: float = 10.0,
        stop_event: Optional[threading.Event] = None,
        metadata: Optional[dict] = None,
        auto_ack: bool = True,
    ):
        """Run a collaboration loop suitable for autonomous agents.

        Behavior:
          - ensures registration is present
          - sends heartbeat periodically
          - polls unread inbox and dispatches to handler
          - optionally acknowledges processed messages
        """
        if stop_event is None:
            stop_event = threading.Event()

        if not self.ensure_registered(metadata=metadata):
            raise RuntimeError("Failed to register agent with hub")

        next_heartbeat = 0.0
        while not stop_event.is_set():
            now = time.time()
            if now >= next_heartbeat:
                self.heartbeat()
                next_heartbeat = now + heartbeat_interval

            try:
                self.process_inbox(handler, unread_only=True, auto_ack=auto_ack)
            except Exception:
                # Keep loop alive for robustness in long-running autonomous agents.
                pass

            stop_event.wait(poll_interval)

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

    # --- Autonomy ---

    def set_autonomy_mode(self, mode: str) -> dict:
        """Set this agent's autonomy mode (fully_autonomous, advisory, manual)."""
        response = self._session.post(
            f"{self.hub_url}/agents/{self.agent_name}/autonomy",
            json={"mode": mode}
        )
        response.raise_for_status()
        return response.json()

    def set_capabilities(self, tags: list[str], description: str = "") -> dict:
        """Declare this agent's capability tags."""
        response = self._session.post(
            f"{self.hub_url}/agents/{self.agent_name}/capabilities",
            json={"tags": tags, "description": description}
        )
        response.raise_for_status()
        return response.json()

    def claim_task(self, project_id: str, task_id: str) -> dict:
        """Attempt to claim a task (validates capability match)."""
        response = self._session.post(
            f"{self.hub_url}/projects/{project_id}/tasks/{task_id}/claim",
            json={"agent": self.agent_name}
        )
        response.raise_for_status()
        return response.json()

    def submit_checkpoint(
        self,
        task_id: str = None,
        state: str = "",
        rationale: str = "",
        metadata: dict = None
    ) -> dict:
        """Submit a checkpoint — required every N heartbeat cycles."""
        response = self._session.post(
            f"{self.hub_url}/agents/{self.agent_name}/checkpoint",
            json={
                "task_id": task_id,
                "state": state,
                "rationale": rationale,
                "metadata": metadata or {}
            }
        )
        response.raise_for_status()
        return response.json()

    def get_my_tasks(self, project_id: str = None) -> list:
        """Get tasks assigned to or claimed by this agent."""
        params = {"agent": self.agent_name}
        if project_id:
            params["project_id"] = project_id
        response = self._session.get(
            f"{self.hub_url}/tasks",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def check_revocation(self) -> dict:
        """Poll for any pending revocation directive."""
        response = self._session.get(
            f"{self.hub_url}/agents/{self.agent_name}/revocation"
        )
        response.raise_for_status()
        return response.json()

    def acknowledge_revocation(self, revocation_id: str) -> bool:
        """Acknowledge a revocation and halt."""
        response = self._session.post(
            f"{self.hub_url}/agents/{self.agent_name}/revocation/ack",
            json={"revocation_id": revocation_id}
        )
        return response.status_code == 200

    # --- Task transitions ---

    def transition_task(
        self,
        project_id: str,
        task_id: str,
        new_status: str,
        blocked_reason: str = None,
        blocked_by: str = None
    ) -> bool:
        """Transition a task to a new KanBan state."""
        json_data = {"status": new_status}
        if blocked_reason:
            json_data["blocked_reason"] = blocked_reason
        if blocked_by:
            json_data["blocked_by"] = blocked_by
        response = self._session.patch(
            f"{self.hub_url}/projects/{project_id}/tasks/{task_id}",
            json=json_data
        )
        return response.status_code == 200
