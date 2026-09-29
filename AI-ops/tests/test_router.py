"""Tests for the LiteLLM model router without real provider requests."""

import asyncio
import json
from typing import Any

import pytest

from agent.models import Incident, IncidentTrigger, InvestigationContext, Severity
from agent.router import ModelRouter, TokenBudgetExceeded


def make_context(token_budget: int = 500) -> InvestigationContext:
    """Create a minimal context for router tests."""
    return InvestigationContext(
        incident=Incident(
            id="inc-router",
            title="Router test",
            service="auth",
            severity=Severity.HIGH,
            description="An offline test incident.",
            triggered_by=IncidentTrigger.ALERTMANAGER,
        ),
        token_budget_remaining=token_budget,
    )


def make_response(
    message: dict[str, Any], prompt_tokens: int = 20, completion_tokens: int = 10
) -> dict[str, Any]:
    """Create the LiteLLM response subset consumed by the router."""
    return {
        "choices": [{"message": message}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


def make_router() -> ModelRouter:
    """Create a router with placeholder test credentials."""
    return ModelRouter("openai", "gpt-test", "not-a-real-key")


def test_router_extracts_tool_call_and_accounts_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A function call is normalized and both token directions reduce budget."""
    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return make_response(
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "prom_query",
                            "arguments": json.dumps({"query": "5xx rate"}),
                        }
                    }
                ]
            },
            prompt_tokens=35,
            completion_tokens=12,
        )

    monkeypatch.setattr("agent.router._acompletion", fake_acompletion)
    router = make_router()
    context = make_context()

    result = asyncio.run(router.ask(context))

    assert result == {"tool": "prom_query", "input": {"query": "5xx rate"}}
    assert context.token_budget_remaining == 453
    assert router.input_tokens_used == 35
    assert router.output_tokens_used == 12
    assert calls[0]["model"] == "openai/gpt-test"
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert any(
        schema["function"]["name"] == "prom_query" for schema in calls[0]["tools"]
    )


def test_router_retries_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid JSON is retried and token usage from both calls is counted."""
    responses = iter(
        [
            make_response({"content": "this is not json"}),
            make_response({"content": "still not JSON"}),
            make_response(
                {"content": '{"action":"observe_more","evidence_hint":"check logs"}'}
            ),
        ]
    )
    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return next(responses)

    monkeypatch.setattr("agent.router._acompletion", fake_acompletion)
    router = make_router()
    context = make_context()

    result = asyncio.run(router.ask(context))

    assert result == {"action": "observe_more", "evidence_hint": "check logs"}
    assert len(calls) == 3
    assert len(calls[0]["messages"]) < len(calls[1]["messages"])
    assert len(calls[1]["messages"]) < len(calls[2]["messages"])
    assert context.token_budget_remaining == 410
    assert router.input_tokens_used == 60
    assert router.output_tokens_used == 30


def test_router_raises_when_budget_is_already_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No completion request is made after the context budget reaches zero."""

    async def unexpected_call(**kwargs: Any) -> dict[str, Any]:
        pytest.fail("LiteLLM must not be called with an exhausted budget")

    monkeypatch.setattr("agent.router._acompletion", unexpected_call)

    with pytest.raises(TokenBudgetExceeded, match="exhausted"):
        asyncio.run(make_router().ask(make_context(token_budget=0)))


def test_router_raises_when_response_consumes_remaining_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completion that uses the full remaining budget raises immediately."""

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        return make_response(
            {"content": '{"action":"finish"}'},
            prompt_tokens=40,
            completion_tokens=10,
        )

    monkeypatch.setattr("agent.router._acompletion", fake_acompletion)
    context = make_context(token_budget=50)

    with pytest.raises(TokenBudgetExceeded, match="exhausted"):
        asyncio.run(make_router().ask(context))

    assert context.token_budget_remaining == 0
