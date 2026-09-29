"""Deterministic OBSERVE → REASON → ACT → LEARN investigation loop."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Protocol

from pydantic import JsonValue

from agent.gate import ApprovalGate
from agent.models import (
    ApprovalRequest,
    Incident,
    InvestigationContext,
    InvestigationResult,
    InvestigationState,
    StateTransition,
    ToolCall,
)
from agent.router import ModelRouter, TokenBudgetExceeded
from agent.tools import Tool, ToolRegistry, ToolResult
from agent.tools.observe import OBSERVE_TOOLS

LOGGER = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[InvestigationState, frozenset[InvestigationState]] = {
    InvestigationState.OBSERVE: frozenset(
        {InvestigationState.REASON, InvestigationState.LEARN}
    ),
    InvestigationState.REASON: frozenset(
        {
            InvestigationState.OBSERVE,
            InvestigationState.ACT,
            InvestigationState.LEARN,
        }
    ),
    InvestigationState.ACT: frozenset(
        {InvestigationState.REASON, InvestigationState.LEARN}
    ),
    InvestigationState.LEARN: frozenset(),
}


class ActionRouter(Protocol):
    """Minimal asynchronous interface required from a model router."""

    async def ask(self, context: InvestigationContext) -> dict[str, JsonValue]:
        """Return a registered tool action or supported control action."""


class InvalidStateTransition(ValueError):
    """Raised when a transition is not part of the investigation state machine."""


class InvestigationLoop:
    """Run bounded model/tool steps and retain an audit trail in the context."""

    def __init__(
        self,
        router: ActionRouter | ModelRouter,
        registry: ToolRegistry | None = None,
        approval_gate: ApprovalGate | None = None,
        max_iterations: int = 12,
    ) -> None:
        """Configure router, tools, approval policy, and maximum model decisions."""
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least one")
        self.router = router
        self.registry = registry or getattr(router, "registry", ToolRegistry())
        self.approval_gate = approval_gate or ApprovalGate()
        self.max_iterations = max_iterations
        self.observe_tool_names = {tool.name for tool in OBSERVE_TOOLS}

    def transition(
        self,
        context: InvestigationContext,
        to_state: InvestigationState,
        reason: str,
    ) -> StateTransition:
        """Validate, apply, persist, and log one explicit state transition."""
        from_state = context.current_state
        if to_state not in ALLOWED_TRANSITIONS[from_state]:
            raise InvalidStateTransition(
                f"Transition {from_state.value} -> {to_state.value} is not allowed"
            )
        if not reason.strip():
            raise ValueError("Transition reason must not be empty")
        if (
            from_state == InvestigationState.REASON
            and to_state == InvestigationState.OBSERVE
        ):
            context.iteration += 1

        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            iteration=context.iteration,
        )
        context.current_state = to_state
        context.state_transitions.append(transition)
        LOGGER.info(
            "Investigation state transition",
            extra={
                "incident_id": context.incident.id,
                "from_state": from_state.value,
                "to_state": to_state.value,
                "iteration": context.iteration,
                "reason": reason,
            },
        )
        return transition

    async def run(self, context: InvestigationContext) -> InvestigationResult:
        """Run until LEARN or the configured decision limit, then summarize facts."""
        if context.current_state == InvestigationState.LEARN:
            return self._learn(context)

        for _ in range(self.max_iterations):
            try:
                action = await self.router.ask(context)
            except TokenBudgetExceeded:
                self.transition(
                    context,
                    InvestigationState.LEARN,
                    "Token budget exhausted.",
                )
                break

            if action.get("action") == "finish":
                self.transition(
                    context,
                    InvestigationState.LEARN,
                    "Router selected finish.",
                )
                break
            if action.get("action") == "observe_more":
                hint = action.get("evidence_hint")
                if not isinstance(hint, str) or not hint.strip():
                    raise ValueError("observe_more requires a non-empty evidence_hint")
                context.evidence_hints.append(hint)
                if context.current_state == InvestigationState.REASON:
                    self.transition(
                        context,
                        InvestigationState.OBSERVE,
                        "Router requested additional evidence.",
                    )
                continue

            tool_name = action.get("tool")
            tool_input = action.get("input")
            if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
                raise ValueError("Router response must contain a tool and object input")
            await self._handle_tool_action(context, tool_name, tool_input)

            if context.current_state == InvestigationState.LEARN:
                break
        else:
            if context.current_state != InvestigationState.LEARN:
                self.transition(
                    context,
                    InvestigationState.LEARN,
                    "Maximum model decision count reached.",
                )

        if context.current_state != InvestigationState.LEARN:
            self.transition(
                context,
                InvestigationState.LEARN,
                "Investigation reached a terminal condition.",
            )
        return self._learn(context)

    async def _handle_tool_action(
        self,
        context: InvestigationContext,
        tool_name: str,
        tool_input: dict[str, JsonValue],
    ) -> None:
        """Dispatch read-only tools or send mutations through the approval gate."""
        tool = self.registry.get(tool_name)
        if context.current_state == InvestigationState.OBSERVE:
            if tool_name not in self.observe_tool_names:
                self.transition(
                    context,
                    InvestigationState.REASON,
                    "Observation decision selected a non-observe tool.",
                )
            elif not tool.is_read_only:
                raise ValueError("OBSERVE state may only call read-only observe tools")

        if tool.is_read_only:
            result = await self.registry.dispatch(tool_name, tool_input, context)
            self._record_tool_result(context, tool_name, tool_input, tool, result)
            if context.current_state == InvestigationState.OBSERVE:
                self.transition(
                    context,
                    InvestigationState.REASON,
                    f"Collected evidence with {tool_name}.",
                )
            elif context.current_state == InvestigationState.ACT:
                self.transition(
                    context,
                    InvestigationState.REASON,
                    f"Completed read-only tool {tool_name}.",
                )
            return

        if context.current_state == InvestigationState.OBSERVE:
            self.transition(
                context,
                InvestigationState.REASON,
                "Mutating action requires reasoning and approval.",
            )
        if context.current_state == InvestigationState.REASON:
            self.transition(
                context,
                InvestigationState.ACT,
                f"Router proposed mutating tool {tool_name}.",
            )

        call = ToolCall(
            tool_name=tool_name,
            input=tool_input,
            output={},
            is_read_only=False,
            risk_level=tool.risk_level,
        )
        request = await self.approval_gate.request_approval(call)
        result = await self.approval_gate.execute_if_approved(call)
        call.output = result.data
        self._record_tool_result(context, tool_name, tool_input, tool, result, call)
        if context.current_state == InvestigationState.ACT:
            status = await self.approval_gate.get_status(request.tool_call.tool_call_id)
            self.transition(
                context,
                InvestigationState.LEARN,
                f"Approval-gated action completed with status {status}.",
            )

    @staticmethod
    def _record_tool_result(
        context: InvestigationContext,
        tool_name: str,
        tool_input: dict[str, JsonValue],
        tool: Tool,
        result: ToolResult,
        call: ToolCall | None = None,
    ) -> None:
        """Append a tool call and its evidence to the investigation context."""
        if call is None:
            call = ToolCall(
                tool_name=tool_name,
                input=tool_input,
                output=result.data,
                is_read_only=True,
                risk_level=tool.risk_level,
            )
        context.tool_calls.append(call)
        context.observations.extend(result.evidence_items)

    @staticmethod
    def _learn(context: InvestigationContext) -> InvestigationResult:
        """Create a deterministic summary containing only recorded evidence."""
        patterns: list[str] = []
        for call in context.tool_calls:
            if not isinstance(call.output, dict):
                continue
            clusters = call.output.get("clusters")
            if isinstance(clusters, list):
                for cluster in clusters:
                    if isinstance(cluster, dict):
                        template = cluster.get("template")
                        count = cluster.get("count")
                        if isinstance(template, str) and isinstance(count, int):
                            patterns.append(
                                f"Log pattern seen {count} time(s): {template}"
                            )
            if call.output.get("anomalous") is True:
                metric = call.output.get("metric")
                value = call.output.get("value")
                threshold = call.output.get("threshold")
                direction = call.output.get("direction")
                patterns.append(
                    f"{metric} value {value} crossed {direction} threshold {threshold}"
                )
            if call.output.get("status") == "match":
                matches = call.output.get("matches")
                if isinstance(matches, list):
                    patterns.append(
                        f"{len(matches)} error(s) occurred within the deploy "
                        "correlation window"
                    )

        return InvestigationResult(
            final_summary=(
                f"Investigation for {context.incident.id} completed with "
                f"{len(context.observations)} evidence item(s) from "
                f"{len(context.tool_calls)} tool call(s)."
            ),
            likely_cause=(
                "No likely cause was established by deterministic tool evidence."
            ),
            recommended_action=(
                "Review the collected evidence and choose an approved remediation."
            ),
            evidence=list(context.observations),
            patterns_found=patterns,
            vault_entries=[],
        )


class AgentLoop:
    """Execute a bounded, cancellable OBSERVE → REASON → ACT → LEARN cycle."""

    def __init__(
        self,
        router: ActionRouter | ModelRouter,
        registry: ToolRegistry | None = None,
        gate: ApprovalGate | None = None,
        cancellation_event: asyncio.Event | None = None,
        max_iterations: int = 8,
    ) -> None:
        """Configure model routing, registered tools, approvals, and shutdown signal."""
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least one")
        self.router = router
        self.registry = registry or getattr(router, "registry", ToolRegistry())
        self.gate = gate or ApprovalGate()
        self.cancellation_event = cancellation_event or asyncio.Event()
        self.max_iterations = max_iterations
        self.context: InvestigationContext | None = None
        self.pending_approvals: list[ApprovalRequest] = []

    async def run(
        self, incident: Incident, max_iterations: int | None = None
    ) -> InvestigationResult:
        """Run at most `max_iterations` model decisions and return the final result."""
        max_iterations = (
            self.max_iterations if max_iterations is None else max_iterations
        )
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least one")
        self.context = InvestigationContext(
            incident=incident,
            token_budget_remaining=100_000,
        )
        self.pending_approvals.clear()
        context = self.context
        decisions = 0

        while context.current_state != InvestigationState.LEARN:
            if self.cancellation_event.is_set():
                self._transition(
                    context, InvestigationState.LEARN, "Shutdown requested."
                )
                break

            if context.current_state == InvestigationState.OBSERVE:
                completed, _ = await self._await_or_cancel(self._observe(context))
                if not completed:
                    self._transition(
                        context, InvestigationState.LEARN, "Shutdown requested."
                    )
                    break
                self._transition(
                    context,
                    InvestigationState.REASON,
                    "Observation pass completed.",
                )

            if context.current_state != InvestigationState.REASON:
                continue
            if decisions >= max_iterations:
                self._transition(
                    context,
                    InvestigationState.LEARN,
                    "Maximum iteration count reached.",
                )
                break

            context.iteration = decisions
            try:
                completed, action = await self._await_or_cancel(
                    self.router.ask(context)
                )
            except TokenBudgetExceeded:
                self._transition(
                    context,
                    InvestigationState.LEARN,
                    "Token budget exhausted.",
                )
                break
            if not completed:
                self._transition(
                    context, InvestigationState.LEARN, "Shutdown requested."
                )
                break
            decisions += 1

            if action.get("action") == "finish":
                self._transition(
                    context, InvestigationState.LEARN, "Router selected finish."
                )
                break
            if action.get("action") == "observe_more":
                hint = action.get("evidence_hint")
                if not isinstance(hint, str) or not hint.strip():
                    raise ValueError("observe_more requires a non-empty evidence_hint")
                context.evidence_hints.append(hint)
                self._transition(
                    context,
                    InvestigationState.OBSERVE,
                    f"Router requested more evidence: {hint}",
                )
                continue

            tool_name = action.get("tool")
            tool_input = action.get("input")
            if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
                raise ValueError("Router response must contain a tool and object input")
            self.registry.validate_schema(tool_name, tool_input)
            await self._act(context, tool_name, tool_input)

        return self._learn_result(context)

    async def _observe(self, context: InvestigationContext) -> None:
        """Run all applicable read-only observe tools, or those matching a hint."""
        read_only_tools = self.registry.list_read_only()
        hint = context.evidence_hints[-1] if context.evidence_hints else None
        candidates = [
            tool
            for tool in read_only_tools
            if self._observe_input(tool, context) is not None
        ]
        if hint:
            normalized_hint = hint.casefold()
            selected = [
                tool
                for tool in candidates
                if normalized_hint in tool.name.casefold()
                or normalized_hint in tool.description.casefold()
                or any(
                    word in tool.name.casefold() or word in tool.description.casefold()
                    for word in normalized_hint.split()
                )
            ]
            if selected:
                candidates = selected

        for tool in candidates:
            if self.cancellation_event.is_set():
                return
            tool_input = self._observe_input(tool, context)
            assert tool_input is not None
            try:
                result = await self.registry.dispatch(tool.name, tool_input, context)
            except Exception as exc:
                result = ToolResult(
                    success=False,
                    data={},
                    error=f"Observe tool failed: {exc}",
                )
            call = ToolCall(
                tool_name=tool.name,
                input=tool_input,
                output=result.data,
                is_read_only=True,
                risk_level=tool.risk_level,
            )
            context.tool_calls.append(call)
            context.observations.extend(result.evidence_items)
            LOGGER.debug(
                "Observe tool completed",
                extra={
                    "incident_id": context.incident.id,
                    "tool_name": tool.name,
                    "success": result.success,
                },
            )

    def _observe_input(
        self, tool: Tool, context: InvestigationContext
    ) -> dict[str, JsonValue] | None:
        """Derive safe observe arguments from schemas and incident facts only."""
        tool_name = tool.name
        if tool_name == "prom_query":
            return {"query": f"incident signals for {context.incident.service}"}
        if tool_name in {"loki_search", "tempo_trace", "topology_get", "deploys_list"}:
            return {"service": context.incident.service}

        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        tool_input: dict[str, JsonValue] = {}
        for key in required:
            definition = properties.get(key, {})
            if "default" in definition:
                tool_input[key] = definition["default"]
            elif key == "service":
                tool_input[key] = context.incident.service
            elif key == "query":
                tool_input[key] = (
                    context.evidence_hints[-1]
                    if context.evidence_hints
                    else context.incident.description
                )
            elif definition.get("enum"):
                tool_input[key] = definition["enum"][0]
            else:
                return None
        return tool_input

    async def _act(
        self,
        context: InvestigationContext,
        tool_name: str,
        tool_input: dict[str, JsonValue],
    ) -> None:
        """Execute read-only tools immediately and mutating tools only via approval."""
        tool = self.registry.get(tool_name)
        self._transition(
            context,
            InvestigationState.ACT,
            f"Router selected tool {tool_name}.",
        )
        call = ToolCall(
            tool_name=tool_name,
            input=tool_input,
            output={},
            is_read_only=self.gate.is_read_only(tool),
            risk_level=tool.risk_level,
        )

        if self.gate.is_read_only(tool):
            try:
                result = await self.registry.dispatch(tool_name, tool_input, context)
            except Exception as exc:
                result = ToolResult(success=False, data={}, error=str(exc))
        else:
            request = await self.gate.request_approval(call)
            self.pending_approvals.append(request)
            LOGGER.warning(
                "Tool approval requested",
                extra={
                    "incident_id": context.incident.id,
                    "tool_name": tool_name,
                    "tool_call_id": request.tool_call.tool_call_id,
                    "status": request.status.value,
                },
            )
            completed, gated_result = await self._await_or_cancel(
                self.gate.execute_if_approved(call)
            )
            if not completed:
                tool_call_id = request.tool_call.tool_call_id
                if (
                    tool_call_id
                    and await self.gate.get_status(tool_call_id) == "pending"
                ):
                    await self.gate.deny(tool_call_id, "Investigation cancelled.")
                return
            result = gated_result
            status = await self.gate.get_status(request.tool_call.tool_call_id)
            LOGGER.warning(
                "Tool approval decision",
                extra={
                    "incident_id": context.incident.id,
                    "tool_name": tool_name,
                    "tool_call_id": request.tool_call.tool_call_id,
                    "status": status,
                    "error": result.error,
                },
            )

        call.output = result.data
        context.tool_calls.append(call)
        context.observations.extend(result.evidence_items)
        LOGGER.debug(
            "Tool call completed",
            extra={
                "incident_id": context.incident.id,
                "tool_name": tool_name,
                "is_read_only": call.is_read_only,
                "success": result.success,
                "error": result.error,
            },
        )
        if self.cancellation_event.is_set():
            self._transition(context, InvestigationState.LEARN, "Shutdown requested.")
            return
        self._transition(
            context,
            InvestigationState.REASON,
            f"Tool {tool_name} completed; success={result.success}.",
        )

    async def _await_or_cancel(
        self, awaitable: Awaitable[object]
    ) -> tuple[bool, object]:
        """Race an operation against the shutdown event and cancel promptly."""
        operation = asyncio.ensure_future(awaitable)
        cancellation = asyncio.create_task(self.cancellation_event.wait())
        done, _ = await asyncio.wait(
            {operation, cancellation}, return_when=asyncio.FIRST_COMPLETED
        )
        if cancellation in done and self.cancellation_event.is_set():
            operation.cancel()
            try:
                await operation
            except asyncio.CancelledError:
                pass
            return False, None
        cancellation.cancel()
        try:
            await cancellation
        except asyncio.CancelledError:
            pass
        return True, await operation

    def _transition(
        self,
        context: InvestigationContext,
        to_state: InvestigationState,
        reason: str,
    ) -> None:
        """Persist and log a validated state change."""
        previous = context.current_state
        if to_state not in ALLOWED_TRANSITIONS[previous]:
            raise InvalidStateTransition(
                f"Transition {previous.value} -> {to_state.value} is not allowed"
            )
        transition = StateTransition(
            from_state=previous,
            to_state=to_state,
            reason=reason,
            iteration=context.iteration,
        )
        context.current_state = to_state
        context.state_transitions.append(transition)
        LOGGER.info(
            "Investigation state transition",
            extra={
                "incident_id": context.incident.id,
                "from_state": previous.value,
                "to_state": to_state.value,
                "iteration": context.iteration,
                "reason": reason,
            },
        )

    @staticmethod
    def _learn_result(context: InvestigationContext) -> InvestigationResult:
        """Compose a deterministic evidence-backed final investigation result."""
        cause = "No likely cause was established by the collected evidence."
        patterns: list[str] = []
        for item in context.observations:
            result = item.result
            if isinstance(result, dict):
                if result.get("status") == "match":
                    cause = (
                        "Errors were observed within the deployment correlation window."
                    )
                    patterns.append("Errors correlated with a recent deployment.")
                summary = result.get("summary")
                if isinstance(summary, str):
                    patterns.append(summary)
                clusters = result.get("clusters")
                if isinstance(clusters, list):
                    for cluster in clusters:
                        if isinstance(cluster, dict) and isinstance(
                            cluster.get("template"), str
                        ):
                            patterns.append(str(cluster["template"]))
        if context.evidence_hints:
            recommendation = (
                "Review the collected evidence, including requested follow-up signals, "
                "before selecting an approved remediation."
            )
        else:
            recommendation = (
                "Review the collected evidence before selecting an approved "
                "remediation."
            )
        return InvestigationResult(
            final_summary=(
                f"Investigation for {context.incident.id} completed with "
                f"{len(context.observations)} evidence item(s) and "
                f"{len(context.tool_calls)} tool call(s)."
            ),
            likely_cause=cause,
            recommended_action=recommendation,
            evidence=list(context.observations),
            patterns_found=patterns,
            vault_entries=[],
        )
