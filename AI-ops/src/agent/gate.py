"""Human approval gate for potentially mutating tool calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from agent.models import ApprovalRequest, ApprovalStatus, ToolCall
from agent.tools.base import ToolResult

DEFAULT_DANGEROUS_TOOLS = {
    "compose_restart_service",
    "compose_scale_service",
    "compose_rollback_image",
    "db_kill_query",
}
ApprovalState = Literal["pending", "approved", "denied"]
ToolExecutor = Callable[[ToolCall], Awaitable[ToolResult]]


@dataclass
class _ApprovalRecord:
    """Internal request state and notification event for one tool call."""

    request: ApprovalRequest
    changed: asyncio.Event


class ApprovalGate:
    """Fail-closed approval gate with deterministic per-instance request IDs."""

    def __init__(
        self,
        dangerous_tools: set[str] | None = None,
        timeout_seconds: float = 300.0,
        executors: dict[str, ToolExecutor] | None = None,
    ) -> None:
        """Configure dangerous tools, approval timeout, and known executors."""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        self.dangerous_tools = set(
            DEFAULT_DANGEROUS_TOOLS if dangerous_tools is None else dangerous_tools
        )
        self.timeout_seconds = timeout_seconds
        self.executors = dict(executors or {})
        self._records: dict[str, _ApprovalRecord] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def request_approval(self, tool_call: ToolCall) -> ApprovalRequest:
        """Store a pending dangerous action or immediately fail closed otherwise."""
        async with self._lock:
            tool_call_id = f"tool-call-{self._next_id:06d}"
            self._next_id += 1
            tool_call.tool_call_id = tool_call_id

            is_known = (
                tool_call.tool_name in self.dangerous_tools
                or tool_call.tool_name in self.executors
            )
            if not is_known:
                status = ApprovalStatus.DENIED
                reason = "Unknown tool; execution is denied by default."
            elif (
                tool_call.tool_name in self.dangerous_tools
                or not tool_call.is_read_only
            ):
                status = ApprovalStatus.PENDING
                reason = None
            else:
                status = ApprovalStatus.APPROVED
                reason = "Registered non-dangerous tool does not require approval."

            request = ApprovalRequest(
                tool_call=tool_call.model_copy(deep=True),
                status=status,
                requested_by="agent",
                reason=reason,
            )
            changed = asyncio.Event()
            if status != ApprovalStatus.PENDING:
                changed.set()
            self._records[tool_call_id] = _ApprovalRecord(request, changed)
            return request.model_copy(deep=True)

    async def get_status(self, tool_call_id: str) -> ApprovalState:
        """Return a request's current status; unknown identifiers are denied."""
        record = self._records.get(tool_call_id)
        if record is None:
            return "denied"
        return record.request.status.value

    @staticmethod
    def is_read_only(tool: object) -> bool:
        """Return a tool's declared read-only status; unknown objects fail closed."""
        return getattr(tool, "is_read_only", False) is True

    async def approve(self, tool_call_id: str, reason: str) -> None:
        """Approve a pending request and wake any callers awaiting its decision."""
        await self._set_status(tool_call_id, ApprovalStatus.APPROVED, reason)

    async def deny(self, tool_call_id: str, reason: str) -> None:
        """Deny a pending request and wake any callers awaiting its decision."""
        await self._set_status(tool_call_id, ApprovalStatus.DENIED, reason)

    async def _set_status(
        self, tool_call_id: str, status: ApprovalStatus, reason: str
    ) -> None:
        """Set a pending request to a terminal state exactly once."""
        async with self._lock:
            record = self._records.get(tool_call_id)
            if record is None:
                raise KeyError(f"Unknown tool call: {tool_call_id}")
            if record.request.status != ApprovalStatus.PENDING:
                raise ValueError(f"Tool call is already {record.request.status.value}")
            record.request.status = status
            record.request.approved_by = (
                "human" if status == ApprovalStatus.APPROVED else None
            )
            record.request.reason = reason
            record.changed.set()

    async def is_approved(self, tool_call_id: str) -> bool:
        """Wait for approval, automatically denying pending requests on timeout."""
        record = self._records.get(tool_call_id)
        if record is None:
            return False
        if record.request.status == ApprovalStatus.PENDING:
            try:
                await asyncio.wait_for(
                    record.changed.wait(), timeout=self.timeout_seconds
                )
            except TimeoutError:
                async with self._lock:
                    if record.request.status == ApprovalStatus.PENDING:
                        record.request.status = ApprovalStatus.DENIED
                        record.request.reason = "Approval timed out; request denied."
                        record.changed.set()
        return record.request.status == ApprovalStatus.APPROVED

    async def execute_if_approved(self, tool_call: ToolCall) -> ToolResult:
        """Execute a registered tool only after approval; otherwise return a no-op."""
        tool_call_id = tool_call.tool_call_id
        if not tool_call_id or tool_call_id not in self._records:
            return self._no_op("No approval request exists; execution denied.")

        approved_call = self._records[tool_call_id].request.tool_call
        if tool_call != approved_call:
            return self._no_op(
                "Tool call differs from the approved request; execution denied."
            )

        if not await self.is_approved(tool_call_id):
            record = self._records[tool_call_id]
            reason = record.request.reason or "Approval denied."
            return self._no_op(f"Execution denied: {reason}")

        executor = self.executors.get(tool_call.tool_name)
        if executor is None:
            return self._no_op("No executor is registered for this tool.")
        return await executor(approved_call)

    @staticmethod
    def _no_op(error: str) -> ToolResult:
        """Return a safe failed result without performing side effects."""
        return ToolResult(success=False, data="", error=error)
