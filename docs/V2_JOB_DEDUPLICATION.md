# Version 2 Job Deduplication and Merge

Exact duplicate detection is owner-isolated and considers canonical URL, source plus external reference, description hash, and the deterministic deduplication key. Importing an exact duplicate returns the existing Job and appends a Source instead of creating a second active Job.

Near duplicates are deterministic hints. The algorithm compares normalized company, title, location, description token similarity, URL/hash signals, and explainable reason codes. A configurable safe threshold creates a canonical candidate pair; it never archives, deletes, or merges automatically.

Candidate actions are `confirm_duplicate`, `not_duplicate`, and `dismiss`. Confirmation records the resolver and time but still does not merge.

`POST /api/jobs/{target_job_id}/merge` requires:

- an owned source Job distinct from the target
- expected revisions for both rows
- an explicit per-field target/source selection
- confirmation text `MERGE JOBS`

The transaction locks both Jobs in canonical UUID order. Sources, Requirements, Tasks, and a sole active Application are moved to the target. Notes and Stage History remain attached through the Application. If both Jobs have active Applications, the merge stops for manual resolution. The source is archived, the target remains active, and audit plus merge-history rows retain a safe summary. Neither Job is physically deleted.
