# Version 2 Roadmap

The final formal release remains planned as `v2.0.0`. The numbered Version 2.0.x entries below are development milestones, not production releases or Git tags.

| Milestone | Scope | Runtime marker | Status |
| --- | --- | --- | --- |
| Version 2.0.1 | Identity, PostgreSQL, Career Profile, Resume foundation | `2.0.0-alpha.1` | Included in Alpha 2 |
| Version 2.0.2 | Job Library, Application Pipeline, Tasks, Dashboard | `2.0.0-alpha.2` | Published as `v2.0.0-alpha.2`; not deployed |
| Version 2.0.3 | Explainable Matching, Ranking, Application Materials | `2.0.0-alpha.3` | In development; PR only |
| Version 2.0.4 | Workers and agent workflows | Planned | Not started |
| Version 2.0.5 | Interview and feedback | Planned | Not started |
| Version 2.0.6 | Production hardening and release preparation | Planned | Not started |

PR #6 and PR #7 were merged in dependency order before `v2.0.0-alpha.2` was tagged. Alpha 2 is a GitHub prerelease and GHCR image set, not a production deployment.

Version 2.0.3 deliberately has no Worker, queue, scheduler, streaming, automatic application, email sender, interview center, production migration, deployment, Alpha 3 tag, release, or image publication. Its scoring is deterministic and explainable, not an Offer probability; LLMs cannot set numeric scores.
