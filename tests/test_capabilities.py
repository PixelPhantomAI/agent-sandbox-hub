"""
Tests for capability matching system.
"""

import pytest
from hub.capabilities import CapabilityRegistry


@pytest.fixture
def cap_reg():
    return CapabilityRegistry()


def test_register_and_get(cap_reg):
    cap_reg.register("claude", ["code", "review"], "Claude agent")
    profile = cap_reg.get("claude")
    assert profile is not None
    assert "code" in profile.tags
    assert "review" in profile.tags


def test_can_claim_sufficient(cap_reg):
    cap_reg.register("claude", ["code", "review"])
    assert cap_reg.can_claim("claude", ["code"]) is True
    assert cap_reg.can_claim("claude", ["code", "review"]) is True


def test_can_claim_insufficient(cap_reg):
    cap_reg.register("claude", ["code"])
    assert cap_reg.can_claim("claude", ["code", "review"]) is False


def test_can_claim_no_requirements(cap_reg):
    cap_reg.register("claude", ["code"])
    assert cap_reg.can_claim("claude", []) is True


def test_can_claim_unknown_agent(cap_reg):
    assert cap_reg.can_claim("unknown", ["code"]) is False


def test_agents_with_capability(cap_reg):
    cap_reg.register("claude", ["code", "review"])
    cap_reg.register("hermes", ["code", "data"])
    cap_reg.register("openclaw", ["review"])
    assert set(cap_reg.agents_with_capability("code")) == {"claude", "hermes"}
    assert set(cap_reg.agents_with_capability("review")) == {"claude", "openclaw"}


def test_unregister(cap_reg):
    cap_reg.register("claude", ["code"])
    cap_reg.unregister("claude")
    assert cap_reg.get("claude") is None
    assert cap_reg.can_claim("claude", ["code"]) is False


def test_list_all(cap_reg):
    cap_reg.register("claude", ["code"])
    cap_reg.register("hermes", ["data"])
    all_profiles = cap_reg.list_all()
    names = {p["agent"] for p in all_profiles}
    assert names == {"claude", "hermes"}
