# Java normalization Phase IIIB candidate

This directory defines a disposable, containerized validation environment for
the merged FastAPI-to-Java normalization integration. It is test infrastructure
only. It does not deploy, inspect, restart, migrate, or otherwise access the
Personal Job Agent production environment.

## Architecture and isolation

The candidate uses five services:

- PostgreSQL 16 with a candidate-only database and volume;
- a one-shot Personal Job Agent Alembic migration service;
- the FastAPI backend built from the checked-out source;
- the real Java application in the `normalization-only` profile; and
- a candidate-only deterministic fault stub for bounded Java failure cases.

The backend uses the repository's test-only mock provider. No DeepSeek or other
external LLM endpoint is configured or called. Redis, Worker, frontend, Nginx,
and production Compose services are not needed by the synchronous Analyze path
and are deliberately absent.

Each run creates a random Compose project name under the
`pja-java-candidate-*` namespace. PostgreSQL, Java, migration, and fault-stub
services have no host port. The backend is the only published service and binds
to a randomly selected `127.0.0.1` port. The data network is internal. Java has
no host proxy inheritance and is reachable only through that network.

## Secrets

Run `./generate-secrets.sh` only through the runner below. It creates
`.env.candidate` and `.candidate-secrets/` with cryptographically random,
candidate-only values and does not print them. Those paths are ignored by Git
and removed by the runner's scoped cleanup trap. The committed
`.env.compose.example` contains placeholders only.

Do not copy production environment files, credentials, user data, or Docker
network names into this directory.

## Run the complete candidate

Prerequisites are Docker Engine, Docker Compose v2, Bash, curl, Python 3, and
OpenSSL. From the repository root run:

```bash
ops/candidate/java-normalization/run-candidate.sh --ephemeral
```

The exact `--ephemeral` flag is mandatory because successful and failed runs
remove their uniquely named candidate containers, networks, volume, generated
environment file, and key file. Cleanup never uses Docker prune and refuses a
project name outside the candidate namespace.

The runner builds images locally; it does not log into a registry or publish an
image. `CANDIDATE_SKIP_BUILD=1` is reserved for local script development after
the exact current-revision images already exist.

## Validation cases

The runner uses only synthetic account, Resume, Project Knowledge, Job
Description, Request ID, and Idempotency-Key values. Its JD fixture contains a
decomposed Unicode character that the existing local path preserves and the
real Java policy deterministically NFC-normalizes. Evidence records contain
only bounded identities, counters, categories, and booleans; raw Resume/JD text,
fingerprint bytes, response bodies, and secrets are excluded.

The single run validates:

- fresh migration to the single `20260730_07` head and a no-op second upgrade;
- local, deterministic shadow, and Java-authoritative modes;
- binding before provider work using a paused mock-provider barrier;
- exact effective-input identity through RAG, prompt, mock provider, result,
  and History;
- Java unavailable, timeout, malformed response, unsupported version,
  Request-ID mismatch, and authoritative second-scan fallback;
- first-scan blocking before Java;
- completed replay across Java-to-local and local-to-Java mode changes;
- a safe synthetic execution-conflict fixture;
- Java, FastAPI, and PostgreSQL restart/persistence behavior;
- configuration-only rollback to local with no schema downgrade;
- host-port, health, restart, OOM, resource, and bounded log checks; and
- 20 sequential synthetic Java-mode observations, not a load or stress test.

`.candidate-results/summary.json` and `resources.json` are ignored local
evidence. Durations and resource snapshots are candidate observations only;
they are not production measurements, performance claims, or an SLA.

## Mode switching and rollback

The runner recreates only its candidate backend with
`ANALYSIS_JD_NORMALIZATION_MODE` set to `local`, `shadow`, or `java`. Shadow
sampling is fixed at `1` for deterministic candidate coverage. Its final
rollback sets the backend to `local`, confirms new requests work, replays an
existing Java-completed result, leaves the schema at `20260730_07`, and then
stops Java independently. No image rebuild or database downgrade is used.

For manual Compose inspection, first generate candidate secrets and always pass
an explicit unique project name, Compose file, and environment file. Prefer the
runner because it enforces bounded waits, assertions, sanitization, and scoped
cleanup.

## Safety and limitations

- Never attach this Compose file to `pja-br0`, production networks, production
  volumes, the Docker socket, or arbitrary host directories.
- Never point its database URL at production.
- Never replace the mock-provider setting with a real provider credential.
- Never use its synthetic latency or resource data as a production claim.
- The candidate is single-host and sequential; it does not prove high
  availability, production capacity, or exactly-once external provider
  execution.
- Phase IIIB supplies validation evidence only. Controlled production rollout
  design remains separate and production rollout has not occurred.
