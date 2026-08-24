AI-Ops Project Plan

Objective

Build the AI-Ops project step by step without changing the agreed architecture or skipping phases.

Fixed Starting Path

aiops-project/
├── app/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── agent.md
├── architecture.md
└── plan.md

This path must remain unchanged.

Phase 1 — Nginx + Python Backend

Goal

Get a working application running behind Nginx.

Architecture

Internet
   |
   v
Nginx
   |
   v
Python Backend

Tasks

Create project directory.

Create app/app.py.

Create app/requirements.txt.

Create app/Dockerfile.

Create nginx/nginx.conf.

Create docker-compose.yml.

Build containers.

Start containers.

Verify Nginx.

Verify backend.

Test /health.

Test /slow.

Test /error.

Completion Criteria

docker ps

shows both containers running.

The following must work:

/
 /health
 /slow
 /error

Do not move to Phase 2 until this is verified.

Phase 2 — Prometheus + Grafana

Goal

Introduce metrics and visualization.

Architecture

Application
    |
    v
Prometheus
    |
    v
Grafana

Tasks

Add Prometheus.

Configure scrape target.

Verify Prometheus is receiving data.

Add Grafana.

Connect Grafana to Prometheus.

Create application dashboard.

Monitor request rate.

Monitor error rate.

Monitor latency.

Monitor CPU.

Monitor memory.

Completion Criteria

Grafana must show live metrics from the application.

Phase 3 — Loki + Logs

Goal

Collect and visualize Nginx/application logs.

Tasks

Add Loki.

Add log collector.

Send Nginx logs to Loki.

Send application logs to Loki.

Connect Loki to Grafana.

Verify /error appears in logs.

Verify Nginx errors appear in logs.

Create log dashboard/panels.

Completion Criteria

A request to /error must be visible in Loki/Grafana.

Phase 4 — Tempo + Tracing

Goal

Add distributed tracing.

Tasks

Add OpenTelemetry instrumentation.

Configure OTLP.

Add Tempo.

Send traces to Tempo.

Connect Tempo to Grafana.

Trace normal requests.

Trace /slow.

Identify slow spans.

Completion Criteria

A request must be visible as a trace in Tempo/Grafana.

Phase 5 — Incident Scenarios

Goal

Create reproducible incidents.

Required Scenarios

Incident 1 — High CPU

Create CPU load.

Confirm CPU increase.

Confirm Prometheus sees it.

Incident 2 — High Latency

Use /slow.

Confirm latency increases.

Confirm traces show the delay.

Incident 3 — High Error Rate

Call /error repeatedly.

Confirm error rate increases.

Confirm Loki contains errors.

Incident 4 — Nginx 502

Stop backend.

Send request through Nginx.

Confirm 502.

Confirm Nginx logs show the failure.

Incident 5 — Bad Deployment

Create a known-bad application version.

Deploy it.

Confirm metrics/logs deteriorate.

Record deployment timestamp.

Completion Criteria

Every incident must be reproducible and documented.

Phase 6 — Alertmanager

Goal

Turn observed failures into incidents.

Tasks

Add Alertmanager.

Configure Prometheus alert rules.

Create high-error-rate alert.

Create high-latency alert.

Create high-CPU alert.

Create service-down alert.

Test each alert.

Configure webhook endpoint.

Completion Criteria

A real incident must produce an Alertmanager notification.

Phase 7 — AI-Ops Lambda

Goal

Create the incident-analysis backend.

Tasks

Create Lambda function.

Define event schema.

Receive alert data.

Query Prometheus.

Query Loki.

Query Tempo.

Collect recent deployment information.

Create structured incident context.

Completion Criteria

Lambda must receive an alert and produce a complete incident context.

Phase 8 — AI Root Cause Analysis

Goal

Use an LLM to analyze incidents.

Tasks

Connect LLM API.

Create incident-analysis prompt.

Send metrics.

Send logs.

Send traces.

Send deployment information.

Generate root cause.

Generate severity.

Generate evidence.

Generate confidence.

Generate recommendation.

Completion Criteria

For a known incident, AI must provide a reasonable evidence-based RCA.

Phase 9 — RAG + Runbooks

Goal

Make AI use project-specific operational knowledge.

Runbooks

Create:

runbooks/
├── high_cpu.md
├── high_memory.md
├── nginx_502.md
├── high_error_rate.md
├── high_latency.md
├── ecs_unhealthy.md
└── deployment_rollback.md

Tasks

Create runbooks.

Select vector/RAG storage.

Index runbooks.

Retrieve relevant runbook.

Add runbook context to AI.

Return recommended procedure.

Completion Criteria

AI must cite/refer to the relevant runbook when recommending an operational action.

Phase 10 — Slack Notifications

Goal

Send AI-generated incident summaries to Slack.

Tasks

Configure Slack integration.

Create incident message.

Include severity.

Include root cause.

Include evidence.

Include confidence.

Include recommendation.

Include approval action.

Completion Criteria

A real incident must generate a useful Slack notification.

Phase 11 — Human-Approved Remediation

Goal

Allow safe operational automation.

Flow

AI Recommendation
       |
       v
Human Approval
       |
       v
Lambda
       |
       v
AWS API

Tasks

Define approved remediation actions.

Create least-privilege IAM role.

Implement remediation Lambda.

Add approval mechanism.

Test rejected action.

Test approved action.

Log every remediation.

Completion Criteria

No remediation happens without explicit approval.

Phase 12 — Recovery Verification

Goal

Verify whether remediation actually fixed the problem.

Flow

Remediation
    |
    v
Wait
    |
    v
Collect Metrics
    |
    v
Compare Before/After
    |
    +---- Healthy ---> Resolved
    |
    +---- Unhealthy -> Escalate

Tasks

Capture pre-remediation metrics.

Execute remediation.

Wait for recovery window.

Collect post-remediation metrics.

Compare results.

Mark incident resolved or unresolved.

Send result to Slack.

Completion Criteria

The platform must report whether the remediation worked.

Phase 13 — GitHub Actions CI/CD

Goal

Connect deployments to AI-Ops.

Pipeline

GitHub
   |
   v
GitHub Actions
   |
   +-- Test
   +-- Build
   +-- Docker
   +-- Push
   +-- Deploy
   |
   v
Application

Tasks

Create CI workflow.

Run tests.

Build Docker image.

Push image to ECR.

Deploy application.

Record deployment version.

Record deployment timestamp.

Feed deployment data to AI-Ops.

Completion Criteria

AI can correlate a production incident with a recent deployment.

Final Acceptance Test

The complete project must successfully demonstrate:

1. Application running
        ↓
2. Metrics collected
        ↓
3. Logs collected
        ↓
4. Traces collected
        ↓
5. Incident intentionally created
        ↓
6. Alert generated
        ↓
7. Lambda receives incident
        ↓
8. Metrics/logs/traces collected
        ↓
9. AI performs RCA
        ↓
10. Runbook retrieved
        ↓
11. Slack notification generated
        ↓
12. Human approves remediation
        ↓
13. Lambda performs remediation
        ↓
14. Recovery verified
        ↓
15. Incident marked resolved

Rules for Progress

Never say a phase is complete until its completion criteria have been tested.

Never skip a phase.

Never change the existing project path without explicit approval.

Never replace a working component just to introduce a more complex technology.

Never give the AI unrestricted production-remediation access.

The next phase starts only after the previous phase is verified.