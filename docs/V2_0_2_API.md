# Version 2.0.2 API

All endpoints below require an authenticated Session. Mutations require a trusted Origin and current CSRF token. Owned resources return a safe 404 for cross-user identifiers. Stale revisions and invalid business transitions return 409.

## Jobs and import

```text
GET/POST              /api/jobs
GET/PATCH/DELETE      /api/jobs/{job_id}
POST                  /api/jobs/{job_id}/archive|restore
POST                  /api/jobs/import/manual|url|file|csv
GET                   /api/jobs/import/csv/template
GET                   /api/jobs/{job_id}/sources|requirements|duplicates
POST/PATCH/DELETE      /api/jobs/{job_id}/requirements[/{requirement_id}]
POST                  /api/jobs/{job_id}/extract-requirements
POST                  /api/jobs/{job_id}/duplicates/{candidate_id}/resolve
POST                  /api/jobs/{target_job_id}/merge
```

Job lists support offset/limit, query, company, title, location, status, employment type, work mode, source type, creation/deadline ranges, archive state, and an allowlisted sort. List items omit the full description.

## Applications and Notes

```text
GET/POST              /api/applications
GET/PATCH/DELETE      /api/applications/{id}
POST                  /api/applications/{id}/archive|restore|transition|reopen|resume
GET                   /api/applications/{id}/history|notes|suggested-tasks
POST                  /api/applications/{id}/notes
PATCH/DELETE          /api/applications/{id}/notes/{note_id}
```

`current_stage` is forbidden in PATCH. Transition and reopen use explicit endpoints. The overlapping legacy path dispatches integer IDs and legacy list queries to Version 1 behavior while UUID IDs and Pipeline list requests use Version 2.

## Tasks and Dashboard

```text
GET/POST              /api/tasks
GET/PATCH/DELETE      /api/tasks/{id}
POST                  /api/tasks/{id}/complete|reopen|archive
GET                   /api/dashboard/summary
```

Dashboard statistics are real owner-scoped SQL aggregates: Job totals, stage groups, active Applications, pending/overdue/next-seven-day Tasks, deadlines, recent safe audit activity, and recent import counts. It returns no fabricated score, prediction, or LLM result.

Analyze accepts an optional owned `job_id` alongside the existing Resume source. Exactly one of `job_id`, raw Job Description, or Job URL is allowed. It does not create a matching record or automatically Analyze an imported Job.
