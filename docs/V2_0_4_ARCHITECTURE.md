# Version 2.0.4 Backend Reliability and Portfolio Architecture

Version 2.0.4 keeps the Version 2.0.3 modular-monolith topology and adds
reliability at the synchronous Analyze boundary. The English Architecture page,
[architecture overview](ARCHITECTURE.md), and [ADRs](adr/README.md) describe
the same implemented system.

Nginx Edge terminates HTTPS, Frontend Nginx serves React and proxies `/api`,
FastAPI owns authentication and product behavior, PostgreSQL 16 is the durable
system of record, Redis is transient coordination, and the Worker/Outbox
processes retain the asynchronous foundation. Only Edge 8080 is public.

Every request receives a validated client or generated Request ID that is
returned through successful and error responses. Analyze errors use the stable
`error_code`, `message`, `request_id`, and `retryable` envelope.

For optional keyed Analyze requests, PostgreSQL stores a user- and
operation-scoped key hash, canonical request fingerprint, lease/attempt state,
bounded response, and optional History ID. A unique constraint and row locks
select one concurrent winner. Completed requests replay without another model
call or History row. History insertion and ledger completion share a
transaction. A provider-started ambiguous outcome becomes `indeterminate` and
is not automatically re-executed.

The SDK has `max_retries=0`; the application makes at most one primary call and
one explicit format-only repair call. These controls do not provide external
exactly-once execution.

Alembic `20260724_06` follows `20260721_05` and adds only
`analyze_idempotency_records`, its constraints, and indexes. PostgreSQL also
executes the optimized Monitoring aggregation in SQL rather than loading all
rows into Python.
