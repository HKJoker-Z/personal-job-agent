# PostgreSQL Query Optimization Case Study

## 1. Business context

Personal Job Agent exposes an administrator Monitoring dashboard for inspecting
sanitized Resume-to-JD analysis behavior. The workflow-Step endpoint reports
per-Step counts, failure/skipped counts, average/minimum/maximum duration, and
nearest-rank p50/p95 duration.

The endpoint is operational rather than part of a retired Jobs, Applications,
Approvals, or Tasks flow. Its data grows with every analysis, so its cost grows
even if the number of Step types remains small.

This case study implements exactly one optimization: aggregate workflow-Step
statistics in PostgreSQL instead of loading every matching metric into Python.

## 2. Original query path

| Layer | Path |
|---|---|
| HTTP | `GET /api/monitoring/workflow-steps?days=30` |
| FastAPI route | `backend/legacy_application.py` |
| Service | `get_workflow_step_performance()` in `backend/monitoring_service.py` |
| Table | `analysis_step_metrics` |

The original service selected complete rows for the time window, sorted all
matches, transferred them to Python, grouped them by `step_key`, and calculated
statistics in application memory.

## 3. Dataset and method

The benchmark used a fresh, loopback-only PostgreSQL 16.14 database migrated to
Alembic `20260721_05`. It contained 300,000 deterministic synthetic
`analysis_step_metrics` rows across six Step keys; 194,399 rows matched the
fixed 30-day interval.

Relevant settings were:

- `shared_buffers = 128MB`
- `work_mem = 4MB`
- `effective_cache_size = 4GB`
- `jit = off`
- `max_parallel_workers_per_gather = 2`
- `random_page_cost = 4`

Each query received two warm-ups and seven measured
`EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)` executions. Application
timing used the same warm-up/run counts, dataset, interval, and local
environment. Reported values are medians; p95 uses nearest rank over the seven
runs.

No production system or real Resume, JD, user, or Project Knowledge data was
used.

## 4. Original SQL

Representative SQL:

```sql
SELECT *
FROM analysis_step_metrics
WHERE created_at >= :start_at
  AND created_at <= :end_at
ORDER BY step_key, created_at;
```

Python then:

1. grouped 194,399 rows by `step_key`;
2. counted statuses;
3. excluded skipped and null-duration rows from latency statistics;
4. calculated average, min, max, nearest-rank p50, and nearest-rank p95; and
5. returned six summary objects.

## 5. Original execution plan

The representative median plan is stored at
[`performance/plans/workflow-step-performance-before.json`](performance/plans/workflow-step-performance-before.json).

Important nodes:

```text
Sort (actual rows=194399)
  Sort Method: external merge
  Sort Space Used: 17656 KiB
  Temp Read Blocks: 2207
  Temp Written Blocks: 2213
  -> Seq Scan on analysis_step_metrics
       actual rows=194399
       rows removed by filter=105601
```

The sequential scan was not inherently wrong: the interval selected about
64.8% of the table. The expensive work was returning wide rows, sorting the
entire match set by timestamp, transferring it, and rebuilding aggregates in
Python.

## 6. Root cause

The endpoint needed six grouped summaries but requested 194,399 complete source
rows. This created three avoidable costs:

- PostgreSQL performed an external disk sort on the complete result.
- The database protocol transferred every selected row to the backend.
- Python allocated, grouped, sorted, and aggregated a large list.

Adding another date index would not fix that result-shape mismatch. At the
measured selectivity, PostgreSQL still had to examine most rows.

## 7. Chosen optimization

PostgreSQL now calculates conditional counts and latency aggregates:

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

The service rounds database values to the existing three-decimal API format.
The SQLite development/test path deliberately retains the established Python
implementation because SQLite does not implement PostgreSQL ordered-set
aggregates.

## 8. Why this query structure was selected

- `FILTER` preserves status and latency inclusion rules without separate
  scans.
- `percentile_disc` implements the existing nearest-rank percentile behavior:
  it returns an observed duration at the first rank meeting the requested
  fraction.
- `GROUP BY step_key` makes the number of returned rows proportional to the
  number of Step types, not the number of executions.
- `ORDER BY step_key` preserves deterministic API ordering.
- No covering/composite index was added because reducing the result shape
  addressed the demonstrated bottleneck without new write or storage cost.

## 9. Before-and-after results

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Median SQL execution | 541.065 ms | 185.212 ms | -65.8% |
| SQL p95 | 601.342 ms | 213.915 ms | -64.4% |
| Median planning | 0.129 ms | 0.170 ms | +0.041 ms |
| Median application execution | 1,308.238 ms | 163.765 ms | -87.5% |
| Application p95 | 1,350.730 ms | 184.048 ms | -86.4% |
| Rows returned by PostgreSQL | 194,399 | 6 | -99.997% |
| Shared hit blocks | 417 | 24,925 | increased |
| Shared read blocks | 3,697 | 0 | warm-cache plan |
| Rows removed by filter | 105,601 | 105,601 | unchanged |
| Scan | Sequential scan | `step_key` index scan | changed |
| Explicit sort | External merge, 17,656 KiB | None | removed |
| Temp blocks read/written | 2,207 / 2,213 | 0 / 0 | removed |

The higher shared-hit count is reported rather than hidden. PostgreSQL used the
existing `ix_analysis_step_metrics_step_key` index to feed a sorted aggregate,
touching more cached pages. Despite that trade-off, SQL execution improved,
temporary I/O disappeared, and application work fell substantially because
only six rows crossed the database boundary.

The representative optimized plan is stored at
[`performance/plans/workflow-step-performance-after.json`](performance/plans/workflow-step-performance-after.json).

These are comparative local measurements, not production latency claims.

## 10. Correctness validation

Before and after API result JSON was identical for all six Step summaries in the
300,000-row benchmark.

PostgreSQL integration tests additionally cover:

- completed, failed, skipped, and other statuses;
- skipped-row exclusion from latency statistics;
- null-duration exclusion;
- average, minimum, maximum, nearest-rank p50, and nearest-rank p95;
- inclusive start/end timestamp boundaries and excluded out-of-range rows;
- deterministic Step ordering;
- empty intervals; and
- a 50,000-row generated plan fixture that returns six grouped rows without a
  disk sort.

Existing SQLite monitoring tests confirm that development/test fallback
behavior remains unchanged.

## 11. Storage and write trade-offs

No index, table, materialized view, cache, or pre-aggregated data was added.
Therefore:

- index/table storage cost is zero;
- metric write amplification is unchanged; and
- no refresh or invalidation mechanism is required.

The trade-off is additional PostgreSQL aggregate CPU and more shared-buffer hits
from the optimizer-selected `step_key` index scan. That is acceptable for this
read-only operational endpoint because it replaces large transfer and Python
materialization costs. Production plans should still be observed after rollout.

## 12. Migration and rollback

There is no Alembic migration. The schema remains at `20260721_05`.

Rollback is a code-only revert to the earlier `SELECT *` plus Python
aggregation. No data transformation or index drop is involved.

## 13. Limitations

- Results describe one isolated PostgreSQL 16.14 environment and deterministic
  distribution.
- The benchmark is single-client and warm-cache; it is not a concurrency or
  production-capacity test.
- The time range selected approximately 64.8% of the table. Other intervals and
  Step-key distributions can produce different plans.
- The optimized plan still examines matching and rejected rows; it removes
  transfer and full-result sorting, not the time-range scan itself.
- The SQLite fallback is intentionally not optimized with PostgreSQL-specific
  functions.
- Monitoring overview, RAG, security, recommendations, History, Resume, Project
  Knowledge, Evaluation, and Agent Run queries are outside this phase.

## 14. Interview talking points

- Start with the result shape: six summaries did not justify returning almost
  200,000 source rows.
- Explain why a sequential scan can be correct at 65% selectivity.
- Show how conditional aggregates and ordered-set percentiles preserve business
  semantics.
- Discuss why no new index was the lowest-risk answer.
- Call out the honest trade-off: buffer hits increased even while database and
  application latency improved.
- Describe stable regression testing through plan shape and bounded result
  cardinality instead of fragile millisecond thresholds.
- Separate local benchmark evidence from production claims.
