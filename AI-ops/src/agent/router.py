"""LiteLLM-backed model routing for the investigation agent."""

from __future__ import annotations

import json
from typing import Any

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import JsonValue

from agent.models import InvestigationContext
from agent.tools import ToolRegistry
from agent.tools.diagnose import register_diagnose_tools
from agent.tools.observe import register_observe_tools

MAX_PARSE_RETRIES = 2


class TokenBudgetExceeded(RuntimeError):
    """Raised when an LLM call would exhaust an investigation token budget."""


class _OutputParseError(ValueError):
    """Indicates that a model response does not match a supported action shape."""


async def _acompletion(**kwargs: Any) -> Any:
    """Import LiteLLM only when making a real request to avoid import-time I/O."""
    import litellm

    return await litellm.acompletion(**kwargs)


class ModelRouter:
    """Route investigation prompts through LiteLLM and parse structured actions."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        registry: ToolRegistry | None = None,
    ) -> None:
        """Create a router for a provider/model using the supplied secret key."""
        if not provider.strip():
            raise ValueError("provider must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if not api_key:
            raise ValueError("api_key must not be empty")

        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.litellm_model = model if "/" in model else f"{provider}/{model}"
        self.registry = registry or self._default_registry()
        self.input_tokens_used = 0
        self.output_tokens_used = 0

    @staticmethod
    def _default_registry() -> ToolRegistry:
        """Create the deterministic built-in fake observe/diagnose registry."""
        registry = ToolRegistry()
        register_observe_tools(registry)
        register_diagnose_tools(registry)
        return registry

    async def build_system_prompt(self, context: InvestigationContext) -> str:
        """Build a stable system prompt containing only explicit incident context."""
        incident = context.incident.model_dump(mode="json")
        observations = [item.model_dump(mode="json") for item in context.observations]
        tool_calls = [item.model_dump(mode="json") for item in context.tool_calls]
        return "\n".join(
            (
                "You are an evidence-grounded incident investigation assistant.",
                "Do not invent facts; use only the supplied incident and evidence.",
                "Choose one registered tool, or return a control action.",
                "Return exactly one JSON object: "
                '{"tool":"registered_tool_name","input":{...}}, '
                '{"action":"finish"}, or '
                '{"action":"observe_more","evidence_hint":"..."}.',
                "A tool call must use that tool's declared input schema.",
                f"Investigation state: {context.current_state.value}",
                f"Iteration: {context.iteration}",
                f"Token budget remaining: {context.token_budget_remaining}",
                f"Incident: {json.dumps(incident, sort_keys=True)}",
                f"Observations: {json.dumps(observations, sort_keys=True)}",
                f"Prior tool calls: {json.dumps(tool_calls, sort_keys=True)}",
                f"Evidence requests: {json.dumps(context.evidence_hints)}",
            )
        )

    def _tool_schemas(self) -> list[dict[str, JsonValue]]:
        """Return OpenAI-compatible schemas for registered and control tools."""
        schemas: list[dict[str, JsonValue]] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self.registry.list_all()
        ]
        schemas.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "description": "Finish the investigation.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "observe_more",
                        "description": "Request more evidence before deciding.",
                        "parameters": {
                            "type": "object",
                            "properties": {"evidence_hint": {"type": "string"}},
                            "required": ["evidence_hint"],
                            "additionalProperties": False,
                        },
                    },
                },
            ]
        )
        return schemas

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        """Read a response field from either a mapping or an SDK object."""
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _account_tokens(self, response: Any, context: InvestigationContext) -> None:
        """Add LiteLLM usage to cumulative counters and reduce context budget."""
        usage = self._get(response, "usage")
        prompt_tokens = self._get(usage, "prompt_tokens")
        completion_tokens = self._get(usage, "completion_tokens")
        if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
            raise ValueError(
                "LiteLLM response must include prompt and completion token counts"
            )

        self.input_tokens_used += prompt_tokens
        self.output_tokens_used += completion_tokens
        consumed = prompt_tokens + completion_tokens
        remaining = context.token_budget_remaining - consumed
        context.token_budget_remaining = max(remaining, 0)
        if remaining <= 0:
            raise TokenBudgetExceeded(
                "Model response exhausted the investigation token budget"
            )

    def _parse_tool_call(self, tool_call: Any) -> dict[str, JsonValue]:
        """Convert a LiteLLM function call into the public action shape."""
        function = self._get(tool_call, "function", tool_call)
        name = self._get(function, "name") or self._get(tool_call, "name")
        arguments = self._get(function, "arguments", self._get(tool_call, "input"))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise _OutputParseError("Tool arguments are not valid JSON") from exc
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise _OutputParseError(
                "Tool call must contain a name and object arguments"
            )

        if name == "finish":
            return {"action": "finish"}
        if name == "observe_more":
            hint = arguments.get("evidence_hint")
            if not isinstance(hint, str) or not hint.strip():
                raise _OutputParseError(
                    "observe_more requires a non-empty evidence_hint"
                )
            return {"action": "observe_more", "evidence_hint": hint}

        try:
            self.registry.validate_schema(name, arguments)
        except (KeyError, ValueError, JsonSchemaValidationError) as exc:
            raise _OutputParseError(str(exc)) from exc
        return {"tool": name, "input": arguments}

    def _parse_message(self, message: Any) -> dict[str, JsonValue]:
        """Parse a tool-call response or JSON action in assistant content."""
        tool_calls = self._get(message, "tool_calls", []) or []
        if tool_calls:
            return self._parse_tool_call(tool_calls[0])

        content = self._get(message, "content")
        if not isinstance(content, str):
            raise _OutputParseError(
                "Assistant response has neither tool calls nor JSON content"
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise _OutputParseError("Assistant content is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise _OutputParseError("Assistant JSON response must be an object")

        if payload.get("action") == "finish":
            return {"action": "finish"}
        if payload.get("action") == "observe_more":
            hint = payload.get("evidence_hint")
            if not isinstance(hint, str) or not hint.strip():
                raise _OutputParseError(
                    "observe_more requires a non-empty evidence_hint"
                )
            return {"action": "observe_more", "evidence_hint": hint}

        name = payload.get("tool")
        arguments = payload.get("input")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise _OutputParseError(
                "JSON response must contain a supported action or tool/input"
            )
        try:
            self.registry.validate_schema(name, arguments)
        except (KeyError, ValueError, JsonSchemaValidationError) as exc:
            raise _OutputParseError(str(exc)) from exc
        return {"tool": name, "input": arguments}

    async def ask(self, context: InvestigationContext) -> dict[str, JsonValue]:
        """Ask LiteLLM for an investigation action with up to two parse retries."""
        if context.token_budget_remaining <= 0:
            raise TokenBudgetExceeded("Investigation token budget is exhausted")

        system_prompt = await self.build_system_prompt(context)
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        schemas = self._tool_schemas()

        for attempt in range(MAX_PARSE_RETRIES + 1):
            response = await _acompletion(
                model=self.litellm_model,
                api_key=self.api_key,
                messages=messages,
                tools=schemas,
                tool_choice="auto",
                response_format={"type": "json_object"},
            )
            self._account_tokens(response, context)
            choices = self._get(response, "choices", []) or []
            if not choices:
                message: Any = None
            else:
                message = self._get(choices[0], "message")
            try:
                return self._parse_message(message)
            except _OutputParseError as exc:
                if attempt >= MAX_PARSE_RETRIES:
                    raise ValueError(
                        "Model returned invalid action after "
                        f"{MAX_PARSE_RETRIES} retries: {exc}"
                    ) from exc
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": str(self._get(message, "content", "")),
                        },
                        {
                            "role": "user",
                            "content": (
                                "The previous response was invalid: "
                                f"{exc}. Return one valid action JSON object."
                            ),
                        },
                    ]
                )

        raise AssertionError("Unreachable retry loop exit")
