"""Typed domain models for deterministic incident investigations."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, JsonValue


class InvestigationState(StrEnum):
    """Ordered states used by the investigation loop."""

    OBSERVE = "OBSERVE"
    REASON = "REASON"
    ACT = "ACT"
    LEARN = "LEARN"


class Severity(StrEnum):
    """Supported incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentTrigger(StrEnum):
    """Supported incident trigger sources."""

    ALERTMANAGER = "alertmanager"
    WEBHOOK = "webhook"


class EvidenceSource(StrEnum):
    """Source category for collected evidence."""

    PROMETHEUS = "prometheus"
    LOKI = "loki"
    TEMPO = "tempo"
    TOPOLOGY = "topology"
    DEPLOYS = "deploys"


class RiskLevel(StrEnum):
    """Risk category assigned to a tool call."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    """Lifecycle status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class StateTransition(BaseModel):
    """Auditable record of one investigation state change."""

    from_state: InvestigationState
    to_state: InvestigationState
    reason: str
    iteration: int = Field(ge=0)
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class Incident(BaseModel):
    """An operational incident submitted for investigation."""

    id: str
    title: str
    service: str
    severity: Severity
    description: str
    created_at: AwareDatetime = Field(default_factory=_utc_now)
    triggered_by: IncidentTrigger


class EvidenceItem(BaseModel):
    """A timestamped result collected from an investigation source."""

    tool_name: str
    query: str
    result: JsonValue
    timestamp: AwareDatetime = Field(default_factory=_utc_now)
    source: EvidenceSource


class ToolCall(BaseModel):
    """A recorded invocation and result for an agent tool."""

    tool_call_id: str | None = None
    tool_name: str
    input: JsonValue
    output: JsonValue
    is_read_only: bool
    risk_level: RiskLevel


class ApprovalRequest(BaseModel):
    """Human approval metadata associated with a proposed tool call."""

    tool_call: ToolCall
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_by: str
    approved_by: str | None = None
    reason: str | None = None
    timestamp: AwareDatetime = Field(default_factory=_utc_now)


class InvestigationContext(BaseModel):
    """Mutable facts and budget for one incident investigation."""

    incident: Incident
    observations: list[EvidenceItem] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    state_transitions: list[StateTransition] = Field(default_factory=list)
    evidence_hints: list[str] = Field(default_factory=list)
    current_state: InvestigationState = InvestigationState.OBSERVE
    iteration: int = Field(default=0, ge=0)
    token_budget_remaining: int = Field(ge=0)


class InvestigationResult(BaseModel):
    """Final evidence-backed summary produced for an investigation."""

    final_summary: str
    likely_cause: str
    recommended_action: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    patterns_found: list[str] = Field(default_factory=list)
    vault_entries: list[str] = Field(default_factory=list)
