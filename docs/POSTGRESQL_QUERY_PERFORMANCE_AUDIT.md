# PostgreSQL Query Performance Audit

**Project:** Personal Job Agent  
**Audit date:** 2026-07-24  
**Product version:** 2.0.3  
**Scope:** Discovery and baseline measurement only  
**Status:** Recommendations only; no query, schema, index, runtime, or deployment change has been implemented

## Executive summary

This audit traced the PostgreSQL queries used by the current Personal Job
Agent product, inventoried the relevant schema and indexes, and measured
representative queries against a deterministic synthetic dataset in an
isolated PostgreSQL 16 environment.

Two candidates provide the clearest, lowest-risk optimization case studies:

1. Move Monitoring and Evaluation aggregation from Python into PostgreSQL.
2. Add an owner-and-sort composite index for the History list.

The first candidate addresses excessive row transfer, Python materialization,
and an external disk sort. The second addresses a user-facing list query that
currently scans and sorts a large table even when returning only 50 rows.

Project Knowledge full-text search, Resume Library queries, Evaluation lists,
and read-only Agent Run inspection were measured but not selected. They are
either already fast, bounded by current product behavior, low frequency, or
less compelling than the two selected candidates.

---

## 1. Repository branch and commit

| Item | Value |
|---|---|
| Repository | `https://github.com/HKJoker-Z/personal-job-agent` |
| Branch audited | `main` |
| Commit audited | `83e02a437382ad1edb3fd1715604dfe214a92278` |
| Upstream | `origin/main` |
| Working tree at the start and end of the audit | Clean |
| Product version | 2.0.3 |

The audited commit matched the commit supplied in the audit request. The
repository contained no pre-existing tracked or untracked changes when the
audit began.

The active application composition includes the current routers alongside
legacy application routes that remain in use. Retirement middleware blocks
the retired Jobs, Job Rankings, Applications, Approvals, and Tasks workflows,
plus mutating Agent Run operations. Those retired workflows were not treated
as optimization priorities.

---

## 2. Schema revision

| Item | Value |
|---|---|
| Database engine | PostgreSQL 16 |
| SQLAlchemy | 2.x |
| PostgreSQL driver | psycopg 3 |
| Migration framework | Alembic |
| Current production schema revision | `20260721_05` |

The isolated benchmark database was built by running the repository's Alembic
migrations through the current head. Indexes were inventoried from the
resulting PostgreSQL catalog rather than inferred only from ORM declarations.
This matters because some indexes created by the legacy database initializer
apply only to SQLite.

In particular, the following legacy initializer indexes do **not** exist in
PostgreSQL because PostgreSQL exits that initialization path:

- `idx_application_records_status`
- `idx_application_records_company_title`

They must not be counted as PostgreSQL indexes.

---

## 3. Candidate query inventory

### 3.1 History list

| Attribute | Detail |
|---|---|
| Endpoint | Current History list route |
| Route source | [`backend/legacy_application.py`](../backend/legacy_application.py), around line 2184 |
| Query source | [`backend/database.py`](../backend/database.py), around line 954 |
| Audience | User-facing |
| Tables | `application_records` |
| Filters | `owner_user_id`; optional `status`; optional company/title wildcard search; admin mode also permits `owner_user_id IS NULL` |
| Ordering | `created_at DESC, id DESC` |
| Pagination | `LIMIT` and `OFFSET` |
| Result shape | Count query plus page query, returning full selected row data |
| Expected cardinality | Tens of thousands of rows per active owner over time |

Approximate owner-scoped count SQL:

```sql
SELECT count(*)
FROM application_records
WHERE owner_user_id = :owner_user_id;
```

Approximate owner-scoped page SQL:

```sql
SELECT *
FROM application_records
WHERE owner_user_id = :owner_user_id
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

Approximate admin predicate:

```sql
WHERE owner_user_id = :owner_user_id
   OR owner_user_id IS NULL
```

Approximate optional search predicate:

```sql
AND (
    company LIKE '%' || :search || '%'
    OR job_title LIKE '%' || :search || '%'
)
```

Current indexes relevant to the query are the primary key and a single-column
`owner_user_id` index. There is no PostgreSQL composite index matching the
owner filter and descending order. PostgreSQL therefore cannot satisfy the
common filtered ordering directly from one index.

The frontend currently requests the first page with `offset=0`, but the API
supports arbitrary offsets. Deep-offset behavior is therefore a latent API
scalability issue, not a demonstrated current frontend bottleneck.

### 3.2 History detail

| Attribute | Detail |
|---|---|
| Endpoint | History detail |
| Query source | [`backend/database.py`](../backend/database.py), around line 1019 |
| Audience | User-facing |
| Tables | `application_records` |
| Filters | Primary key plus owner authorization |
| Ordering/pagination | None |
| Expected cardinality | Exactly zero or one row |

Approximate SQL:

```sql
SELECT *
FROM application_records
WHERE id = :id
  AND owner_user_id = :owner_user_id;
```

The primary-key lookup is already efficient. The extra owner predicate is a
correctness and authorization check and does not require another index.

### 3.3 History delete and related metric lookup

| Attribute | Detail |
|---|---|
| Path | History delete |
| Query source | [`backend/database.py`](../backend/database.py), around line 1151 |
| Audience | User-facing mutation, inspected only; not executed in the benchmark |
| Tables | `application_records`, related `analysis_metrics` |
| Relevant issue | `analysis_metrics.application_id` is a foreign key without a supporting index |

A read-only proxy query demonstrated that locating an analysis metric by
`application_id` scans the full `analysis_metrics` table:

```sql
SELECT id
FROM analysis_metrics
WHERE application_id = :application_id;
```

This remains a secondary finding because the exact delete path was not
executed during a read-only audit and production deletion frequency is
unknown.

### 3.4 Resume list

| Attribute | Detail |
|---|---|
| Endpoint | Resume Library list |
| ORM source | [`backend/app/resumes/repository.py`](../backend/app/resumes/repository.py), around line 17 |
| Audience | User-facing |
| Tables | `resumes` |
| Filters | `user_id`, `archived_at IS NULL` |
| Ordering | `is_primary DESC, updated_at DESC, created_at DESC` |
| Pagination | No database pagination |
| Expected cardinality | Normally small per user |

SQLAlchemy expression, approximately:

```python
select(Resume).where(
    Resume.user_id == user_id,
    Resume.archived_at.is_(None),
).order_by(
    Resume.is_primary.desc(),
    Resume.updated_at.desc(),
    Resume.created_at.desc(),
)
```

Approximate SQL:

```sql
SELECT *
FROM resumes
WHERE user_id = :user_id
  AND archived_at IS NULL
ORDER BY is_primary DESC, updated_at DESC, created_at DESC;
```

The existing partial unique primary-resume index begins with `user_id`, but it
only contains rows where `is_primary IS TRUE AND archived_at IS NULL`; it
cannot service the complete active resume list. Even so, expected user-level
cardinality is low, and the exaggerated benchmark remained fast.

### 3.5 Primary Resume and active version

| Attribute | Detail |
|---|---|
| Endpoint | Primary Resume retrieval |
| ORM source | [`backend/app/resumes/repository.py`](../backend/app/resumes/repository.py), around line 26 |
| Service source | [`backend/app/resumes/service.py`](../backend/app/resumes/service.py), around line 100 |
| Audience | User-facing |
| Tables | `resumes`, `resume_versions` |
| Filters | User, primary flag, not archived; then active-version lookup |
| Query count | Fixed two queries |
| Expected cardinality | Zero or one Resume, then zero or one active version |

The first query is supported by the partial unique primary-resume index. The
second query is a fixed lookup, so this is not an N+1 pattern.

### 3.6 Resume version list

| Attribute | Detail |
|---|---|
| Path | Resume version list |
| ORM source | [`backend/app/resumes/repository.py`](../backend/app/resumes/repository.py), around line 62 |
| Audience | User-facing |
| Tables | `resume_versions` |
| Filter | `resume_id` |
| Ordering | Version/order fields defined by the repository |
| Existing index | Unique `(resume_id, version_number)` and a separate `resume_id` index |
| Expected cardinality | Small per Resume |

The ORM loads complete version objects, including potentially large
`content_json` and `parsed_text` columns, although the list serializer does not
need all of that content. This is a valid projection improvement opportunity,
but measured latency and current cardinality do not justify making it a top
case study.

### 3.7 Project Knowledge full-text search

| Attribute | Detail |
|---|---|
| Endpoint | Project Knowledge search used by Resume-to-JD analysis |
| Route source | [`backend/legacy_application.py`](../backend/legacy_application.py), around line 1631 |
| Query source | [`backend/database.py`](../backend/database.py), around line 1692 |
| Audience | User-facing synchronous workflow |
| Tables | `knowledge_documents`, `knowledge_chunks` |
| Filters | Owner/document scope; full-text query; fallback substring scan |
| Ordering | Full-text rank and/or chunk order |
| Pagination | Bounded result limit |
| Existing indexes | Document/chunk unique index and GIN full-text expression index |

Approximate full-text predicate:

```sql
WHERE document_id = :document_id
  AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
```

The current route always supplies a specific supported Project Knowledge
document. Product limits cap that document at approximately 30,000
characters, corresponding to roughly 35 chunks in normal operation. The
no-hit fallback is also restricted to the selected document. This makes the
real path much smaller than a global corpus search.

### 3.8 Monitoring overview

| Attribute | Detail |
|---|---|
| Endpoint family | Monitoring overview, RAG, security, and recommendations |
| Shared query source | [`backend/monitoring_service.py`](../backend/monitoring_service.py), around line 318 |
| Audience | Operational |
| Tables | `analysis_metrics` |
| Filter | `created_at` range |
| Ordering | `created_at DESC` |
| Pagination | None |
| Current result shape | Every matching row and every column |
| Aggregation | Performed in Python |
| Expected cardinality | Tens or hundreds of thousands of rows as operational history grows |

Approximate SQL:

```sql
SELECT *
FROM analysis_metrics
WHERE created_at >= :start_at
  AND created_at < :end_at
ORDER BY created_at DESC;
```

The query has a usable `created_at` index, but the application transfers and
materializes the full time window, including fields not needed by every
dashboard calculation. Several monitoring endpoints call the same row-loading
helper independently, amplifying work when the dashboard loads.

### 3.9 Monitoring workflow-step statistics

| Attribute | Detail |
|---|---|
| Endpoint | Monitoring workflow-step metrics |
| Query source | [`backend/monitoring_service.py`](../backend/monitoring_service.py), around line 363 |
| Audience | Operational |
| Tables | `analysis_step_metrics` |
| Filter | `created_at` range |
| Ordering | `step_key, created_at` |
| Pagination | None |
| Current result shape | Every matching row and every column |
| Aggregation | Grouping and percentile calculation in Python |

Approximate SQL:

```sql
SELECT *
FROM analysis_step_metrics
WHERE created_at >= :start_at
  AND created_at < :end_at
ORDER BY step_key, created_at;
```

The measured time range selected about 65% of the table. At that selectivity,
a sequential scan is reasonable. The expensive part is reading 194,391 rows,
sorting them to disk, transferring them to the application, and aggregating in
Python.

### 3.10 Monitoring trace list and detail

| Attribute | Detail |
|---|---|
| Path | Analysis trace list and trace detail |
| Source | [`backend/monitoring_service.py`](../backend/monitoring_service.py), around lines 482 and 534 |
| Audience | Operational |
| Tables | Analysis metric and step metric tables |
| Filters | Time, owner, outcome, workflow identifiers as applicable |
| Pagination | Offset-based list; direct detail lookup |

The measured filtered list remained within an acceptable range, including at
an exaggerated offset of 10,000. It is not selected for immediate work.

### 3.11 Evaluation list and detail

| Attribute | Detail |
|---|---|
| Path | Evaluation run list and detail |
| Source | [`backend/evaluation_service.py`](../backend/evaluation_service.py), around lines 386 and 410 |
| Audience | Operational |
| Tables | `evaluation_runs`, `evaluation_results` |
| Filters | Owner and run identifiers |
| Pagination | Offset-based list |
| Expected cardinality/frequency | Lower-frequency operational workflow |

Existing owner, run, and start-time indexes support the principal access
paths. The exaggerated deep list measurement remained fast.

### 3.12 Read-only Agent Run list, detail, and event timeline

| Attribute | Detail |
|---|---|
| Path | Agent Run list, detail, event timeline |
| Service source | [`backend/app/agent_runs/service.py`](../backend/app/agent_runs/service.py), around lines 176, 184, 193, and 719 |
| Audience | Retained read-only operational infrastructure |
| Tables | `agent_runs`, `agent_steps`, `agent_run_events`, approval-related history |
| Filters | Owner, run ID, status |
| Ordering | Run creation time; step order; event ID |
| Pagination | List limit/offset; events use `id > after_id` |

The event timeline already uses a keyset-like predicate:

```sql
WHERE run_id = :run_id
  AND id > :after_id
ORDER BY id
LIMIT :limit;
```

The `(run_id, id)` index is well aligned with that query. Run detail performs
a redundant owned-run check in a fixed number of queries, but does not exhibit
an N+1 query pattern.

---

## 4. Relevant current index inventory

The following inventory reflects the migrated PostgreSQL schema used for the
benchmark.

### `application_records`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Single-column index | `(owner_user_id)` |
| Single-column index | `(workflow_id)` |
| Important absence | No `(owner_user_id, created_at DESC, id DESC)` index |
| Important absence | No PostgreSQL status index |
| Important absence | No PostgreSQL company/title search index |

The owner-only index supports counting owner rows but does not cover the list
ordering. It is not redundant with the proposed composite index until actual
PostgreSQL usage statistics prove otherwise.

### `resumes`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Single-column index | `(user_id)` |
| Partial unique index | `(user_id) WHERE is_primary IS TRUE AND archived_at IS NULL` |

The partial unique index correctly enforces one active Primary Resume per user.

### `resume_versions`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Unique index | `(resume_id, version_number)` |
| Single-column index | `(resume_id)` |
| Unindexed foreign keys | Parent/source-file/creator references where applicable |

The separate `resume_id` index is likely a left-prefix duplicate of the unique
composite index, but it should not be removed without production index-usage
evidence and constraint review.

### `file_assets`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Unique index | `(storage_key)` |
| Single-column index | `(user_id)` |
| Single-column index | `(sha256)` |

### `knowledge_documents`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Single-column index | Owner identifier |

### `knowledge_chunks`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Unique index | `(document_id, chunk_index)` |
| Single-column index | `(document_id)` |
| Full-text index | GIN on `to_tsvector('simple', content)` |

The separate `document_id` index may duplicate the left prefix of the unique
index. The GIN expression matches the current full-text expression. Because
the real workflow is document-scoped and bounded, no new full-text index is
recommended.

### `analysis_metrics`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Unique index | `(workflow_id)` |
| Single-column indexes | `(created_at)`, `(outcome)`, owner identifier |
| Important absence | No index on `application_id` foreign key |

The `created_at` index is useful for selective time windows. For a window that
matches roughly 65% of the table, a sequential scan can be cheaper and is not
automatically a problem.

### `analysis_step_metrics`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Single-column indexes | `(created_at)`, owner identifier, `(step_key)`, `(workflow_id)` |
| Important absence | No composite index covering the current date filter and sort |

A composite date/sort index is not recommended as the first fix. It would
still return almost 200,000 wide rows in the measured window, while
server-side aggregation removes the need to return or globally sort those
rows.

### `evaluation_runs`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Unique index | `(run_id)` |
| Single-column indexes | Owner identifier, `(started_at)` |

### `evaluation_results`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Single-column indexes | Owner identifier, `(run_id)` |

### `agent_runs`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Unique indexes | Owner/workflow and owner/idempotency combinations |
| Composite index | `(owner_user_id, status, created_at)` |
| Other indexes | Several single-column indexes supporting lookup paths |

### `agent_steps`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Composite index | `(run_id, step_order)` |
| Composite index | `(status, scheduled_at)` |
| Other indexes | Unique and single-column indexes, including overlapping prefixes |

### `agent_run_events`

| Type | Definition |
|---|---|
| Primary key | `(id)` |
| Composite index | `(run_id, id)` |
| Other indexes | Single-column indexes, some overlapping with composite prefixes |

### Approval-related retained tables

These tables contain overlapping single and composite indexes. Because
Approvals are retired from current product use, index removal or redesign is
outside this audit's optimization scope.

### Cross-cutting index findings

- Several foreign keys do not have supporting indexes. The clearest current
  example is `analysis_metrics.application_id`.
- Some single-column indexes duplicate the left prefix of composite or unique
  indexes.
- No duplicate index should be removed based only on schema appearance.
  Production `pg_stat_user_indexes`, constraint dependencies, write rates, and
  representative query plans are required first.
- Sequential scans in the monitoring benchmark are reasonable when the date
  range matches most of a table.
- The most justified new index is the History owner-and-order index because it
  directly matches a current, user-facing query.

---

## 5. Benchmark dataset sizes

### Environment

| Item | Value |
|---|---|
| Isolation | Local temporary database only |
| PostgreSQL | 16.14 |
| Listen address | `127.0.0.1` |
| Temporary port | `55432` |
| CPU visible to benchmark | 4 vCPU, Intel Xeon Gold 6148 |
| Memory visible to benchmark | Approximately 3.6 GiB |
| `shared_buffers` | 128 MiB |
| `work_mem` | 4 MiB |
| `effective_cache_size` | 4 GiB |
| `jit` | Off |
| `max_parallel_workers_per_gather` | 2 |
| `random_page_cost` | 4 |

Docker was not used because the local Docker daemon was unavailable to the
audit process. Instead, the PostgreSQL 16.14 server package was unpacked into
a temporary directory and run as an unprivileged local process bound only to
loopback.

### Deterministic synthetic fixture

| Table/domain | Rows |
|---|---:|
| Users | 5 |
| File assets | 2,000 |
| Resumes | 2,000 |
| Resume versions | 6,000 |
| Application/History records | 50,000 |
| Project Knowledge documents | 500 |
| Project Knowledge chunks | 50,000 |
| Analysis metrics | 100,000 |
| Analysis step metrics | 300,000 |
| Evaluation runs | 10,000 |
| Evaluation results | 100,000 |
| Agent runs | 10,000 |
| Agent steps | 50,000 |
| Agent run events | 100,000 |
| Approval requests retained for compatibility | 1,000 |

Additional measured distributions:

- History rows for the principal benchmark owner: 35,000.
- Unowned History rows visible through the admin predicate: 5,000.
- Analysis metrics in the measured rolling period: approximately 64,800.
- Analysis step metrics in the measured rolling period: approximately
  194,400.
- Project Knowledge scoped-search stress document: 100 chunks. This already
  exceeds the roughly 35 chunks expected from the current product's
  30,000-character supported document limit.

All text and JSON content was synthetic and generated deterministically with
SQL series and hash-based values. No real Resume, job description, email,
account, or Project Knowledge data was used. No generated dataset was added
to the repository.

---

## 6. `EXPLAIN ANALYZE` baseline summaries

### Method

Every shortlisted or comparative SQL query was captured with:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)
```

Each SQL case received two warm-up executions followed by seven measured
executions. Values below are medians unless a range is explicitly shown.
Application-level core timings used one warm-up followed by five measured
executions.

These local timings are comparative baselines, not production service-level
objectives. Hardware, concurrency, connection latency, cache state, and real
data distributions will affect production results.

### Baseline table

| Query | Planning | Execution | Actual/result rows | Principal plan | Buffers and sort | App-level core |
|---|---:|---:|---:|---|---|---:|
| History owner count | 0.055 ms | 4.641 ms | 35,000 / 1 | Index-only scan | 30 hits, 0 reads | Not separately material |
| History first page | 0.092 ms | 58.507 ms | 35,000 qualifying / 50 returned | Sequential scan + top-N sort | 1,128 hits, 12,372 reads; top-N 50 KiB | 65.176 ms |
| History offset 25,000 | 0.103 ms | 54.706 ms | 25,050 processed for 50 returned | Parallel sequential scan + Gather Merge | 1,050 hits, 11,540 reads; external merge about 4.4 MiB/worker; 1,301 temp reads, 1,325 temp writes | 57.450 ms |
| History admin first page | — | 64.062 ms | 40,000 qualifying / 50 returned | Sequential scan + top-N sort | 10,000 removed; 12,048 reads | — |
| History `%Company 42%` search | 0.121 ms | 41.482 ms | Estimated 7, actual 200 / 50 returned | Sequential scan + top-N sort | 49,800 removed; 10,800 reads | — |
| History detail | — | 0.013 ms | 1 | Primary-key index | Negligible | — |
| Monitoring overview row load | 0.115 ms | 17.074 ms | 64,797 | Date index scan | 3,296 hits, 0 reads | 993.373 ms |
| Monitoring workflow-step row load | 0.135 ms | 537.288 ms | 194,391 | Sequential scan + external sort | 160 hits, 4,455 reads; 20,432 KiB disk sort; 2,554 temp reads, 2,560 temp writes | 1,991.685 ms |
| Read-only proposed step aggregate | — | 186.876 ms | 6 | Scan + grouped aggregate | No large result transfer; no external final sort | 181.700 ms |
| Read-only proposed overview aggregate | — | 23.522 ms | 1 | Conditional aggregate | No large result transfer | Not separately recorded |
| Monitoring trace list, offset 10,000 | — | 13.028 ms | Page result | Existing filtered list plan | No material issue | 31.464 ms |
| Resume list, exaggerated 400 rows/user | — | 0.327 ms | 400 | Small filtered scan/sort | In memory | 9.290 ms |
| Primary Resume lookup | — | 0.012 ms | 1 | Partial unique index | Negligible | 2.817 ms for fixed two-query service path |
| Scoped Project Knowledge FTS hit | — | 2.580 ms | Bounded | GIN/document filtering | No material issue | 9.441 ms |
| Scoped Project Knowledge no-hit fallback | — | 0.063 ms | Bounded document scan | Document-scoped scan | No material issue | 12.436 ms |
| Evaluation list, offset 8,000 | — | 2.460 ms | Page result | Existing indexes | No material issue | 8.728 ms |
| Agent Run list | — | 0.978 ms | Page result | Existing owner/status indexes | No material issue | 15.853 ms |
| Agent Run detail | — | — | One run with related rows | Fixed query count | No N+1 | 5.094 ms |
| Agent Run events | — | 0.039 ms | Bounded page | `(run_id, id)` index | No material issue | 2.657 ms |
| `analysis_metrics.application_id` proxy | — | 23.444 ms | 1 | Sequential scan of 100,000 rows | 99,999 removed by filter | Not applicable |

### Important plan interpretation

#### History first page

The owner index is useful for the count but does not provide the requested
order. PostgreSQL chose to scan 50,000 wide rows, retain 35,000 owner rows, and
perform a top-N sort to return 50. The work is disproportionate to the result
size and will grow with History volume.

#### History deep offset

The median happened to be slightly lower than the first-page median because
PostgreSQL selected a parallel plan. That does not mean deep offset is cheaper.
The query still processes and sorts at least `offset + limit` rows, spills to
temporary storage, and grows linearly with offset. The plan shape is the
important finding.

#### Monitoring overview

Database execution alone was only 17.074 ms because the date index found the
rows in cache. Application-level work was 993.373 ms because 64,797 complete
rows had to be converted, transferred, materialized, and aggregated in Python.
Optimizing only the index would miss the dominant cost.

#### Monitoring workflow steps

The measured time range selected about 65% of 300,000 rows. PostgreSQL
reasonably used a sequential scan. The query then sorted 194,391 rows by
`step_key, created_at`, spilling about 20 MiB to disk before the application
performed the actual statistics. Returning six grouped aggregate rows reduced
application-level core time by approximately 90.9%.

#### Cardinality estimation

The main owner count estimate was accurate: 34,998 estimated versus 35,000
actual. The wildcard History search was less accurate: 7 estimated versus 200
actual. This is a secondary reason to avoid relying on the current `LIKE
'%term%'` plan for future large-scale search, but not enough by itself to
justify a trigram index today.

---

## 7. Top optimization candidates

Only two candidates are selected. They demonstrate different SQL concepts and
avoid presenting several nearly identical list-index changes.

### Scoring method

Each category is scored from 1 to 5. For implementation risk, 5 means low
risk. Maximum score is 40.

| Candidate | Product relevance | Measurable problem | Growth realism | Optimization clarity | Interview value | Low implementation risk | Testability | Trade-off clarity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Monitoring server-side aggregation | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 5 | **39/40** |
| History owner/order composite index | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 4 | **38/40** |
| History wildcard search | 4 | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 30/40 |
| Resume list/version projection | 5 | 2 | 2 | 4 | 3 | 4 | 4 | 4 | 28/40 |
| Project Knowledge FTS | 5 | 2 | 2 | 3 | 4 | 3 | 4 | 4 | 27/40 |
| Evaluation list | 3 | 2 | 3 | 4 | 3 | 4 | 4 | 4 | 27/40 |
| Agent Run inspection | 2 | 2 | 3 | 4 | 3 | 4 | 4 | 4 | 26/40 |

Selected candidates:

1. Monitoring and Evaluation server-side aggregation.
2. History list composite indexing, with keyset pagination held as a separate
   optional follow-up if real deep-page usage is demonstrated.

---

## 8. Why each candidate was selected

### Candidate 1: Monitoring server-side aggregation

- It is part of the current operational product and several dashboard
  endpoints depend on the same raw-row loading pattern.
- It has the largest measured application-level cost: approximately 1.0
  second for overview processing and approximately 2.0 seconds for workflow
  steps in the local fixture.
- The workflow-step query spills an approximately 20 MiB sort to temporary
  storage.
- The result needed by the API is a handful of aggregates, not nearly 200,000
  source rows.
- The improvement is easy to explain and measure: push filtering, grouping,
  counts, averages, and percentiles to PostgreSQL and return bounded result
  sets.
- A read-only prototype showed about a 90.9% reduction in application-level
  core time for workflow-step statistics.
- It requires no new index initially and adds no index storage or write
  amplification.

### Candidate 2: History owner/order composite index

- History is a current, user-facing workflow.
- The normal first page scans and sorts a 98 MiB table to return only 50 rows.
- The existing owner-only index does not cover the stable sort order.
- The optimization exactly matches equality filtering followed by descending
  ordering.
- It demonstrates a clear PostgreSQL composite-index principle: equality
  prefix, then ordered columns, with a deterministic tie-breaker.
- It preserves the current API response and query semantics.
- It is independently testable with both correctness and plan-regression
  tests.

---

## 9. Proposed changes

No proposal in this section has been implemented.

### 9.1 Candidate 1: aggregate Monitoring data in PostgreSQL

#### Exact problem

Monitoring helpers execute `SELECT *` over a time range, return tens or
hundreds of thousands of rows, and calculate summary statistics in Python.
The workflow-step helper additionally asks PostgreSQL to sort all rows before
they are transferred.

#### Baseline plan

- Overview: date index scan, 64,797 rows returned, 17.074 ms database
  execution, 993.373 ms application-level core processing.
- Workflow steps: sequential scan, 194,391 rows, external merge sort, 537.288
  ms database execution, 1,991.685 ms application-level core processing.

#### Proposed SQL/ORM shape

Use conditional aggregation for overview statistics:

```sql
SELECT
    count(*) AS total_count,
    count(*) FILTER (WHERE outcome = 'success') AS success_count,
    count(*) FILTER (WHERE outcome = 'failure') AS failure_count,
    avg(duration_ms) FILTER (WHERE duration_ms IS NOT NULL) AS avg_duration_ms
FROM analysis_metrics
WHERE created_at >= :start_at
  AND created_at < :end_at;
```

Use grouped aggregates and ordered-set percentile functions for workflow-step
statistics:

```sql
SELECT
    step_key,
    count(*) AS total_count,
    count(*) FILTER (WHERE status = 'success') AS success_count,
    count(*) FILTER (WHERE status = 'failure') AS failure_count,
    avg(duration_ms)
        FILTER (
            WHERE duration_ms IS NOT NULL
              AND status <> 'skipped'
        ) AS avg_duration_ms,
    percentile_disc(0.5) WITHIN GROUP (ORDER BY duration_ms)
        FILTER (
            WHERE duration_ms IS NOT NULL
              AND status <> 'skipped'
        ) AS p50_duration_ms,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_ms)
        FILTER (
            WHERE duration_ms IS NOT NULL
              AND status <> 'skipped'
        ) AS p95_duration_ms
FROM analysis_step_metrics
WHERE created_at >= :start_at
  AND created_at < :end_at
GROUP BY step_key
ORDER BY step_key;
```

The final expressions must be matched exactly to current Python semantics,
including skipped rows, null durations, rounding, status categories, and
empty periods.

RAG and recommendation summaries should use the same bounded aggregate
approach. Security finding payloads require more care because JSON content may
be malformed or heterogeneous. A safe first implementation can select only
the narrow required columns and retain defensive Python parsing. PostgreSQL
JSON expansion should be considered only after malformed-data behavior has
explicit tests.

#### Proposed indexes

None initially.

The benchmark time window selected approximately 65% of both metric tables.
An additional index is unlikely to eliminate the dominant cost and would add
write overhead to high-growth operational tables. Reassess after deploying
the aggregate queries and observing production plans for real time-window
distributions.

#### Expected benefit

- Workflow-step application-level core time reduced from about 1,991.685 ms
  to about 181.700 ms in the local benchmark.
- Bounded response from PostgreSQL: one overview row and roughly one row per
  step key.
- Elimination of large Python object lists and most database-to-application
  transfer.
- Elimination of the unnecessary global `step_key, created_at` disk sort.
- Lower application memory pressure and more predictable dashboard latency.

#### Rollback

Keep the existing Python aggregation helper behavior covered by parity tests.
Rollback consists of reverting the service query changes; there is no schema
object to remove.

### 9.2 Candidate 2: index the History owner and stable order

#### Exact problem

The common owner-scoped list filters by `owner_user_id`, then orders by
`created_at DESC, id DESC`. The existing owner-only index cannot return rows
in that order, so PostgreSQL scans and sorts a large set to return a small
page.

#### Baseline plan

- First page: sequential scan plus top-N sort, 58.507 ms median.
- 35,000 rows qualify and 50 are returned.
- 12,372 shared-buffer reads in the median representative result.
- Deep offset: parallel scan and external merge sort with temporary I/O.

#### Proposed index

```sql
CREATE INDEX ix_application_records_owner_created_id
ON application_records (
    owner_user_id,
    created_at DESC,
    id DESC
);
```

For a populated deployment, implementation planning should consider a
concurrent PostgreSQL index build so that normal writes are not blocked for
the duration of index creation. The exact Alembic transaction handling must
be tested against the project's deployment process.

#### Why this column order

- `owner_user_id` is the equality predicate and must be the leading column.
- `created_at DESC` matches the primary sort.
- `id DESC` is the deterministic tie-breaker and makes page order stable when
  timestamps are equal.

#### Why not a covering index

History rows contain potentially large URL, text, and JSON fields. Including
those columns would materially increase index size and write cost. The list
still needs heap access for its displayed data, so the narrow ordering index
is the smallest justified design.

#### Query change

No ORM or raw SQL change is required for the initial optimization. Retain:

```sql
WHERE owner_user_id = :owner_user_id
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

The admin `owner = :owner OR owner IS NULL` predicate may not receive the same
benefit. It should be benchmarked independently. A `UNION ALL` rewrite is
possible, but it should not be introduced without correctness tests for
deduplication, ordering, counts, and visibility semantics.

#### Optional later keyset pagination

The current frontend only requests `offset=0`. Therefore, changing the public
pagination contract is not part of the smallest initial fix.

If API telemetry later demonstrates real deep-page usage, introduce cursor
pagination separately:

```sql
SELECT *
FROM application_records
WHERE owner_user_id = :owner_user_id
  AND (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
```

This avoids work proportional to the offset and remains stable when the cursor
contains both ordering columns.

#### Expected benefit

- Direct ordered index scan for the common owner-scoped page.
- Work scales primarily with the page size rather than all owner rows.
- No explicit sort for the common path.
- Stable ordering under equal timestamps.
- Better first-page latency and buffer behavior as History grows.

#### Rollback

Drop the new index and retain the existing query:

```sql
DROP INDEX ix_application_records_owner_created_id;
```

The existing owner-only index should not be dropped in the same migration.
Its removal, if later justified, should be a separate change informed by
production index-usage data.

---

## 10. Expected trade-offs

### Monitoring server-side aggregation

| Benefit | Cost/risk |
|---|---|
| Far fewer rows transferred | PostgreSQL performs more aggregate CPU work |
| Lower Python memory and CPU | Percentile semantics must match Python exactly |
| No new index storage | PostgreSQL-specific ordered-set aggregates need a compatible test/fallback strategy if SQLite tests remain |
| Bounded API computation | Null, skipped, empty-window, timezone, and rounding behavior can cause subtle differences |
| Removes external row sort | Security JSON is unsafe to expand without malformed-payload tests |

Migration risk is low because there is no schema migration. Correctness risk
is moderate and should be controlled with result-parity tests.

### History composite index

| Benefit | Cost/risk |
|---|---|
| Faster owner-scoped ordered pages | Additional index storage |
| Avoids common-path sort | One extra index update per History insert/update/delete |
| No initial API change | Index construction requires deployment planning on a populated table |
| Stable order through `id` tie-breaker | Admin `OR owner IS NULL` path may need a different plan |
| Supports future cursor pagination | Keyset pagination would be a separate API contract change |

The proposed index is expected to be only a few MiB at the 50,000-row
benchmark scale, but production size must be measured before migration.

### General cautions

- Do not add a trigram extension and indexes merely because wildcard search
  exists.
- Do not add date indexes to solve a query whose date range matches most rows.
- Do not remove apparently duplicated indexes without production usage and
  dependency data.
- Do not introduce caching before making the SQL result shape reasonable.

---

## 11. Files likely to change during implementation

No implementation changes have been made. If approved, the likely change set
is:

### History index

- [`backend/database.py`](../backend/database.py) only if a query or pagination
  adjustment is approved; the initial index alone may not require it.
- A new Alembic migration under the repository's migration directory.
- [`backend/legacy_application.py`](../backend/legacy_application.py) only if
  cursor pagination or admin-query restructuring is approved.
- [`frontend/src/legacy-workspace.jsx`](../frontend/src/legacy-workspace.jsx)
  only if the public pagination contract changes.
- PostgreSQL integration and History route tests.

### Monitoring aggregation

- [`backend/monitoring_service.py`](../backend/monitoring_service.py).
- Monitoring service tests.
- PostgreSQL integration tests for ordered-set aggregates and query result
  parity.

Runtime configuration, Docker configuration, deployment infrastructure, and
production data do not need to change for the recommended first phase.

---

## 12. Tests that should be added

### History correctness tests

- Owner-scoped page returns exactly the same rows before and after indexing.
- Records with equal `created_at` values are ordered deterministically by
  descending `id`.
- User isolation remains enforced.
- Admin visibility of owned and unowned records remains correct.
- Status filtering composes correctly with owner filtering.
- Wildcard company/title search returns unchanged results.
- Count and page queries remain consistent.
- If keyset pagination is later approved, consecutive pages contain no
  duplicates or omissions, including equal timestamps and concurrent inserts.

### History schema and plan tests

- Migration creates exactly
  `(owner_user_id, created_at DESC, id DESC)`.
- Downgrade removes only the new index.
- A generated PostgreSQL fixture demonstrates an ordered index scan without
  an explicit sort for the owner-scoped first page.
- Plan assertions should check important nodes and index names, not brittle
  exact cost numbers.
- Generated benchmark data must remain uncommitted.

### Monitoring correctness tests

- New SQL aggregates match the current Python results on the same fixture.
- Empty time windows.
- One-row groups.
- Odd and even duration counts for percentile behavior.
- Null durations.
- Skipped steps.
- Success, failure, and other status categories.
- Timestamp boundaries and timezone-aware inputs.
- Existing rounding and output types.
- Missing and malformed JSON security payloads.
- Multiple owners if owner scoping applies.

### Monitoring performance regression tests

- PostgreSQL returns a bounded number of aggregate rows regardless of source
  row count.
- Workflow-step query does not perform the previous global external sort.
- The application does not materialize every metric ORM/raw row.
- Performance assertions should use plan shape, returned-row bounds, and
  absence of temp sorting rather than strict wall-clock thresholds.

### Existing suites to extend

- `backend/test_monitoring_service.py`
- `backend/test_v2_postgres_integration.py`
- `backend/test_v2_foundation.py`
- `backend/test_evaluation_service.py`
- `backend/test_v2_agent_workflows.py`
- Relevant current route/retirement tests, including
  `backend/test_v201_feature_retirement.py`

---

## 13. Queries considered but rejected

### Project Knowledge full-text search

The realistic document-scoped hit measured 2.580 ms at the database and 9.441
ms at the application level. The no-hit fallback measured 0.063 ms at the
database and 12.436 ms at the application level. A global, unscoped 50,000
chunk stress query reached about 138.806 ms, but that is not the current route:
the product always supplies a document and currently bounds its size.

No Project Knowledge query or index change is justified by current behavior.

### Resume Library and Primary Resume

An exaggerated 400-resume list measured 0.327 ms in PostgreSQL and 9.290 ms at
the application level. The Primary Resume query measured 0.012 ms; its
two-query service path measured 2.817 ms. These are current product paths, but
they do not exhibit a material performance problem.

Selecting fewer fields for version lists could reduce large text/JSON
materialization, but expected list cardinality is small and the measured case
does not compete with the selected candidates.

### Evaluation

An exaggerated list at offset 8,000 measured 2.460 ms in PostgreSQL and 8.728
ms at the application level. It is operational, lower frequency, and already
fast enough for this discovery phase.

### Read-only Agent Runs

Run list, detail, and event timeline were all fast. The events query is already
aligned with `(run_id, id)` and uses an `after_id` cursor. The redundant
owned-run detail check is a minor fixed-query inefficiency, not an N+1
problem. This retained infrastructure is lower priority than current
user-facing and monitoring paths.

### Monitoring trace list

The exaggerated offset-10,000 trace list measured 13.028 ms in PostgreSQL and
31.464 ms at the application level. This is acceptable relative to the
aggregate endpoints.

### History detail

The primary-key detail lookup measured 0.013 ms and requires no optimization.

### History wildcard search

Wildcard search is measurable: 41.482 ms with 49,800 rows removed by filter,
and the estimate of 7 rows was below the actual 200. A `pg_trgm` extension and
GIN/GiST trigram indexes could help at larger scale, but they add extension
management, storage, and write costs. Search frequency and production
selectivity are unknown. It remains a good later candidate after telemetry,
not one of the smallest justified first changes.

### Deep `OFFSET` pagination

Deep History offset produces linear work and temporary I/O, but the current
frontend requests only `offset=0`. A keyset contract is valuable if external
or future clients use deep pages. It is intentionally separated from the
initial composite-index recommendation.

### `analysis_metrics.application_id` foreign-key lookup

The read-only proxy scan took 23.444 ms across 100,000 rows and removed 99,999
rows. An index may be justified if History deletion or related joins are
frequent. The exact mutation was not executed in this audit, and there is not
enough evidence to rank it above the selected candidates.

### Duplicate index removal

Several single-column indexes appear redundant with composite-index prefixes.
Removal could reduce storage and write amplification, but production usage
statistics were deliberately not accessed. No index removal is recommended
from schema inspection alone.

---

## 14. Confirmation that production was untouched

Production was not contacted or benchmarked.

- No production hostname, database, credentials, data, logs, or volumes were
  accessed.
- No production query was executed.
- No production index, constraint, migration, row, configuration, or
  deployment resource was changed.
- The benchmark ran only in a temporary PostgreSQL 16.14 instance bound to
  `127.0.0.1:55432`.
- The fixture contained only deterministic synthetic data.
- The temporary PostgreSQL process was stopped after measurement.
- Its temporary directory was moved to the desktop trash through a
  recoverable operation when direct recursive deletion was rejected by the
  execution guard.

---

## 15. Confirmation of repository modifications and stopping point

At completion of the discovery audit, the repository was still clean:

```text
## main...origin/main
```

The audit itself made no application-code, migration, index, test, runtime,
Docker, deployment, or data change. No commit or pull request was created as
part of the audit.

The later publication request authorized adding this English report. Therefore
this Markdown document is the sole repository content added for publication;
it does not implement any recommendation.

The recommended next implementation phase, only after explicit approval, is:

1. Add parity and performance-plan tests for Monitoring aggregation.
2. Replace full-row Monitoring loads with PostgreSQL aggregates.
3. Add and benchmark the History owner/order composite index through a new
   migration.
4. Re-run the same deterministic benchmark and compare median plans and
   application timings.
5. Evaluate cursor pagination, trigram search, foreign-key indexing, and
   duplicate-index removal only as separate evidence-driven follow-ups.

This report stops at discovery, measurement, and proposal. No SQL
optimization has been implemented.
