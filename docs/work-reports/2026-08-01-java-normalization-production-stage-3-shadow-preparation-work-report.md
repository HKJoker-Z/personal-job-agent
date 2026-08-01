# Java Normalization Production Stage 3 Shadow Preparation Work Report

## 1. Repository and starting production state

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Starting `main`: `739ad80ba31cc1143768f1f8baba0cb530d5e399`
- Branch: `ops/java-normalization-production-stage-3-shadow`
- Public application version: `2.0.4`
- Production and repository Alembic: `20260730_07`
- Backend image digest:
  `sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`
- Java image digest:
  `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`
- Starting normalization mode: `local`

Phase IVB deployment-report PR #40 was already merged normally as
`739ad80ba31cc1143768f1f8baba0cb530d5e399`, and its post-merge repository CI
run `30690813943` passed. At preparation start, Phase IVB evidence recorded
healthy zero-restart/non-OOM Backend and Java, a private Java service, and
Backend-only attachment to `pja-java-normalization-internal`.

## 2. Exact scope and configuration diff

This preparation adds one final additive production override. Relative to the
approved Phase IVB render, only the FastAPI Backend environment changes:

- `ANALYSIS_JD_NORMALIZATION_MODE`: `local` to `shadow`;
- `JD_NORMALIZATION_SHADOW_SAMPLE_RATE`: `0` to `1.0`;
- reviewed limits become explicit: connect 200 ms, response 600 ms, total
  800 ms, and maximum response 262144 bytes; and
- expected versions become explicit: policy `jd-normalization-v1` and
  dictionary `skills-v1`.

The Phase IVB override remains mandatory and earlier in the Compose sequence.
It continues to provide the immutable Backend image, private origin
`http://java-normalization:8080`, read-only key file, and Backend-only external
Java network. The Shadow override contains no image, secret, port, mount, or
network declaration.

No application source, image digest, database migration, public port, Java
Compose/runtime, Nginx, PostgreSQL, Redis, Frontend, Java key, Project
Knowledge, or version changes.

## 3. Backend-only scope

Only `backend` is changed and later eligible for recreation. Worker and Outbox
remain explicitly `local` through Phase IVB. PostgreSQL, Redis, Worker,
Outbox, Frontend, Edge/Nginx, Java, and the legacy Backend do not join or leave
networks and are not recreated by the planned cutover.

FastAPI remains the only Python service on
`pja-java-normalization-internal`. Java remains in the independent
`pja-java-normalization` Compose project with no host-published port.

## 4. Sample-rate decision

The bounded Phase IVC-A rate is deterministically `1.0`. This makes every
later user-initiated, non-replayed Analyze eligible for a Shadow observation
and avoids insufficient evidence from a tiny traffic base. Sampling remains
domain-separated from the stable input fingerprint; it does not use a user ID
or raw text.

The rate changes observation eligibility only. It does not make Java output
authoritative and does not authorize this task to generate Analyze traffic.

## 5. Timeout, validation, and fallback behavior

The merged client retains one application attempt, zero transport retries, no
redirect, `trust_env=False`, a 200 ms connect timeout, 600 ms response
read/write timeout, 800 ms total deadline, and 256 KiB streaming response
limit. Expected versions remain `jd-normalization-v1` and `skills-v1`.

Local preprocessing and its security scan complete first. Shadow Java failure,
timeout, authentication/HTTP error, invalid response, Request ID mismatch,
oversize, hash mismatch, or version mismatch becomes only a bounded outcome.
It cannot fail Analyze or alter the local authoritative choice.

## 6. Safe observation and authority boundary

Merged source and tests prove that Shadow:

- keeps local JD authoritative for execution fingerprint, RAG, prompt,
  History, provider input, and public response;
- makes at most one synchronous Java attempt after the existing scan;
- uses the trusted FastAPI Request ID and requires the response ID contract;
- cannot block or mutate the user result through its observation-only second
  scan;
- emits only mode/source, attempted/sampled, stable outcome, bounded duration,
  equality boolean, bounded finding count, expected versions, fallback false,
  and trusted Request ID metadata; and
- bypasses Java for a valid completed idempotency replay.

Raw or sanitized JD, Resume, prompt, response, History, input/content hashes,
API key, Authorization header, Java body, and arbitrary exception text are not
observation fields and must not be inspected during rollout.

## 7. Deployment order

1. Fast-forward production source to the reviewed preparation merge commit.
2. Run immediate read-only preflight and stop on any mismatch.
3. Install only the reviewed Shadow override root:root mode `0444`.
4. Render the exact existing production Compose/environment sequence with
   Phase IVB and then Phase IVC-A last.
5. Prove the intended Backend-only environment change and unchanged image,
   mounts, networks, services, and ports.
6. Record the pre-cutover Backend ID and bounded Java health-only log baseline.
7. Recreate only FastAPI Backend with `--no-deps --wait`.
8. Validate health, version, schema, topology, resources, logs, and rollback
   render without calling Analyze.

## 8. Stop conditions

Stop before mutation for a version/schema/image/mode mismatch, unhealthy or
restarted/OOM container, Java non-health traffic, topology/port conflict,
available RAM below 1.5 GiB, or root disk below 6 GiB.

After cutover, roll back only Backend to local for startup/configuration
failure, public health failure, restart/OOM, secret exposure, Java public or
unexpected network attachment, resource pressure, unexpected port/image
change, or a bounded log security failure. Later Phase IVC-B must also stop for
unauthorized/version mismatch, Request ID failure, unexplained Shadow outcome,
or Java-correlated Analyze failure.

## 9. Rollback to local

Rollback omits only the final Stage 3 override and renders the unchanged Phase
IVB stack. The result is the same Backend image in mode `local`, sample rate
`0`, with the same networks and read-only key mount; Worker and Outbox remain
local. If needed, recreate only Backend.

No image rollback, database downgrade, Java restart/removal, key rotation,
History transformation, completed-response rewrite, Redis change, or other
service recreation is required. A healthy Shadow deployment remains running
for later user-initiated evidence and is not rolled back merely to test the
command.

## 10. Changed files

- `deploy/production/compose.java-normalization-stage-3-shadow.override.yaml`
- `scripts/test-v201-production-runtime.sh`
- `docs/operations/JAVA_NORMALIZATION_PRODUCTION_ROLLOUT.md`
- `docs/work-reports/2026-08-01-java-normalization-production-stage-3-shadow-preparation-work-report.md`
- `docs/work-reports/README.md`

## 11. Validation before merge

Local validation at implementation commit
`0ada5fc1bc374ef95e7ee54bf07da24be27232c7` passed:

- `git diff --check`;
- Bash syntax and ShellCheck for the changed regression script;
- YAML parsing and Compose rendering for Phase IVB local and Phase IVC-A
  Shadow stacks;
- exact comparison proving only the bounded Backend environment differs;
- Backend Shadow/sample/limits/version assertions;
- Worker/Outbox local-mode assertions;
- Backend-only Java network and key-mount assertions;
- immutable image and unchanged port/service topology assertions;
- targeted Shadow configuration, client, authority, safe-log, and replay tests
  in `test_java_normalization_config.py`,
  `test_java_normalization_client.py`,
  `test_analyze_normalization_shadow.py`, and
  `test_analyze_idempotency.py`; and
- repository safety and secret scans.

The production regression rendered both the Phase IVB local stack and the
Phase IVC-A stack, asserted the exact Shadow values, and normalized those
fields to prove the complete remaining Compose document was unchanged. No
full local suite was duplicated because no application runtime source changed;
the complete suite remains a required GitHub check.

## 12. Delivery metadata

- Preparation PR:
  <https://github.com/HKJoker-Z/personal-job-agent/pull/41>
- Implementation commit:
  `0ada5fc1bc374ef95e7ee54bf07da24be27232c7`
- Initial validation metadata commit:
  `3107e5e57b5f2e2b2b9f71f865de406df9a10f69`
- PR delivery metadata commit: this follow-up commit
- Final operational head:
  `b99fd785cd7d129caf42972278c84ec346d8a9ff`
- Final operational-head result: 18 successful contexts, zero failures, and
  two intentional pull-request publication skips; GitHub reported CLEAN and
  MERGEABLE
- Authoritative runs:
  - repository CI `30691940768`: success;
  - integrated Backend production `30691940780`: success;
  - Java service CI `30691940770`: success;
  - isolated Java candidate `30691940773`: success; and
  - Java production assets `30691940779`: success, publication skipped as
    required for a pull request
- Final report rollup: this report-only commit
- Required merge method: normal merge commit

## 13. Preparation boundary confirmations

- Production was not modified during preparation.
- Production remained `2.0.4` at Alembic `20260730_07` in local mode.
- No Backend, Frontend, or Java image was built, published, or deployed.
- No migration was added, edited, or run.
- No application or Java runtime source was changed.
- No Java-authoritative mode was enabled.
- No `/api/analyze` request or production user Session was used.
- No production test user was created.
- No Resume, JD, History, prompt, response, or other user content was inspected.
- No DeepSeek or other external LLM was called.
- No version bump, repository tag, or GitHub Release was created.
