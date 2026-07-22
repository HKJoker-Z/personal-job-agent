# Version 2 roadmap status

## Current release: 2.0.3

Version 2.0.3 is the stable production release. It retains the simplified
Version 2.0.1 workspace and PostgreSQL 16 Backup/Restore gates from Version
2.0.2, then adds resilient DeepSeek parsing/repair/fallback and safe Resume-page
upload with automatic Primary Resume selection.

Current product scope is Dashboard, Analyze, Profile, Resume Library/Versions,
History, Project Knowledge RAG, historical Agent Runs, administrator
Monitoring/Evaluation, and Account controls. Jobs, Job Rankings, Applications,
Approvals, and Tasks remain removed or disabled from the public workflow.

## Retained foundations

PostgreSQL 16, Redis, Dramatiq, Transactional Outbox, authenticated SSE,
server-side Sessions, backup/restore, immutable GHCR images, HTTPS Nginx Edge,
and rollback assets remain supported. Retired-feature tables remain only for
compatibility, recovery, and rollback.

## Historical documents

Files named `V2_0_2_*`, `V2_0_3_*`, and `V2_0_4_*` may describe development
milestones that were later consolidated into Version 2.0.0. Current public
scope is defined by the Version 2.0.1, 2.0.2, and 2.0.3 release notes plus the
current code and retirement tests.

## Future work

Reasonable future work includes retrieval precision, claim-to-evidence links,
optional OCR after security review, accessibility, operator observability, and
safer deployment switching. These are not implemented commitments. Version
2.0.3 does not include automatic application submission, a browser extension,
an interview platform, Kubernetes, or high availability.
