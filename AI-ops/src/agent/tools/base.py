"""Base protocol and deterministic registry for investigation tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, JsonValue

from agent.models import EvidenceItem, InvestigationContext, RiskLevel


class ToolResult(BaseModel):
    """Structured result returned by a tool invocation."""

    success: bool
    data: dict[str, JsonValue] | str
    error: str | None = None
    evidence_items: list[EvidenceItem] = Field(default_factory=list)


class Tool(ABC):
    """Abstract contract implemented by each investigation tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique registry name for this tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a concise description of this tool's behavior."""

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """Return the JSON Schema used to validate tool input."""

    @property
    @abstractmethod
    def is_read_only(self) -> bool:
        """Return whether this tool performs no mutations."""

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        """Return the risk classification for this tool."""

    @abstractmethod
    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        """Execute the tool for validated input and investigation context."""


class ToolRegistry:
    """Register, validate, filter, and dispatch tools in registration order."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._validators: dict[str, Draft202012Validator] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool after checking its name and JSON Schema."""
        if not tool.name.strip():
            raise ValueError("Tool name must not be empty")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        Draft202012Validator.check_schema(tool.input_schema)
        self._tools[tool.name] = tool
        self._validators[tool.name] = Draft202012Validator(tool.input_schema)

    def get(self, name: str) -> Tool:
        """Return a registered tool or raise `KeyError` for an unknown name."""
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def list_all(self) -> list[Tool]:
        """Return all registered tools in deterministic registration order."""
        return list(self._tools.values())

    def list_read_only(self) -> list[Tool]:
        """Return read-only tools in their registration order."""
        return [tool for tool in self._tools.values() if tool.is_read_only]

    def list_risky(self) -> list[Tool]:
        """Return tools with medium, high, or critical risk, in registration order."""
        risky_levels = {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}
        return [
            tool for tool in self._tools.values() if tool.risk_level in risky_levels
        ]

    def validate_schema(self, name: str, input: dict[str, JsonValue]) -> None:
        """Validate input for a registered tool; raise JSON Schema errors if invalid."""
        self.get(name)
        self._validators[name].validate(input)

    async def dispatch(
        self,
        name: str,
        input: dict[str, JsonValue],
        context: InvestigationContext,
    ) -> ToolResult:
        """Validate input, then asynchronously invoke the named tool."""
        self.validate_schema(name, input)
        return await self._tools[name].run(input, context)
