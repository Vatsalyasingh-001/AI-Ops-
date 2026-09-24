# Self-Healing SRE / AIOps Platform

> **An open-source, zero-cost, closed-loop SRE platform that detects service failures, diagnoses incidents using metrics and logs, performs controlled automated remediation, verifies recovery, and escalates unresolved incidents.**

---

## 1. Project Overview

Modern applications consist of multiple services, reverse proxies, databases, APIs, and infrastructure components. When one of these components fails, an SRE typically needs to:

1. Detect the problem
2. Investigate the incident
3. Identify the root cause
4. Perform remediation
5. Verify that the service has recovered
6. Escalate the incident if recovery fails

This project automates that workflow.

The platform creates a **closed-loop self-healing system** using entirely open-source technologies.

The system continuously observes applications, detects failures, analyzes the available telemetry, selects an approved remediation action, executes it, and verifies whether the system recovered.

```text
                ┌─────────────────────┐
                │      Applications   │
                │                     │
                │   Website A         │
                │   Website B         │
                └──────────┬──────────┘
                           │
                           ▼
                      ┌─────────┐
                      │  NGINX  │
                      └────┬────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
       Prometheus        Loki           OTel
            │              │              │
            └──────────────┼──────────────┘
                           │
                           ▼
                        Grafana
                           │
                           ▼
                     Alertmanager
                           │
                           ▼
                ┌──────────────────────┐
                │ Self-Healing Engine  │
                │                      │
                │ Detection            │
                │ Diagnosis            │
                │ Policy               │
                │ Remediation          │
                │ Verification         │
                └──────────┬───────────┘
                           │
                           ▼
                     Application
                       Recovery
```

---

# 2. Project Goals

The primary goals are:

* Build a production-style SRE architecture locally
* Monitor multiple independent services
* Collect metrics, logs, and traces
* Detect service failures automatically
* Generate alerts based on SLO/threshold conditions
* Diagnose failures using available telemetry
* Execute safe automated remediation
* Verify whether remediation succeeded
* Prevent infinite remediation loops
* Understand service dependencies
* Escalate incidents that cannot be automatically resolved
* Provide a Grafana-based observability dashboard
* Add optional AI-assisted Root Cause Analysis (RCA)
* Keep the entire project **zero-cost**

---

# 3. Cost Model

The project is designed to run without paid infrastructure.

### Target Cost

```text
Infrastructure cost: ₹0
Monitoring cost:     ₹0
Logging cost:        ₹0
Dashboard cost:      ₹0
Alerting cost:       ₹0
Container cost:      ₹0
Database cost:       ₹0
```

All major components are open-source and can run locally using Docker.

### Technology

| Component           | Technology           | Cost |
| ------------------- | -------------------- | ---: |
| Containers          | Docker               |   ₹0 |
| Reverse Proxy       | NGINX                |   ₹0 |
| Metrics             | Prometheus           |   ₹0 |
| Dashboards          | Grafana              |   ₹0 |
| Alerting            | Alertmanager         |   ₹0 |
| Logs                | Loki                 |   ₹0 |
| Telemetry           | OpenTelemetry        |   ₹0 |
| Log Agent           | Promtail / Vector    |   ₹0 |
| Backend             | Python               |   ₹0 |
| Self-Healing Engine | Python               |   ₹0 |
| AI/RCA              | Optional local model |   ₹0 |
| Infrastructure      | Local machine        |   ₹0 |

> The project intentionally avoids paid cloud services, paid monitoring platforms, and mandatory external APIs.

---

# 4. High-Level Architecture

```text
                         LOCAL MACHINE
                              │
                 ┌────────────┴────────────┐
                 │                         │
                 ▼                         ▼
              NGINX                   Applications
                 │                    ┌────────────┐
          ┌──────┴──────┐             │ Website A  │
          │             │             └────────────┘
          ▼             ▼             ┌────────────┐
     Website A      Website B          │ Website B  │
                                      └────────────┘

                 APPLICATION TELEMETRY
                         │
          ┌──────────────┼───────────────┐
          ▼              ▼               ▼
      Prometheus       Loki            OTel
          │              │               │
          └──────────────┼───────────────┘
                         ▼
                      Grafana
                         │
                         ▼
                   Alertmanager
                         │
                         ▼
              Self-Healing Controller
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Diagnosis        Policy       Remediation
                                         │
                                         ▼
                                    Application
                                         │
                                         ▼
                                    Verification
                                         │
                              ┌──────────┴─────────┐
                              ▼                    ▼
                           Healthy              Failed
                              │                    │
                           Resolve             Escalate
```

---

# 5. Core SRE Philosophy

The project follows the SRE closed-loop model:

```text
OBSERVE
   ↓
DETECT
   ↓
DIAGNOSE
   ↓
DECIDE
   ↓
REMEDIATE
   ↓
VERIFY
   ↓
RESOLVE / ESCALATE
```

This is the core concept behind the entire platform.

---

# 6. Components

## 6.1 NGINX

NGINX acts as the reverse proxy and entry point for the applications.

Example:

```text
example-a.local → Website A
example-b.local → Website B
```

Architecture:

```text
Client
  │
  ▼
NGINX
 ├── Website A
 └── Website B
```

NGINX also provides an important dependency relationship.

If both websites fail simultaneously, the system should investigate NGINX or another shared dependency before independently restarting both applications.

---

# 7. Website Services

The project contains at least two independently monitored services.

```text
Website A
Website B
```

Each application should provide:

```text
/
 /health
 /metrics
```

### Health endpoint

Example:

```json
{
  "status": "healthy"
}
```

The health endpoint is used by the verification engine to determine whether a service recovered.

---

# 8. Prometheus

Prometheus is responsible for collecting metrics.

Example metrics:

```text
http_requests_total
http_request_duration_seconds
http_5xx_total
process_cpu_usage
process_memory_usage
```

Prometheus allows the system to answer:

> What is happening?

Examples:

```text
Request rate = 1,500 req/min
5xx rate = 18%
P95 latency = 4.8s
CPU = 85%
Memory = 72%
```

---

# 9. Grafana

Grafana provides the human-facing observability dashboard.

The dashboard should display:

### Application Health

```text
Website A    🟢
Website B    🟢
NGINX        🟢
```

### Traffic

```text
Requests/sec
Request rate
```

### Reliability

```text
Availability
Error rate
5xx rate
```

### Performance

```text
P50 latency
P95 latency
P99 latency
```

### Infrastructure

```text
CPU
Memory
Disk
Network
```

### Healing

```text
Incidents
Remediation attempts
Successful recoveries
Failed recoveries
MTTR
```

---

# 10. Loki

Loki provides centralized log storage.

Application logs are collected and sent to Loki.

Example:

```text
2026-09-24 12:00:10 INFO Request received
2026-09-24 12:00:12 ERROR Database connection timeout
2026-09-24 12:00:12 ERROR Request failed
```

Metrics can tell us:

```text
Error rate increased
```

Logs can tell us:

```text
Database connection timeout
```

Therefore metrics and logs complement each other.

---

# 11. OpenTelemetry

OpenTelemetry provides a standard framework for collecting telemetry.

The project can use:

* Metrics
* Logs
* Traces

A trace can show the path of a request:

```text
Client
  ↓
NGINX
  ↓
Website A
  ↓
API
  ↓
Database
```

Example:

```text
NGINX       20ms
Website A   50ms
API        100ms
Database  4.5sec
```

This makes it possible to identify where latency originates.

---

# 12. Alertmanager

Prometheus identifies conditions that violate predefined thresholds.

Example:

```yaml
alert: WebsiteHighErrorRate

expr: error_rate > 0.10

for: 5m
```

The alert is sent to Alertmanager.

```text
Prometheus
    │
    ▼
Alertmanager
    │
    ▼
Self-Healing Controller
```

Alertmanager is responsible for routing and grouping alerts.

---

# 13. Self-Healing Engine

The Self-Healing Engine is the central component of the project.

It consists of:

```text
Self-Healing Engine
│
├── Detection
├── Incident Manager
├── Diagnosis Engine
├── Dependency Engine
├── Policy Engine
├── Remediation Engine
└── Verification Engine
```

---

# 14. Detection Engine

The Detection Engine receives alerts from Alertmanager.

Example:

```json
{
  "alert": "WebsiteHighErrorRate",
  "service": "website-a",
  "severity": "critical"
}
```

The system then validates the condition.

It may check:

```text
/health
metrics
error rate
latency
recent logs
```

This prevents the system from performing unnecessary remediation based on a transient or invalid signal.

---

# 15. Incident Manager

Every detected incident receives an incident record.

Example:

```json
{
  "incident_id": "INC-001",
  "service": "website-a",
  "alert": "HighErrorRate",
  "severity": "critical",
  "status": "investigating"
}
```

The incident progresses through states:

```text
DETECTED
   ↓
INVESTIGATING
   ↓
REMEDIATING
   ↓
VERIFYING
   ↓
RESOLVED
```

or:

```text
DETECTED
   ↓
INVESTIGATING
   ↓
REMEDIATING
   ↓
VERIFYING
   ↓
FAILED
   ↓
ESCALATED
```

---

# 16. Diagnosis Engine

The Diagnosis Engine determines the likely cause of the incident.

It uses:

```text
Metrics
Logs
Traces
Health checks
Dependencies
Recent deployments
Service state
```

Example:

```text
5xx ↑
CPU normal
Memory normal
NGINX healthy
Database healthy
Recent deployment detected
```

Possible diagnosis:

```text
Application/deployment related failure
```

---

# 17. Dependency Engine

The system maintains a dependency graph.

Example:

```text
                 NGINX
                /     \
               /       \
        Website A     Website B
             │             │
             ▼             ▼
           API A         API B
             │             │
             └──────┬──────┘
                    ▼
                 Database
```

The dependency graph prevents incorrect remediation.

For example:

```text
Website A 🔴
Website B 🔴
```

The controller checks:

```text
Do both services share a dependency?
```

If yes:

```text
Check shared dependency
```

rather than blindly restarting both services.

---

# 18. Policy Engine

The Policy Engine determines which remediation actions are permitted.

Example:

```yaml
website-a:
  high_error_rate:
    action: restart
    max_attempts: 2
    cooldown: 300
```

This means:

* Restart Website A
* Maximum two attempts
* Wait five minutes before another automated attempt

The LLM, if used, does not bypass the Policy Engine.

---

# 19. Remediation Engine

The Remediation Engine executes approved actions.

Possible actions include:

```text
restart service
restart container
reload NGINX
rollback deployment
scale service
clear temporary state
```

The initial implementation should use only safe and deterministic actions.

The first remediation should be:

```text
Restart application
```

---

# 20. Verification Engine

After remediation, the system must confirm that recovery actually occurred.

Example:

```text
Restart Website A
        ↓
Wait 10 seconds
        ↓
Check /health
        ↓
Check 5xx rate
        ↓
Check latency
```

Successful recovery:

```text
Before:
5xx = 25%
Health = DOWN

After:
5xx = 0.2%
Health = UP
```

Result:

```text
INCIDENT RESOLVED
```

---

# 21. Retry and Safety Mechanism

Automated remediation can become dangerous if not controlled.

The system therefore implements:

### Maximum attempts

```text
max_attempts = 2
```

### Cooldown

```text
cooldown = 5 minutes
```

### Idempotency

The same incident should not trigger duplicate actions unnecessarily.

### Blast-radius control

The system should modify only the affected component whenever possible.

### Escalation

If remediation fails:

```text
Automated healing failed
        ↓
Stop automation
        ↓
Escalate to SRE
```

---

# 22. Failure Scenarios

The platform should demonstrate multiple failure scenarios.

## Scenario 1 — Application Crash

```text
Website A
   ↓
Crash
   ↓
Prometheus detects failure
   ↓
Alertmanager
   ↓
Self-Healing Controller
   ↓
Restart Website A
   ↓
Health verification
   ↓
Recovered
```

---

## Scenario 2 — High Error Rate

```text
5xx rate > threshold
        ↓
Alert
        ↓
Diagnosis
        ↓
Check logs
        ↓
Identify likely cause
        ↓
Approved remediation
        ↓
Verification
```

---

## Scenario 3 — High Latency

```text
P95 latency increases
        ↓
Prometheus alert
        ↓
Controller
        ↓
Inspect traces/logs
        ↓
Identify slow dependency
        ↓
Apply appropriate remediation
```

---

## Scenario 4 — NGINX Failure

```text
NGINX
  ↓
Failure
  ↓
Website A 🔴
Website B 🔴
```

The dependency engine identifies that both services depend on NGINX.

Instead of:

```text
Restart Website A
Restart Website B
```

the system performs:

```text
Check NGINX
   ↓
Repair NGINX
   ↓
Verify Website A
   ↓
Verify Website B
```

---

# 23. AI-Assisted RCA

AI is an optional layer rather than the foundation of the system.

The deterministic SRE pipeline must work without AI.

The AI layer receives:

```text
Metrics
+
Logs
+
Traces
+
Recent deployments
+
Service dependencies
```

Example context:

```text
Error rate: 22%
P95 latency: 4.8 sec
CPU: 35%
Memory: 42%

Logs:
Database connection timeout

Recent deployment:
5 minutes ago
```

The AI can generate:

```text
Likely Cause:
Database connectivity issue.

Evidence:
- Increased database timeout errors
- Increased 5xx responses
- CPU and memory are normal

Suggested Action:
Verify database connectivity.
```

The output goes to the Policy Engine.

```text
AI
 ↓
Recommendation
 ↓
Policy Engine
 ↓
Approved?
 ↓
Remediation
```

The AI should not receive unrestricted infrastructure access.

---

# 24. Why AI Is Not the First Component

A reliable SRE platform should not depend entirely on an LLM.

The core system must first work:

```text
Monitoring
     ↓
Alerting
     ↓
Diagnosis
     ↓
Policy
     ↓
Remediation
     ↓
Verification
```

AI is then added to improve:

* RCA
* incident summaries
* anomaly explanations
* remediation recommendations
* post-incident analysis

This makes the system more deterministic and safer.

---

# 25. SRE Metrics

The platform can track important SRE metrics.

## Availability

```text
Availability =
Successful Requests / Total Requests
```

## Error Rate

```text
Error Rate =
Failed Requests / Total Requests
```

## Latency

Track:

```text
P50
P95
P99
```

## MTTD

Mean Time To Detect.

```text
Incident Start → Detection
```

## MTTR

Mean Time To Recovery.

```text
Incident Start → Recovery
```

The project should demonstrate that automated remediation can reduce MTTR for predefined failure scenarios.

---

# 26. SLO-Based Alerting

Instead of monitoring only infrastructure thresholds, the project can also use service-level objectives.

Example:

```text
Availability SLO = 99.9%
Latency SLO = P95 < 500ms
Error SLO = < 1%
```

Example:

```text
Actual availability = 98.5%
SLO = 99.9%
```

This indicates a reliability problem.

---

# 27. Error Budget

For a 99.9% availability SLO:

```text
Allowed downtime ≈ 0.1%
```

The error budget helps determine whether the service is consuming reliability too quickly.

The system can display:

```text
SLO:          99.9%
Availability: 99.95%
Error Budget: Healthy
```

or:

```text
SLO:          99.9%
Availability: 99.4%
Error Budget: Exhausted
```

---

# 28. Project Repository Structure

```text
self-healing-platform/
│
├── README.md
│
├── apps/
│   ├── website-a/
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── website-b/
│       ├── app.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── nginx/
│   ├── nginx.conf
│   └── Dockerfile
│
├── controller/
│   ├── app.py
│   ├── controller.py
│   ├── incident_manager.py
│   ├── diagnosis.py
│   ├── dependency.py
│   └── policy.py
│
├── remediation/
│   ├── actions.py
│   ├── docker.py
│   └── nginx.py
│
├── verification/
│   ├── health.py
│   ├── metrics.py
│   └── recovery.py
│
├── integrations/
│   ├── prometheus.py
│   ├── alertmanager.py
│   ├── loki.py
│   └── otel.py
│
├── ai/
│   ├── rca.py
│   ├── prompts.py
│   └── recommendations.py
│
├── policies/
│   ├── website-a.yaml
│   ├── website-b.yaml
│   └── nginx.yaml
│
├── monitoring/
│   ├── prometheus.yml
│   ├── alertmanager.yml
│   └── rules/
│
├── dashboards/
│   └── grafana/
│
├── tests/
│
├── docker-compose.yml
│
└── docs/
    ├── architecture.md
    ├── failure-scenarios.md
    ├── runbooks.md
    └── ai-rca.md
```

---

# 29. Implementation Roadmap

## Phase 1 — Application Environment

Build:

```text
Website A
Website B
NGINX
Docker Compose
```

Verify:

```text
Website A → accessible
Website B → accessible
NGINX → routing correctly
```

---

## Phase 2 — Observability

Add:

```text
Prometheus
Grafana
```

Implement:

```text
Request metrics
Error metrics
Latency metrics
CPU
Memory
Health checks
```

---

## Phase 3 — Logging

Add:

```text
Loki
Promtail / Vector
```

Centralize:

```text
NGINX logs
Website A logs
Website B logs
Self-Healing Controller logs
```

---

## Phase 4 — Alerting

Add:

```text
Alertmanager
```

Create alerts for:

```text
Service down
High error rate
High latency
High CPU
High memory
```

---

## Phase 5 — Self-Healing Controller

Implement:

```text
Webhook
     ↓
Incident Manager
     ↓
Diagnosis
     ↓
Policy
     ↓
Remediation
     ↓
Verification
```

Start with one action:

```text
Restart service
```

---

## Phase 6 — Dependency-Aware Healing

Implement:

```text
Service Registry
Dependency Graph
Shared Dependency Detection
```

Example:

```text
NGINX
 ├── Website A
 └── Website B
```

---

## Phase 7 — Advanced Remediation

Add controlled actions:

```text
Restart
Reload
Rollback
Scale
```

Every action must have:

```text
Permission
Policy
Maximum attempts
Cooldown
Verification
```

---

## Phase 8 — OpenTelemetry

Add:

```text
Distributed tracing
```

Use traces for:

```text
Latency investigation
Dependency failures
Request flow
```

---

## Phase 9 — AI-Assisted RCA

Add:

```text
Metrics
+
Logs
+
Traces
+
Deployment information
        ↓
       LLM
        ↓
 RCA / Recommendation
```

Keep execution behind the Policy Engine.

---

# 30. Testing Strategy

The system should be tested by intentionally creating failures.

### Test 1

```text
Stop Website A
```

Expected:

```text
Alert → Restart → Verify → Resolve
```

### Test 2

```text
Stop Website B
```

Expected:

```text
Alert → Restart → Verify → Resolve
```

### Test 3

```text
Break NGINX
```

Expected:

```text
A + B failure
      ↓
Dependency analysis
      ↓
NGINX identified
      ↓
NGINX remediation
      ↓
A + B recovery
```

### Test 4

```text
Generate 5xx errors
```

Expected:

```text
High error alert
      ↓
Diagnosis
      ↓
Policy
      ↓
Remediation
      ↓
Verification
```

### Test 5

Make the service permanently fail.

Expected:

```text
Attempt 1
   ↓
Failed

Attempt 2
   ↓
Failed

Stop automation
   ↓
Escalation
```

This demonstrates safe failure handling.

---

# 31. Security Model

The self-healing engine should not have unrestricted system access.

Use:

```text
Least Privilege
```

The controller should only be allowed to perform predefined actions.

For example:

```text
Allowed:
✓ restart website-a
✓ restart website-b
✓ reload nginx

Not allowed:
✗ arbitrary shell commands
✗ delete infrastructure
✗ modify unrelated services
✗ unrestricted container access
```

---

# 32. Failure Prevention

The system must avoid becoming a source of additional failures.

Safety mechanisms:

```text
Maximum remediation attempts
Cooldown
Idempotency
Dependency awareness
Action allowlist
Health verification
Audit logs
Escalation
```

Every remediation should be recorded.

Example:

```json
{
  "incident_id": "INC-001",
  "service": "website-a",
  "action": "restart",
  "attempt": 1,
  "result": "success",
  "duration": "14s"
}
```

---

# 33. Audit Trail

Every automated action should be logged.

Example:

```text
12:00:10 ALERT Website A unhealthy

12:00:12 INCIDENT INC-001 CREATED

12:00:15 DIAGNOSIS Website A process unavailable

12:00:17 POLICY restart approved

12:00:18 ACTION restart website-a

12:00:28 HEALTH CHECK passed

12:00:30 INCIDENT INC-001 RESOLVED
```

This makes the system explainable and useful for post-incident analysis.

---

# 34. Example End-to-End Incident

### Normal state

```text
Website A 🟢
Website B 🟢
NGINX    🟢
```

### Failure

Website A crashes.

```text
Website A 🔴
```

### Detection

Prometheus detects:

```text
up{service="website-a"} = 0
```

### Alert

Alertmanager sends:

```text
WebsiteDown
```

### Diagnosis

Controller checks:

```text
Website A → DOWN
NGINX → UP
Website B → UP
```

Conclusion:

```text
Website A is isolated failure.
```

### Policy

```text
Website A down → restart
```

### Remediation

```text
Restart Website A
```

### Verification

```text
/health → 200
```

### Result

```text
Website A 🟢
```

### Incident

```text
RESOLVED
```

---

# 35. What Makes This an SRE Project?

This project demonstrates practical SRE concepts:

* Observability
* SLIs
* SLOs
* Error budgets
* Alerting
* Incident management
* Automated remediation
* Health checks
* Dependency management
* RCA
* MTTD
* MTTR
* Runbooks
* Safe automation
* Failure testing
* Escalation
* Reliability engineering

It is not simply a monitoring dashboard.

The major difference is the **closed feedback loop**:

```text
Monitor
   ↓
Detect
   ↓
Diagnose
   ↓
Act
   ↓
Verify
```

---

# 36. Technology Stack

```text
Backend:
Python

Containers:
Docker
Docker Compose

Reverse Proxy:
NGINX

Metrics:
Prometheus

Visualization:
Grafana

Logs:
Loki

Telemetry:
OpenTelemetry

Alerting:
Alertmanager

Automation:
Python Self-Healing Controller

Configuration:
YAML

AI:
Optional local LLM / OpenAI-compatible API

Testing:
Pytest
curl
Docker
```

---

# 37. Zero-Cost Architecture

The complete local architecture is:

```text
                    LOCAL MACHINE
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
      NGINX                         Website A / B
        │                                 │
        └────────────────┬────────────────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
         Prometheus     Loki        OTel
             │           │           │
             └───────────┼───────────┘
                         ▼
                      Grafana
                         │
                         ▼
                   Alertmanager
                         │
                         ▼
                Self-Healing Engine
                         │
                         ▼
                  Docker / Services
                         │
                         ▼
                     Recovery
```

No mandatory cloud infrastructure is required.

---

# 38. Future Enhancements

Possible future improvements include:

### Kubernetes

Replace Docker-based remediation with Kubernetes:

```text
Deployment
Service
Pod
HPA
```

### Cloud Integration

Adapters can later be added for:

```text
AWS
Azure
GCP
```

### Advanced AI

Add:

```text
AI RCA
Incident summarization
Anomaly detection
Runbook recommendation
Predictive failure detection
```

### Automated Rollback

Detect:

```text
Deployment
    ↓
Error rate increases
    ↓
Rollback
    ↓
Verify
```

### ChatOps

Integrate incident notifications with:

```text
Slack
Microsoft Teams
Email
```

---

# 39. Final Architecture

```text
                         ┌───────────────┐
                         │    CLIENT     │
                         └───────┬───────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │     NGINX     │
                         └───────┬───────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
              ┌───────────┐             ┌───────────┐
              │ Website A │             │ Website B │
              └─────┬─────┘             └─────┬─────┘
                    │                         │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
               Prometheus      Loki          OTel
                    │            │            │
                    └────────────┼────────────┘
                                 │
                                 ▼
                            ┌──────────┐
                            │ Grafana  │
                            └────┬─────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │ Alertmanager │
                         └──────┬───────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │   SELF-HEALING ENGINE   │
                   │                         │
                   │ Detection               │
                   │ Incident Management     │
                   │ Diagnosis               │
                   │ Dependency Analysis     │
                   │ Policy Engine           │
                   │ Remediation             │
                   │ Verification            │
                   └────────────┬────────────┘
                                │
                     ┌──────────┴──────────┐
                     │                     │
                     ▼                     ▼
                 Remediate              Verify
                     │                     │
                     └──────────┬──────────┘
                                │
                                ▼
                           Applications
                                │
                         ┌──────┴──────┐
                         │             │
                      Healthy        Failed
                         │             │
                         ▼             ▼
                     RESOLVED       ESCALATE
```

---

# 40. Project Outcome

At the end of the project, the platform should be able to demonstrate:

```text
✓ Multiple applications
✓ Reverse proxy
✓ Metrics collection
✓ Centralized logging
✓ Distributed tracing
✓ Grafana dashboards
✓ Automated alerting
✓ Incident management
✓ Failure diagnosis
✓ Dependency awareness
✓ Automated remediation
✓ Recovery verification
✓ Retry limits
✓ Cooldowns
✓ Escalation
✓ SLO monitoring
✓ MTTR measurement
✓ Optional AI-assisted RCA
```

The final objective is to demonstrate a **closed-loop SRE system** where the platform doesn't simply tell an engineer that something is broken.

It can:

```text
OBSERVE
   ↓
DETECT
   ↓
UNDERSTAND
   ↓
DECIDE
   ↓
REPAIR
   ↓
VERIFY
   ↓
ESCALATE IF NECESSARY
```

---

## Project Tagline

> **Observe. Detect. Diagnose. Heal. Verify.**

This project demonstrates how traditional observability can evolve into an automated, policy-driven, and eventually AI-assisted SRE platform — entirely using open-source technologies and a zero-cost local environment.
