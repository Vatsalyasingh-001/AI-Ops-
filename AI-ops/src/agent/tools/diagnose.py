"""Pure, deterministic diagnosis tools for metrics, logs, and deploy timing."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import JsonValue

from agent.models import EvidenceItem, EvidenceSource, InvestigationContext, RiskLevel
from agent.tools.base import Tool, ToolRegistry, ToolResult

_METRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "metric": {"type": "string", "minLength": 1},
        "baseline": {"type": "number"},
        "current": {"type": "number"},
    },
    "required": ["metric", "baseline", "current"],
    "additionalProperties": False,
}
_LOG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "logs": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                        "required": ["message"],
                    },
                ]
            },
        },
        "top_n": {"type": "integer", "minimum": 1},
    },
    "required": ["logs", "top_n"],
    "additionalProperties": False,
}
_DEPLOY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "deploy_timestamp": {"type": "string", "format": "date-time"},
        "errors": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string", "format": "date-time"},
                    {
                        "type": "object",
                        "properties": {
                            "timestamp": {"type": "string", "format": "date-time"},
                            "message": {"type": "string"},
                        },
                        "required": ["timestamp"],
                    },
                ]
            },
        },
        "window_minutes": {"type": "number", "minimum": 0},
    },
    "required": ["deploy_timestamp", "errors", "window_minutes"],
    "additionalProperties": False,
}
_ANOMALY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "metric": {"type": "string", "minLength": 1},
        "value": {"type": "number"},
        "threshold": {"type": "number"},
        "direction": {"enum": ["above", "below"]},
    },
    "required": ["metric", "value", "threshold", "direction"],
    "additionalProperties": False,
}

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")


class _DiagnosticTool(Tool):
    """Shared read-only, low-risk metadata for local diagnosis tools."""

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW


def _result(
    tool_name: str,
    query: str,
    source: EvidenceSource,
    data: dict[str, JsonValue],
) -> ToolResult:
    """Return computed data together with source-attributed evidence."""
    evidence = EvidenceItem(
        tool_name=tool_name,
        query=query,
        result=data,
        source=source,
    )
    return ToolResult(success=True, data=data, evidence_items=[evidence])


def _normalize_template(message: str) -> str:
    """Replace common dynamic log tokens so equivalent errors cluster together."""
    template = _UUID_PATTERN.sub("<UUID>", message)
    template = _IPV4_PATTERN.sub("<IP>", template)
    template = _NUMBER_PATTERN.sub("<NUM>", template)
    return re.sub(r"\s+", " ", template.casefold()).strip()


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalize it to timezone-aware UTC."""
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


class MetricBaselineDiffTool(_DiagnosticTool):
    """Compute absolute and percentage change from a metric baseline."""

    @property
    def name(self) -> str:
        return "metric_baseline_diff"

    @property
    def description(self) -> str:
        return "Compute the absolute and percentage change between metric values."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _METRIC_SCHEMA

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        baseline = float(input["baseline"])
        current = float(input["current"])
        delta = current - baseline
        change_percent = round(delta / baseline * 100, 6) if baseline != 0 else None
        data: dict[str, JsonValue] = {
            "metric": str(input["metric"]),
            "baseline": baseline,
            "current": current,
            "absolute_change": delta,
            "change_percent": change_percent,
            "percentage_change_defined": baseline != 0,
        }
        query = f"percentage change for {input['metric']} from {baseline} to {current}"
        return _result(self.name, query, EvidenceSource.PROMETHEUS, data)


class LogErrorCorrelateTool(_DiagnosticTool):
    """Cluster log errors by normalized message template and return top-N."""

    @property
    def name(self) -> str:
        return "log_error_correlate"

    @property
    def description(self) -> str:
        return "Cluster error messages by template and return the most frequent groups."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _LOG_SCHEMA

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        logs = input["logs"]
        top_n = int(input["top_n"])
        count_by_template: dict[str, int] = {}
        examples_by_template: dict[str, list[str]] = {}
        for log in logs:
            message = str(log if isinstance(log, str) else log["message"])
            template = _normalize_template(message)
            count_by_template[template] = count_by_template.get(template, 0) + 1
            examples = examples_by_template.setdefault(template, [])
            if len(examples) < 3 and message not in examples:
                examples.append(message)

        clusters = [
            {
                "template": template,
                "count": count_by_template[template],
                "examples": examples_by_template[template],
            }
            for template in sorted(
                count_by_template,
                key=lambda item: (-count_by_template[item], item),
            )[:top_n]
        ]
        data: dict[str, JsonValue] = {
            "total_errors": len(logs),
            "top_n": top_n,
            "clusters": clusters,
        }
        return _result(
            self.name,
            f"group {len(logs)} error logs by template; return top {top_n}",
            EvidenceSource.LOKI,
            data,
        )


class DeployTimeCorrelateTool(_DiagnosticTool):
    """Find errors within a symmetric time window around a deployment."""

    @property
    def name(self) -> str:
        return "deploy_time_correlate"

    @property
    def description(self) -> str:
        return "Find timestamped errors within a window before or after a deployment."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _DEPLOY_SCHEMA

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        try:
            deploy_time = _parse_timestamp(str(input["deploy_timestamp"]))
            window_seconds = float(input["window_minutes"]) * 60
            matches: list[dict[str, JsonValue]] = []
            for error in input["errors"]:
                timestamp = str(error if isinstance(error, str) else error["timestamp"])
                error_time = _parse_timestamp(timestamp)
                delta_seconds = (error_time - deploy_time).total_seconds()
                if abs(delta_seconds) <= window_seconds:
                    match: dict[str, JsonValue] = {
                        "timestamp": timestamp,
                        "minutes_from_deploy": round(delta_seconds / 60, 3),
                    }
                    if isinstance(error, dict) and "message" in error:
                        match["message"] = error["message"]
                    matches.append(match)
        except (KeyError, TypeError, ValueError) as exc:
            return ToolResult(
                success=False, data={}, error=f"Invalid timestamp input: {exc}"
            )

        matched = bool(matches)
        data: dict[str, JsonValue] = {
            "status": "match" if matched else "no_match",
            "matched": matched,
            "deploy_timestamp": str(input["deploy_timestamp"]),
            "window_minutes": float(input["window_minutes"]),
            "matches": matches,
        }
        query = (
            f"find errors within {data['window_minutes']} minutes of "
            f"deploy at {data['deploy_timestamp']}"
        )
        return _result(self.name, query, EvidenceSource.LOKI, data)


class AnomalyFlagTool(_DiagnosticTool):
    """Flag a metric value that crosses a caller-provided threshold."""

    @property
    def name(self) -> str:
        return "anomaly_flag"

    @property
    def description(self) -> str:
        return "Apply a strict above/below threshold check to a metric value."

    @property
    def input_schema(self) -> dict[str, Any]:
        return _ANOMALY_SCHEMA

    async def run(
        self, input: dict[str, JsonValue], context: InvestigationContext
    ) -> ToolResult:
        value = float(input["value"])
        threshold = float(input["threshold"])
        direction = str(input["direction"])
        anomalous = value > threshold if direction == "above" else value < threshold
        data: dict[str, JsonValue] = {
            "metric": str(input["metric"]),
            "value": value,
            "threshold": threshold,
            "direction": direction,
            "anomalous": anomalous,
        }
        query = f"check whether {input['metric']} is {direction} {threshold}"
        return _result(self.name, query, EvidenceSource.PROMETHEUS, data)


metric_baseline_diff = MetricBaselineDiffTool()
log_error_correlate = LogErrorCorrelateTool()
deploy_time_correlate = DeployTimeCorrelateTool()
anomaly_flag = AnomalyFlagTool()

DIAGNOSE_TOOLS: tuple[Tool, ...] = (
    metric_baseline_diff,
    log_error_correlate,
    deploy_time_correlate,
    anomaly_flag,
)


def register_diagnose_tools(registry: ToolRegistry) -> None:
    """Register all pure diagnosis tools in deterministic order."""
    for tool in DIAGNOSE_TOOLS:
        registry.register(tool)
