# Version 2.0.5 - Production Java Normalization Integration

Version 2.0.5 completes the staged production rollout of deterministic Java Job
Description normalization while preserving FastAPI as the single public
application and workflow owner. It advances application version metadata only;
the production Alembic head remains `20260730_07`.

## Changes

- Runs the Spring Boot service only with its stateless `normalization-only`
  profile. PostgreSQL, Flyway, JPA, persistence routes, and database health are
  inactive in this profile.
- Connects FastAPI privately to Java over the dedicated internal Docker network.
  Java has no host-published port, and no browser credential or public API
  contract crosses the boundary.
- Retains three explicit modes: `local`, observation-only `shadow`, and
  authoritative `java`. Production is configured as `java`; `local` remains the
  application default and emergency rollback mode.
- Uses the existing Analyze input fingerprint for deterministic Shadow sampling.
  Shadow observations never change the effective JD or execution result.
- Preserves the stable request fingerprint and completed-replay behavior. A
  separate domain-bound `analyze-execution-v1` fingerprint binds the effective
  source and content before retrieval, prompt construction, provider work,
  scoring, History, and result finalization.
- Applies FastAPI's authoritative second security scan to every successful Java
  result before that result may become effective.
- Contains a bounded Java boundary failure or rejected second scan as
  `fallback_local`, using the already scanned local candidate without exposing
  Java internals to the public response.
- Keeps one Java attempt, transport retries disabled, bounded timeouts and
  response size, strict Request ID/policy/dictionary validation, no redirects,
  and no inherited proxy configuration.
- Records production evidence for four Java-authoritative Analyze requests: four
  Java successes, no Java failure or fallback, four accepted second scans, four
  pre-provider execution bindings, four Java execution sources, and no duplicate
  Provider or History side effect.
- Updates `python-dotenv`, `requests`, and `urllib3` to their current patched
  releases after the release dependency scan identified fixed advisories.

The expected normalization policy is `jd-normalization-v1` and the expected
dictionary is `skills-v1`. Neither changes in this release.

## Upgrade

Publish Backend and Frontend images from the reviewed release source commit
under full-commit-SHA tags and record their immutable registry digests. Reuse the
existing Java digest because Java source and runtime metadata are unchanged.

Immediately before cutover require production Version `2.0.4`, Alembic
`20260730_07`, mode `java`, healthy Backend and Java containers, restart count
zero, OOM false, at least 1.5 GiB available RAM, at least 6 GiB available root
disk, and the unchanged private Java/public Edge topology. Deploy Backend,
Worker, and Outbox from the same new Python digest and deploy the Frontend digest
because its visible version metadata changes. Do not recreate PostgreSQL, Redis,
Java, or Edge/Nginx.

No migration command is required. After cutover, require public Version `2.0.5`,
Alembic `20260730_07`, mode `java`, exact reviewed image digests, healthy services,
zero restarts/OOM, unchanged public ports, and private healthy Java. Validation
must not invoke `/api/analyze` or another business workflow.

## Rollback

Retain the previous immutable Backend and Frontend digests. An image rollback
restores Backend, Worker, and Outbox consistently to the previous Python digest
and Frontend to its previous digest while keeping Alembic `20260730_07`.

For an urgent Java-boundary safety issue, omit the Stage 4 and Shadow overrides
and recreate only Backend in `local` mode. This mode rollback requires no schema
downgrade, Java restart/removal, key rotation, History rewrite, idempotency
transformation, or Redis operation.

## Known observations and limitations

- During the four-request production evidence window, the existing Provider path
  produced one accepted response, one bounded call failure, and two bounded
  output rejections. The existing deterministic analysis fallback contained all
  three non-success outcomes and all four public requests completed. These are
  non-Java Provider-containment observations, not Java failures.
- Four production requests are bounded rollout evidence, not an SLA, load test,
  capacity result, reliability estimate, or performance-improvement claim.
- No completed production replay occurred in that window; the merged regression
  suite supplies replay compatibility evidence.
- Java normalization is deliberately narrow and stateless. FastAPI remains the
  owner of security, idempotency, RAG, provider interaction, scoring, History,
  monitoring, and every public API contract.
- The npm production-dependency audit reports the React Router RSC-mode advisory.
  This client-only Vite application does not enable React Server Components,
  framework actions, or server routing. The finding is recorded as not
  applicable to the deployed execution path pending an upstream non-breaking
  patched release.
