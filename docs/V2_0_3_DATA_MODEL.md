# Version 2.0.3 Data Model

Alembic revision `20260721_05` follows `20260717_04`. It makes one minimal product-schema change:

| Table | Change |
| --- | --- |
| `resumes` | Add non-null Boolean `is_primary`, default false |

Migration upgrade behavior:

- backfills the newest active Resume as primary for each user who has one;
- adds partial unique index `uq_resumes_user_primary_active` on `owner_user_id` where the Resume is primary and not archived;
- preserves every Resume, Resume Version, and File Asset row.

Application transactions clear the old primary before assigning the new one. Upload extraction and validation happen before this transaction, so a failed upload cannot alter the current primary. Archiving the primary assigns the newest remaining active Resume or leaves the user with no primary.

No new table is introduced. Analysis status and warnings use the existing History `notes` storage as a private prefixed metadata object, so complete, repaired, partial, and fallback results can be saved without another schema change. Ordinary History notes remain compatible.

Downgrade removes only the primary index and column; it does not remove Resume records or files.
