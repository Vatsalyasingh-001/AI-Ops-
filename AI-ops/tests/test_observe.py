"""Tests for deterministic fake observe tools."""

import asyncio

import pytest
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from agent.models import (
    EvidenceSource,
    Incident,
    IncidentTrigger,
    InvestigationContext,
    Severity,
)
from agent.tools import ToolRegistry
from agent.tools.observe import register_observe_tools

TOOL_CASES = [
    ("prom_query", {"query": "sum(rate(http_requests_total[5m]))"}),
    ("loki_search", {"service": "auth"}),
    ("tempo_trace", {"service": "auth"}),
    ("topology_get", {"service": "auth"}),
    ("deploys_list", {"service": "auth"}),
]
EXPECTED_SOURCES = {
    "prom_query": EvidenceSource.PROMETHEUS,
    "loki_search": EvidenceSource.LOKI,
    "tempo_trace": EvidenceSource.TEMPO,
    "topology_get": EvidenceSource.TOPOLOGY,
    "deploys_list": EvidenceSource.DEPLOYS,
}


def make_registry() -> ToolRegistry:
    """Create a registry containing all fake observe tools."""
    registry = ToolRegistry()
    register_observe_tools(registry)
    return registry


def make_context() -> InvestigationContext:
    """Create a minimal valid context for a fake tool invocation."""
    return InvestigationContext(
        incident=Incident(
            id="inc-observe",
            title="Observe tool test",
            service="auth",
            severity=Severity.HIGH,
            description="Context for offline observe tool tests.",
            triggered_by=IncidentTrigger.ALERTMANAGER,
        ),
        token_budget_remaining=100,
    )


def test_observe_tools_dispatch_structured_evidence() -> None:
    """Every registered stub returns data and matching source-tagged evidence."""
    registry = make_registry()
    results = {}

    assert [tool.name for tool in registry.list_read_only()] == [
        "prom_query",
        "loki_search",
        "tempo_trace",
        "topology_get",
        "deploys_list",
    ]

    for name, tool_input in TOOL_CASES:
        result = asyncio.run(registry.dispatch(name, tool_input, make_context()))

        assert result.success is True
        assert isinstance(result.data, dict)
        assert len(result.evidence_items) == 1
        evidence = result.evidence_items[0]
        assert evidence.tool_name == name
        assert evidence.source == EXPECTED_SOURCES[name]
        assert evidence.result == result.data
        results[name] = result.data

    prom_data = results["prom_query"]
    loki_data = results["loki_search"]
    tempo_data = results["tempo_trace"]
    topology_data = results["topology_get"]
    deploy_data = results["deploys_list"]

    assert prom_data["summary"] == "5xx rate: 0.2% → 8.7%"
    assert loki_data["logs"][0]["level"] == "ERROR"
    assert loki_data["deploy_timestamp"] < loki_data["logs"][0]["timestamp"]
    assert tempo_data["endpoint"] == "/auth/validate"
    assert topology_data["edges"]
    assert all("timestamp" in deploy for deploy in deploy_data["deploys"])


def test_observe_tool_schemas_accept_valid_and_reject_invalid_inputs() -> None:
    """Each stub validates inputs according to its registered JSON Schema."""
    registry = make_registry()

    for name, tool_input in TOOL_CASES:
        registry.validate_schema(name, tool_input)

        with pytest.raises(JsonSchemaValidationError):
            registry.validate_schema(name, {})
