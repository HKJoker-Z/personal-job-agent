# Version 2.0.4 Release and Production Deployment Work Report

Date of implementation scope: 2026-07-24  
Release and deployment execution: 2026-07-27  
Repository: `HKJoker-Z/personal-job-agent`

## Executive summary

Version 2.0.4 was released and made the production version. PR #21 was
verified at its reported final head and merged with a normal merge commit.
A metadata-only release-preparation PR was then merged, the resulting `main`
commit passed CI, and the annotated `v2.0.4` tag was created at that validated
commit.

The release workflow published immutable Backend and Frontend images. One
isolated PostgreSQL 16 restore/migration rehearsal and one bounded internal
candidate acceptance were completed. Production was backed up, Project
Knowledge was synchronized with the official upload/rebuild mechanism, the
additive Alembic migration was applied, and public port 8080 was switched from
Version 2.0.3 to Version 2.0.4.

All 100 post-cutover public health checks returned exactly `2.0.4`. No real
DeepSeek request was made during this work.

## GitHub delivery record

### PR #21

- PR: [#21](https://github.com/HKJoker-Z/personal-job-agent/pull/21)
- Verified final head:
  `325030b14f6f9c4d74136fbc2202a5eca72bd824`
- Merge method: merge commit, without squash, rebase, admin bypass, or
  required-check bypass
- Merge commit:
  `76ef02730dd36a5732bc5421a45e32356060a6bb`
- Pre-merge state: open, clean, and mergeable
- Required checks: all ten required checks passed
- Implementation Work Report: present in `docs/work-reports/`
- Migration head: `20260724_06`
- PR evidence stated that no production access and no real DeepSeek call
  occurred during implementation.
- Post-merge `main` CI passed, and local `main` matched `origin/main`.

### Version 2.0.4 release preparation

The repository still reported Version 2.0.3 after PR #21, so the minimal
release-preparation path was used.

- Branch: `release/version-2.0.4`
- Commit: `0c77e18b68bf5f573f69fff2886ee867b8642606`
- PR: [#22](https://github.com/HKJoker-Z/personal-job-agent/pull/22)
- PR title: `Release: Prepare Version 2.0.4`
- Merge method: merge commit
- PR merge commit and final validated release `main` commit:
  `b7ee8643d556638622afff526e53fe254824482b`
- Final-main CI:
  [run 30232154440](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30232154440),
  successful

The release-preparation commit changed 35 files, with 316 insertions and 272
deletions. Changes were limited to required version metadata, container and
test version expectations, current-version documentation, Architecture page
release labels, and the Version 2.0.4 release notes. It did not add a product
feature or Redis caching.

### Tag, images, and GitHub Release

- Annotated tag: `v2.0.4`
- Tag object:
  `3bbf88954fbf7dcdf29e40dee8ceb45c0c485c6d`
- Tag target:
  `b7ee8643d556638622afff526e53fe254824482b`
- Tag message:
  `Version 2.0.4 - Backend Reliability and Portfolio Architecture`
- Release workflow:
  [Release Container Images run 30232388612](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30232388612),
  successful
- Backend digest:
  `sha256:305f1151c572be4745cf909eb7389c7566e6b15c5fe4ec7b7021ef1d069e906d`
- Frontend digest:
  `sha256:09e80b4d51f1069458fe8c4a55ef3b2796789e1191fd9f8fa43c77288d45ebd9`
- GitHub Release:
  [Version 2.0.4 - Backend Reliability and Portfolio Architecture](https://github.com/HKJoker-Z/personal-job-agent/releases/tag/v2.0.4)
- Release status: published, not a draft, and not a prerelease

For each component, the tags `v2.0.4`, `2.0.4`, `2.0`, `2`, `latest`, and
`sha-b7ee864` were resolved and verified to point to the one immutable digest
shown above.

The release notes cover the Architecture page and ADRs, three-minute demo
assets, PostgreSQL monitoring aggregation optimization, Request ID
correlation, the stable Analyze error contract, PostgreSQL-backed
idempotency, completed replay, concurrent duplicate protection, atomic
History persistence, indeterminate provider state, SDK `max_retries=0`, and
Alembic `20260724_06`. They explicitly do not claim external exactly-once
execution and do not present synthetic benchmark latency as production
latency.

## Release scope audit

The released scope contains the already merged portfolio and Backend
reliability work:

- English Architecture page
- Architecture documentation and ADRs
- Reproducible three-minute demo material
- PostgreSQL monitoring aggregation optimization
- Full Request ID correlation
- Stable Analyze error envelope and Frontend error-code handling
- PostgreSQL-backed Analyze idempotency
- Completed-result replay
- Concurrent duplicate suppression
- Atomic History/result finalization
- Explicit indeterminate provider state
- Provider SDK `max_retries=0`
- Alembic revision `20260724_06`

No unrelated feature and no Redis caching were added.

## Release validation

The validation completed before tagging or production cutover:

| Validation | Result |
|---|---|
| Targeted Analyze idempotency tests | 19 passed |
| Full Backend suite | 433 passed; 10 opt-in PostgreSQL tests skipped locally and covered by PostgreSQL 16 CI |
| PostgreSQL 16 integration | Passed in required CI |
| Frontend tests | 64 passed |
| Frontend production build | Passed |
| Clean Alembic upgrade | Passed |
| `20260721_05` to `20260724_06` upgrade | Passed |
| Supported downgrade and re-upgrade | Passed |
| Backend and Frontend Docker builds | Passed |
| Compose validation | Passed |
| Mock LLM Docker smoke | Passed |
| PostgreSQL backup/restore regression | Passed |
| Repository safety checks | Passed |
| Secret scan | Passed using the repository's exact CI policy |
| `git diff --check` | Passed |

No validation used a real DeepSeek request.

## Production Version 2.0.3 baseline and backups

Immediately before migration and cutover, production reported:

- Application version: `2.0.3`
- Alembic revision: `20260721_05`
- PostgreSQL: 16.9
- Backend digest:
  `sha256:b1737cde8150e358a280418c9496157ea186ce5eb0024c306c2fa970d65ad4d6`
- Frontend digest:
  `sha256:383e009e9aa563d02a2ab79693c0d9f729884a039ddd9b833173d56b408e8cba`

### Runtime and Compose rollback copy

- Path:
  `/var/backups/personal-job-agent-v2/v2.0.3-pre-v2.0.4-cutover-20260727T024142Z`
- Compose SHA-256:
  `a8850a4af7f40adbb7bb03fbd0a115cb146a90e8dd19c4b9217246c5b83f55aa`
- Backed-up Project Knowledge SHA-256:
  `3a7e903ec5aa2ba95c78961deda494f833e41c315aa50476e8bc012dd67626be`
- The copy includes the production `/opt` release/runtime configuration,
  `/etc` runtime configuration, and the previous Project Knowledge runtime
  file.

### PostgreSQL 16 production backup

- Backup path:
  `/var/backups/personal-job-agent-v2/v2-production/v2-20260727-024157-2ef4985f`
- Manifest:
  `/var/backups/personal-job-agent-v2/v2-production/v2-20260727-024157-2ef4985f/manifest.json`
- Manifest SHA-256:
  `bf0f6b5a6a8a7b77e138b03163bca753a4af297d9a0a29c2a90060c7dc8af482`
- `postgres.dump` SHA-256:
  `8dcd7e9b72fc70369ca6b7842b2247cf064e79a1bd59b4ed1da446c71964e18d`
- `files.tar.gz` SHA-256:
  `2e3f052710f48804606df2ee702666d38ea20dcb57329e8d51a3f4e964f0cdc4`
- `PROJECT_KNOWLEDGE.md` SHA-256:
  `3a7e903ec5aa2ba95c78961deda494f833e41c315aa50476e8bc012dd67626be`
- Database inventory aggregate:
  `38dd9b8e0995a6de4ddfbbcc1a487372af6eccf348dc53ab8a57354ca5cce4d6`
- Inventory: 55 tables and 223 total rows
- Backup verifier: passed
- Manifest version: 2
- Recorded application version: 2.0.3
- Recorded Alembic revision: `20260721_05`
- PostgreSQL server, client, dump, and restore major: 16

The first invocation safely refused before writing because the older live
Compose file did not expose the newer provenance variables. The same official
backup workflow was rerun with explicit immutable Version 2.0.3 provenance;
only the successful path above was retained as the production backup.

## Single PostgreSQL 16 migration rehearsal

Exactly one isolated restore target was used. The exact production backup was
restored into PostgreSQL 16 and migrated from `20260721_05` to
`20260724_06`.

The first strict inventory comparison reported one policy mismatch:
`schemas.public.owner` was `pg_database_owner` in the source and
`pja_migration` in the disposable target. Data was not different. The
explicit allowed mapping for `pg_database_owner -> pja_migration` had been
omitted from that comparison. On the same restored target, adding that narrow
mapping produced a strict inventory result with zero mismatches. No second
restore rehearsal was created.

The same target was used for a supported downgrade inspection and re-upgrade.
The final rehearsal result was:

- Revision: `20260724_06`
- Existing table count checked: 55
- Existing row total checked: 223
- Existing row-count mismatches: 0
- Existing per-table checksum mismatches: 0
- Sequence mismatches: 0
- Invalid foreign keys: 0
- `analyze_idempotency_records`: present
- Initial `analyze_idempotency_records` rows: 0

The isolated containers, network, file targets, and candidate volumes were
removed after verification.

## One bounded internal candidate

One internal candidate used the immutable Version 2.0.4 image digests and was
bound only to `127.0.0.1:18091`.

Two setup issues were corrected before the acceptance window began: the
ephemeral TLS directory needed traversal permission for the unprivileged edge
user, and the external application bridge had initially been created with
Docker's `internal` flag, which prevents localhost port publishing. The empty
candidate network was corrected without creating a second candidate or a
second acceptance run.

The bounded acceptance result was:

- Health returned exactly `2.0.4`.
- Readiness succeeded.
- PostgreSQL, Redis, Worker, Outbox, Backend, Frontend, and Edge were healthy.
- All restart counts were zero in the accepted state.
- Login, session cookie, and CSRF enforcement passed.
- DOCX Resume upload succeeded and the uploaded Resume became Primary.
- Normal Analyze succeeded with the built-in Mock provider.
- The first keyed Analyze succeeded.
- Completed replay returned an identical body and
  `Idempotency-Replayed: true`.
- Replay created no second History row.
- A changed payload with the same key returned 409
  `IDEMPOTENCY_KEY_REUSED`.
- Twelve simultaneous duplicates produced one winner and eleven completed
  replays, with exactly one History row.
- A deterministic fallback was stored and replayed. For this check, Mock was
  disabled and the provider key was empty in the test environment, so the
  code failed locally before constructing a provider client. Backend logs
  contained `MissingApiKey` and no `DeepSeek call started` marker.
- History and the optimized Monitoring overview worked.
- The Architecture route and its compiled page bundle loaded.
- Project Knowledge PostgreSQL full-text search worked.
- The only host binding was `127.0.0.1:18091`; Backend, PostgreSQL, and Redis
  had no host bindings.

All candidate data, containers, networks, and candidate-only volumes were
removed precisely after acceptance.

## Project Knowledge synchronization

### Baseline identification and backup

- Git Version 2.0.4 raw SHA-256:
  `77c61e521964a2ca3c8d0812e8427ace76794513062ee8a7084aaff15327fd52`
- Production runtime old SHA-256:
  `3a7e903ec5aa2ba95c78961deda494f833e41c315aa50476e8bc012dd67626be`
- Production runtime new canonical SHA-256:
  `3ca4d157e7857700f856f3aa86de6d52f6409e261676aa9bd1f19f6adaccb806`
- Dedicated synchronization backup:
  `/var/backups/personal-job-agent-v2/project-knowledge-v2.0.4-sync-20260727T041120Z`
- Synchronization manifest SHA-256:
  `ea7e785f7ab7f37a2c0e4075e5de563e97698753788fdef0bd4e048527598a5c`
- Synchronization report SHA-256:
  `e8e6f65fbb1eedcb8d1bae9472ffb06524b4216b6b0feb2aba8134a03a1259f3`

The old runtime hash did not match a raw Git blob because the official upload
path canonicalizes whitespace and the final newline. It was nevertheless a
known prior version: the earlier official synchronization manifest at
`/var/backups/personal-job-agent-v2/project-knowledge-sync-20260722T024715Z/manifest.json`
records that exact runtime hash as the successful canonical output. Its
baseline was the Git Version 2.0.2 Project Knowledge file. Therefore there
were no unknown manual production edits and no stop-before-overwrite condition.

### Replace, rebuild, and search verification

The existing authenticated `/api/project-knowledge/upload` endpoint was used
to replace the runtime file and rebuild it, followed by an explicit
`/api/project-knowledge/rebuild`.

- Previous current-document chunk count: 34
- New current-document chunk count: 35
- `ix_knowledge_chunks_fts`: valid and ready
- Runtime file mode restored to `0600`

All required searches used `postgresql_fts` and returned results:

| Query | Hits |
|---|---:|
| PostgreSQL idempotency | 5 |
| Idempotency-Key | 1 |
| Request fingerprint | 5 |
| Request ID | 5 |
| stable error contract | 5 |
| SQL aggregation optimization | 2 |
| Architecture page | 5 |

No DeepSeek call was used by synchronization or search verification.

## Production migration and cutover

### Production Alembic result

While Version 2.0.3 was still serving traffic, the Version 2.0.4 immutable
Backend image ran the additive migration:

`20260721_05 -> 20260724_06`

The production result was:

- Alembic current: `20260724_06`
- `analyze_idempotency_records`: present
- Ledger rows immediately after migration: 0

Production was not downgraded.

### Public cutover

- Cutover started: `2026-07-27T04:22:33Z`
- Cutover completed: `2026-07-27T04:23:23Z`
- Mechanism: the existing Compose project and its established production
  overrides were updated in place with the two immutable Version 2.0.4
  digests and `APP_VERSION=2.0.4`, followed by `compose up --no-build --wait`
- PostgreSQL and Redis containers and volumes were preserved.
- No `docker compose down -v`, Docker prune, or persistent-volume deletion
  occurred.

The cutover preserved:

- Public HTTPS on port 8080
- Docker bridge `pja-br0`
- Policy routing rule preference 8999
- Active `personal-job-agent-routing.service`
- Active `mihomo.service`
- Private Backend, PostgreSQL, and Redis ports
- Version 2.0.3 rollback images and configuration

### Public validation

- Public health: 100 of 100 HTTPS checks returned exactly `2.0.4`
- A final health check after synthetic-data cleanup also returned `2.0.4`
- HTTPS certificate validation passed using the production address and local
  resolver override; certificate verification was not disabled for this check.
- Login and CSRF checks passed.
- Resume upload and Primary Resume checks passed.
- History listing passed.
- The Architecture page and its compiled bundle passed.
- Request ID round-trip passed.
- The stable Analyze error envelope passed with
  `INPUT_SECURITY_BLOCKED`.
- The security-blocked Analyze workflow showed
  `run_llm_analysis=skipped`.
- A first valid Idempotency-Key was persisted as a failed pre-provider
  attempt, and an invalid key returned stable
  `IDEMPOTENCY_KEY_INVALID`.
- No History row was created by either pre-provider error.
- All seven Project Knowledge searches passed.
- The optimized PostgreSQL Monitoring overview returned a valid 30-day
  aggregate.
- PostgreSQL, Redis, Worker, Outbox, Backend, Frontend, and Edge were healthy.
- `migrate` and `redis-init` completed with exit code zero.
- Every production container restart count was zero.
- The only host port owned by this Compose project was public edge 8080.
  Backend 8000, PostgreSQL 5432, and Redis 6379 were not listening on the
  host.

Because the task prohibited real DeepSeek calls and production correctly
prohibits its Mock provider, a normal provider-path Analyze and completed
replay were not repeated through the public production endpoint. Those paths
were validated once in the immutable-digest internal candidate. Public
production validation intentionally used a credential-pattern security
fixture that stops before provider execution. This is the honest boundary of
the production validation.

## Synthetic-data cleanup

Candidate cleanup removed the entire isolated candidate project and its
candidate-only volumes.

Production cleanup was scoped by the temporary user's UUID, one workflow
UUID, and one exact storage key. It removed:

- 1 temporary user
- 3 temporary sessions
- 8 temporary audit events
- 1 Resume
- 1 Resume Version
- 1 file-asset row and its one physical DOCX file
- 1 failed Analyze idempotency record
- 1 synthetic analysis metric
- 16 synthetic analysis-step metrics

Post-cleanup queries returned zero for all of those exact identities. The
Project Knowledge replacement was retained because it is release data, not
synthetic validation data. Temporary cookies, credentials, request bodies,
and local validation directories were deleted.

## Rollback assets

The following rollback assets remain available:

- Version 2.0.3 Backend digest:
  `sha256:b1737cde8150e358a280418c9496157ea186ce5eb0024c306c2fa970d65ad4d6`
- Version 2.0.3 Frontend digest:
  `sha256:383e009e9aa563d02a2ab79693c0d9f729884a039ddd9b833173d56b408e8cba`
- Version 2.0.3 runtime/Compose copy:
  `/var/backups/personal-job-agent-v2/v2.0.3-pre-v2.0.4-cutover-20260727T024142Z`
- PostgreSQL 16 backup:
  `/var/backups/personal-job-agent-v2/v2-production/v2-20260727-024157-2ef4985f`
- Previous Project Knowledge:
  both the runtime/Compose copy above and
  `/var/backups/personal-job-agent-v2/project-knowledge-v2.0.4-sync-20260727T041120Z/PROJECT_KNOWLEDGE.before.md`
- Version 2.0.2 release assets:
  `/opt/personal-job-agent-v2/releases/v2.0.2`
- Version 2.0.2 pre-Version 2.0.3 runtime backup:
  `/var/backups/personal-job-agent-v2/v2.0.2-pre-v2.0.3-cutover-20260721T094933Z`
- Version 1.9 rollback assets:
  `/var/backups/personal-job-agent-v2/v1.9-pre-v2.0.0-cutover-20260718T074348Z`

The production schema remains at the additive `20260724_06` revision. The
documented rollback preference is to restore Version 2.0.3 images and runtime
configuration while retaining the migrated schema. Schema downgrade is a
last resort, must occur without active Analyze traffic, and must not delete
the idempotency ledger without a verified backup.

## Risks and limitations

- Analyze idempotency prevents duplicate application-side provider starts
  after a durable claim; it does not provide external exactly-once execution.
- A transport failure after provider acceptance can remain indeterminate.
- No production-latency claim is based on synthetic candidate timing.
- The candidate's Mock provider does not prove the availability or latency of
  the external DeepSeek service.
- Public production validation did not call the provider and did not enable
  Mock in production. Completed replay was therefore demonstrated in the
  isolated candidate, while production was limited to pre-provider stable
  errors and idempotency persistence.
- PostgreSQL-backed idempotency is intentionally authoritative. Redis remains
  queue/SSE infrastructure; Redis caching was not added.
- The migration adds a ledger table. Production downgrade was deliberately
  not exercised.

## Final state

- Final validated release `main` commit and tag target:
  `b7ee8643d556638622afff526e53fe254824482b`
- Tag: `v2.0.4`
- Final production application version: `2.0.4`
- Final production Alembic revision: `20260724_06`
- Final production Backend digest:
  `sha256:305f1151c572be4745cf909eb7389c7566e6b15c5fe4ec7b7021ef1d069e906d`
- Final production Frontend digest:
  `sha256:09e80b4d51f1069458fe8c4a55ef3b2796789e1191fd9f8fa43c77288d45ebd9`
- Public health result: 100/100 checks reported exactly `2.0.4`
- Real DeepSeek calls during this work: 0

This report is post-release delivery evidence. Its later documentation commit
does not move the already published `v2.0.4` tag from the validated release
commit above.
