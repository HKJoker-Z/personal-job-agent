# Version 2 Roadmap

The formal release is `v2.0.0`. The numbered Version 2.0.x entries below were development milestones, not separate production releases or stable Git tags.

| Milestone | Scope | Runtime marker | Status |
| --- | --- | --- | --- |
| Version 2.0.1 | Identity, PostgreSQL, Career Profile, Resume foundation | `2.0.0-alpha.1` | Included in Alpha 2 |
| Version 2.0.2 | Job Library, Application Pipeline, Tasks, Dashboard | `2.0.0-alpha.2` | Published as `v2.0.0-alpha.2`; not deployed |
| Version 2.0.3 | Explainable Matching, Ranking, Application Materials | `2.0.0-alpha.3` | Published prerelease; not deployed |
| Version 2.0.4 | Reliable Agent workflows and final v2 production readiness | `2.0.0` | Included in formal `v2.0.0` |

PR #6 and PR #7 were merged in dependency order before `v2.0.0-alpha.2` was tagged. Alpha 2 is a GitHub prerelease and GHCR image set, not a production deployment.

Version 2.0.4 is the final feature foundation included in formal `v2.0.0`. It adds Redis/Dramatiq, a Transactional Outbox, durable Runs/Steps/Events, retry/cancellation/resume, approvals, SSE, budgets, concurrency controls, heartbeat/Dead Letter recovery, a 20-step asynchronous Application Package workflow, hardened production Compose, and backup/restore validation. The formal release does not deploy production, submit applications, or send email.

Interview Center, Mock Interview, the formal STAR Story module, automatic applications, automatic email, browser extensions, and multi-model intelligent routing are deferred to Version 2.1.x.
