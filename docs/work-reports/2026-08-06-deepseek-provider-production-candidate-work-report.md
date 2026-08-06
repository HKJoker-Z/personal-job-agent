# DeepSeek Provider Production Candidate Rollout Work Report

Date: 2026-08-06
Repository: HKJoker-Z/personal-job-agent
Decision: NO-GO. Production was not modified.

## 1. Repository and delivery baseline

PR #53 final head:
5b14585679ea063d702a36bdca7ed4586215b4aa.

PR #53 normal merge commit:
bb9f4141300b76f2e00b3729e8fc5e490cae681f.

Production source commit before this rollout attempt:
bb9f4141300b76f2e00b3729e8fc5e490cae681f.

The final PR #53 checks passed, the PR was CLEAN and MERGEABLE, and post-merge
main CI passed. Local main matched origin/main before the production
preflight.

## 2. Scope and exclusions

This phase performed the authorized pre-deployment inspection and rollback
baseline capture for the Provider Acceptance Hardening candidate. It did not
build or publish images, modify production configuration, recreate production
containers, call production /api/analyze, or inspect production content.

No production Resume, JD, Prompt, Project Knowledge, Provider response,
reasoning_content, History body, Request ID, user identifier, Session, Cookie,
API key, Authorization header, or arbitrary exception string was inspected or
stored.

No migration, Java source/configuration/image/policy/dictionary change,
version bump, tag, Release, image publication, deployment, or rollback was
performed.

## 3. Production rollback baseline

The authorized production Docker host was identified only as a local
production Docker host. The production Compose project is
personal-job-agent-v2, with working directory `/opt/personal-job-agent-v2`.
The observed Compose configuration revision was:

`89322817c9b20557631bd4075b32ed44ac44dd6dec7d4ea753ecb9102dfe81f1`.

The production environment file mode was 0600. Its values were not printed.

Previous production application image digests:

| Service group | Immutable image digest |
|---|---|
| Backend, Worker, Outbox | `ghcr.io/hkjoker-z/personal-job-agent-backend@sha256:79fac56ae0884cc5362356c2d3d3f981e681286e9214faea4b4a4c1d03255b57` |
| Frontend and Edge | `ghcr.io/hkjoker-z/personal-job-agent-frontend@sha256:325bae0c95b8f571e6d1a5a64dff4ae3012ff71c929c15e7c47aebe4652c0996` |
| Java normalization | `ghcr.io/hkjoker-z/personal-job-agent-java-normalization@sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f` |

The existing Compose configuration files were:

- `/opt/personal-job-agent-v2/compose.yaml`;
- `/opt/personal-job-agent-v2/compose.redis-init-idempotent.override.yaml`;
- `/opt/personal-job-agent-v2/compose.edge-tmpfs-idempotent.override.yaml`;
- `/opt/personal-job-agent-v2/compose.v2-network-aliases.override.yaml`;
- `/opt/personal-job-agent-v2/compose.edge-trusted-https.override.yaml`;
- `/opt/personal-job-agent-v2/compose.edge-cutover-8080.override.yaml`;
- `/opt/personal-job-agent-v2/compose.java-normalization-stage-2.override.yaml`;
- `/opt/personal-job-agent-v2/compose.java-normalization-stage-3-shadow.override.yaml`;
- `/opt/personal-job-agent-v2/compose.java-normalization-stage-4-java.override.yaml`.

Rollback readiness was preserved with the previous image references and
configuration revision. No rollback was needed. If a later deployment had
been attempted, the exact application restore sequence would be:

```sh
cd /opt/personal-job-agent-v2
export BACKEND_IMAGE=ghcr.io/hkjoker-z/personal-job-agent-backend@sha256:79fac56ae0884cc5362356c2d3d3f981e681286e9214faea4b4a4c1d03255b57
export FRONTEND_IMAGE=ghcr.io/hkjoker-z/personal-job-agent-frontend@sha256:325bae0c95b8f571e6d1a5a64dff4ae3012ff71c929c15e7c47aebe4652c0996
export RELEASE_VERSION=2.0.5
docker compose --project-name personal-job-agent-v2 \
  --env-file /etc/personal-job-agent-v2/production.env \
  -f compose.yaml \
  -f compose.redis-init-idempotent.override.yaml \
  -f compose.edge-tmpfs-idempotent.override.yaml \
  -f compose.v2-network-aliases.override.yaml \
  -f compose.edge-trusted-https.override.yaml \
  -f compose.edge-cutover-8080.override.yaml \
  -f compose.java-normalization-stage-2.override.yaml \
  -f compose.java-normalization-stage-3-shadow.override.yaml \
  -f compose.java-normalization-stage-4-java.override.yaml \
  up -d --no-build --pull never worker outbox-dispatcher backend frontend
```

The restore health checks are bounded and content-free:

```sh
docker inspect --format '{{.State.Health.Status}} {{.RestartCount}} {{.State.OOMKilled}}' \
  personal-job-agent-v2-backend-1 personal-job-agent-v2-worker-1 \
  personal-job-agent-v2-outbox-dispatcher-1 personal-job-agent-v2-frontend-1
curl --insecure --fail --silent --output /dev/null https://127.0.0.1:8080/healthz
docker exec personal-job-agent-v2-backend-1 alembic current
docker exec pja-java-normalization-java-normalization-1 sh -c \
  'curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8080/actuator/health/readiness >/dev/null'
```

## 4. Production health and baseline state

Before the stop decision, Backend, Worker, Outbox, Frontend, Java, PostgreSQL,
Redis, and Edge/Nginx were running and healthy. All observed restart counts
were zero and all observed OOM flags were false.

Safe health results:

- Backend readiness: ready, Version 2.0.5;
- Frontend/Edge HTTPS health: HTTP 200;
- Java readiness: pass;
- Alembic current: 20260730_07;
- Alembic head: 20260730_07;
- Backend normalization mode: java;
- Java policy: jd-normalization-v1;
- skill dictionary: skills-v1;
- public Edge binding: unchanged at the existing HTTPS service;
- Java host port: none.

Available memory was 2,307,534,848 bytes. Docker/root disk available space
was 5,151,522,816 bytes, with 88% capacity used. The established production
preflight requirement is at least 6 GiB available to retain old and new
images. The observed capacity is approximately 4.80 GiB and fails that gate.
No cleanup or deletion was performed to force the gate.

## 5. Network path and proxy decision

The production Backend process had these safe proxy-presence results:

| Variable | Backend process |
|---|---|
| HTTP_PROXY | absent |
| HTTPS_PROXY | absent |
| ALL_PROXY | absent |
| NO_PROXY | absent |

No proxy values or credentials were printed. Because the Backend did not
inherit the unsupported SOCKS ALL_PROXY and the direct origin path was
available, no production proxy or Java/Nginx network change was made.

Unauthenticated, no-key preflight to the configured origin
`https://api.deepseek.com` passed:

- DNS resolution: pass;
- direct TCP/TLS: pass, TLS 1.3;
- unauthenticated HTTPS: reached the origin and returned HTTP 401, as
  expected without an API key.

The preflight did not send the API key.

## 6. Provider configuration gate

The validated candidate configuration remains:

- model: deepseek-v4-pro;
- response mode: json_object;
- thinking: disabled;
- primary output tokens: 1600;
- length-retry output tokens: 2400;
- format-repair output tokens: 1000;
- application token maximum: 5000;
- SDK automatic retries: zero;
- one primary retry maximum;
- one format-only repair maximum;
- three Provider calls maximum.

The running pre-hardening production Backend exposed the old primary token
configuration category `800`, and the hardening-specific model, thinking,
length-retry, repair, deadline, and backoff fields were not present in that
old container. This was expected before rollout and confirms that a candidate
configuration change would have been required. The disk gate stopped the
rollout before any configuration edit or container replacement.

The production secret was present for the running Backend and was not printed.
No candidate model, alias, token limit, timeout, or retry value was silently
substituted.

## 7. Candidate image and deployment status

The disk prerequisite failed before image build and publication. Therefore:

- candidate image tag: not created;
- candidate Backend image digest: not built or published;
- candidate Frontend image digest: not built or published;
- Worker and Outbox candidate image: not built or published;
- Java image: unchanged and not rebuilt;
- deployment sequence: not started;
- post-deployment health: not applicable;
- production candidate Analyze executions: 0;
- production History or Provider side effects: 0.

No public candidate service was exposed.

## 8. Production gate decision

Decision: NO-GO.

The exact blocking prerequisite is insufficient Docker/root capacity: only
5,151,522,816 bytes were available versus the established 6 GiB minimum
required before retaining the previous and candidate application images.
Deploying would violate the rollback and capacity safety gate. No production
Analyze cohort was generated, so no user-content or synthetic production
content was used.

Because deployment did not start, there are no production complete, repaired,
partial, fallback, retry, repair, token, Provider-latency, end-to-end-latency,
Job Summary, Match Reasons, security, serialization, idempotency, or History
cohort results to report.

## 9. Regression and safety checks

Completed checks applicable before the stop:

- PR #53 final-head checks: passed;
- PR #53 post-merge main CI: passed;
- source main matched origin/main: passed;
- current production Backend readiness: passed;
- current Java readiness: passed;
- current PostgreSQL and Redis health: passed;
- current Edge/Nginx HTTPS health: passed;
- Alembic current/head equality: passed;
- direct DeepSeek DNS/TLS/unauthenticated HTTPS preflight: passed;
- proxy presence inspection: passed without value disclosure;
- rollback image digest capture: passed;
- no production content inspection: passed by procedure.

No destructive database test, load test, stress test, production Analyze
request, migration command, or external LLM call was made.

## 10. Commits and report pull request

Production source commit: bb9f4141300b76f2e00b3729e8fc5e490cae681f.

This report branch is `ops/deepseek-provider-production-candidate`.

Report PR URL will be finalized after the documentation-only PR is opened.
The required PR title is:

`Ops: Record DeepSeek provider production candidate`

## 11. Exact next prerequisite

Free or expand Docker/root capacity without deleting production data or
changing the approved service topology, then repeat the pre-deployment disk
gate and confirm at least 6 GiB is available while retaining the recorded
previous images. Re-run the complete preflight, verify the exact validated
Provider configuration can be applied without changing Java or migrations,
then build/publish immutable candidate Backend and Frontend images from the
same merged source commit. Do not resume deployment from this blocked run or
generate production Analyze traffic until all prerequisites pass.

## 12. Risks and negative effects

The rollout was not attempted, so there was no production latency, token,
Provider acceptance, restart, schema, or user-impact evidence. Releasing
capacity by deleting images, volumes, backups, or other runtime data would
weaken rollback and was intentionally not performed. The old production
configuration remains active, including its pre-hardening Provider token
budget category, until a separately approved and capacity-safe rollout.

## 13. Required confirmations

- No migration was added, edited, run, stamped, downgraded, or otherwise
  applied.
- Java source, configuration, image, policy, and dictionary were unchanged.
- No production content was inspected or printed.
- No production /api/analyze call was made.
- No candidate image was built or published.
- No deployment or rollback occurred.
- No application version bump occurred; production remains v2.0.5.
- No tag or GitHub Release was created.
- No external LLM was called in this production-candidate phase.
