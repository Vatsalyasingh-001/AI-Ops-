"""Tests for the human approval gate and its fail-closed behavior."""

import asyncio

from agent.gate import ApprovalGate
from agent.models import RiskLevel, ToolCall
from agent.tools.base import ToolResult


def make_tool_call(tool_name: str = "compose_restart_service") -> ToolCall:
    """Create a representative mutating tool call."""
    return ToolCall(
        tool_name=tool_name,
        input={"service": "auth"},
        output={},
        is_read_only=False,
        risk_level=RiskLevel.HIGH,
    )


def test_approved_dangerous_tool_executes() -> None:
    """Execution waits for a human decision and invokes the registered executor."""
    executed: list[str] = []

    async def executor(tool_call: ToolCall) -> ToolResult:
        executed.append(tool_call.tool_name)
        return ToolResult(success=True, data={"restarted": tool_call.input["service"]})

    async def scenario() -> None:
        gate = ApprovalGate(executors={"compose_restart_service": executor})
        tool_call = make_tool_call()
        request = await gate.request_approval(tool_call)
        assert request.status.value == "pending"
        assert request.tool_call.tool_call_id is not None

        waiting = asyncio.create_task(gate.execute_if_approved(tool_call))
        await asyncio.sleep(0)
        assert not waiting.done()
        await gate.approve(tool_call.tool_call_id, "Approved for recovery.")

        result = await waiting
        assert await gate.get_status(tool_call.tool_call_id) == "approved"
        assert result.success is True
        assert result.data == {"restarted": "auth"}

    asyncio.run(scenario())
    assert executed == ["compose_restart_service"]


def test_registered_mutating_tool_requires_approval() -> None:
    """Mutating tools cannot bypass approval by using a non-default tool name."""

    async def executor(tool_call: ToolCall) -> ToolResult:
        return ToolResult(success=True, data="updated")

    async def scenario() -> str:
        gate = ApprovalGate(executors={"custom_mutation": executor})
        request = await gate.request_approval(make_tool_call("custom_mutation"))
        return request.status.value

    assert asyncio.run(scenario()) == "pending"


def test_denied_action_returns_safe_no_op() -> None:
    """Denied calls never invoke the executor and return a failed no-op result."""
    executed: list[str] = []

    async def executor(tool_call: ToolCall) -> ToolResult:
        executed.append(tool_call.tool_name)
        return ToolResult(success=True, data="should not execute")

    async def scenario() -> ToolResult:
        gate = ApprovalGate(executors={"compose_restart_service": executor})
        tool_call = make_tool_call()
        await gate.request_approval(tool_call)
        await gate.deny(tool_call.tool_call_id, "Change window is closed.")
        return await gate.execute_if_approved(tool_call)

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.data == ""
    assert "Change window is closed" in result.error
    assert executed == []


def test_approval_cannot_be_reused_for_modified_tool_call() -> None:
    """Changing approved arguments invalidates the call and prevents execution."""
    executed: list[str] = []

    async def executor(tool_call: ToolCall) -> ToolResult:
        executed.append(tool_call.tool_name)
        return ToolResult(success=True, data="executed")

    async def scenario() -> ToolResult:
        gate = ApprovalGate(executors={"compose_restart_service": executor})
        tool_call = make_tool_call()
        request = await gate.request_approval(tool_call)
        await gate.approve(request.tool_call.tool_call_id, "Approved for auth.")
        tool_call.input = {"service": "payments"}
        return await gate.execute_if_approved(tool_call)

    result = asyncio.run(scenario())

    assert result.success is False
    assert "differs from the approved request" in result.error
    assert executed == []


def test_pending_request_times_out_to_denied() -> None:
    """A pending request auto-denies after the configured short test timeout."""

    async def scenario() -> tuple[bool, str]:
        gate = ApprovalGate(timeout_seconds=0.01)
        tool_call = make_tool_call()
        request = await gate.request_approval(tool_call)

        approved = await gate.is_approved(tool_call.tool_call_id)
        status = await gate.get_status(request.tool_call.tool_call_id)
        return approved, status

    approved, status = asyncio.run(scenario())

    assert approved is False
    assert status == "denied"


def test_unknown_tool_defaults_to_denied() -> None:
    """Unregistered tools and unknown request IDs fail closed without execution."""

    async def scenario() -> tuple[bool, ToolResult, str]:
        gate = ApprovalGate()
        tool_call = make_tool_call("unregistered_action")
        request = await gate.request_approval(tool_call)
        result = await gate.execute_if_approved(tool_call)
        unknown_status = await gate.get_status("missing-id")
        return request.status.value == "denied", result, unknown_status

    denied, result, unknown_status = asyncio.run(scenario())

    assert denied is True
    assert result.success is False
    assert "Unknown tool" in result.error
    assert unknown_status == "denied"
