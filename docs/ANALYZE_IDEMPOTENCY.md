# Analyze PostgreSQL Idempotency

## Scope

This design applies only to synchronous `POST /api/analyze`. It does not create
Agent Runs, make Analyze asynchronous, use Redis as a ledger, alter
authentication, or change the RAG design.

## Contract and fingerprint

Clients may send the bounded `Idempotency-Key` documented in
`V2_0_3_API.md`. Keys are user- and operation-scoped. PostgreSQL stores a
domain-separated SHA-256 hash, never the raw key.

`analyze-request-fingerprint:v1` is SHA-256 over canonical JSON with sorted
keys, explicit nulls, compact separators, and UTF-8. It includes effective
Resume/JD hashes, Resume Version ID, normalized Job URL, RAG and top-k,
Project Knowledge document/content version hash, History choice,
`deepseek-chat`, compact-analysis contract version, and the security policy
version. Request IDs, time, cookies, CSRF values, and generated IDs are
excluded.

## State machine

```text
new/failed --claim--> processing --finalize--> completed
                         |
                         +--lease expired, provider absent--> processing takeover
                         |
                         +--provider started + ambiguous crash--> indeterminate
```

The unique constraint on `(user_id, operation, idempotency_key_hash)` is the
multi-process arbitration point. Each winner receives a random attempt token.
Provider-boundary and finalization updates require that token, so stale attempts
cannot overwrite a takeover. Transactions are short; no transaction or row lock
is held during provider I/O.

Immediately before the primary call and before the optional repair call, the
winner persists `provider_started_at`. OpenAI-compatible SDK automatic
transport retries are disabled with `max_retries=0`. The application permits at
most one primary call and one explicit format repair. Handled timeout, 5xx,
invalid JSON, or repair failure can still finalize the deterministic fallback.

## Atomic History

For `save_to_history=true`, the History row, normalized response,
`history_record_id`, response status, and completed ledger state commit in one
transaction. Any error rolls all of them back. For false, the bounded normalized
response JSON is stored for exact replay. The response limit is 512 KiB.
Monitoring metrics remain separate best-effort writes and do not determine
response correctness.

## Retention and operations

`ANALYZE_IDEMPOTENCY_RETENTION_HOURS` defaults to 24 (bounded 1–168).
`ANALYZE_IDEMPOTENCY_LEASE_SECONDS` defaults to 180 (bounded 5–300), covering
the primary timeout, optional repair timeout, and finalization margin. Claim-time
maintenance processes at most 100 rows: stale provider-started rows become
indeterminate, expired pre-provider rows become failed, and only expired
terminal rows are deleted. Expiry/status and status/lease indexes keep work
bounded. JSON storage means PostgreSQL growth follows request volume and
response size; retention and the 512 KiB cap bound that exposure.

## Security

Authentication, active-account checks, Origin, CSRF, Resume ownership, and
input validation occur before replay disclosure. Logs and responses do not
contain the raw key, Resume/JD text, prompts, provider bodies, cookies, or
secrets. The key is retry correlation only and grants no authority.
