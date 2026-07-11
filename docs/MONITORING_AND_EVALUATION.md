# Monitoring and Evaluation

## Version 1.8 Overview

Version 1.8 adds a lightweight AI observability and behavioral evaluation layer to Personal Job Application Agent. It records sanitized workflow metadata for Analyze requests, exposes local monitoring APIs, provides a trace explorer by `workflow_id`, and runs an offline deterministic Behavioral Evaluation Suite.

This is local SQLite monitoring for development and portfolio demonstration. It is not distributed tracing, production-grade APM, OpenTelemetry, Langfuse, Prometheus, or Grafana.

## Monitoring Architecture

The Analyze API writes metadata-only metrics to SQLite in best-effort mode. Monitoring write failures are logged as safe error types and do not fail the primary Analyze request.

The monitoring layer records:

- Workflow outcome and total duration
- Step-level status and duration
- LLM step duration
- RAG hit and source counts
- Security status and finding codes
- PII redaction counts
- Recommendation action code
- Application history linkage when saved
- Safe error code and error stage for failed or blocked requests

## Metrics Data Model

Version 1.8 adds:

- `analysis_metrics`
- `analysis_step_metrics`
- `evaluation_runs`
- `evaluation_results`

`analysis_metrics` stores one row per workflow ID. `analysis_step_metrics` stores one row per workflow step without step messages. Evaluation tables store run summaries and safe check results.

## Privacy and Data Minimization

Metrics are stored locally in SQLite.

Monitoring tables do not store:

- Raw resumes
- Raw job descriptions
- Full prompts
- Full model outputs
- RAG chunk content
- Detected secret values
- Prompt injection attack text
- Step messages

Monitoring records metadata and counts only.

## Workflow Metrics

Workflow metrics include outcome, workflow status, total duration, LLM duration, source type, JSON parse success, saved-to-history status, application ID, and safe error codes.

Outcomes are:

- `completed`
- `completed_with_warnings`
- `failed`
- `blocked`

## RAG Metrics

RAG metrics include:

- RAG-enabled runs
- RAG hit runs
- RAG no-hit runs
- RAG hit rate
- Average source count
- Average retrieval duration
- Reconciliation runs
- Total reconciled skills or keywords

`rag_reconciliation_count` counts actual RAG evidence corrections from missing to matched status.

## Security Metrics

Security metrics include:

- Passed
- Passed with warnings
- Blocked
- Prompt injection detections
- Sensitive credential detections
- Output leakage detections
- Email, phone, and address redaction counts
- Finding code distribution

Finding distributions use stable finding codes only. They do not include malicious text or secrets.

## Recommendation Metrics

Recommendation metrics include action distribution:

- `apply_now`
- `improve_resume_first`
- `upskill_first`
- `save_for_later`
- `skip`

Human decision metrics include:

- `pending`
- `accepted`
- `dismissed`
- `completed`

Acceptance rate is `(accepted + completed) / decisions`. Empty denominators return `0`.

## Trace Explorer

The trace APIs expose sanitized metadata by workflow ID. Trace detail includes workflow timing, step status and duration, RAG metadata, security metadata, JSON parse status, saved-to-history status, next action code, and safe error code/stage.

Trace detail does not include resumes, job descriptions, prompts, model responses, RAG content, detected secrets, or original error strings.

## Behavioral Evaluation Suite

The Behavioral Evaluation Suite is deterministic, offline, and repeatable. It does not call DeepSeek or any external LLM. It checks rule compliance and regression behavior across security scanning, PII redaction, safe prompt construction, RAG evidence behavior, recommendation rules, workflow timing, legacy defaults, and output leakage scanning.

Evaluation pass rate means deterministic behavioral and rule compliance checks passed. It is not model accuracy, hiring success probability, or real-world job-search performance.

## Offline Evaluation Cases

Cases live in `backend/evals/cases.json` and use fictitious, sanitized test data. TEST ONLY fake secret strings are used only to exercise redaction and blocking behavior.

Evaluation results store:

- Case ID
- Case name
- Category
- Status
- Duration
- Safe check booleans
- Short failure summary

Evaluation results do not store full case input, prompts, model outputs, or secrets.

## Percentile Calculation

Workflow P50 and P95 use nearest-rank percentile implemented with the Python standard library.

Steps:

1. Drop skipped steps and null durations.
2. Sort remaining durations ascending.
3. Compute `ceil(percentile / 100 * n)`.
4. Return the value at that 1-based rank.

No NumPy or Pandas dependency is used.

## Limitations

- Monitoring is local and process-level.
- Monitoring persistence is best effort.
- Current traces are local application traces, not distributed traces.
- No external observability vendor is required.
- No raw prompts or private inputs are stored in monitoring tables.
- No additional DeepSeek calls are used for monitoring.
- Offline evaluation does not call external LLMs.
- Evaluation pass rate is not model accuracy.
- Metrics are suitable for local development and portfolio demonstration, not production APM.

## Future OpenTelemetry Integration

The metadata-only workflow IDs, step metrics, and trace API provide a foundation for future OpenTelemetry integration. Version 1.8 does not implement OpenTelemetry export, distributed tracing, Prometheus scraping, Grafana dashboards, or Langfuse integration.
