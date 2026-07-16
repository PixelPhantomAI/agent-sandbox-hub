import time
import pytest
from hub.agents import AgentRegistry, Agent


def test_agent_register():
    r = AgentRegistry()
    a = r.register("claude", "claude", {"version": "1.0"})
    assert a.name == "claude"
    assert a.agent_type == "claude"
    assert a.status == "online"


def test_agent_register_duplicate():
    r = AgentRegistry()
    r.register("claude", "claude")
    a2 = r.register("claude", "claude", {"v": "2"})  # re-register
    assert a2.name == "claude"


def test_agent_heartbeat():
    r = AgentRegistry()
    r.register("claude", "claude")
    assert r.heartbeat("claude") is True
    agent = r.get_agent("claude")
    assert agent.status == "online"


def test_agent_heartbeat_unknown():
    r = AgentRegistry()
    assert r.heartbeat("nobody") is False


def test_agent_unregister():
    r = AgentRegistry()
    r.register("claude", "claude")
    assert r.unregister("claude") is True
    assert r.get_agent("claude") is None


def test_agent_unregister_unknown():
    r = AgentRegistry()
    assert r.unregister("nobody") is False


def test_list_agents():
    r = AgentRegistry()
    r.register("claude", "claude")
    r.register("hermes", "hermes")
    agents = r.list_agents()
    assert len(agents) == 2
    names = {a["name"] for a in agents}
    assert names == {"claude", "hermes"}


def test_list_agents_filter():
    r = AgentRegistry()
    r.register("claude", "claude")
    r.register("hermes", "hermes")
    r.get_agent("claude").status = "busy"
    online = r.list_agents(status="online")
    assert len(online) == 1
    assert online[0]["name"] == "hermes"


def test_agent_cleanup_stale():
    r = AgentRegistry(heartbeat_timeout=1)
    r.register("claude", "claude")
    time.sleep(1.5)
    stale = r.cleanup_stale()
    assert "claude" in stale
    assert r.get_agent("claude") is None


def test_agent_still_live_not_cleaned():
    r = AgentRegistry(heartbeat_timeout=5)
    r.register("claude", "claude")
    time.sleep(0.5)
    stale = r.cleanup_stale()
    assert "claude" not in stale
    assert r.get_agent("claude") is not None


def test_agent_metadata():
    r = AgentRegistry()
    a = r.register("claude", "claude", {"version": "2.0", "os": "linux"})
    assert a.metadata["version"] == "2.0"
    assert a.metadata["os"] == "linux"
