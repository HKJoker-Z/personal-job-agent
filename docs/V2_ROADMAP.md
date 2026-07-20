# Version 2 roadmap status

## Current release: 2.0.1

Version 2.0.1 is a patch release focused on safe usability and operational correctness:

- bounded Remember Me and email-only persistence
- one responsive authenticated navigation
- direct Resume-to-JD Analyze flow
- retirement of Jobs, Job Rankings, Applications, Approvals, and Tasks without deleting data
- verified Project Knowledge updated for the PostgreSQL/Redis/Dramatiq production stack
- actual Project Knowledge retrieval, prompt evidence, source reporting, and skill reconciliation
- formal Redis-init, Nginx tmpfs, Docker alias, health-version, and rollback deployment fixes

## Retained foundations

Profile, Resume Versions, History, Project Knowledge, Monitoring/Evaluation, PostgreSQL, Redis, Dramatiq, Transactional Outbox, SSE, backup/restore, and historical Agent Runs remain supported. Retired-feature tables remain compatible for rollback.

## Historical documents

The `V2_0_2`, `V2_0_3`, and `V2_0_4` architecture/API/test documents record how Version 2.0.0 was built. They do not define the Version 2.0.1 public product surface. Public retirement behavior is defined by the 2.0.1 release notes and tests.

## Future work

Future work is deliberately uncommitted. Version 2.0.1 does not implement Version 2.1 capabilities, automatic job application, a browser extension, an interview platform, or high-availability orchestration.
