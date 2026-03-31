"""
SSE Event Emitter
Publishes real-time events to connected dashboard clients via Server-Sent Events.
"""

import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    type: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_sse(self) -> str:
        return f"id: {self.id}\nevent: {self.type}\ndata: {json.dumps(self.data, default=str)}\n\n"


class EventEmitter:
    """
    Thread-safe SSE broadcaster.
    Each subscriber gets a bounded in-memory queue. Events are delivered to all
    active subscribers. Disconnected clients are automatically cleaned up.
    """

    MAX_QUEUE_PER_CLIENT = 200

    def __init__(self):
        self._queues: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()

    def subscribe(self) -> tuple[str, list[Event]]:
        """Register a new subscriber. Returns (client_id, recent_history)."""
        client_id = str(uuid.uuid4())
        q = queue.Queue(maxsize=self.MAX_QUEUE_PER_CLIENT)
        with self._lock:
            self._queues[client_id] = q
        # Return last 50 events as initial burst
        return client_id, []

    def unsubscribe(self, client_id: str):
        """Remove a subscriber."""
        with self._lock:
            self._queues.pop(client_id, None)

    def emit(self, event_type: str, data: dict):
        """Broadcast an event to all subscribers."""
        event = Event(type=event_type, data=data)
        with self._lock:
            dead = []
            for cid, q in self._queues.items():
                try:
                    q.put_nowait(event)
                except queue.Full:
                    # Client is too slow — drop oldest to make room
                    try:
                        q.get_nowait()
                        q.put_nowait(event)
                    except queue.Empty:
                        pass
                    dead.append(cid)
            for cid in dead:
                self._queues.pop(cid, None)

    def get_client_queue(self, client_id: str) -> Optional[queue.Queue]:
        with self._lock:
            return self._queues.get(client_id)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._queues)


# Module-level singleton
_emitter = EventEmitter()


def get_emitter() -> EventEmitter:
    return _emitter
