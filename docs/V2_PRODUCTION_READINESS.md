# Version 2.0.4 production readiness

Version 2.0.4 is ready for production only after the release, immutable-image,
backup/restore, migration, one-candidate, Project Knowledge, cutover, cleanup,
and rollback gates in [Deployment](DEPLOYMENT.md) pass.

Application acceptance covers the English Architecture page and ADRs, fictional
three-minute demo assets, Request ID correlation, the stable four-field Analyze
error contract, PostgreSQL-backed keyed Analyze replay/conflict/concurrency,
atomic History completion, fallback replay, and the optimized PostgreSQL
Monitoring aggregation.

Infrastructure acceptance requires PostgreSQL 16 at Alembic `20260724_06`,
healthy Redis/Worker/Outbox, exact component digests, stable restart counts,
HTTPS, only public Edge 8080, and preservation of `pja-br0`, routing preference
8999, Mihomo, TLS, persistent volumes, and Version 2.0.3 rollback assets.

Stop promotion on any failed required check, manifest/checksum or restored-data
mismatch, unexpected Project Knowledge diff, real-provider access, floating
image, version instability, duplicate History, unhealthy dependency, restart,
public private-service port, or inability to restore Version 2.0.3.
