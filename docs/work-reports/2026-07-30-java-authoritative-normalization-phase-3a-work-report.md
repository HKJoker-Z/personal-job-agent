# Java-Authoritative Normalization Phase IIIA Work Report

## 1. Repository

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Stable production version: Personal Job Agent `2.0.4`
- This report describes source implementation and isolated validation only.

## 2. Phase II PR final head

Phase II PR
[#33](https://github.com/HKJoker-Z/personal-job-agent/pull/33) ended at
`3f133e479fcb3043bec3fef7a8f830f48196d071`. Its final head contained the
complete Phase II Work Report and the report-only CI-delivery metadata
correction.

## 3. Phase II merge commit

PR #33 was merged with a normal merge commit, without squash, rebase, admin
bypass, tag, release, image publication, deployment, or production access:

`ac17aa567ad664f03dbb978f7fd06c2f76e3ad05`

## 4. Starting main commit

Phase IIIA started from the pulled, matching local and remote `main` commit
`ac17aa567ad664f03dbb978f7fd06c2f76e3ad05`. The post-merge repository CI was
green after rerunning one timestamp-sensitive Phase II assertion; Phase IIIA
also made that comparison ignore nondeterministic step timestamps.

## 5. Phase IIIA branch

`feat/java-authoritative-normalization-execution-fingerprint`

## 6. Exact scope

Phase IIIA adds the Analyze execution identity and attempt-token binding,
enables Java-authoritative selection with safe local fallback, makes the
post-Java security scan authoritative, propagates one effective JD through the
existing downstream workflow, preserves replay/provider protections, and adds
PostgreSQL, mode, idempotency, security, and failure validation.

## 7. Scope exclusions

The work does not add candidate Compose, deployment code, production
configuration, Nginx changes, release workflows, version metadata changes,
React changes, Java runtime/POM/Docker/Compose/Flyway/policy/dictionary changes,
or `docs/PROJECT_KNOWLEDGE.md`. It does not add Java persistence integration or
a new monitoring table.

## 8. Existing idempotency model

The source-of-truth ledger is `analyze_idempotency_records`, represented by
`AnalyzeIdempotencyRecord`. Its unique identity is user, operation
`analyze:v1`, and the domain-separated Idempotency-Key hash. States remain
`processing`, `completed`, `failed`, and `indeterminate`. Processing claims
use a bounded lease and UUID attempt token. A stale pre-provider attempt may be
taken over; a stale post-provider attempt becomes indeterminate and is not
silently retried. Terminal retention remains 24 hours by default. The existing
expiry/status and processing/lease indexes are unchanged.

## 9. Stable request fingerprint

`analyze-request-fingerprint:v1` is unchanged. It remains computable before
Java, binds the key to stable Analyze input, supports the early claim and
completed replay, and continues to include the acquired local JD, owned
Resume/version input, URL, RAG/top-k and Project Knowledge version, History
choice, model, analysis contract, and security policy. Local, shadow, and Java
configuration do not change it.

## 10. Execution fingerprint

The new execution fingerprint is a deterministic 32-byte SHA-256 over
domain-separated canonical JSON. It includes the stable request fingerprint,
execution contract, effective source, SHA-256 of the exact effective JD text,
effective policy identity, and an explicit dictionary version or null. Fields
are sorted deterministically and encoded as compact UTF-8 JSON.

It excludes Request ID, Idempotency-Key, attempt token, time, randomness,
database IDs, Java duration, error text, and a configured mode that does not
change the selected execution. Fingerprint bytes and text hashes are not
logged or returned.

## 11. Execution contract version

The contract is `analyze-execution-v1`. The hash domain is separately
versioned, and code rejects unsupported contract/source/version combinations
before persistence.

## 12. Effective normalization sources

- `local`: existing sanitized local JD, no Java attempt.
- `java`: validated and authoritatively rescanned Java text.
- `fallback_local`: existing sanitized local JD selected after one failed or
  rejected Java attempt.

`shadow` is not an effective source because local remains authoritative.

## 13. Local normalization identity

The existing local behavior is explicitly identified as
`fastapi-local-jd-v1` with a null skill-dictionary version. This is not labeled
as the Java normalization policy. The local preprocessing implementation was
not changed; a future semantic change must intentionally update this contract.

## 14. Alembic migration

Exactly one new forward-only revision was added:
`20260730_07`, following `20260724_06`. Remote revision names were checked
before selection and no collision existed. Existing migrations were not
edited. Operational rollback is configuration-first and does not require a
database downgrade.

## 15. Schema constraints

The existing ledger receives nullable:

- `execution_fingerprint` (`bytea`/binary, 32 bytes);
- `execution_contract_version` (bounded string);
- `normalization_source` (bounded string);
- `normalization_policy_version` (bounded string);
- `skill_dictionary_version` (bounded string); and
- `execution_bound_at` (timezone-aware timestamp).

Checks enforce exact fingerprint length, allowed sources, nonblank present
values, and consistent all-null or bound metadata. Java requires a dictionary
version; local and fallback-local require null. There is no default, backfill,
destructive rewrite, new table, or unjustified lookup index.

## 16. Legacy-row compatibility

All existing rows are preserved. A completed legacy row whose execution
metadata is null still replays its exact stored status/body across mode
changes. It makes no Java/provider call, does not bind metadata, and does not
write History. Unknown historical normalization information is not invented.
Legacy failed and indeterminate rows retain the existing state-machine rules.

## 17. Attempt-token binding

`bind_execution` scopes its atomic update by record, user, operation, key hash,
`processing` state, and current attempt token. A stale token cannot bind or
overwrite. All-null metadata may be bound once; an exactly identical binding
is idempotent; a different existing binding is immutable.

## 18. Binding transaction

Execution binding uses one conditional SQL update and commits before Project
Knowledge retrieval, prompt construction, or provider execution. It also
refreshes the existing lease. Provider-start updates and finalization require
the exact expected binding. History creation, completed response persistence,
and ledger completion remain one finalization transaction; failures roll back
without partial History.

## 19. Java mode

`java` now passes startup validation only with the same bounded origin, absolute
key file, timeout, response-size, policy, and dictionary requirements as the
remote client boundary. FastAPI makes exactly one Java attempt. A response must
pass HTTP/content/size/JSON/schema/hash/version/skill/metadata/Request-ID
validation and the authoritative second security scan before Java text becomes
effective. The public Analyze schema is unchanged.

## 20. Local mode

`local` remains the default. It creates no Java client, makes no Java request,
uses the exact existing sanitized local JD, identifies it with
`fastapi-local-jd-v1`, and binds source `local` for new keyed attempts before
downstream work.

## 21. Shadow mode

Phase II deterministic sampling and observation-only behavior remain. The
first sanitized local JD remains effective and binds source `local`.
Successful, failed, or unsampled shadow work cannot change the execution
fingerprint, RAG, prompt, provider behavior, deterministic fallback, History,
or public response. Shadow failure remains non-fatal.

## 22. Java fallback

Connection/response/total timeout, unavailability, client/server HTTP errors,
oversized response, invalid content/JSON/schema, hash/policy/dictionary/Request
ID mismatch, skill validation failure, unexpected client failure, and
authoritative scan rejection all select `fallback_local`. The local contract
identity and null dictionary are bound before downstream work. There is no
Java retry and no Java error exposure. A later retry cannot replace an already
bound Java execution with fallback-local under the same key.

## 23. Security-scan ordering

The existing first Resume/JD scan runs before Java. A blocked first scan
returns the unchanged public security error and calls neither Java nor the
provider. Java receives only the bounded first-scan sanitized JD. Shadow keeps
its observation-only scan. Java success requires a second authoritative scan;
blocked or unusable Java output is discarded and local fallback is selected.
Prompt-injection, sensitive-data, and output-leak controls were not weakened.

## 24. Effective JD propagation

After source selection, `context.sanitized_job_text` is assigned exactly once
to the selected effective text. Existing downstream consumers continue to use
that single field. Resume ownership, Job URL acquisition, SSRF/DNS/IP checks,
browser security, user identity, and unrelated History fields are completed or
resolved independently and are not influenced by Java output.

## 25. RAG input

Project Knowledge retrieval query construction receives the selected effective
JD. Tests assert the exact Java text on success and the exact existing local
text on fallback.

## 26. Prompt input

Safe prompt construction receives the same selected effective JD. Java text
cannot reach prompt construction before response validation, the
authoritative second scan, and execution binding.

## 27. History input

History continues to persist derived result fields and the optional original
Job URL; it does not persist raw, local sanitized, or Java-normalized JD text.
The derived scoring/recommendation result is produced from the selected
effective JD. Keyed finalization creates History exactly once in the same
transaction as the stored completed response.

## 28. Provider boundary

The SDK remains `max_retries=0`. Existing primary and explicit single
format-repair limits are unchanged. The ledger records provider start only
when the current attempt and exact execution binding match. Provider-ambiguous
or stale post-provider cases remain indeterminate and are not reclassified as
safe retries.

## 29. Completed replay

Completed replay remains the earliest terminal route path after stable input
acquisition/claim. It returns the stored response with
`Idempotency-Replayed: true` and does not scan, call Java, recompute/bind an
execution fingerprint, call a provider, or rewrite History. It remains valid
across local/shadow/java mode changes and version changes.

## 30. Stale takeover behavior

A safely reclaimable pre-provider claim receives a new attempt token but keeps
any existing execution metadata. Identical selection may continue according to
existing rules. A changed source, exact effective JD hash, policy, dictionary,
or execution contract cannot proceed under the same key.

## 31. Execution conflict

Different already-bound execution metadata returns the stable safe public code
`IDEMPOTENCY_EXECUTION_CONFLICT` with a request for a new Idempotency-Key. The
response exposes no fingerprint, source/version internals, SQL, constraint
name, key hash, or attempt token. Same-key/different stable input still uses
the existing `IDEMPOTENCY_KEY_REUSED` path.

## 32. Monitoring evidence

Existing structured logging records bounded fields: configured mode, effective
source, Java-attempted boolean, bounded outcome, fallback boolean, duration,
policy, dictionary when applicable, and authoritative second-scan outcome.
Shadow retains its bounded comparison fields. No JD/Resume text, actual hash,
fingerprint, API key, Authorization, Java body, or arbitrary exception message
is recorded. No new metrics table or unbounded label was added.

## 33. Configuration

Supported modes are `local`, `shadow`, and `java`; unknown modes fail startup.
Default remains `local` and needs no Java origin/key. `shadow` and `java`
require a validated absolute HTTP/HTTPS origin, absolute bounded key file,
bounded connect/response/total timeouts, bounded response size and pool, and
nonblank bounded expected policy/dictionary versions. There is no bypass flag.
Production configuration was not changed.

## 34. Migration tests

SQLite migration structure tests and isolated PostgreSQL 16 correctness tests
cover upgrade from `20260724_06`, fresh upgrade, Alembic validation, second
upgrade no-op, head reporting, legacy completed-row preservation/replay,
all-null metadata, 32-byte fingerprint, allowed/nonblank/consistent fields,
valid local metadata, attempt-token binding, idempotent identical binding,
different binding conflict, stale attempt rejection, binding-required
finalization, and rollback without partial History.

## 35. Mode tests

Tests cover no-client/no-call local behavior; deterministic shadow
sample/success/failure and local authority; Java success with one sanitized
request, Request-ID/version validation and exact effective downstream text;
every stable Java client failure category; authoritative scan rejection; local
fallback; lifecycle cleanup; bounded safe observations; and unchanged public
response shape.

## 36. Idempotency tests

Tests cover unchanged stable fingerprint conflict, canonical execution
fingerprints, legacy and new completed replay across mode changes, no replay
Java/provider/History side effects, identical takeover binding, changed
source/text binding conflict, pre-binding Java failure to fallback-local,
crash/failure after Java binding followed by a conflicting fallback attempt,
database binding failure before provider, provider ambiguity, exact-once
History finalization, and provider call counts.

## 37. Failure tests

The test matrix covers Java unavailable/timeouts, HTTP errors,
malformed/oversized responses, schema/hash/version/skill/Request-ID failures,
second-scan rejection, binding database failure, stale tokens, finalization
rollback, primary provider failure, explicit repair, ambiguous provider
boundary, and database unavailability. Assertions require bounded safe public
errors and absence of input, secret, hash, fingerprint, and Java error leakage.

## 38. Full backend validation

Local validation completed:

- Python compile: passed.
- Full unit/integration discovery: 495 tests passed; only the 12 explicitly
  opt-in PostgreSQL tests were skipped in that discovery run.
- Separate PostgreSQL 16 suite: 12 passed, zero skipped.
- Focused idempotency suite: 30 passed.
- Focused Java-authoritative selection/integration and migration suites:
  passed.
- Dependency integrity: `pip check` passed.
- OpenAPI inspection: 79 public paths, unchanged Analyze contract, no internal
  normalization route or execution metadata.
- No real DeepSeek or another external LLM was configured or called.

## 39. Java regression validation

The unchanged Java service passed:

- Maven Surefire: 67 tests, zero failures/errors/skips.
- Maven Failsafe: 46 tests, zero failures/errors/skips, including 37
  PostgreSQL/Flyway tests and nine normalization-only profile tests.
- Runtime dependency inspection: passed; H2 absent.
- Existing full-profile container smoke: healthy, zero restarts, two Flyway
  versions, replay/update/history/persistence passed.
- Existing normalization-only smoke: healthy, zero restarts, no OOM, no
  database container, persistence route absent, normalize-only OpenAPI; one
  local point-in-time observation was 193.6 MiB / 384 MiB.

These are regression observations, not candidate or production measurements.
No Java source, POM, Dockerfile, Compose, migration, policy, or dictionary was
modified.

## 40. GitHub CI

Implementation/documentation head
`3ecee5e55fcf5151a715d1962a7a5caeed73a86b` passed all 13 PR check contexts:

- repository CI run `30519346726`: backend tests, frontend build, PostgreSQL
  integration, backend/frontend Docker build, Version 2 mock-provider smoke,
  PostgreSQL 16 backup/restore, Compose validation, production-runtime
  regression, script validation, and repository safety all passed; and
- Java CI run `30519346762`: Maven verify, existing full-profile container
  smoke, and existing normalization-only/no-database smoke all passed.

The pull request was `CLEAN` and `MERGEABLE` after this check set. This
report-only delivery-metadata commit triggers the final authoritative check
set; its status is the PR #34 check rollup. No workflow publishes, releases, or
deploys this change.

## 41. Changed files

Implementation:

- `backend/alembic/versions/20260730_07_add_analyze_execution_binding.py`
- `backend/app/analyze/execution.py`
- `backend/app/analyze/idempotency.py`
- `backend/app/analyze/normalization_client.py`
- `backend/app/analyze/normalization_runtime.py`
- `backend/app/analyze/normalization_shadow.py`
- `backend/app/api/errors.py`
- `backend/app/db/models.py`
- `backend/app/readiness.py`
- `backend/config.py`
- `backend/legacy_application.py`
- `backend/logging_utils.py`

Tests:

- `backend/test_analyze_idempotency.py`
- `backend/test_analyze_normalization_shadow.py`
- `backend/test_java_authoritative_normalization.py`
- `backend/test_java_normalization_client.py`
- `backend/test_java_normalization_config.py`
- `backend/test_v2_database_migration.py`
- `backend/test_v2_postgres_integration.py`

Documentation:

- `.env.example`
- `README.md`
- `docs/V2_0_3_API.md`
- `docs/V2_SECURITY.md`
- `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- `docs/work-reports/README.md`
- this report

## 42. Commit SHAs

Logical implementation commits:

- `30e79b13adca165ee4af8d98bc60380d361ccc8b` — execution migration and
  persistence binding.
- `06638c29071705c70c8bb0132f95040e51c8a7f9` — Java-authoritative selection,
  authoritative scan, fallback, and effective-input propagation.
- `d7eac946abc8aeca6cb9d918be6da017e73b28b4` — migration, mode,
  idempotency, concurrency, replay, and failure tests.
- `3ecee5e55fcf5151a715d1962a7a5caeed73a86b` — configuration/API/security/
  architecture documentation and the mandatory Work Report.

The final report-metadata commit is recorded by the pull request history
because a commit cannot embed its own SHA.

## 43. PR URL

Phase IIIA PR
[#34](https://github.com/HKJoker-Z/personal-job-agent/pull/34):
`https://github.com/HKJoker-Z/personal-job-agent/pull/34`

The PR title is
`Backend: Add Java-authoritative normalization execution contract`. It remains
open and must not be merged as part of Phase IIIA delivery.

## 44. Risks and limitations

This code adds bounded synchronous internal I/O in Java mode and does not claim
exactly-once external provider execution. Java/local policy output can differ;
an active claim correctly conflicts if its selected execution changes. Safe
structured logs are not a durable metrics warehouse. No candidate latency,
load, resource, topology, or production evidence exists, and no performance,
high-availability, or public Java exposure claim is made.

## 45. Rollback

Operational rollback is:

`ANALYSIS_JD_NORMALIZATION_MODE=local`

Restart FastAPI with valid local configuration. New keyed requests use local
execution identity; completed legacy/local/Java/fallback-local responses remain
exactly replayable. No database downgrade, History rewrite, Java data
transformation, or image rebuild is required.

## 46. Confirmation that candidate Compose was not added

Confirmed. Candidate environment creation and validation remain Phase IIIB.

## 47. Confirmation that production configuration was unchanged

Confirmed. No production environment, production Compose, Nginx, version
metadata, or production secret/configuration file was modified.

## 48. Confirmation that Java runtime code was untouched

Confirmed. No file under `services/jd-normalization-service` was modified.

## 49. Confirmation that no image was published

Confirmed. Local validation built ephemeral local images only; no registry
login, push, or publication occurred.

## 50. Confirmation that no release or deployment occurred

Confirmed. No tag, release, deployment, candidate rollout, or production
rollout occurred.

## 51. Confirmation that production was untouched

Confirmed. Production was not accessed, inspected, modified, restarted, or
synchronized. `docs/PROJECT_KNOWLEDGE.md` was not modified.

## 52. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Tests used mocks, deterministic local providers, or explicit local
fallback. No real DeepSeek or other external LLM request was made.
