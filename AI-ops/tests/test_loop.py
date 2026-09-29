"""Tests for deterministic investigation orchestration and state transitions."""

import asyncio
from collections.abc import Sequence
from time import perf_counter
from typing import Any

import pytest

from agent.loop import AgentLoop, InvalidStateTransition, InvestigationLoop
from agent.models import (
    Incident,
    IncidentTrigger,
    InvestigationContext,
    InvestigationState,
    RiskLevel,
    Severity,
    ToolCall,
)
from agent.tools import Tool, ToolRegistry, ToolResult
from agent.tools.diagnose import register_diagnose_tools
from agent.tools.observe import register_observe_tools


class ActionTool(Tool):
    """Small configurable fake tool for ACT and approval-path testing."""

    def __init__(self, name: str, read_only: bool, required: bool = True) -> None:
        self._name = name
        self._read_only = read_only
        self._required = required

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Test tool {self._name}."

    @property
    def input_schema(self) -> dict[str, Any]:
        properties = {"service": {"type": "string"}} if self._required else {}
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if self._required:
            schema["required"] = ["service"]
        return schema

    @property
    def is_read_only(self) -> bool:
        return self._read_only

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW if self._read_only else RiskLevel.HIGH

    async def run(
        self, input: dict[str, Any], context: InvestigationContext
    ) -> ToolResult:
        return ToolResult(success=True, data={"tool": self.name, "input": input})


class ActionSequenceRouter:
    """Return predefined actions and reduce context budget on each decision."""

    def __init__(self, actions: Sequence[dict[str, Any]]) -> None:
        self.actions = list(actions)
        self.calls = 0

    async def ask(self, context: InvestigationContext) -> dict[str, Any]:
        self.calls += 1
        context.token_budget_remaining -= 10
        return self.actions.pop(0)


def make_agent_registry() -> ToolRegistry:
    """Create tools for auto-observe, read-only ACT, and approved mutation."""
    registry = ToolRegistry()
    registry.register(ActionTool("baseline_reader", True, required=False))
    registry.register(ActionTool("read_auth", True))
    registry.register(ActionTool("compose_restart_service", False))
    return registry


class SequenceRouter:
    """Test router that returns predetermined actions in order."""

    def __init__(self, actions: Sequence[dict[str, Any]]) -> None:
        self.actions = list(actions)
        self.contexts: list[InvestigationContext] = []

    async def ask(self, context: InvestigationContext) -> dict[str, Any]:
        self.contexts.append(context.model_copy(deep=True))
        return self.actions.pop(0)


def make_context() -> InvestigationContext:
    """Create a minimal investigation context for loop tests."""
    return InvestigationContext(
        incident=Incident(
            id="inc-loop",
            title="Loop test incident",
            service="auth",
            severity=Severity.HIGH,
            description="An offline loop test.",
            triggered_by=IncidentTrigger.ALERTMANAGER,
        ),
        token_budget_remaining=100,
    )


def make_registry() -> ToolRegistry:
    """Create a registry containing all fake observe and diagnosis tools."""
    registry = ToolRegistry()
    register_observe_tools(registry)
    register_diagnose_tools(registry)
    return registry


def test_loop_observes_reasons_and_learns_with_transition_log() -> None:
    """Read-only actions collect evidence and every state change is persisted."""
    router = SequenceRouter(
        [
            {"tool": "prom_query", "input": {"query": "5xx rate"}},
            {
                "tool": "anomaly_flag",
                "input": {
                    "metric": "5xx rate",
                    "value": 8.7,
                    "threshold": 5,
                    "direction": "above",
                },
            },
            {"action": "finish"},
        ]
    )
    context = make_context()
    loop = InvestigationLoop(router, make_registry())

    result = asyncio.run(loop.run(context))

    assert context.current_state == InvestigationState.LEARN
    assert [
        (event.from_state.value, event.to_state.value)
        for event in context.state_transitions
    ] == [("OBSERVE", "REASON"), ("REASON", "LEARN")]
    assert len(context.observations) == 2
    assert len(context.tool_calls) == 2
    assert result.evidence == context.observations
    assert result.patterns_found == ["5xx rate value 8.7 crossed above threshold 5.0"]
    assert "2 evidence item(s)" in result.final_summary


def test_loop_returns_to_observe_for_requested_evidence() -> None:
    """An observe-more control action is recorded before the next observation."""
    router = SequenceRouter(
        [
            {"tool": "prom_query", "input": {"query": "5xx rate"}},
            {"action": "observe_more", "evidence_hint": "Search auth errors"},
            {"tool": "loki_search", "input": {"service": "auth"}},
            {"action": "finish"},
        ]
    )
    context = make_context()
    loop = InvestigationLoop(router, make_registry())

    asyncio.run(loop.run(context))

    assert context.evidence_hints == ["Search auth errors"]
    assert context.iteration == 1
    assert [
        (event.from_state.value, event.to_state.value)
        for event in context.state_transitions
    ] == [
        ("OBSERVE", "REASON"),
        ("REASON", "OBSERVE"),
        ("OBSERVE", "REASON"),
        ("REASON", "LEARN"),
    ]
    assert "Search auth errors" in router.contexts[2].evidence_hints


def test_loop_stops_at_configured_decision_limit() -> None:
    """The bounded loop transitions to LEARN instead of cycling forever."""
    router = SequenceRouter(
        [
            {"tool": "prom_query", "input": {"query": "5xx rate"}},
            {"action": "observe_more", "evidence_hint": "Check again"},
        ]
    )
    context = make_context()
    loop = InvestigationLoop(router, make_registry(), max_iterations=2)

    asyncio.run(loop.run(context))

    assert context.current_state == InvestigationState.LEARN
    assert context.state_transitions[-1].reason == (
        "Maximum model decision count reached."
    )


def test_loop_rejects_illegal_transition_without_mutating_context() -> None:
    """Illegal edges are rejected and do not update state or transition history."""
    context = make_context()
    loop = InvestigationLoop(SequenceRouter([]), make_registry())

    with pytest.raises(InvalidStateTransition, match="OBSERVE -> ACT"):
        loop.transition(context, InvestigationState.ACT, "Skip reasoning")

    assert context.current_state == InvestigationState.OBSERVE
    assert context.state_transitions == []


def test_agent_loop_happy_path_with_approved_mutation() -> None:
    """The full loop observes, acts read-only, then runs an approved risky tool."""

    async def scenario() -> tuple[Any, AgentLoop, list[str]]:
        actions = ActionSequenceRouter(
            [
                {"tool": "read_auth", "input": {"service": "auth"}},
                {
                    "tool": "compose_restart_service",
                    "input": {"service": "auth"},
                },
                {"action": "finish"},
            ]
        )
        executions: list[str] = []

        async def restart(tool_call: ToolCall) -> ToolResult:
            executions.append(tool_call.tool_name)
            return ToolResult(success=True, data={"restarted": "auth"})

        from agent.gate import ApprovalGate

        gate = ApprovalGate(executors={"compose_restart_service": restart})
        loop = AgentLoop(actions, make_agent_registry(), gate)
        task = asyncio.create_task(loop.run(make_context().incident))
        while not loop.pending_approvals:
            if task.done():
                await task
            await asyncio.sleep(0)
        request = loop.pending_approvals[0]
        await gate.approve(request.tool_call.tool_call_id, "Approved in test.")
        result = await task
        return result, loop, executions

    result, loop, executions = asyncio.run(scenario())
    assert loop.context is not None
    assert loop.context.current_state == InvestigationState.LEARN
    assert [
        (item.from_state.value, item.to_state.value)
        for item in loop.context.state_transitions
    ] == [
        ("OBSERVE", "REASON"),
        ("REASON", "ACT"),
        ("ACT", "REASON"),
        ("REASON", "ACT"),
        ("ACT", "REASON"),
        ("REASON", "LEARN"),
    ]
    assert executions == ["compose_restart_service"]
    assert result.evidence == loop.context.observations


def test_agent_loop_denial_returns_to_reason_with_reduced_budget() -> None:
    """A denied call is recorded, budget is reduced, and the loop continues."""

    async def scenario() -> tuple[Any, AgentLoop, int]:
        router = ActionSequenceRouter(
            [
                {
                    "tool": "compose_restart_service",
                    "input": {"service": "auth"},
                },
                {"action": "finish"},
            ]
        )

        async def restart(tool_call: ToolCall) -> ToolResult:
            pytest.fail("Denied tool must not be executed")

        from agent.gate import ApprovalGate

        gate = ApprovalGate(executors={"compose_restart_service": restart})
        loop = AgentLoop(router, make_agent_registry(), gate)
        task = asyncio.create_task(loop.run(make_context().incident))
        while not loop.pending_approvals:
            if task.done():
                await task
            await asyncio.sleep(0)
        request = loop.pending_approvals[0]
        await gate.deny(request.tool_call.tool_call_id, "Denied by test.")
        result = await task
        return result, loop, router.calls

    result, loop, calls = asyncio.run(scenario())
    assert loop.context is not None
    assert calls == 2
    assert loop.context.token_budget_remaining == 99_980
    assert loop.context.current_state == InvestigationState.LEARN
    denied_call = loop.context.tool_calls[-1]
    assert denied_call.tool_name == "compose_restart_service"
    assert denied_call.output == ""
    assert "No likely cause" in result.likely_cause


def test_agent_loop_respects_max_iteration_cap() -> None:
    """The loop transitions to LEARN once its configured decision count is reached."""
    router = ActionSequenceRouter([{"tool": "read_auth", "input": {"service": "auth"}}])
    loop = AgentLoop(router, make_agent_registry())

    asyncio.run(loop.run(make_context().incident, max_iterations=1))

    assert router.calls == 1
    assert loop.context is not None
    assert loop.context.current_state == InvestigationState.LEARN
    assert loop.context.state_transitions[-1].reason == (
        "Maximum iteration count reached."
    )


def test_stubbed_full_investigation_completes_under_two_seconds() -> None:
    """A full local stub-backed investigation stays within the latency target."""
    router = ActionSequenceRouter(
        [
            {"tool": "tempo_trace", "input": {"service": "auth"}},
            {"action": "finish"},
        ]
    )
    loop = AgentLoop(router, make_registry())
    started = perf_counter()

    result = asyncio.run(loop.run(make_context().incident))

    elapsed = perf_counter() - started
    assert result.evidence
    assert loop.context is not None
    assert loop.context.current_state == InvestigationState.LEARN
    assert elapsed < 2.0


def test_agent_loop_cancels_mid_router_call() -> None:
    """Setting the shutdown event interrupts a blocked router and learns safely."""

    class BlockingRouter:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def ask(self, context: InvestigationContext) -> dict[str, Any]:
            self.started.set()
            await asyncio.Event().wait()
            return {"action": "finish"}

    async def scenario() -> tuple[Any, AgentLoop]:
        router = BlockingRouter()
        loop = AgentLoop(router, make_agent_registry())
        task = asyncio.create_task(loop.run(make_context().incident))
        await router.started.wait()
        loop.cancellation_event.set()
        result = await task
        return result, loop

    result, loop = asyncio.run(scenario())
    assert loop.context is not None
    assert loop.context.current_state == InvestigationState.LEARN
    assert loop.context.state_transitions[-1].reason == "Shutdown requested."
    assert "completed" in result.final_summary
