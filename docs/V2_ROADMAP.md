# Version 2 roadmap status

## Current release: 2.0.5

Version 2.0.5 is the stable production release. It retains the Version 2.0.4
reliability and portfolio architecture work and adds the reviewed private,
stateless Java normalization-only integration with explicit local, Shadow, and
Java-authoritative modes. Production uses Java mode with safe local fallback;
the application schema remains `20260730_07`.

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
scope is defined by the Version 2.0.1 through 2.0.5 release notes plus the
current code and retirement tests.

## Future work

Reasonable future work includes retrieval precision, claim-to-evidence links,
optional OCR after security review, accessibility, operator observability, and
safer deployment switching. These are not implemented commitments. Version
2.0.5 does not include automatic application submission, a browser extension,
an interview platform, Kubernetes, or high availability.
