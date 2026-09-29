"""Deterministic fake observability tools for exercising the observe phase."""

from __future__ import annotations

from typing import Any

from pydantic import JsonValue

from agent.models import EvidenceItem, EvidenceSource, InvestigationContext, RiskLevel
from agent.tools.base import Tool, ToolRegistry, ToolResult

DEPLOY_TIMESTAMP = "2026-09-30T12:00:00Z"

_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string", "minLength": 1}},
    "required": ["query"],
    "additionalProperties": False,
}
_SERVICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"service": {"type": "string", "minLength": 1}},
    "required": ["service"],
    "additionalProperties": False,
}


def _tool_result(
    tool_name: str,
    query: str,
    source: EvidenceSource,
    data: dict[str, JsonValue],
) -> ToolResult:
    """Wrap fake source data in a successful result and traceable evidence."""
    evidence = EvidenceItem(
        tool_name=tool_name,
        query=query,
        result=data,
        source=source,
    )
    return ToolResult(success=True, data=data, evidence_items=[evidence])


class PromQueryTool(Tool):
    """Return a fixed fake 5xx metric comparison."""

    @property
    def name(self) -> str:
        return "prom_query"

    @property
    def description(self) -> str:
        return "Return a fake Prometheus metric difference for the supplied query."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _QUERY_SCHEMA

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        data: dict[str, JsonValue] = {
            "metric": "5xx rate",
            "summary": "5xx rate: 0.2% → 8.7%",
            "baseline_percent": 0.2,
            "current_percent": 8.7,
        }
        return _tool_result(
            self.name, str(input["query"]), EvidenceSource.PROMETHEUS, data
        )


class LokiSearchTool(Tool):
    """Return fixed fake error excerpts close to a deploy timestamp."""

    @property
    def name(self) -> str:
        return "loki_search"

    @property
    def description(self) -> str:
        return "Return fake service error logs near a recent deploy."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _SERVICE_SCHEMA

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        service = str(input["service"])
        data: dict[str, JsonValue] = {
            "service": service,
            "deploy_timestamp": DEPLOY_TIMESTAMP,
            "logs": [
                {
                    "timestamp": "2026-09-30T12:00:14Z",
                    "level": "ERROR",
                    "message": "token validation failed: upstream returned 503",
                },
                {
                    "timestamp": "2026-09-30T12:00:22Z",
                    "level": "ERROR",
                    "message": "request failed while loading signing key",
                },
            ],
        }
        query = f"error logs for {service} near deploy at {DEPLOY_TIMESTAMP}"
        return _tool_result(self.name, query, EvidenceSource.LOKI, data)


class TempoTraceTool(Tool):
    """Return a fake p95 latency spike for the auth validation endpoint."""

    @property
    def name(self) -> str:
        return "tempo_trace"

    @property
    def description(self) -> str:
        return "Return a fake latency comparison for /auth/validate traces."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _SERVICE_SCHEMA

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        service = str(input["service"])
        data: dict[str, JsonValue] = {
            "service": service,
            "endpoint": "/auth/validate",
            "p95_latency_ms": {"baseline": 140, "current": 1820},
        }
        query = f"p95 trace latency for {service} /auth/validate"
        return _tool_result(self.name, query, EvidenceSource.TEMPO, data)


class TopologyGetTool(Tool):
    """Return a fixed fake service dependency graph."""

    @property
    def name(self) -> str:
        return "topology_get"

    @property
    def description(self) -> str:
        return "Return a fake dependency graph centered on the requested service."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _SERVICE_SCHEMA

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        service = str(input["service"])
        data: dict[str, JsonValue] = {
            "service": service,
            "nodes": ["api-gateway", "auth", "users-db"],
            "edges": [
                {"from": "api-gateway", "to": "auth"},
                {"from": "auth", "to": "users-db"},
            ],
        }
        return _tool_result(
            self.name,
            f"service dependencies for {service}",
            EvidenceSource.TOPOLOGY,
            data,
        )


class DeploysListTool(Tool):
    """Return fixed fake recent deployments for the requested service."""

    @property
    def name(self) -> str:
        return "deploys_list"

    @property
    def description(self) -> str:
        return "Return fake recent deployment versions and timestamps."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _SERVICE_SCHEMA

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        service = str(input["service"])
        data: dict[str, JsonValue] = {
            "service": service,
            "deploys": [
                {"version": "v2.4.1", "timestamp": DEPLOY_TIMESTAMP},
                {"version": "v2.4.0", "timestamp": "2026-09-29T18:30:00Z"},
            ],
        }
        return _tool_result(
            self.name,
            f"recent deployments for {service}",
            EvidenceSource.DEPLOYS,
            data,
        )


prom_query_tool = PromQueryTool()
loki_search_tool = LokiSearchTool()
tempo_trace_tool = TempoTraceTool()
topology_get_tool = TopologyGetTool()
deploys_list_tool = DeploysListTool()

OBSERVE_TOOLS: tuple[Tool, ...] = (
    prom_query_tool,
    loki_search_tool,
    tempo_trace_tool,
    topology_get_tool,
    deploys_list_tool,
)


def register_observe_tools(registry: ToolRegistry) -> None:
    """Register all fake observe tools in deterministic order."""
    for tool in OBSERVE_TOOLS:
        registry.register(tool)
