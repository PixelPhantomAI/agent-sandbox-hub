"""
Inter-Agent Messaging Tests
"""

import time
import pytest
from hub.messages import MessageStore, Message


def test_send_message():
    store = MessageStore()
    msg = store.send("alice", "bob", "Hello Bob!", "text")
    assert msg.from_agent == "alice"
    assert msg.to_agent == "bob"
    assert msg.content == "Hello Bob!"
    assert msg.delivered is False
    assert msg.message_type == "text"


def test_get_inbox():
    store = MessageStore()
    store.send("alice", "bob", "Hello", "text")
    store.send("alice", "bob", "Hello again", "text")
    store.send("carol", "bob", "Carol says hi", "text")

    inbox = store.get_inbox("bob", unread_only=False)
    assert len(inbox) == 3
    # Messages returned oldest-first (insertion order)
    assert inbox[0].from_agent == "alice"
    assert inbox[0].content == "Hello"
    assert inbox[1].from_agent == "alice"
    assert inbox[1].content == "Hello again"
    assert inbox[2].from_agent == "carol"


def test_get_inbox_unread_only():
    """When unread_only=True, messages are returned but NOT marked as delivered."""
    store = MessageStore()
    store.send("alice", "bob", "Hello", "text")

    # First call with unread_only=True: returns msg, doesn't mark delivered
    first = store.get_inbox("bob", unread_only=True)
    assert len(first) == 1
    assert first[0].delivered is False

    # Second call with unread_only=True: msg still returned (still undelivered)
    second = store.get_inbox("bob", unread_only=True)
    assert len(second) == 1


def test_ack():
    store = MessageStore()
    msg = store.send("alice", "bob", "Hello", "text")
    assert store.ack(msg.id) is True
    assert store.ack("nonexistent") is False


def test_get_history():
    store = MessageStore()
    store.send("alice", "bob", "msg1", "text")
    time.sleep(0.01)
    store.send("bob", "alice", "msg2", "text")
    time.sleep(0.01)
    store.send("alice", "bob", "msg3", "text")

    history = store.get_history("alice", "bob")
    assert len(history) == 3
    # Newest first (reverse chronological)
    assert history[0].content == "msg3"
    assert history[1].content == "msg2"
    assert history[2].content == "msg1"


def test_get_history_limit():
    store = MessageStore()
    for i in range(10):
        store.send("alice", "bob", f"msg{i}", "text")
    history = store.get_history("alice", "bob", limit=3)
    assert len(history) == 3


def test_broadcast():
    store = MessageStore()
    msg = store.send("alice", "*", "Announcement!", "text")
    assert msg.to_agent == "*"
    inbox = store.get_inbox("*")
    assert len(inbox) == 1


def test_ack_sets_acknowledged_flag():
    store = MessageStore()
    msg = store.send("alice", "bob", "Hello", "text")
    store.get_inbox("bob", unread_only=False)  # marks delivered
    store.ack(msg.id)  # should set acknowledged
    # Message should still be findable by ID
    assert msg.acknowledged is True
