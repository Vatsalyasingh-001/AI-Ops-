"""Tests for tool registration, validation, filtering, and dispatch."""

import asyncio
from typing import Any

import pytest
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import JsonValue

from agent.models import (
    Incident,
    IncidentTrigger,
    InvestigationContext,
    RiskLevel,
    Severity,
)
from agent.tools import Tool, ToolRegistry, ToolResult

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}


class EchoTool(Tool):
    """Test tool that echoes validated input and identifies its own name."""

    def __init__(self, name: str, is_read_only: bool, risk_level: RiskLevel) -> None:
        self._name = name
        self._is_read_only = is_read_only
        self._risk_level = risk_level

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Echo the query for registry tests."

    @property
    def input_schema(self) -> dict[str, Any]:
        return INPUT_SCHEMA

    @property
    def is_read_only(self) -> bool:
        return self._is_read_only

    @property
    def risk_level(self) -> RiskLevel:
        return self._risk_level

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        return ToolResult(
            success=True, data={"tool": self.name, "query": input["query"]}
        )


def make_registry() -> ToolRegistry:
    """Build a registry with three tools covering read-only and risk levels."""
    registry = ToolRegistry()
    registry.register(EchoTool("safe_lookup", True, RiskLevel.LOW))
    registry.register(EchoTool("sensitive_lookup", True, RiskLevel.HIGH))
    registry.register(EchoTool("restart_service", False, RiskLevel.CRITICAL))
    return registry


def make_context() -> InvestigationContext:
    """Create the minimum valid investigation context for tool calls."""
    return InvestigationContext(
        incident=Incident(
            id="inc-tools",
            title="Tool registry test",
            service="checkout",
            severity=Severity.MEDIUM,
            description="Test context only.",
            triggered_by=IncidentTrigger.ALERTMANAGER,
        ),
        token_budget_remaining=100,
    )


def test_registry_registers_and_dispatches_by_name() -> None:
    """Dispatch validates input and invokes only the selected registered tool."""
    registry = make_registry()
    selected_tool = registry.get("sensitive_lookup")

    result = asyncio.run(
        registry.dispatch(
            "sensitive_lookup", {"query": "current errors"}, make_context()
        )
    )

    assert selected_tool.name == "sensitive_lookup"
    assert result.success is True
    assert result.data == {"tool": "sensitive_lookup", "query": "current errors"}


def test_registry_validates_tool_input_schema() -> None:
    """Valid inputs pass while inputs not matching the registered schema fail."""
    registry = make_registry()

    registry.validate_schema("safe_lookup", {"query": "service health"})

    with pytest.raises(JsonSchemaValidationError):
        registry.validate_schema("safe_lookup", {"query": 42})


def test_registry_filters_read_only_and_risky_tools() -> None:
    """Read-only classification and risk level are filtered independently."""
    registry = make_registry()

    assert [tool.name for tool in registry.list_read_only()] == [
        "safe_lookup",
        "sensitive_lookup",
    ]
    assert [tool.name for tool in registry.list_risky()] == [
        "sensitive_lookup",
        "restart_service",
    ]
