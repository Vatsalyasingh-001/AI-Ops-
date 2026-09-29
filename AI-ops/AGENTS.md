# AI-Ops Project Context

Read this file before exploring or changing the repository. It is the quick-start context for coding agents; consult the linked project documents only when their detail is needed.

## Project goal

Build an incremental DevOps/SRE incident investigation platform. Preserve the existing sample service and add new capabilities in small, verified steps. The current agent-package scope is a deterministic, framework-agnostic `OBSERVE → REASON → ACT → LEARN` loop with evidence, model routing, tools, and human approval.

## Repository map

- `app/`: existing Flask demo backend, containerized independently with its own `requirements.txt` and Python 3.11 Docker image.
- `nginx/`, `docker-compose.yml`: reverse proxy and local service composition.
- `prometheus/`, `grafana/`: metrics configuration and provisioned Grafana dashboard/data source.
- `src/agent/`: Python agent package; currently contains domain models, tool protocol/registry, deterministic fake observe tools, pure diagnosis tools, LiteLLM router, human approval gate, bounded investigation loop, and public factory functions.
- `tests/`: root project tests for the agent package.
- `pyproject.toml`, `uv.lock`: root uv project for the agent package (Python >=3.12; Pydantic, jsonschema, and LiteLLM runtime dependencies; Ruff and pytest development tools).
- `docs/agent.md`, `docs/architecture.md`, `docs/plan.md`: original project rules, architecture, and phased roadmap. Use them for detail, but verify status against the current tree and this file.

## Current implementation status

**Present in the repository:**
- Flask demo endpoints `/`, `/health`, `/slow`, `/error`, plus Prometheus metrics in `app/app.py`.
- Nginx, Prometheus, and Grafana configuration; Compose declares backend, Nginx, Prometheus, and Grafana services.
- Agent Pydantic models in `src/agent/models.py`: ordered state and enums, incident/evidence/tool/approval/context/result models.
- Abstract tool protocol and registry in `src/agent/tools/base.py`: JSON Schema validation, name-based async dispatch, read-only filtering, and medium-or-higher-risk filtering.
- Five deterministic read-only fake tools in `src/agent/tools/observe.py`: metrics, logs, traces, topology, and deployment evidence; register them with `register_observe_tools()`.
- Four read-only pure computation tools in `src/agent/tools/diagnose.py`: metric baseline deltas, log-template clustering, deploy-window correlation, and threshold anomaly flags; register them with `register_diagnose_tools()`.
- LiteLLM router in `src/agent/router.py`: provider/model routing, JSON-mode action parsing, two parse retries, prompt/completion token budget accounting, and lazy provider-library import to avoid import-time network access. Tests mock all completions.
- Approval gate in `src/agent/gate.py`: deterministic tool-call IDs, pending/approved/denied states, timeout auto-denial, and execution only through injected executors after approval; execution is bound to the exact approved call snapshot.
- Full `AgentLoop` orchestration in `src/agent/loop.py`: auto-observation, router decisions, read-only ACT calls, approval-gated mutations, bounded iterations, cancellation event, transition/tool/approval logging, and deterministic result synthesis. The earlier `InvestigationLoop` helper remains for transition-focused compatibility tests.
- Public async `create_agent()` and `investigate()` entry points in `src/agent/__init__.py` wire one shared registry, LiteLLM router, gate, and configured loop; these are the only names in the root package's `__all__`.
- Thirty-nine offline tests in `tests/`: model, registry, observe-tool, diagnosis-tool, mocked-router, approval-gate, loop lifecycle/performance, and factory/public-API coverage.

**Not implemented in the agent package yet:**
- External integrations or operational side effects.

Files/configuration being present does not prove that a service or roadmap phase has been run or verified. Do not claim runtime or phase completion without actually testing it. Loki, Tempo, Alertmanager, and later roadmap capabilities are not part of the current agent implementation.

## Work rules

- Work only on the user's requested chunk. Make small, reviewable changes; run the full validation gate after each chunk and stop for the user's explicit **“next”** before continuing.
- Keep the existing project paths and Flask demo intact unless the user explicitly asks to change them. Do not conflate the root uv agent project with `app/`'s separate Flask/Docker environment.
- Keep `src/agent/` framework-agnostic. FastAPI, if ever introduced elsewhere, must not become an agent runtime dependency. Do not add Kubernetes, Docker runtime logic, webhook transports, vault clients, or integrations to the agent package unless explicitly requested.
- Use typed Pydantic models and docstrings. Do not use LangChain or CrewAI. Route model calls through LiteLLM when implementing the router; read Anthropic/OpenAI credentials only from environment variables, never hard-code secrets.
- The loop must be deterministic: no hidden randomness; make state changes explicit and log every transition. Keep investigation evidence traceable to tool results; do not invent operational facts.
- Treat actions as unsafe until gated. Require explicit human approval before any mutating action; analysis and recommendations alone do not authorize execution.
- Update this context file when verified implementation status or the validation workflow materially changes. Avoid copying the full roadmap here.

## Validation

Run from the repository root after each implementation chunk:

`uv run ruff check . && uv run ruff format --check . && uv run pytest`

The root Ruff configuration intentionally scopes lint/format checks to `src/**/*.py` and `tests/**/*.py`; the existing Flask demo has its own dependency/runtime setup. Tests must not require real provider API keys or network access.