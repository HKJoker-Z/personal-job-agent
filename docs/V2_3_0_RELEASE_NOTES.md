# Version 2.3.0

## Applications editing

- Company and Position can now be edited from the Applications page.
- Editing remains restricted to these two user-facing fields.
- Updates persist immediately and preserve existing application data.
- Existing revision conflict protection remains active.

## Operations

- Production release disk preflight threshold adjusted from 6 GiB to 5 GiB
  (5,368,709,120 bytes).
- No database migration; Alembic remains 20260820_08.
- No new dependency.
