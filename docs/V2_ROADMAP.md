# Version 2 roadmap status

## Current release candidate: 2.1.0

Version 2.1.0 is the prepared release candidate; public production remains
Version 2.0.7 until deployment. It retains the private, stateless Java
normalization-only integration and bounded synchronous Analyze behavior, and
adds the focused Applications submission-record workflow. The target schema is
`20260820_08`.

Current product scope is Dashboard, Analyze, Applications, Profile, Resume
Library/Versions, History, Project Knowledge RAG, historical Agent Runs,
administrator Monitoring/Evaluation, and Account controls. Jobs, Job Rankings,
Approvals, and Tasks remain removed or disabled from the public workflow.

## Retained foundations

PostgreSQL 16, Redis, Dramatiq, Transactional Outbox, authenticated SSE,
server-side Sessions, backup/restore, immutable GHCR images, HTTPS Nginx Edge,
and rollback assets remain supported. Retired-feature tables remain only for
compatibility, recovery, and rollback.

## Historical documents

Files named `V2_0_2_*`, `V2_0_3_*`, and `V2_0_4_*` may describe development
milestones that were later consolidated into Version 2.0.0. Current public
scope is defined by the Version 2.0.1 through 2.1.0 release notes plus the
current code and retirement tests.

## Future work

Reasonable future work includes retrieval precision, claim-to-evidence links,
optional OCR after security review, accessibility, operator observability, and
safer deployment switching. These are not implemented commitments. Version
2.1.0 does not include automatic application submission, a browser extension,
an interview platform, Kubernetes, or high availability.
