"""Tests for deterministic pure-computation diagnosis tools."""

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
from agent.tools.diagnose import register_diagnose_tools


def make_registry() -> ToolRegistry:
    """Create a registry containing all diagnosis tools."""
    registry = ToolRegistry()
    register_diagnose_tools(registry)
    return registry


def make_context() -> InvestigationContext:
    """Create a minimal context for offline tool invocations."""
    return InvestigationContext(
        incident=Incident(
            id="inc-diagnose",
            title="Diagnosis fixture",
            service="auth",
            severity=Severity.HIGH,
            description="Hand-crafted local test data.",
            triggered_by=IncidentTrigger.ALERTMANAGER,
        ),
        token_budget_remaining=100,
    )


def test_metric_baseline_diff_computes_percentage_change() -> None:
    """Metric deltas use (current - baseline) / baseline as a percentage."""
    registry = make_registry()
    result = asyncio.run(
        registry.dispatch(
            "metric_baseline_diff",
            {"metric": "error_rate", "baseline": 2, "current": 3},
            make_context(),
        )
    )

    assert result.success is True
    assert result.data["absolute_change"] == 1
    assert result.data["change_percent"] == 50
    assert result.evidence_items[0].source == EvidenceSource.PROMETHEUS


def test_metric_baseline_diff_marks_zero_baseline_undefined() -> None:
    """A zero baseline reports the absolute change without dividing by zero."""
    registry = make_registry()
    result = asyncio.run(
        registry.dispatch(
            "metric_baseline_diff",
            {"metric": "request_count", "baseline": 0, "current": 5},
            make_context(),
        )
    )

    assert result.data["change_percent"] is None
    assert result.data["percentage_change_defined"] is False


def test_log_error_correlate_clusters_templates_and_returns_top_n() -> None:
    """Dynamic numbers are normalized and clusters are ranked by frequency."""
    registry = make_registry()
    logs = [
        {"message": "Request 101 failed with status 500"},
        {"message": "request 202 failed with status 500"},
        "request 303 failed with status 500",
        {"message": "database connection to 10.0.0.1 timed out"},
        {"message": "database connection to 10.0.0.2 timed out"},
    ]
    result = asyncio.run(
        registry.dispatch(
            "log_error_correlate",
            {"logs": logs, "top_n": 1},
            make_context(),
        )
    )

    assert result.data["total_errors"] == 5
    assert result.data["clusters"] == [
        {
            "template": "request <num> failed with status <num>",
            "count": 3,
            "examples": [
                "Request 101 failed with status 500",
                "request 202 failed with status 500",
                "request 303 failed with status 500",
            ],
        }
    ]
    assert result.evidence_items[0].source == EvidenceSource.LOKI


def test_deploy_time_correlate_finds_nearby_errors_and_no_match() -> None:
    """Only errors within the inclusive symmetric time window are returned."""
    registry = make_registry()
    deploy_input = {
        "deploy_timestamp": "2026-09-30T12:00:00Z",
        "window_minutes": 10,
        "errors": [
            {"timestamp": "2026-09-30T11:55:00Z", "message": "before deploy"},
            {"timestamp": "2026-09-30T12:07:00Z", "message": "after deploy"},
            {"timestamp": "2026-09-30T12:11:00Z", "message": "outside window"},
        ],
    }
    result = asyncio.run(
        registry.dispatch("deploy_time_correlate", deploy_input, make_context())
    )
    no_match = asyncio.run(
        registry.dispatch(
            "deploy_time_correlate",
            {
                "deploy_timestamp": "2026-09-30T12:00:00Z",
                "window_minutes": 5,
                "errors": ["2026-09-30T12:20:00Z"],
            },
            make_context(),
        )
    )

    assert result.data["status"] == "match"
    assert [item["minutes_from_deploy"] for item in result.data["matches"]] == [
        -5,
        7,
    ]
    assert no_match.data["status"] == "no_match"
    assert no_match.data["matches"] == []
    assert result.evidence_items[0].source == EvidenceSource.LOKI


@pytest.mark.parametrize(
    ("value", "threshold", "direction", "expected"),
    [(11, 10, "above", True), (4, 5, "below", True), (10, 10, "above", False)],
)
def test_anomaly_flag_applies_strict_threshold(
    value: int, threshold: int, direction: str, expected: bool
) -> None:
    """Threshold comparisons are strict and deterministic."""
    registry = make_registry()
    result = asyncio.run(
        registry.dispatch(
            "anomaly_flag",
            {
                "metric": "latency_ms",
                "value": value,
                "threshold": threshold,
                "direction": direction,
            },
            make_context(),
        )
    )

    assert result.data["anomalous"] is expected
    assert result.evidence_items[0].source == EvidenceSource.PROMETHEUS


def test_diagnose_tools_are_read_only_and_validate_schemas() -> None:
    """All diagnose tools are read-only and reject invalid schema inputs."""
    registry = make_registry()
    assert [tool.name for tool in registry.list_read_only()] == [
        "metric_baseline_diff",
        "log_error_correlate",
        "deploy_time_correlate",
        "anomaly_flag",
    ]

    for tool_name in (tool.name for tool in registry.list_read_only()):
        with pytest.raises(JsonSchemaValidationError):
            registry.validate_schema(tool_name, {})
