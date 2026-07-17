# Version 2.0.3 Data Model

Alembic revision `20260713_03` follows `20260713_02`; the earlier migrations are unchanged. It adds ten tables:

| Table | Purpose |
| --- | --- |
| `job_match_analyses` | Immutable scoring input/output snapshot with Profile/Job/Resume revisions and weight config |
| `job_match_dimensions` | Eight deterministic dimension results |
| `job_match_evidence` | Source IDs/revisions, match kind, confidence, and contribution |
| `job_rank_runs` | Reproducible ranking configuration |
| `job_rank_items` | Ordered Job/Analysis rows and factor contributions |
| `application_packages` | Application-scoped source snapshot and review status |
| `application_materials` | Logical Resume, letter, answer, and future message resources |
| `application_material_versions` | Immutable content lineage, provider metadata, validation state, and finalization time |
| `material_evidence_links` | Hashed claim-to-source support result |
| `material_reviews` | Private append-only review decisions |

Ownership columns and common foreign keys/filter columns are indexed. Check constraints limit scores, confidence, coverage, status enums, and version numbers. PostgreSQL has a partial unique index permitting only one approved Package per Application. SQLite tests enforce the equivalent service rule.

An Analysis is never overwritten when its Profile or Job changes. A Rank Item references the exact Analysis used. A Package captures Profile revision, Job revision, finalized source Resume Version, and Match Analysis. A Material Version never contains a copied full Profile or Job Description; evidence remains linked by source ID/revision and a safe summary.

Downgrade removes only these Alpha 3 tables and indexes, returning to `20260713_02`. Fresh upgrade, Alpha 2 upgrade, downgrade, and re-upgrade are all integration-tested on PostgreSQL.
