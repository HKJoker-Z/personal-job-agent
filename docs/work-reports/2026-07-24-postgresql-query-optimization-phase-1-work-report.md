# PostgreSQL Query Optimization Phase 1 Work Report

**Date:** 2026-07-24

**Project:** Personal Job Agent

**Scope:** One PostgreSQL query optimization case

**Status:** Implementation and local evidence complete; pull-request metadata
and CI results are updated in the delivery section after publication

## Executive outcome

This phase optimized exactly one current operational query:
`GET /api/monitoring/workflow-steps`. PostgreSQL now returns six grouped
workflow-Step summaries instead of returning 194,399 complete metric rows for
Python aggregation.

On an isolated PostgreSQL 16.14 database containing 300,000 deterministic
synthetic Step rows, the same two-warm-up/seven-measurement protocol showed:

- median SQL execution: 541.065 ms to 185.212 ms (-65.8%);
- median application execution: 1,308.238 ms to 163.765 ms (-87.5%);
- result rows crossing the database boundary: 194,399 to 6;
- external 17,656 KiB sort and temporary I/O: removed; and
- before/after API result JSON: identical.

No cache, index, Alembic migration, production change, or retired-feature
optimization was added.

---

## 1. Repository and starting commit

| Item | Value |
|---|---|
| Repository | `https://github.com/HKJoker-Z/personal-job-agent` |
| Starting branch | `main` |
| Starting commit | `f731c24c75a81d9c7cbda86963067a39dbf09b86` |
| Audit report | `docs/POSTGRESQL_QUERY_PERFORMANCE_AUDIT.md` |
| Audit commit contained in `main` | Yes |
| Original audited application commit | `83e02a437382ad1edb3fd1715604dfe214a92278` |
| Product version | 2.0.3 |
| Alembic head | `20260721_05` |

Initial verification:

```text
## main...origin/main
f731c24 (HEAD -> main, origin/main) docs: add PostgreSQL performance audit
83e02a4 Merge pull request #17 ...
```

`git fetch origin --prune` followed by
`git rev-list --left-right --count main...origin/main` returned `0 0`.
The working tree was clean. No unrelated work was discarded or overwritten.

## 2. Branch

```text
perf/postgresql-query-optimization-phase-1
```

The branch was created only after confirming local `main` and `origin/main`
both pointed to the starting commit.

## 3. Audit validation

The entire 1,241-line audit report was reviewed before implementation.

The audit is measurement-backed rather than static analysis only. It states
that each SQL case used:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)
```

The original audit environment was PostgreSQL 16.14 with two warm-ups and seven
measured executions. It recorded planning/execution time, actual/estimated
rows, scan and sort nodes, shared and temporary buffers, rows removed by
filters, loops, result counts, and application-level timings.

The key measured audit baseline for the selected query was:

- 300,000 `analysis_step_metrics` rows;
- approximately 194,400 rows in the period;
- sequential scan plus external sort;
- 537.288 ms median SQL execution;
- 20,432 KiB disk sort;
- 2,554/2,560 temp blocks read/written; and
- 1,991.685 ms application-level core timing.

Because real PostgreSQL 16 plans and repeated measurements existed, no
speculative index was necessary.

## 4. Candidate summary

The audit prioritized current History, Resume, Project Knowledge, Monitoring
and Evaluation, and retained read-only Agent Run paths. Retired Jobs, Job
Rankings, Applications, Approvals, and Tasks were excluded unless needed by a
current path.

| Candidate | Current path | Existing index/plan evidence | Audit median | Recommendation |
|---|---|---|---:|---|
| Monitoring workflow-Step statistics | `GET /api/monitoring/workflow-steps`; `backend/monitoring_service.py` | Date and Step-key single-column indexes; 194,391 rows, sequential scan, external sort | 537.288 ms SQL; 1,991.685 ms app | Aggregate counts and percentiles in PostgreSQL; no initial index |
| Monitoring overview | `GET /api/monitoring/overview`; shared Monitoring row loader | `created_at` index; 64,797 rows returned | 17.074 ms SQL; 993.373 ms app | Conditional PostgreSQL aggregate |
| History list | Current History endpoint; `backend/database.py` | Owner-only index; sequential scan plus top-N sort for 35,000 owner rows | 58.507 ms | Composite `(owner_user_id, created_at DESC, id DESC)` |
| History wildcard search | History company/title filter | No PostgreSQL trigram index; 49,800 rows removed | 41.482 ms | Collect usage evidence before `pg_trgm` |
| Resume list | Resume Library repository | Owner and partial primary indexes; low user cardinality | 0.327 ms SQL | No immediate index; projection is optional later |
| Primary Resume | Resume repository/service | Partial unique active-primary index | 0.012 ms SQL | No change |
| Project Knowledge FTS | Document-scoped current RAG path | GIN FTS plus `(document_id, chunk_index)` | 2.580 ms hit | No change; current document is bounded |
| Monitoring trace list | Operational trace endpoint | Existing filters/indexes | 13.028 ms at offset 10,000 | No immediate change |
| Evaluation list | Operational Evaluation endpoint | Owner/run/start indexes | 2.460 ms at offset 8,000 | No immediate change |
| Agent Run inspection/events | Retained read-only path | `(run_id, id)` supports event cursor | 0.039 ms event SQL | No immediate change |

Relevant selected-table indexes before and after this phase:

- primary key `(id)`;
- `ix_analysis_step_metrics_created_at`;
- `ix_analysis_step_metrics_owner_user_id`;
- `ix_analysis_step_metrics_step_key`; and
- `ix_analysis_step_metrics_workflow_id`.

This phase does not add, remove, or change any index.

## 5. Selected candidate

**Selected:** PostgreSQL server-side aggregation for workflow-Step Monitoring
statistics.

Selection reasons, in priority order:

1. It is a current administrator operational path.
2. The audit demonstrated a measurable query and application problem.
3. Metric rows grow with every analysis while Step-key cardinality stays small.
4. Conditional aggregates preserve the response contract without a schema
   change.
5. It is a strong portfolio case: result-shape optimization, filtered
   aggregates, ordered-set percentiles, and plan interpretation.
6. It carries lower production migration risk than adding an index to a
   populated user-facing table.
7. It is reproducible with deterministic synthetic data.
8. The benefits and costs are explicit, including increased cached-buffer hits
   in the selected optimized plan.

This phase narrows the audit's broader "Monitoring server-side aggregation"
candidate to one exact query and endpoint. Monitoring overview, RAG, security,
and recommendation queries remain unchanged.

## 6. Rejected candidates

### History owner/order index

This was the audit's second-ranked candidate and remains justified, but it
requires an Alembic migration and populated-table index-build planning. The
selected Monitoring query offered a correctness-preserving code-only change
and stronger result-shape evidence. It is deferred, not rejected permanently.

### Monitoring overview

Its dominant application-level transfer cost is real, but implementing it in
the same phase would be a second query optimization. It is excluded to preserve
the exact-one-candidate scope.

### History wildcard search

The scan is measurable, but a trigram extension/index adds storage, write, and
operational cost without current search-frequency telemetry.

### Resume list and version projection

Measured queries were already fast and expected per-user cardinality is low.
Avoiding large version fields is valid cleanup, but not the strongest measured
case.

### Project Knowledge full-text search

The real route is scoped to one bounded document and measured quickly. The
slower global 50,000-chunk stress case is not the product query.

### Evaluation, Monitoring traces, and Agent Runs

They were acceptably fast in the audit. Agent Run events already use an
appropriate `(run_id, id)` cursor path. Retained Agent Runs are also lower
product priority.

### `analysis_metrics.application_id`

A read-only proxy exposed an unindexed lookup, but the exact History deletion
mutation was intentionally not benchmarked. Frequency and operational impact
remain unknown.

### Duplicate index removal

Schema inspection showed possible left-prefix duplicates, but no production
index-usage data was accessed. Removing indexes without usage and constraint
evidence would be speculative.

## 7. Synthetic dataset

The isolated phase benchmark kept the selected-query dataset aligned with the
audit:

| Fixture | Count |
|---|---:|
| `analysis_step_metrics` total | 300,000 |
| Rows in fixed measured interval | 194,399 |
| Distinct Step keys returned | 6 |
| Status patterns | `completed`, `failed`, `skipped` |
| Null duration pattern | Every 29th generated row |

Step keys:

- `parse_resume`
- `parse_job`
- `retrieve_project_evidence`
- `build_prompt`
- `run_llm_analysis`
- `normalize_result`

Representative deterministic generator:

```sql
INSERT INTO analysis_step_metrics (
    workflow_id,
    step_key,
    status,
    duration_ms,
    duration_us,
    created_at
)
SELECT
    'synthetic-workflow-' || i,
    (ARRAY[
        'parse_resume',
        'parse_job',
        'retrieve_project_evidence',
        'build_prompt',
        'run_llm_analysis',
        'normalize_result'
    ])[(i % 6) + 1],
    CASE
        WHEN i % 10 = 0 THEN 'skipped'
        WHEN i % 17 = 0 THEN 'failed'
        ELSE 'completed'
    END,
    CASE WHEN i % 29 = 0 THEN NULL ELSE (i % 2000) + 0.125 END,
    CASE WHEN i % 29 = 0 THEN NULL ELSE (i % 2000) * 1000 + 125 END,
    TIMESTAMPTZ '2026-07-24 04:00:00+00'
        - (i * INTERVAL '13.3334 seconds')
FROM generate_series(1, 300000) AS fixture(i);
```

The fixed query interval was inclusive:

```text
2026-06-24T04:00:00+00:00
through
2026-07-24T04:00:00+00:00
```

All strings and values were synthetic. No real Resume, JD, account, email,
History, or Project Knowledge content was used. The generated database was not
committed.

## 8. PostgreSQL version and benchmark settings

| Item | Value |
|---|---|
| PostgreSQL | 16.14 |
| Isolation | Temporary unprivileged process; loopback only |
| Schema | Alembic `20260721_05` |
| CPU visible | 4 vCPU, Intel Xeon Gold 6148 |
| Memory visible | Approximately 3.6 GiB |
| `shared_buffers` | 128 MiB |
| `work_mem` | 4 MiB |
| `effective_cache_size` | 4 GiB |
| `jit` | Off |
| `max_parallel_workers_per_gather` | 2 |
| `random_page_cost` | 4 |
| Warm-ups per SQL/application case | 2 |
| Measured executions per SQL/application case | 7 |

Docker was not used because the local process could not access the Docker
daemon. PostgreSQL 16.14 was unpacked into a temporary directory and started as
the unprivileged workspace user. The server was not exposed beyond loopback.

## 9. Original query

Source:

- route: `backend/legacy_application.py`,
  `GET /api/monitoring/workflow-steps`;
- service: `backend/monitoring_service.py`,
  `get_workflow_step_performance()`.

Original SQL:

```sql
SELECT *
FROM analysis_step_metrics
WHERE created_at >= :start_at
  AND created_at <= :end_at
ORDER BY step_key, created_at;
```

Original application algorithm:

1. fetch all rows;
2. construct `dict[step_key, list[row]]`;
3. exclude `status = 'skipped'` and null durations from latency values;
4. count all/status rows;
5. calculate average, min, max, and nearest-rank p50/p95 in Python; and
6. return sorted Step summaries.

## 10. Baseline plan

Representative artifact:

[`../performance/plans/workflow-step-performance-before.json`](../performance/plans/workflow-step-performance-before.json)

Plan outline:

```text
Sort (actual rows=194399, loops=1)
  Sort Key: step_key, created_at
  Sort Method: external merge
  Sort Space: 17656 KiB, Disk
  Temp Read/Write Blocks: 2207 / 2213
  -> Seq Scan on analysis_step_metrics
       estimated rows=195231
       actual rows=194399
       rows removed by filter=105601
```

The estimated and actual row counts were close. The scan was rational because
the interval selected 64.8% of the table. The external sort and oversized
result were the actionable problems.

## 11. Baseline measurements

SQL measured runs:

| Run | Planning | Execution |
|---:|---:|---:|
| 1 | 0.134 ms | 541.065 ms |
| 2 | 0.122 ms | 601.342 ms |
| 3 | 0.138 ms | 563.061 ms |
| 4 | 0.137 ms | 519.474 ms |
| 5 | 0.129 ms | 570.409 ms |
| 6 | 0.128 ms | 523.807 ms |
| 7 | 0.128 ms | 527.814 ms |

Summary:

| Metric | Baseline |
|---|---:|
| Median planning | 0.129 ms |
| Planning p95 | 0.138 ms |
| Median execution | 541.065 ms |
| Execution p95 | 601.342 ms |
| Estimated rows | 195,231 |
| Actual/returned rows | 194,399 |
| Rows removed by filter | 105,601 |
| Scan | Sequential scan |
| Index | None |
| Shared hit blocks | 417 |
| Shared read blocks | 3,697 |
| Sort | External merge, 17,656 KiB disk |
| Temp read/write blocks | 2,207 / 2,213 |
| Join strategy | None |
| Root loops | 1 |

Application measured runs in milliseconds:

```text
1289.421, 1349.409, 1255.838, 1316.278, 1350.730, 1308.238, 1254.380
```

Median was 1,308.238 ms and p95 was 1,350.730 ms.

## 12. Root cause

The response cardinality was six, but the database result cardinality was
194,399. The original query:

- selected unused identifiers, owner fields, workflow IDs, microsecond
  durations, and timestamps;
- sorted every match by timestamp even though only per-Step percentiles were
  needed;
- crossed the database boundary once per matching execution; and
- duplicated grouping and aggregation work in Python.

This is a result-shape problem. Adding a filtered-column index would not remove
the wide result, protocol transfer, Python materialization, or aggregation.

## 13. Implementation

Only the PostgreSQL path of `get_workflow_step_performance()` changed.

The new query performs:

- `COUNT(*)` for total rows;
- conditional counts with `FILTER` for completed, failed, and skipped;
- filtered `AVG`, `MIN`, and `MAX`;
- `percentile_disc(0.50)` and `percentile_disc(0.95)` for nearest-rank
  percentiles;
- `GROUP BY step_key`; and
- deterministic `ORDER BY step_key`.

Representative implemented SQL:

```sql
SELECT
    step_key,
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
    COUNT(*) FILTER (WHERE status = 'skipped') AS skipped_count,
    AVG(duration_ms) FILTER (
        WHERE duration_ms IS NOT NULL AND status <> 'skipped'
    ) AS average_ms,
    MIN(duration_ms) FILTER (
        WHERE duration_ms IS NOT NULL AND status <> 'skipped'
    ) AS minimum_ms,
    MAX(duration_ms) FILTER (
        WHERE duration_ms IS NOT NULL AND status <> 'skipped'
    ) AS maximum_ms,
    percentile_disc(0.50) WITHIN GROUP (ORDER BY duration_ms) FILTER (
        WHERE duration_ms IS NOT NULL AND status <> 'skipped'
    ) AS p50_ms,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_ms) FILTER (
        WHERE duration_ms IS NOT NULL AND status <> 'skipped'
    ) AS p95_ms
FROM analysis_step_metrics
WHERE created_at >= :start_at
  AND created_at <= :end_at
GROUP BY step_key
ORDER BY step_key;
```

The existing three-decimal API formatting remains in Python. SQLite retains
the original implementation because it lacks PostgreSQL ordered-set aggregate
support. No surrounding Monitoring endpoint was changed.

## 14. Alembic migration

No migration was created.

Reasons:

- the optimization changes only query structure;
- all required columns and the existing Step-key index already exist;
- the benchmark did not justify another index;
- write amplification and index storage remain unchanged; and
- rollback is a code revert.

The migration chain remains:

```text
20260712_01 -> 20260713_02 -> 20260713_03 -> 20260717_04 -> 20260721_05
```

`CREATE INDEX CONCURRENTLY` is not relevant because no index is added.

## 15. Correctness tests

Added PostgreSQL integration coverage proves:

- total/completed/failed/skipped counts;
- unchanged handling of nonterminal/other statuses;
- exclusion of skipped rows from all latency calculations;
- exclusion of null duration rows from latency calculations;
- average, minimum, maximum, nearest-rank p50, and nearest-rank p95;
- inclusive start and end timestamps;
- exclusion immediately outside both boundaries;
- deterministic alphabetical Step ordering;
- empty-period response; and
- a bounded six-row aggregate result over a 50,000-row generated fixture.

The plan-regression test avoids timing thresholds. It asserts:

- six grouped result rows;
- all 50,000 source rows represented in the summaries; and
- no disk-based explicit Sort node.

Existing SQLite Monitoring tests continue to cover the compatibility path,
including skipped-row percentile behavior and empty monitoring state.

The 300,000-row before/after benchmark also serialized both application
responses and compared them. Result:

```text
RESULTS_IDENTICAL=true
```

## 16. Optimized plan

Representative artifact:

[`../performance/plans/workflow-step-performance-after.json`](../performance/plans/workflow-step-performance-after.json)

Plan outline:

```text
Sorted Aggregate (actual rows=6, loops=1)
  Group Key: step_key
  Temp Read/Write Blocks: 0 / 0
  -> Index Scan using ix_analysis_step_metrics_step_key
       estimated rows=195231
       actual rows=194399
       rows removed by filter=105601
```

PostgreSQL selected the existing Step-key index to feed the grouped ordered-set
aggregate. No explicit Sort node or temporary I/O remained.

## 17. Optimized measurements

SQL measured runs:

| Run | Planning | Execution |
|---:|---:|---:|
| 1 | 0.218 ms | 204.840 ms |
| 2 | 0.170 ms | 185.212 ms |
| 3 | 0.221 ms | 213.915 ms |
| 4 | 0.171 ms | 178.411 ms |
| 5 | 0.169 ms | 203.163 ms |
| 6 | 0.165 ms | 168.535 ms |
| 7 | 0.164 ms | 167.464 ms |

Summary:

| Metric | Optimized |
|---|---:|
| Median planning | 0.170 ms |
| Planning p95 | 0.221 ms |
| Median execution | 185.212 ms |
| Execution p95 | 213.915 ms |
| Estimated rows | 6 |
| Actual/returned rows | 6 |
| Rows removed by filter | 105,601 |
| Scan | Index scan |
| Index | `ix_analysis_step_metrics_step_key` |
| Shared hit blocks | 24,925 |
| Shared read blocks | 0 |
| Explicit sort | None |
| Temp read/write blocks | 0 / 0 |
| Join strategy | None |
| Root loops | 1 |

Application measured runs in milliseconds:

```text
165.001, 184.048, 163.689, 163.765, 161.267, 159.973, 177.417
```

Median was 163.765 ms and p95 was 184.048 ms.

## 18. Before-and-after table

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Median execution time | 541.065 ms | 185.212 ms | -355.853 ms (-65.8%) |
| Execution p95 | 601.342 ms | 213.915 ms | -387.427 ms (-64.4%) |
| Median planning time | 0.129 ms | 0.170 ms | +0.041 ms |
| Median application time | 1,308.238 ms | 163.765 ms | -1,144.473 ms (-87.5%) |
| Application p95 | 1,350.730 ms | 184.048 ms | -1,166.682 ms (-86.4%) |
| Shared buffer hits | 417 | 24,925 | +24,508 |
| Shared buffer reads | 3,697 | 0 | -3,697 in representative warm plan |
| Rows removed by filter | 105,601 | 105,601 | unchanged |
| Returned rows | 194,399 | 6 | -194,393 (-99.997%) |
| Scan type | Sequential scan | Step-key index scan | changed |
| Index used | None | `ix_analysis_step_metrics_step_key` | existing index |
| Sort method | External merge | No explicit sort | removed |
| Sort memory/disk | 17,656 KiB disk | None | removed |
| Temp blocks read/written | 2,207 / 2,213 | 0 / 0 | removed |
| Join strategy | None | None | unchanged |
| Loops | 1 | 1 | unchanged |

The increased shared-hit count is an explicit trade-off, not an improvement.
The selected index scan touches more cached pages in Step-key order. The
meaningful wins are bounded result cardinality, removed disk sort/temp I/O, and
reduced database plus application execution time.

## 19. Storage and write cost

| Area | Impact |
|---|---|
| New table/index storage | 0 |
| Existing data rewrite | 0 |
| Metric insert/update overhead | Unchanged |
| Cache invalidation | None |
| Migration lock | None |
| Read CPU | PostgreSQL performs grouped aggregates and percentiles |
| Buffer access | More shared hits in the representative optimized plan |
| Application memory/CPU | Substantially reduced by returning six rows |

## 20. Risks

- `percentile_disc` is PostgreSQL-specific. The service explicitly preserves
  the SQLite fallback.
- Percentile, status, null, boundary, ordering, and rounding semantics could
  drift if the query is changed without parity tests.
- PostgreSQL may select another valid plan for a different data distribution
  or period.
- The optimized query still examines 300,000 rows in the representative index
  scan and rejects 105,601; it does not make scan work disappear.
- More shared-buffer hits can increase database cache pressure under
  concurrency even though large transfer and application work are removed.
- The benchmark is single-client and local, not a production capacity test.

## 21. Rollback

Rollback is code-only:

1. revert the PostgreSQL aggregate branch in
   `backend/monitoring_service.py`;
2. restore the original `SELECT * ... ORDER BY step_key, created_at`; and
3. retain or adjust the tests according to the restored behavior.

There is no index, schema object, data backfill, or cache entry to remove.

## 22. Full validation results

### Completed before pull-request publication

| Check | Result |
|---|---|
| Targeted SQLite Monitoring suite | Passed: 20 tests |
| New PostgreSQL correctness test | Passed |
| New PostgreSQL plan-regression test | Passed |
| Python compilation of changed modules | Passed |
| Plan JSON parsing | Passed |
| `git diff --check` | Passed |
| Before/after result JSON parity | Passed |

### Final local validation

| Check | Result |
|---|---|
| Full backend unittest discovery | Passed: 393 tests, 9 skipped opt-in PostgreSQL tests |
| Full PostgreSQL integration suite | Passed: 9 tests |
| Fresh PostgreSQL 16 Alembic upgrade | Passed during benchmark setup |
| Upgrade from previous revision | Passed in PostgreSQL integration migration tests |
| Downgrade and re-upgrade | Passed across supported revisions in the PostgreSQL integration suite |
| Alembic schema drift check | Passed: no new upgrade operations detected |
| Repository safety checks | Passed |
| Full phase changed-file secret scan | Passed: 9 files |
| Compose config validation | Passed with non-secret local placeholder values |
| Shell syntax | Passed for `scripts/*.sh` |
| ShellCheck | Passed for `scripts/*.sh`, `deploy/postgres/*.sh`, and `deploy/production/*.sh` |
| Local Docker image/smoke/runtime checks | Not runnable: this workspace user cannot access the Docker daemon; delegated to required GitHub CI jobs |
| Frontend checks | Not required; no frontend file changed |

No DeepSeek or other model-provider request is part of any test or benchmark.

## 23. Changed files

Implementation and evidence:

- `backend/monitoring_service.py`
- `backend/test_v2_postgres_integration.py`
- `docs/performance/plans/workflow-step-performance-before.json`
- `docs/performance/plans/workflow-step-performance-after.json`

Portfolio documentation:

- `docs/POSTGRESQL_QUERY_OPTIMIZATION_CASE_STUDY.md`
- `README.md`
- `docs/PROJECT_KNOWLEDGE.md`
- `docs/work-reports/README.md`
- `docs/work-reports/2026-07-24-postgresql-query-optimization-phase-1-work-report.md`

No frontend, runtime, Docker, Compose, deployment, release, or production file
was changed.

## 24. Commit SHAs

| Commit | Purpose |
|---|---|
| `b70fccf` | PostgreSQL workflow-Step aggregation, integration tests, and representative plans |
| Pending documentation commit | Case study, verified Project Knowledge, README link, and Work Report |

## 25. Pull request number and URL

Pending branch publication and pull-request creation.

## 26. CI results

Pending pull-request creation. The branch will not be merged by this task.

## 27. Confirmation that production was untouched

Confirmed.

- No production database, data, credentials, hostname, logs, metrics, or
  volume was accessed.
- No production SQL or migration was executed.
- No production index, table, row, configuration, deployment, release, or tag
  was changed.
- All query measurements used an isolated loopback-only PostgreSQL 16.14
  process and deterministic synthetic data.
- No deploy or release command was run.

## 28. Confirmation that DeepSeek was not called

Confirmed. DeepSeek was not called during repository inspection,
implementation, benchmarking, testing, documentation, or pull-request
preparation.

---

## Reproduction command outline

The benchmark used repository dependencies and a disposable PostgreSQL 16.14
server. Connection values below are placeholders; no credentials are stored in
this report.

```bash
# Start an isolated PostgreSQL 16 server bound to loopback.
# Create a test-named database.

cd backend
APP_ENV=test \
TEST_DATABASE_URL='postgresql+psycopg://<local-user>@<loopback>/<test-db>' \
DATABASE_URL='postgresql+psycopg://<local-user>@<loopback>/<test-db>' \
../.venv/bin/alembic -c alembic.ini upgrade head
```

After loading the deterministic fixture and running `ANALYZE`, both variants
used:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)
-- original or optimized query
```

Execution protocol:

1. two warm-up executions;
2. seven recorded SQL executions;
3. nearest-rank p95 over the seven execution values;
4. selection of the plan whose execution time was closest to the median;
5. two application warm-ups;
6. seven recorded application executions; and
7. serialized before/after response equality comparison.

For a stable CI-scale performance regression, the PostgreSQL integration test
generates 50,000 rows in one `generate_series` statement and asserts result and
plan shape rather than a machine-specific millisecond threshold.
