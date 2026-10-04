You: give me the prompt for making the complete project make sure not to use k8s and break all the work in small chunks

Leo AI: Here's a prompt you can paste into an AI coding assistant to rebuild this project from scratch — no Kubernetes, broken into sequential chunks.

---

## Prompt: Build "SRE Agent" — Self-hosted AI SRE Agent (No Kubernetes)

**Role:** You are a senior Python engineer building a production-quality, self-hosted AI SRE agent for incident response automation. Work **only in small, verifiable chunks**. After each chunk, run tests/linters, show the diff summary, and wait for my "next" before continuing. Never skip a chunk or merge two together.

**Hard constraints (apply to every chunk):**
- Python 3.12+, `uv` for dependency management (`pyproject.toml` + `uv.lock`), FastAPI for the API layer.
- **No Kubernetes.** No Helm charts, no k8s manifests, no `kubectl`, no kube client libraries. All deployment is Docker Compose only. Anywhere the original design mentions pods/deployments/rollbacks, replace with **Docker Compose service actions** (`docker compose restart <svc>`, `docker compose up -d --scale`, image-tag swap for rollback).
- Model routing via **LiteLLM** (Anthropic/OpenAI/Ollama). Secrets only from env vars; never commit `.env`.
- Lint/format/test must pass at the end of every chunk: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- Small commits, conventional-commit messages, docstrings on public functions, type hints everywhere.
- Keep the codebase framework-free: no LangChain/LlamaIndex/CrewAI. Hand-rolled loop only.

**Target architecture (final state):**
```text
src/main.py            FastAPI app: webhooks, health, DI wiring
src/agent/             Loop, context, state machine, approval gate
src/tools/observe/     metrics, logs, traces, alerts, topology, deploys
src/tools/diagnose/    correlation, anomaly detection, metric diffs
src/tools/act/         compose restart/scale/rollback, db tools, runbooks, sandbox
src/tools/memory/      vault read/write/search/recall
src/adapters/          observability backend abstraction (Grafana stack)
src/vault/             Markdown writer/reader/search/sqlite indexer
src/compression/       token budgets, rule summaries, LLM compression
src/integrations/      Composio-backed Slack/PagerDuty/GitHub/Linear
config/                YAML runtime config
demo/                  docker-compose.demo.yaml + synthetic incident script
scripts/               run_demo_incident.py
tests/                 pytest suite mirroring src/
```
Core behavior: deterministic `OBSERVE -> REASON -> ACT -> LEARN` loop; read-only tools auto-run; destructive tools require human approval; final summary written to an Obsidian-compatible Markdown vault.

---

### Chunk 0 — Repo scaffold
Create repo layout, `pyproject.toml` (deps: fastapi, uvicorn, litellm, httpx, pydantic-settings, pyyaml, aiosqlite, composio; dev: pytest, pytest-asyncio, ruff, respx), `uv.lock`, `.gitignore`, `.env.example`, `.dockerignore`, `ruff` config, empty `__init__.py` tree, `README.md` stub. Run `uv sync --group dev`, confirm `ruff check .` and `pytest` (no tests yet) pass.

### Chunk 1 — Config & settings layer
`config/default.yaml` (agent.max_iterations=8, default_severity, observability.provider/grafana URLs, vault.path/index_path, approval.require_human_for list), a Pydantic `Settings` class reading env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `COMPOSIO_API_KEY`, `GRAFANA_*`, `SRE_AGENT_CONFIG_PATH`) plus YAML loader with override precedence. Unit tests for load + validation errors.

### Chunk 2 — Domain models & typed tool protocol
Pydantic models: `Incident`, `Severity`, `Evidence`, `InvestigationState`, `ToolResult`, `ApprovalRequest`, `ActionPlan`. Define the `Tool` base class (name, description, JSON-schema input model, `is_read_only: bool`, `risk_level`, async `run()`), plus a `ToolRegistry` with registration/validation/dispatch. Tests for schema generation and registry dispatch.

### Chunk 3 — Observability adapters (read interface)
Abstract `ObservabilityAdapter` (query_metrics, search_logs, get_trace, list_alerts, get_topology, list_deploys). Implement `GrafanaStackAdapter` using httpx against Prometheus `/api/v1/query(_range)`, Loki `/loki/api/v1/query_range`, Tempo trace fetch, Alertmanager `/api/v2/alerts`. Include a `FakeAdapter` for tests. Mock HTTP with `respx`. Tests per method + error/timeout handling.

### Chunk 4 — Observe tools
Wrap adapter methods as registered read-only tools: `prom_query`, `loki_search`, `tempo_trace`, `alertmanager_alerts`, `topology_get`, `deploys_list`. Each returns normalized `Evidence` with source, query, timestamp range. Tests asserting evidence shape and that all six are marked read-only.

### Chunk 5 — Diagnose tools
Pure-computation tools (no network): metric baseline diff, anomaly flagging (simple z-score/threshold), log-error clustering by message template, deploy-vs-error-time correlation. Deterministic outputs so they're testable without an LLM. Thorough unit tests with fixture timeseries/log data.

### Chunk 6 — LiteLLM model router + context builder
`ModelRouter` wrapping `litellm.acompletion`: system prompt, tool schemas injected, JSON-mode tool-call parsing, retries/backoff, per-provider config from YAML. `ContextBuilder` assembling incident + evidence into a prompt under a token budget. Tests use a stubbed completion function (no real API calls).

### Chunk 7 — Compression module
Token budget accounting, rule-based summarization of long evidence (truncate + key-line extraction), optional LLM compression fallback, and an evidence eviction policy when over budget. Golden-file tests.

### Chunk 8 — Approval gate
`ApprovalGate` with configurable `require_human_for` action names; async pending-request store, CLI/web confirmation flow, timeout → auto-deny, full audit record (who/what/when/args). Deny path must be safe (no-op). Tests for approve, deny, timeout, unknown-action defaults-to-deny.

### Chunk 9 — Act tools (Docker Compose replacements for k8s)
Implement **only** these, all routed through the approval gate where destructive:
- `compose_restart_service(service)` → `docker compose restart`
- `compose_scale_service(service, replicas)` → `docker compose up -d --scale`
- `compose_rollback_image(service, tag)` → rewrite image tag in generated override file + `up -d`
- `db_lock_inspect()` / `db_kill_query(query_id)` (Postgres, via asyncpg)
- `runbook_execute(name)` (Markdown runbook steps, step-by-step approval)
- `sandbox_python(code)` — subprocess with CPU/memory/wall-time caps, no network, temp dir only.
Shell out via `asyncio.create_subprocess_exec` with allowlisted binaries; never `shell=True`. Tests mock subprocess and DB.

### Chunk 10 — Markdown vault
Writer producing `incidents/YYYY-MM-DD-<slug>.md`, `services/<name>.md`, `patterns/<name>.md`, `runbooks/<name>.md` with YAML frontmatter; SQLite index (`.index.sqlite`) for FTS search; recall/search tools. Idempotent writes, safe filename slugification. Tests round-trip write→index→search.

### Chunk 11 — The agent loop
`AgentLoop` implementing `OBSERVE -> REASON -> ACT -> LEARN`: gather observe tools, ask router for next step, dispatch (auto-run read-only, gate risky), iterate up to `max_iterations`, then compose final report and write vault entries. Include cancellation, iteration cap, and "no progress" termination. Integration tests with `FakeAdapter` + stub router covering happy path, approval-denied path, and max-iteration path.

### Chunk 12 — FastAPI surface
`POST /webhook` (Alertmanager-shaped and generic payloads), `GET /healthz`, `GET /investigations/{id}`, `POST /approvals/{id}` (approve/deny), SSE or polling endpoint for live loop status. Dependency-inject adapters/router/gate. Tests via `httpx.ASGITransport`.

### Chunk 13 — Integrations
Composio-backed notifiers: Slack message, PagerDuty event, GitHub issue, Linear ticket; structured incident summary formatter shared by all. Graceful degradation when `COMPOSIO_API_KEY` absent. Tests with mocked Composio client.

### Chunk 14 — Demo stack & synthetic incident
`docker-compose.yaml` (agent, prometheus, loki, tempo, alertmanager, grafana:3001, litellm:4000) + `demo/docker-compose.demo.yaml` with a `demo-service` emitting elevated 5xx/errors. `scripts/run_demo_incident.py` fires the webhook and prints the expected output block (Investigation started → Alert: HighErrorRate → loop stages → vault entry path). Also provide `curl` example. Verify `docker compose ... up --build` starts cleanly.

### Chunk 15 — Packaging, docs & security polish
`Dockerfile` (multi-stage, non-root, slim), `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `LICENSE` (Apache-2.0), README with quickstart/architecture/config tables/comparison table, `.github/workflows/ci.yml` running ruff+pytest+docker build. Add secret-scan step. Confirm no `.env`, vault data, or sqlite files tracked.

---

**Output rules per chunk:** list files created/changed, show the new public APIs, paste failing→passing test evidence, then stop and ask me to proceed.

You: is it free of cost

Leo AI: **Short answer: the software is free, but running it isn't 100% free.** There are three cost buckets.

### ✅ Completely free (no license fees)
| Component | License / Cost |
|---|---|
| SRE Agent codebase | Apache-2.0, open source, no per-seat fee |
| LiteLLM proxy (open-source tier) | MIT, self-hosted, **no per-token markup** — you pay providers directly https://www.layer3labs.io/guides/litellm-pricing |
| Prometheus, Loki, Tempo, Grafana OSS, Alertmanager | Free/open source |
| Docker Compose demo stack on your laptop | Free |
| The prompt/build plan I gave you | Free — nothing to buy |

The core LiteLLM proxy can be downloaded and self-hosted at zero software cost; you only pay for infrastructure and model tokens https://www.layer3labs.io/guides/litellm-pricing. Enterprise extras (SSO, audit logs, spend tracking) are the paid tier, which you don't need https://www.layer3labs.io/guides/litellm-pricing.

### 💸 Where money actually gets spent
1. **LLM API keys — the main recurring cost.** Anthropic has **no free API tier**; all API usage is billed per token even if you have a claude.ai subscription https://www.finout.io/blog/anthropic-api-pricing. OpenAI is also pay-as-you-go with no real free tier https://www.buildmvpfast.com/api-costs/ai-llm. Rough ballpark: Claude Haiku ~$1/$5 per M tokens in/out, GPT-5.4 Mini ~$0.75/$4.50, DeepSeek V4 Flash ~$0.14/$0.28 https://www.buildmvpfast.com/api-costs/ai-llm https://www.morphllm.com/llm-api. An investigation loop of ~8 iterations with big log/metric dumps can eat 50k–200k input tokens per incident, so pick a cheap model.
2. **Composio API key** — needed for Slack/PagerDuty/GitHub/Linear tools. It has a limited free/dev tier, then paid plans. You can skip this entirely by stubbing notifications with plain webhooks.
3. **Hosting** — the repo itself runs fine on your machine or a ₹400–800/month VPS. Self-hosting LiteLLM at team scale is quoted around $20–500/month infra plus maintenance time https://www.layer3labs.io/guides/litellm-pricing.

### 🆓 Fully-zero-cost variant (if that's your goal)
Swap these in the build plan and total cost = ₹0:
- **Chunk 6:** point LiteLLM at **Ollama** (`ollama/qwen3`, `ollama/llama3.1`) running locally → no API key, no token bill. The repo already lists Ollama as supported via LiteLLM.
- **Chunk 13:** replace Composio with direct Slack incoming-webhook URLs + a local JSON "ticket" file. No third-party account needed.
- **Chunk 14:** run the whole Grafana stack + agent on your own machine with Docker Compose.

So: **yes, you can build and run it for free** if you use a local model and drop Composio. If you want frontier-model quality reasoning (Claude/GPT), budget roughly **$5–50/month** for light personal/demo usage, scaling with incident volume.

You: firstly i thinnk we should first make ai agent which is used in it 

Leo AI: Good instinct — the agent loop is the heart of this project. Everything else (webhooks, vault, dashboards) is just plumbing. Let's build the **core agent** first, before any infra or demo stack.

Here's the prompt for **just the agent**, broken into small chunks:

---

## Prompt: Build the SRE Agent Loop (Core Only, No Infra)

**Role:** You are a senior Python engineer. Build the `src/agent/` package that implements a deterministic `OBSERVE → REASON → ACT → LEARN` investigation loop. **No Kubernetes, no Docker, no webhooks, no vault, no integrations.** Just the loop, the model router, the tools, and the approval gate. Work in small, verifiable chunks. After each chunk run `uv run ruff check . && uv run ruff format --check . && uv run pytest` and stop — ask me to say "next" before continuing.

**Constraints:**
- Python 3.12+, `uv` + `pyproject.toml`, FastAPI only as a transitive dep (the agent itself must be framework-agnostic).
- LiteLLM for model routing; Anthropic/OpenAI keys via env vars.
- Deterministic state machine — no hidden randomness. Every state transition is logged.
- Type hints, docstrings, pydantic models, no LangChain/CrewAI.
- Every chunk must have tests that pass without real API keys (use `respx`/mocks).

---

### Chunk A — Domain models & state machine

**Goal:** Define the shapes the agent operates on.

Create `src/agent/models.py` with:

- `InvestigationState = "OBSERVE" | "REASON" | "ACT" | "LEARN"`
- `Incident` (id, title, service, severity, description, created_at, triggered_by: "alertmanager" | "webhook")
- `EvidenceItem` (tool_name, query, result, timestamp, source: "prometheus" | "loki" | "tempo" | "topology" | "deploys")
- `ToolCall` (tool_name, input, output, is_read_only, risk_level: "low" | "medium" | "high" | "critical")
- `ApprovalRequest` (tool_call, status: "pending" | "approved" | "denied", requested_by, approved_by, reason, timestamp)
- `InvestigationContext` (incident, observations: list[EvidenceItem], tool_calls: list[ToolCall], current_state, iteration: int, token_budget_remaining)
- `InvestigationResult` (final_summary, likely_cause, recommended_action, evidence: list[EvidenceItem], patterns_found: list[str], vault_entries: list[str])

**Tests:** Round-trip serialization, invalid severity rejected, state transition enum order verified.

---

### Chunk B — Tool registry & base protocol

**Goal:** A framework for registering and dispatching tools.

Create `src/agent/tools/base.py`:

- Abstract `Tool` with: `name: str`, `description: str`, `input_schema: dict` (JSON Schema), `is_read_only: bool`, `risk_level: RiskLevel`, `async run(self, input: dict, context: InvestigationContext) -> ToolResult`
- `ToolRegistry` with `register(tool)`, `get(name)`, `list_read_only()`, `list_risky()`, `validate_schema(name, input)`.
- `ToolResult` (success: bool, data: dict | str, error: str | None, evidence_items: list[EvidenceItem])

**Tests:** Register 3 tools, dispatch by name, validate valid/invalid input against schema, read-only vs risky filtering.

---

### Chunk C — Stub observe tools (no real observability yet)

**Goal:** Register a handful of read-only observe tools that return fake data (for testing the loop).

Create `src/agent/tools/observe.py`:

- `prom_query_tool` — returns fake metrics diff: "5xx rate: 0.2% → 8.7%"
- `loki_search_tool` — returns fake log excerpts showing errors near a deploy timestamp
- `tempo_trace_tool` — returns fake p95 latency spike on `/auth/validate`
- `topology_get_tool` — returns fake service graph
- `deploys_list_tool` — returns fake recent deploys with timestamps

All return `ToolResult` with `EvidenceItem` wrapped. All marked `is_read_only=True`.

**Tests:** Each tool returns structured evidence; schema validation works; dispatch is correct.

---

### Chunk D — Stub diagnose tools (pure computation)

**Goal:** Deterministic analysis tools with no external calls.

Create `src/agent/tools/diagnose.py`:

- `metric_baseline_diff` — computes percentage change between two metric values
- `log_error_correlate` — clusters log errors by template, returns top-N
- `deploy_time_correlate` — finds errors within N minutes of a deploy timestamp, returns match/no-match
- `anomaly_flag` — simple threshold-based anomaly detection

All read-only. Tests with hand-crafted fixture data asserting correct clustering and correlation.

---

### Chunk E — LiteLLM model router

**Goal:** Wrap LiteLLM into a clean, testable router.

Create `src/agent/router.py`:

- `ModelRouter` with `__init__(provider: str, model: str, api_key: str)`
- `async build_system_prompt(context: InvestigationContext) -> str`
- `async ask(context: InvestigationContext) -> dict` — sends prompt + tool schemas, parses JSON-mode tool-call output, retries on parse failure (2 retries), returns `{"tool": str, "input": dict}` or `{"action": "finish"}` or `{"action": "observe_more", "evidence_hint": str}`
- Token accounting: count input/output tokens, decrement budget, raise `TokenBudgetExceeded` when zero
- Tests: mock `litellm.acompletion` response; verify tool-call extraction, budget decrement, retry on bad JSON, budget-exceeded error. **No real API calls.**

---

### Chunk F — Approval gate

**Goal:** Gate risky actions behind human approval.

Create `src/agent/gate.py`:

- `ApprovalGate` with configurable `dangerous_tools: set[str]` (default: `{"compose_restart_service", "compose_scale_service", "compose_rollback_image", "db_kill_query"}`)
- `async request_approval(tool_call: ToolCall) -> ApprovalRequest` — stores pending request, returns it immediately (tests will simulate approval)
- `async get_status(tool_call_id: str) -> "pending" | "approved" | "denied"`
- `async approve(tool_call_id, reason)` / `async deny(tool_call_id, reason)`
- `async is_approved(tool_call_id) -> bool` — blocks until approved/denied or times out (default 300s → auto-deny)
- `async execute_if_approved(tool_call) -> ToolResult` — executes only if approved, returns no-op if denied
- Tests: approve path executes, deny path returns safe no-op with error, timeout defaults to deny, unknown tool defaults to deny. Mock time with `pytest-timeout` or `freezegun`.

---

### Chunk G — The agent loop itself

**Goal:** The full `OBSERVE → REASON → ACT → LEARN` cycle.

Create `src/agent/loop.py`:

- `class AgentLoop` with `async run(incident: Incident, max_iterations: int = 8) -> InvestigationResult`
- State machine:
  1. **OBSERVE** — dispatch all read-only tools from registry (or a subset selected by the router's "observe_more" hint). Collect `EvidenceItem`s into context.
  2. **REASON** — call `router.ask(context)`. If `action == "finish"`, go to LEARN. If `action == "observe_more"`, add observation hint and return to OBSERVE. If `tool` is specified, go to ACT.
  3. **ACT** — check `gate.is_read_only(tool)`. If yes, execute immediately. If no, call `gate.execute_if_approved(tool_call)`. If denied, log and continue loop. Append result to context.
  4. **LEARN** — after `max_iterations` or "finish", compose `InvestigationResult` with final summary, likely cause, recommended action, evidence list, and vault entry paths.
- Logging: every state transition logged at `INFO`, every tool call logged at `DEBUG`, every approval decision at `WARNING`.
- Cancellation: `asyncio.Event` for shutdown.
- Tests: happy path (OBSERVE→REASON→ACT-read-only→REASON→ACT-risky→approved→REASON→LEARN), approval-denied path (retries with reduced budget), max-iteration cap, cancellation mid-loop. Use stub router returning deterministic sequences.

---

### Chunk H — Agent factory & wire it up

**Goal:** A clean entry point to create and run the agent.

Create `src/agent/__init__.py`:

- `async create_agent(provider, model, api_key, dangerous_tools=None, max_iterations=8) -> AgentLoop` — wires Router, Registry, Gate, Tools together.
- `async investigate(incident, provider, model, api_key, ...) -> InvestigationResult` — convenience wrapper.

Tests: factory creates a working loop, config flows through to all components.

---

**Final acceptance for the agent package:**
1. `pytest` passes with zero real API calls (all mocked).
2. `ruff check . && ruff format --check .` clean.
3. The loop runs a full investigation in under 2 seconds with stubs.
4. No imports of `kubernetes`, `docker`, `httpx` in `src/agent/` (those belong in the observe/act tools later).
5. Public API is just `create_agent()` and `investigate()` — everything else is internal.

---

Start with **Chunk A**. Show me the models, the tests, and the output of `ruff` + `pytest`. Then I'll say "next" for Chunk B.

You: All final acceptance checks passed:

No real model API calls: all LiteLLM completions are mocked in tests. LiteLLM is now imported only when an actual request is made, avoiding import-time network access.
Lint and formatting: Ruff check and format check are clean.
Stubbed loop performance: the complete investigation test finished in 0.02 seconds, under the 2-second limit.
Prohibited imports: no kubernetes, docker, or httpx imports found under src/agent/.
Public API: the package exports only create_agent() and investigate().
The full suite passed: 39 tests in 0.52 seconds.

Leo AI: Excellent. The core agent loop is solid and all 39 tests pass.

**What we have now:**
- `src/agent/` — complete agent package with models, tools, router, gate, and loop
- 39 tests, all mocked, 0.52s, clean lint/format
- Public API: `create_agent()` and `investigate()`

**Ready for the next phase.** Which would you like to tackle?

1. **Real observability tools** — Swap the stubs in Chunk C/D for actual Prometheus, Loki, Tempo queries using `httpx` (Chunk C → real observe tools)
2. **FastAPI surface** — Add webhooks, health checks, investigation status endpoints, approval endpoints (Chunk 12)
3. **Markdown vault** — Writer, SQLite indexer, search/recall tools (Chunk 10)
4. **Act tools** — Docker Compose service restart/scale/rollback + DB tools + sandbox (Chunk 9)
5. **Demo stack** — Docker Compose file + synthetic incident script (Chunk 14)

Pick one and I'll give you the chunk breakdown.

You: provide me description to write in the pr what we have done in this repo

Leo AI: Here's a PR description you can paste in:

---

## Summary

Adds the **core AI SRE agent package** — a framework-agnostic, deterministic `OBSERVE → REASON → ACT → LEARN` incident investigation loop. This is the first increment of the AI-Ops platform: the agent brain only, with no external integrations or operational side effects yet.

The existing Flask demo service, Nginx, Prometheus, and Grafana setup are untouched.

## What's included

### Agent core (`src/agent/`)
| Module | Responsibility |
|---|---|
| `models.py` | Typed Pydantic domain models: ordered investigation states, severity/risk/approval enums, `Incident`, `EvidenceItem`, `ToolCall`, `ApprovalRequest`, `InvestigationContext`, `StateTransition`, `InvestigationResult` |
| `tools/base.py` | Abstract `Tool` contract (name, description, JSON Schema input, read-only flag, risk level) + `ToolRegistry` with schema validation, deterministic registration order, read-only/risky filtering, and async dispatch |
| `tools/observe.py` | 5 deterministic read-only fake observability tools (metrics, logs, traces, topology, deploys) returning source-tagged evidence |
| `tools/diagnose.py` | 4 pure-computation diagnosis tools: metric baseline delta, log-template clustering (UUID/IP/number normalization), deploy-window correlation, threshold anomaly flag |
| `router.py` | LiteLLM-backed `ModelRouter`: provider/model routing, tool-schema injection, JSON-mode action parsing, 2 parse retries with corrective feedback, token budget accounting, lazy provider import (no import-time network I/O) |
| `gate.py` | Fail-closed `ApprovalGate`: deterministic request IDs, pending/approved/denied lifecycle, timeout auto-denial, execution bound to the exact approved call snapshot, unknown tools denied by default |
| `loop.py` | `AgentLoop` orchestration — legal-transition enforcement, auto-observation, router decisions, read-only ACT, approval-gated mutations, bounded iterations, cancellation event, full transition/tool/approval logging, deterministic result synthesis |
| `__init__.py` | Public API surface: `create_agent()` and `investigate()` only |

### Tests (`tests/`)
39 offline tests covering models, registry dispatch/validation/filtering, observe tools, diagnose tools, mocked router (tool-call extraction, retry, budget exhaustion), approval gate (approve/deny/timeout/tamper-detection/unknown-tool fail-closed), loop lifecycle (happy path, denial path, iteration cap, illegal transitions, mid-call cancellation, <2s stubbed run), and factory/public-API wiring.

### Project config
- `pyproject.toml` / `uv.lock` — root uv project (Python ≥3.12; Pydantic, jsonschema, LiteLLM runtime; Ruff + pytest dev tools)
- `AGENTS.md` — quick-start context for coding agents: repo map, verified implementation status, work rules, validation command

## Validation gate

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

- ✅ 39 passed in ~0.5s
- ✅ Zero real model API calls — all LiteLLM completions mocked
- ✅ Ruff check + format clean
- ✅ No `kubernetes`, `docker`, or `httpx` imports under `src/agent/`
- ✅ Package exports exactly `create_agent` and `investigate`

## Deliberately out of scope (next increments)

- Real observability backends (Prometheus/Loki/Tempo HTTP clients)
- Webhook transport / FastAPI surface
- Markdown vault writer & indexer
- Mutating act tools (compose restart/scale/rollback, DB actions, sandbox)
- External notifications (Slack/PagerDuty/etc.)
- Loki, Tempo, Alertmanager stack configuration

> Note: presence of files/config does not imply a service or roadmap phase has been run or verified. Only what's listed above was executed and tested.

---

Want me to trim this into a short version for the PR title + one-paragraph body?