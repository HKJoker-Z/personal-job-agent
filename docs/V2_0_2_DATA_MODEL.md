# Version 2.0.2 Data Model

Revision `20260713_02` adds ten tables after Version 2.0.1 head `20260712_01`.

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `jobs` | Owned normalized Job record | non-negative salary, bounded description/URL, active per-user dedup key, revision, soft archive |
| `job_sources` | Manual/URL/PDF/DOCX/CSV/migrated provenance | owner and Job indexes; no credentials or response headers |
| `job_requirements` | Evidence-bound structured requirements | confidence 0–1, valid enums/spans, review state |
| `job_duplicate_candidates` | Canonical exact/near pair | distinct Jobs, one ordered pair, score 0–1, explicit resolution |
| `applications` | Owned Job Pipeline record | one active Application per owner/Job, revision, soft archive, owned Resume Version |
| `application_stage_history` | Append-only transition ledger | no update/delete through ORM; before/after revisions |
| `application_notes` | Private Application Notes | plain text, revision, soft delete |
| `application_tasks` | User-confirmed Tasks | owned optional Job/Application, due/reminder/completion state, revision, soft archive |
| `job_import_runs` | Safe import counts and status | counts and bounded error summary only; never source bodies |
| `job_merge_history` | Merge selection and safe summary | target/source retained; user and timestamp audit |

All business tables carry an indexed ownership column. Common stage, status, due date, deadline, normalized name, source type, and archive filters are indexed. PostgreSQL and SQLite use partial unique indexes for active Job deduplication and active Application uniqueness; the service layer also enforces these rules.

Dates use timezone-aware UTC values. JSON columns use SQLAlchemy's cross-database JSON type. Upgrade creates only the new tables; downgrade removes only those tables and leaves the Version 2.0.1 foundation intact.

Foreign keys restrict deletion where history or private files must survive. Job archive, Application archive, Note deletion, and Task deletion are non-destructive. Stage History and Job Merge History are retained.
