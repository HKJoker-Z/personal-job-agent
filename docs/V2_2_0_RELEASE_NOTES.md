# Version 2.2.0 release notes

Version 2.2.0 is a focused Applications improvement release from the Version
2.1.0 production baseline. Alembic remains `20260820_08`; there is no migration.

## Changes

- Add owned `DELETE /api/applications/{id}` with physical database deletion.
- Add a confirmation naming the Company and Job Title, followed by list refresh
  and a concise success message.
- Preserve source Analysis/History, Resume, Resume Version, and all other
  Applications when an Application is deleted.
- Display saved plain-text Resume snapshots with preserved line breaks,
  paragraphs, readable line height and width, and safe long-line wrapping.
- Align Applications header padding with the main cards across mobile, tablet,
  and desktop layouts.

## Validation and rollback

Release gates include full backend/frontend tests, production frontend build,
Docker and Compose validation, real PostgreSQL 16 DELETE preservation coverage,
strict backup/restore rehearsal, isolated candidate smoke, health/readiness,
and immutable image verification. Existing npm advisories are not changed by
this release and are assessed separately without an automatic dependency fix.

Rollback restores the recorded immutable Version 2.1.0 application images and
configuration. PostgreSQL, Redis, Java, files, Project Knowledge, and Alembic
`20260820_08` remain in place; database restore is a separate approved incident
action using the verified pre-release backup.
