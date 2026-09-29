"""Tests for the investigation agent's domain models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.models import (
    ApprovalRequest,
    ApprovalStatus,
    EvidenceItem,
    EvidenceSource,
    Incident,
    IncidentTrigger,
    InvestigationContext,
    InvestigationResult,
    InvestigationState,
    RiskLevel,
    Severity,
    ToolCall,
)


def test_domain_models_round_trip_json() -> None:
    """All domain models preserve their values through JSON serialization."""
    timestamp = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    incident = Incident(
        id="inc-123",
        title="Elevated latency",
        service="checkout",
        severity=Severity.HIGH,
        description="Latency exceeded the service objective.",
        created_at=timestamp,
        triggered_by=IncidentTrigger.ALERTMANAGER,
    )
    evidence = EvidenceItem(
        tool_name="query_metrics",
        query="p95 latency over five minutes",
        result={"value": 2.4, "labels": ["checkout"]},
        timestamp=timestamp,
        source=EvidenceSource.PROMETHEUS,
    )
    tool_call = ToolCall(
        tool_name="query_metrics",
        input={"range_minutes": 5},
        output={"samples": [1.8, 2.4]},
        is_read_only=True,
        risk_level=RiskLevel.LOW,
    )
    approval = ApprovalRequest(
        tool_call=tool_call,
        status=ApprovalStatus.APPROVED,
        requested_by="agent",
        approved_by="operator",
        reason="Approved for the maintenance window.",
        timestamp=timestamp,
    )
    context = InvestigationContext(
        incident=incident,
        observations=[evidence],
        tool_calls=[tool_call],
        current_state=InvestigationState.ACT,
        iteration=2,
        token_budget_remaining=1200,
    )
    result = InvestigationResult(
        final_summary="Checkout latency is elevated.",
        likely_cause="A recent database slowdown.",
        recommended_action="Inspect the database connection pool.",
        evidence=[evidence],
        patterns_found=["latency increased after deployment"],
        vault_entries=["runbook://checkout-latency"],
    )

    models = [incident, evidence, tool_call, approval, context, result]
    for model in models:
        restored = type(model).model_validate_json(model.model_dump_json())
        assert restored == model


def test_incident_rejects_invalid_severity() -> None:
    """Incident severity must use one of the supported values."""
    with pytest.raises(ValidationError):
        Incident(
            id="inc-invalid",
            title="Unknown severity",
            service="checkout",
            severity="urgent",
            description="Unsupported severity value.",
            triggered_by=IncidentTrigger.WEBHOOK,
        )


def test_investigation_state_order_is_deterministic() -> None:
    """Investigation states are declared in their required loop order."""
    assert [state.value for state in InvestigationState] == [
        "OBSERVE",
        "REASON",
        "ACT",
        "LEARN",
    ]
