# ADR 0002: Keep AI advisory and controls deterministic

## Status

Accepted

## Context

Resume/JD analysis benefits from model-assisted interpretation, but model
responses can be unavailable, malformed, incomplete, or unsupported by the
current evidence. Authentication, evidence trust, scoring, persistence, and
employment decisions cannot safely depend on unverified model output.

Version 2.0.3 already implements bounded prompting, tolerant parsing, one
format-only repair, deterministic fallback, evidence grounding, and
backend-owned scoring.

## Decision

Use DeepSeek only for advisory structured judgments. Deterministic application
code validates and scans inputs, controls Project Knowledge retrieval, validates
evidence IDs, reconciles skills and claims, creates trusted source metadata,
calculates the final weighted score, and persists the normalized result.

Return a stable result state of `complete`, `repaired`, `partial`, or `fallback`
and expose warnings and evidence for human review. Do not let the model submit
applications, contact employers, guarantee ATS performance, or make autonomous
hiring decisions.

## Consequences

- The application can return a basic, stable fallback result when the provider
  or model format fails.
- Unsupported claims and references can be removed without discarding all
  usable advisory content.
- Final scores and source metadata are calculated by inspectable backend rules
  rather than accepted as model assertions.
- Results still require human interpretation, and model-assisted content can
  vary between otherwise equivalent requests.
- The deterministic controls add validation and reconciliation work around the
  provider call.
