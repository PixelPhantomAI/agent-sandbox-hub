"""
Tests for Sandbox Isolation
"""

import time
from hub.sandbox import SandboxEnforcer


def test_rate_limit_allows_within_limit():
    sandbox = SandboxEnforcer()
    agent = "test-agent"
    # Should allow up to 60 requests
    for _ in range(60):
        assert sandbox.check_rate_limit(agent) is True


def test_rate_limit_blocks_over_limit():
    sandbox = SandboxEnforcer()
    agent = "test-agent"
    # Use up the limit
    for _ in range(60):
        sandbox.check_rate_limit(agent)
    # Next one should be blocked
    assert sandbox.check_rate_limit(agent) is False


def test_rate_limit_per_agent():
    sandbox = SandboxEnforcer()
    agent1 = "agent1"
    agent2 = "agent2"
    for _ in range(60):
        sandbox.check_rate_limit(agent1)
    # Agent2 should still be allowed
    assert sandbox.check_rate_limit(agent2) is True


def test_external_url_blocked():
    sandbox = SandboxEnforcer()
    # External URLs should be blocked
    assert sandbox.check_message_content("Check out https://google.com") is False
    assert sandbox.check_message_content("Visit http://example.com for info") is False
    # Bare IPs are not matched by the URL regex (they'd appear in URLs like http://8.8.8.8)
    # which is caught by the URL pattern anyway
    assert sandbox.check_message_content("http://8.8.8.8") is False


def test_internal_url_allowed():
    sandbox = SandboxEnforcer()
    # Internal URLs should be allowed
    assert sandbox.check_message_content("Connect to 172.28.0.10:8080") is True
    assert sandbox.check_message_content("localhost:3000") is True
    assert sandbox.check_message_content("http://127.0.0.1/api") is True


def test_audit_logging():
    sandbox = SandboxEnforcer()
    sandbox.audit("agent1", "test_action", {"key": "value"})
    log = sandbox.get_audit_log(10)
    assert len(log) == 1
    assert log[0]["agent"] == "agent1"
    assert log[0]["action"] == "test_action"
    assert log[0]["details"] == {"key": "value"}


def test_audit_log_limit():
    sandbox = SandboxEnforcer()
    # Add many entries
    for i in range(100):
        sandbox.audit(f"agent{i}", "action", {})
    log = sandbox.get_audit_log(50)
    assert len(log) == 50


def test_message_content_empty():
    sandbox = SandboxEnforcer()
    assert sandbox.check_message_content("") is True
    assert sandbox.check_message_content(None) is True
