"""
Inter-Agent Messaging System
Handles message passing between agents with delivery confirmation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import threading
import uuid


@dataclass
class Message:
    id: str
    from_agent: str
    to_agent: str
    content: str
    message_type: str = "text"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    delivered: bool = False
    acknowledged: bool = False


class MessageStore:
    def __init__(self, max_history: int = 100):
        self._messages: dict[str, Message] = {}
        self._lock = threading.RLock()
        self._max_history = max_history

    def send(self, from_agent: str, to_agent: str, content: str, message_type: str = "text") -> Message:
        """Send a message to an agent."""
        with self._lock:
            message = Message(
                id=str(uuid.uuid4()),
                from_agent=from_agent,
                to_agent=to_agent,
                content=content,
                message_type=message_type
            )
            self._messages[message.id] = message
            self._trim_history()
            return message

    def get_inbox(self, agent_name: str, unread_only: bool = False) -> list[Message]:
        """Get messages for an agent, optionally unread only."""
        with self._lock:
            inbox = [
                msg for msg in self._messages.values()
                if msg.to_agent == agent_name
                and (not unread_only or not msg.delivered)
            ]
            for msg in inbox:
                msg.delivered = True
            inbox.sort(key=lambda m: m.timestamp, reverse=True)
            return inbox

    def ack(self, message_id: str) -> bool:
        """Acknowledge a message receipt."""
        with self._lock:
            if message_id not in self._messages:
                return False
            self._messages[message_id].acknowledged = True
            return True

    def get_history(self, agent_a: str, agent_b: str, limit: int = 50) -> list[Message]:
        """Get message history between two agents."""
        with self._lock:
            history = [
                msg for msg in self._messages.values()
                if (msg.from_agent == agent_a and msg.to_agent == agent_b)
                or (msg.from_agent == agent_b and msg.to_agent == agent_a)
            ]
            history.sort(key=lambda m: m.timestamp, reverse=True)
            return history[:limit]

    def _trim_history(self):
        """Trim old messages if over max_history."""
        if len(self._messages) > self._max_history * 2:
            to_remove = [
                mid for mid, msg in self._messages.items()
                if msg.acknowledged
            ]
            for mid in to_remove[:len(self._messages) - self._max_history]:
                del self._messages[mid]
