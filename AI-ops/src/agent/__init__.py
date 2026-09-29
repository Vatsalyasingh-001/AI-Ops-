"""Public factory and convenience entry points for the AI-Ops agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["create_agent", "investigate"]

if TYPE_CHECKING:
    from agent.loop import AgentLoop
    from agent.models import Incident, InvestigationResult

del TYPE_CHECKING


async def create_agent(
    provider: str,
    model: str,
    api_key: str,
    dangerous_tools: set[str] | None = None,
    max_iterations: int = 8,
) -> AgentLoop:
    """Wire the router, registry, observe/diagnose tools, gate, and loop."""
    from agent.gate import ApprovalGate
    from agent.loop import AgentLoop
    from agent.router import ModelRouter
    from agent.tools import ToolRegistry
    from agent.tools.diagnose import register_diagnose_tools
    from agent.tools.observe import register_observe_tools

    registry = ToolRegistry()
    register_observe_tools(registry)
    register_diagnose_tools(registry)
    router = ModelRouter(
        provider=provider,
        model=model,
        api_key=api_key,
        registry=registry,
    )
    gate = ApprovalGate(dangerous_tools=dangerous_tools)
    return AgentLoop(
        router=router,
        registry=registry,
        gate=gate,
        max_iterations=max_iterations,
    )


async def investigate(
    incident: Incident,
    provider: str,
    model: str,
    api_key: str,
    dangerous_tools: set[str] | None = None,
    max_iterations: int = 8,
) -> InvestigationResult:
    """Create a configured agent and run one incident investigation."""
    agent = await create_agent(
        provider=provider,
        model=model,
        api_key=api_key,
        dangerous_tools=dangerous_tools,
        max_iterations=max_iterations,
    )
    return await agent.run(incident)
