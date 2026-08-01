# Java Normalization Production Stage 4 Java Preparation Work Report

## 1. Repository and starting production state

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Starting `main`: `87569e1ed13645c8cf52e8ce6c07ea5bb74c97b4`
- Branch: `ops/java-normalization-production-stage-4-java`
- Phase IVC-B report PR: [#44](https://github.com/HKJoker-Z/personal-job-agent/pull/44)
- Public application version: exactly `2.0.4`
- Production and repository Alembic: exactly `20260730_07`
- Starting normalization mode: exactly `shadow`
- Backend image digest:
  `sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`
- Java image digest:
  `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`
- Backend and Java: healthy, restart count zero, OOM false

PR #44 was already merged normally at the starting commit. Its verified
Phase IVC-B evidence contains five sampled Shadow requests, five Java
successes, zero failures/fallbacks, 5/5 Request ID matches, expected policy
and dictionary versions, no safety or authority defect, and a GO to prepare
Phase IVD-A. Preparation itself made no production change.

## 2. Exact configuration diff

This preparation adds one final additive production override after the
existing Stage 2 and Stage 3 files. Relative to the approved Shadow render,
its complete semantic change is:

- FastAPI `backend` environment
  `ANALYSIS_JD_NORMALIZATION_MODE`: `shadow` to `java`.

The new override contains no image, secret, mount, timeout, response-size,
policy, dictionary, port, network, dependency, command, healthcheck, or
resource declaration. Worker and Outbox retain the explicit `local` values
from Stage 2; the shared value is not unavoidable.

## 3. Unchanged production contract

The required earlier overrides remain in the render and preserve:

- Backend and Java immutable image digests;
- application version `2.0.4` and Alembic `20260730_07`;
- private origin `http://java-normalization:8080`;
- the existing API-key file as a read-only mount, never a Compose literal;
- 200 ms connect, 600 ms response, and 800 ms total deadlines;
- 262144-byte maximum Java response;
- expected policy `jd-normalization-v1` and dictionary `skills-v1`;
- one Java attempt, no transport/application retry, no redirect, and
  `trust_env=False`;
- Backend-only attachment to `pja-java-normalization-internal`; and
- current public ports and all service topology.

FastAPI remains the only Python service on the private Java network. Java
remains in Compose project `pja-java-normalization`, has no host-published
port, and has no PostgreSQL, Redis, application-network, or public-network
attachment.

## 4. Java success and fallback behavior

In mode `java`, a validated Java response becomes the effective JD and records
source `java`. DNS, connection, timeout, HTTP, authentication, response-size,
JSON/schema/hash, Request ID, policy, dictionary, or other bounded validation
failure selects the existing locally sanitized JD and source
`fallback_local`. Java errors and bodies remain hidden from the public result;
fallback itself does not fail Analyze.

The client performs exactly one bounded attempt without retry. The existing
local candidate and first security scan always complete before Java is
eligible.

## 5. Authoritative second security scan

A successful Java normalized result receives the second FastAPI security scan
before it can enter RAG or prompt construction. An unsafe or unusable result
cannot become authoritative and instead selects `fallback_local`. Unlike
Shadow's observation-only scan, this Java-mode scan is authoritative and its
findings merge conservatively with the first scan.

## 6. Execution-fingerprint binding

After selecting source `java` or `fallback_local`, FastAPI computes the
domain-separated `analyze-execution-v1` fingerprint from the stable input
fingerprint and exact effective normalization contract. It atomically binds
that choice to the current processing attempt before Project Knowledge RAG,
prompt construction, provider work, scoring, History derivation, or result
finalization.

Matching completed idempotency rows replay their existing response before a
Java or provider call and without rewriting History. An unfinished attempt
cannot silently switch between local/Java contracts because the execution
binding rejects a conflicting choice.

## 7. Deployment order

1. Merge this preparation through a normal pull-request merge commit.
2. Fast-forward production source to that reviewed merge commit.
3. Run the immediate read-only version/schema/mode/image/health/resource/
   topology/log-safety preflight; stop on any mismatch.
4. Install only the Stage 4 override root:root mode `0444`.
5. Render the exact existing production files with Stage 4 last and prove the
   only Shadow-to-Java difference is the Backend mode value.
6. Record unchanged IDs for services that must not be recreated.
7. Recreate only FastAPI Backend with `--no-deps --wait`.
8. Validate health, version, schema, images, topology, security, resources,
   contracts, and rollback render without calling Analyze.
9. Leave Java mode running for later user-initiated evidence; stop before
   Phase IVD-B.

## 8. Emergency rollback to local

Omit both Stage 4 and Stage 3, retain the base stack and Stage 2 override, and
render Backend `local` with sample rate `0`, the same image, networks, and
read-only key mount. If any deployment gate fails, recreate only Backend from
that exact local render.

Rollback requires no image change, database downgrade, Java removal/restart,
key rotation, PostgreSQL/Redis operation, History rewrite, completed response
change, idempotency transformation, or recreation of Worker, Outbox,
Frontend, Edge/Nginx, or another service.

## 9. Stop conditions

Stop before mutation for any version, schema, current-mode, image, health,
restart, OOM, resource, topology, port, secret, bounded-log, or rollback-
render mismatch. After cutover, roll Backend directly to local for startup or
public-health failure, restart/OOM, secret exposure, resource pressure,
unexpected image/port/network/service change, missing fallback safety, or any
configuration/security defect. Do not downgrade the database.

## 10. Changed files

- `deploy/production/compose.java-normalization-stage-4-java.override.yaml`
- `scripts/test-v201-production-runtime.sh`
- `docs/operations/JAVA_NORMALIZATION_PRODUCTION_ROLLOUT.md`
- `docs/work-reports/2026-08-01-java-normalization-production-stage-4-java-preparation-work-report.md`
- `docs/work-reports/README.md`

No application source, Java source, migration, image digest, existing Compose
service, public port, schema, or release metadata changed.

## 11. Validation and delivery metadata

The preparation will record its implementation commit, PR URL, required
checks, and normal merge commit here before production mutation. Local
validation covers whitespace/YAML/Bash/ShellCheck checks, Stage 2 local,
Stage 3 Shadow, and Stage 4 Java Compose renders, an exact normalized diff,
Backend-only network/secret assertions, Worker/Outbox local assertions,
targeted authoritative/fallback/security/binding/replay tests, and repository
safety scans.

## 12. Preparation boundary confirmations

- Production was not changed during preparation.
- No `/api/analyze` or other production workflow request was generated.
- No production test user, Session, or user-content inspection was used.
- No Resume, JD, prompt, History, response, Java body, provider body, hash,
  Cookie, Authorization, or secret value was inspected.
- No DeepSeek or other external LLM was called.
- No Backend, Frontend, or Java image was built or published.
- No migration was added, edited, run, or downgraded.
- No application or Java runtime source changed.
- No tag, GitHub Release, or version bump to `2.0.5` occurred.
- Java-authoritative production mode was not enabled during preparation.
