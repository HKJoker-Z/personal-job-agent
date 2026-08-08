# Version 2.0.6 production readiness

Version 2.0.6 is production-ready only after the immutable-image, preflight,
cutover, health, rollback, tag, release, Project Knowledge, and final-report
gates in [Deployment](DEPLOYMENT.md) pass.

Application acceptance covers the private stateless Java normalization-only
service; FastAPI-to-Java private integration; `local`, deterministic `shadow`,
and authoritative `java` modes; stable request fingerprint and completed replay;
the `analyze-execution-v1` binding before Provider work; authoritative second
security scan; and safe `fallback_local` containment.

Infrastructure acceptance requires PostgreSQL 16 at Alembic `20260730_07`, mode
`java`, reviewed immutable application digests, the unchanged immutable Java
digest, healthy services, zero restarts/OOM, sufficient host resources, only the
established Edge public port, and private Java networking. Release validation
must not generate Analyze traffic, inspect user content, call an external LLM,
or add/run a migration.

The prepared source includes the validated Provider deadline enforcement. The
synchronous Analyze path has a 130-second
monotonic Provider deadline, a 30-second fallback/finalization reserve, and a
175-second application safety deadline inside the unchanged 180-second client
bound. Primary and repair calls derive their connect/read/write/pool timeout
components from the remaining absolute deadline; SDK retries remain disabled,
application retry/repair counts remain unchanged, and the response-body stream
is subject to the same total deadline. Candidate validation must confirm that
deadline exhaustion selects the deterministic `fallback` state, finalizes
History/idempotency at most once, and leaves no Provider operation active past
the deadline.

Stop promotion on any failed required check, unexpected version/schema/mode,
floating deployment reference, image/source-label mismatch, unhealthy service,
restart/OOM event, exposed Java port, secret finding, topology drift, or loss of
rollback readiness.

Operator rollback is to restore the Version 2.0.5 application image and
compose/configuration revision. No Java source,
Java policy/dictionary, Alembic revision, or database downgrade is part of the
change.
