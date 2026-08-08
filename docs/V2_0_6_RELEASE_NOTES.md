# Version 2.0.6 — Bounded Provider Deadlines and Resilient Analyze

Version 2.0.6 is prepared but not yet published. It keeps `/api/analyze`
synchronous and preserves the existing Java normalization-only production
topology and Alembic head `20260730_07`.

## Improvements

- Enforces one bounded absolute Provider deadline for primary, retry, repair,
  response-body handling, and finalization reserve.
- Preserves safe, deterministic fallback when Provider work fails, times out,
  or produces unusable output. `fallback` is a supported Analyze result state,
  not a server error state.
- Uses a pragmatic shallow Provider output contract. The Provider supplies
  bounded narrative material while Backend-owned score, skills, evidence,
  security, RAG metadata, History, and serialization remain authoritative.
- Salvages valid peer fields into `partial` when non-critical fields, aliases,
  evidence references, or unsupported narrative claims require cleanup.
- Keeps Job Summary and Match Reasons stable, with usable content or an
  explicit unavailable representation for every completed Analyze result.
- Retains exact completed idempotency replay and exactly-once History
  finalization evidence; a completed replay performs no Provider call.
- Improves Provider monitoring and bounded error categorization while keeping
  raw prompts, Resume/JD text, Provider bodies, credentials, and reasoning out
  of operational metadata.
- Updates the directly used PDF parser to `pypdf` 6.15.0 after dependency
  auditing identified fixed malformed-PDF denial-of-service conditions.
- Hardens the production-candidate collector and records bounded operational
  evidence without inspecting production/user content.

## Production-candidate evidence

The carried-forward controlled candidate completed 10/10 authorized synthetic
Analyze executions with HTTP 200 public JSON, zero deadline exhaustion,
maximum two Provider calls, zero security or serialization defects, finalized
History/idempotency for every execution, and no duplicate History. Its states
were complete 6, partial 1, and fallback 3; Provider acceptance was 7/10 and
Provider quality was recorded as **DEGRADED**. Acceptance percentage is a
monitoring observation, not a release hard gate; hard correctness, safety,
boundedness, and persistence gates remain decisive.

A deterministic first-request/completed-replay check separately confirmed
fallback completion, stable Job Summary and Match Reasons, two first-request
Provider calls, zero replay Provider-call delta, exactly-once History reuse,
and approximately 17.876 ms replay duration.

## Compatibility and operations

- Java behavior is unchanged: production remains normalization-only/private,
  with policy `jd-normalization-v1`, dictionary `skills-v1`, unchanged
  Request ID/hash/version contract, and unchanged `fallback_local` behavior.
- No new Alembic migration is included or required. Current and head remain
  `20260730_07`; no upgrade or downgrade is needed.
- Backend, Worker, and Outbox continue to share the reviewed Backend artifact
  where the deployment process requires it. Frontend/Edge uses its reviewed
  immutable artifact. The unchanged Java image may be reused.
- Release validation uses synthetic inputs and Mock Provider behavior. It does
  not call the real DeepSeek API, generate another Provider-quality cohort, or
  inspect production/user content.

## Known observation

During the controlled candidate, Provider quality was **DEGRADED** with 7/10
accepted results. Deterministic fallback remained safe and bounded, and
Provider quality is monitored separately from hard correctness. Version 2.0.6
does not claim zero Provider failures, fully healthy Provider quality, or 100%
Provider acceptance.

The React Router advisory was corrected with the smallest compatible locked
update from `react-router-dom` 7.18.1 to 7.18.2. The advisory concerns unstable
RSC APIs, which this client-only Vite SPA does not use; production dependencies
are clean after the update. Separate development-only audit findings remain
outside the shipped frontend runtime and are documented in the release work
report rather than addressed with unrelated upgrades.

## Explicitly not shipped

Version 2.0.6 does not ship PR #57's dedicated direct-networking behavior,
`trust_env=False`, `DEEPSEEK_NETWORK_MODE`, or direct-network routing changes.
It does not make Analyze asynchronous or queued, change the DeepSeek prompt
deadline/acceptance/network contract beyond the already merged behavior, add
Java Resume PDF/DOCX parsing, change Java logic, add a migration, or publish a
GitHub tag/release in this preparation phase.

## Rollback

Rollback restores the recorded immutable Version 2.0.5 Backend, Worker/Outbox,
Frontend/Edge, and Java image/configuration references. PostgreSQL schema and
Redis remain compatible; Alembic stays at `20260730_07`, and no downgrade is
required. Restore the previous Compose/configuration revision and exact image
digests, verify readiness/version/topology, and leave production untouched if
the release gate is not satisfied.
