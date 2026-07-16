"""Unit tests for autonomous helpers in the AgentClient SDK."""

import threading
import time

from spokes import AgentClient


class FakeClient(AgentClient):
    def __init__(self):
        super().__init__("http://hub:8080", "tester", "test")
        self._messages = []
        self._acks = []
        self._registered = False
        self.heartbeat_calls = 0

    def register(self, metadata=None):
        self._registered = True
        return {"id": self.agent_name}

    def heartbeat(self):
        self.heartbeat_calls += 1
        return self._registered

    def get_messages(self, unread_only=False):
        return list(self._messages)

    def ack(self, message_id: str):
        self._acks.append(message_id)
        return True


def test_process_inbox_dispatches_and_acks():
    c = FakeClient()
    c._messages = [
        {"id": "m1", "content": "one"},
        {"id": "m2", "content": "two"},
    ]

    seen = []
    processed = c.process_inbox(lambda m: seen.append(m["content"]))

    assert processed == 2
    assert seen == ["one", "two"]
    assert c._acks == ["m1", "m2"]


def test_run_autonomous_loop_registers_and_handles_messages():
    c = FakeClient()
    c._messages = [{"id": "m1", "content": "task"}]

    seen = []
    stop = threading.Event()

    t = threading.Thread(
        target=c.run_autonomous_loop,
        kwargs={
            "handler": lambda m: seen.append(m["content"]),
            "poll_interval": 0.02,
            "heartbeat_interval": 0.02,
            "stop_event": stop,
        },
        daemon=True,
    )
    t.start()
    time.sleep(0.08)
    stop.set()
    t.join(timeout=1)

    assert seen
    assert "task" in seen
    assert c._acks
    assert c.heartbeat_calls > 0
