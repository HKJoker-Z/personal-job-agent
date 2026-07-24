# ADR 0003: Use PostgreSQL-owned work with Redis and Dramatiq

## Status

Accepted

## Context

The repository contains a durable Agent Run foundation with long-running Steps,
retries, leases, recovery, heartbeats, and dead-letter records. Queue transport
must not become the authoritative record, and queue payloads must not carry
Resume text, Job Description text, credentials, or other business content.

In Version 2.0.3 the direct `/api/analyze` workflow is synchronous. The public
Application workflow that created Agent Runs is retired, along with public
Agent Run create/retry/resume operations. Retained Runs remain readable,
streamable, and cancellable, while the worker and Outbox processes remain
required production components.

## Decision

Store Agent Runs, Steps, Events, leases, attempts, Outbox events, worker
heartbeats, and dead letters in PostgreSQL. Record an Outbox event in the
database state boundary, then let the standalone production dispatcher publish
due messages to the Redis-backed Dramatiq queue.

Limit queue payloads to validated Run ID, Step ID, workflow type, attempt, and
correlation ID. Dramatiq uses JSON encoding and disables framework-owned
retries; application state and rules own retry scheduling. Workers claim Steps
through PostgreSQL locking and leases, write liveness/active-task heartbeats,
and recover expired Steps. The dispatcher recovers interrupted publications
and orphaned deliveries and dead-letters exhausted Redis publication attempts.

Use Redis additionally for cross-process per-user SSE connection counting in
production. The SSE endpoint reads Agent Run events from PostgreSQL; Redis does
not carry the event history. Do not route the synchronous Resume/JD analysis
through Redis or the worker.

## Consequences

- PostgreSQL remains the recoverable source of truth when Redis delivery is
  interrupted or duplicated.
- Identifier-only messages reduce sensitive-data exposure in the broker.
- Database claims, delivery attempts, leases, and idempotency make duplicate
  delivery safe and permit bounded recovery.
- Redis, the worker, and the Outbox dispatcher add production health and
  operational dependencies even though new public Agent work is disabled.
- The retained asynchronous foundation must not be presented as event-driven
  microservices or as automatic job-application behavior.
- Production Redis persistence improves broker recovery, but it does not
  replace PostgreSQL ownership of durable workflow state.
