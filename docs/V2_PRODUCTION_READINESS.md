# Version 2.2.0 production readiness

Version 2.2.0 is production-ready only after the immutable-image, preflight,
backup/restore, candidate, health, rollback, tag, release, and final-report
gates in [Deployment](DEPLOYMENT.md) pass.

Application acceptance covers the Version 2.1.0 workflow plus confirmed
physical deletion of an owned Application, preservation of its source
Analysis/History and Resume, an unaffected second Application, ownership and
authentication boundaries, readable unchanged Resume snapshot text, and the
375 px, 768 px, and desktop Applications layouts.

Infrastructure acceptance requires a verified PostgreSQL 16 pre-release backup,
an isolated restore rehearsal, PostgreSQL 16 at unchanged Alembic
`20260820_08`, mode `java`, reviewed immutable application digests, the unchanged
immutable Java digest, healthy services, zero restarts/OOM, sufficient host
resources, only the established Edge public port, and private Java networking.
Release validation must not inspect production user content or call an external
LLM. No migration is part of Version 2.2.0.

The private stateless Java normalization-only service, FastAPI-to-Java boundary,
`local`/`shadow`/`java` modes, execution binding, second security scan, bounded
Provider deadlines, and safe deterministic fallback remain unchanged.

Stop promotion on any failed required check, unexpected version/schema/mode,
floating deployment reference, image/source-label mismatch, unhealthy service,
restart/OOM event, exposed Java port, secret finding, topology drift, failed
PostgreSQL DELETE preservation check, or loss of rollback readiness.

Operator image rollback restores the Version 2.1.0 application images and
configuration while retaining schema `20260820_08`. A database restore is a
separate explicit incident action using the verified pre-release backup. No Java
source or Java policy/dictionary change is part of the release.
