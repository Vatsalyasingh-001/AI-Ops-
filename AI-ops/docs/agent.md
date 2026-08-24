AI-Ops Project Agent Instructions

Purpose

This document defines the rules that must be followed while building the AI-Ops project.

The goal is to build the project incrementally and never skip ahead without completing and validating the current phase.

Project Goal

Build an AI-powered DevOps/SRE incident management platform that:

Runs a sample backend behind Nginx.

Collects metrics, logs, and traces.

Detects operational incidents.

Sends incident context to an AI analysis service.

Performs AI-assisted root cause analysis.

Uses runbooks through RAG.

Sends incident summaries and recommendations to Slack.

Supports human-approved remediation.

Verifies whether remediation recovered the service.

Integrates CI/CD and deployment history.

Non-Negotiable Rules

1. Follow the planned phases

The implementation order is fixed:

Nginx + Python backend

Prometheus + Grafana

Loki + logs

Tempo + traces

Intentional failure scenarios

Alertmanager

Lambda AI-Ops analyzer

AI root cause analysis

RAG + runbooks

Slack notifications

Human-approved remediation

Recovery verification

GitHub Actions CI/CD integration

Do not jump to a later phase because it looks easier or more interesting.

2. Do not change the project path

The initial application structure is fixed:

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

When new components are introduced, extend this structure deliberately. Do not rename or move the existing paths unless explicitly approved.

3. Validate every phase

A phase is complete only when:

Configuration is created.

Containers/services start successfully.

The component is tested.

Expected output is verified.

Documentation is updated if necessary.

Never mark a phase complete based only on configuration files.

4. Keep the architecture simple first

The first deployment must be:

Internet → Nginx → Python backend

Do not initially add:

ALB

ECS

Lambda

API Gateway

RAG

AI

Slack

Those components are introduced later according to plan.

5. Prefer working systems over unnecessary complexity

Use the simplest implementation that demonstrates the concept.

Do not introduce Kubernetes, Terraform, Kafka, databases, service meshes, or additional infrastructure unless a later phase explicitly requires them.

6. Security

Never hard-code:

AWS access keys

API keys

LLM API keys

Slack tokens

passwords

Use environment variables, AWS IAM roles, AWS Secrets Manager, or GitHub Actions secrets where appropriate.

7. AI must not have unrestricted remediation access

The first AI implementation is advisory only.

The flow must be:

Incident → AI analysis → Recommendation → Human approval → Remediation

Automatic remediation may only be introduced after the human-approved remediation path has been tested.

8. Incident data must be evidence-based

The AI should receive actual:

Prometheus metrics

Loki logs

Tempo traces

deployment information

relevant runbook content

The AI must not invent operational facts.

9. Every incident must be reproducible

We should maintain intentional test scenarios such as:

High CPU

High latency

High error rate

Nginx 502

Bad deployment

Each scenario should have a documented way to reproduce it and a documented expected result.

10. Do not rewrite working components unnecessarily

Once a phase is working, preserve it.

When adding a new phase:

Add the required component.

Integrate it with the existing component.

Avoid replacing working architecture unless there is a documented reason.

Initial Application

The initial backend must expose:

/

/health

/slow

/error

These endpoints are intentional and should remain available because they will be used later to generate observability incidents.

Completion Standard

At every stage, answer:

What did we build?

Where is it located?

How do we start it?

How do we test it?

What output should we see?

What failure scenario can we reproduce?

Is the current phase complete?

Only then move to the next phase.

Current Starting Point

We start at Phase 1.

Target:

Internet → Nginx → Python backend

Nothing beyond Phase 1 should be considered implemented until Phase 1 is verified.