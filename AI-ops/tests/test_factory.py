"""Tests for the public agent factory and investigation convenience wrapper."""

import asyncio
from typing import Any

import agent
from agent import create_agent, investigate
from agent.models import Incident, IncidentTrigger, InvestigationState, Severity


def make_incident() -> Incident:
    """Create an incident for offline factory tests."""
    return Incident(
        id="inc-factory",
        title="Factory test incident",
        service="auth",
        severity=Severity.HIGH,
        description="A test incident with no external dependencies.",
        triggered_by=IncidentTrigger.ALERTMANAGER,
    )


def finish_response() -> dict[str, Any]:
    """Return a valid minimal LiteLLM response that ends an investigation."""
    return {
        "choices": [{"message": {"content": '{"action":"finish"}'}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5},
    }


def test_public_api_contains_only_factory_and_convenience_function() -> None:
    """The package exports only create_agent and investigate as public API."""
    assert agent.__all__ == ["create_agent", "investigate"]
    assert not hasattr(agent, "TYPE_CHECKING")


def test_create_agent_wires_configuration_and_tool_registry() -> None:
    """Factory settings are shared by router, gate, registry, and loop."""
    agent = asyncio.run(
        create_agent(
            provider="openai",
            model="gpt-test",
            api_key="placeholder-test-key",
            dangerous_tools={"custom_restart"},
            max_iterations=3,
        )
    )

    assert agent.router.provider == "openai"
    assert agent.router.model == "gpt-test"
    assert agent.router.api_key == "placeholder-test-key"
    assert agent.router.registry is agent.registry
    assert agent.gate.dangerous_tools == {"custom_restart"}
    assert agent.max_iterations == 3
    assert {"prom_query", "loki_search", "metric_baseline_diff"}.issubset(
        {tool.name for tool in agent.registry.list_all()}
    )


def test_factory_loop_runs_without_real_api_call(monkeypatch: Any) -> None:
    """The composed factory loop executes a mocked finish response end to end."""
    requests: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        requests.append(kwargs)
        return finish_response()

    monkeypatch.setattr("agent.router._acompletion", fake_acompletion)
    agent = asyncio.run(
        create_agent(
            provider="anthropic",
            model="claude-test",
            api_key="placeholder-test-key",
            max_iterations=2,
        )
    )
    result = asyncio.run(agent.run(make_incident()))

    assert result.evidence
    assert agent.context is not None
    assert agent.context.current_state == InvestigationState.LEARN
    assert requests[0]["model"] == "anthropic/claude-test"


def test_investigate_convenience_wrapper(monkeypatch: Any) -> None:
    """The public convenience function returns an InvestigationResult."""

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        return finish_response()

    monkeypatch.setattr("agent.router._acompletion", fake_acompletion)
    result = asyncio.run(
        investigate(
            incident=make_incident(),
            provider="openai",
            model="gpt-test",
            api_key="placeholder-test-key",
            max_iterations=1,
        )
    )

    assert result.final_summary.startswith("Investigation for inc-factory")
    assert result.evidence
