AI-Ops Project Architecture

1. Project Objective

Build an AI-powered AIOps platform that detects infrastructure/application incidents, correlates metrics, logs, traces, and deployment information, performs AI-assisted root cause analysis, recommends remediation, and eventually performs human-approved remediation.

2. Final Target Architecture

                              USERS
                                |
                                | HTTP/HTTPS
                                v
                         +--------------+
                         |    Nginx     |
                         | Reverse Proxy|
                         +------+-------+
                                |
                                v
                       +-----------------+
                       | Python Backend  |
                       | Flask/Gunicorn  |
                       +--------+--------+
                                |
                 +--------------+--------------+
                 |              |              |
                 v              v              v
               Logs          Metrics         Traces
                 |              |              |
                 v              v              v
               Loki        Prometheus         Tempo
                 |              |              |
                 +--------------+--------------+
                                |
                                v
                            Grafana
                                |
                                v
                           Alertmanager
                                |
                                v
                       +------------------+
                       | AI-Ops Lambda    |
                       | Incident Analyzer|
                       +--------+---------+
                                |
                 +--------------+--------------+
                 |              |              |
                 v              v              v
            Prometheus        Loki           Tempo
                 |              |              |
                 +--------------+--------------+
                                |
                                v
                       +------------------+
                       | AI / LLM Engine  |
                       | RCA + Analysis   |
                       +--------+---------+
                                |
                       +--------+--------+
                       |                 |
                       v                 v
                    Runbooks           Slack
                      / RAG
                       |                 |
                       +--------+--------+
                                |
                         Human Approval
                                |
                                v
                       +------------------+
                       | Remediation      |
                       | Lambda + Boto3   |
                       +--------+---------+
                                |
                     +----------+----------+
                     |          |          |
                     v          v          v
                    EC2        ECS      AWS APIs
                     |          |          |
                     +----------+----------+
                                |
                                v
                         Recovery Check
                                |
                                v
                            Grafana

3. Phase 1 Architecture

Phase 1 intentionally contains only:

Internet
   |
   v
EC2
   |
   +-- Docker
       |
       +-- Nginx :80
       |
       +-- Python Backend :8000

Docker Compose will connect Nginx to the backend.

4. Phase 1 Application Structure

AI-ops/
├── README.md
├── docker-compose.yml
├── docs/
│   ├── agent.md
│   ├── architecture.md
│   └── plan.md
├── app/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── prometheus/
│   └── prometheus.yml
└── grafana/
    └── provisioning/
        ├── dashboards/
        │   ├── backend-overview.json
        │   └── dashboard.yml
        └── datasources/
            └── datasource.yml

5. Backend Endpoints

/

Returns:

AI-Ops Demo Application

/health

Returns a healthy status.

/slow

Intentionally delays the response by approximately five seconds.

Purpose:

Demonstrate latency.

Later generate latency alerts.

Validate Prometheus latency metrics.

/error

Intentionally raises an application error.

Purpose:

Generate application errors.

Validate Loki logs.

Later trigger high-error-rate alerts.

Provide an AI RCA scenario.

6. Observability Architecture

After Phase 1:

Application
   |
   +---- Metrics ---> Prometheus ---> Grafana
   |
   +---- Logs ------> Loki --------> Grafana
   |
   +---- Traces ----> Tempo -------> Grafana

The three signals are:

Metrics: what is happening?

Logs: what happened?

Traces: where did the request spend time?

7. Incident Pipeline

Incident
   |
   v
Prometheus / Alertmanager
   |
   v
AI-Ops Lambda
   |
   +---- Query metrics
   +---- Query logs
   +---- Query traces
   +---- Query deployment history
   |
   v
AI Analysis
   |
   +---- Root cause
   +---- Severity
   +---- Evidence
   +---- Confidence
   +---- Recommendation
   |
   v
Slack
   |
   v
Human Approval
   |
   v
Remediation Lambda
   |
   v
AWS
   |
   v
Recovery Verification

8. AI Input

The AI should receive structured incident context:

Incident:
Service:
Alert:
Timestamp:
Severity:

Metrics:
- CPU
- Memory
- Error rate
- Request rate
- P95/P99 latency

Logs:
- Recent errors
- Repeated error patterns
- Relevant stack traces

Traces:
- Slow spans
- Failed spans
- Service dependency information

Deployment:
- Current version
- Previous version
- Recent deployment time

Runbook:
- Relevant operational procedure

9. AI Output

The AI should return:

Incident Summary
Severity
Probable Root Cause
Evidence
Confidence
Recommended Action
Relevant Runbook
Risk / Safety Notes

The AI must distinguish between evidence and inference.

10. Remediation Architecture

Initial:

AI
 |
 v
Recommendation
 |
 v
Human
 |
 +-- Reject
 |
 +-- Approve
       |
       v
    Lambda
       |
       v
   AWS API

Examples:

Restart service.

Force ECS deployment.

Roll back deployment.

Scale service.

Remediation permissions must follow least privilege.

11. CI/CD Architecture

Later:

Developer
   |
   v
GitHub
   |
   v
GitHub Actions
   |
   +-- Test
   +-- Build
   +-- Docker image
   +-- Push image
   +-- Deploy
   |
   v
Application
   |
   v
Observability
   |
   v
AI-Ops

The AI should be able to correlate incidents with recent deployments.

12. Design Principle

The architecture follows:

Observe → Detect → Correlate → Analyze → Recommend → Approve → Remediate → Verify