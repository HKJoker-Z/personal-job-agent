# DeepSeek Direct Connectivity Candidate Work Report

Date: 2026-08-07
Decision: **GO_DIRECT**
Production action: none

This is a bounded evidence phase for PR #56. It does not authorize a
production network change, deployment, merge, version bump, image release,
tag, or GitHub Release. All real Provider calls used the approved candidate
secret mechanism, synthetic fixtures, and a disposable Backend container.
Only aggregate metadata is recorded below.

## 1. Repository

Repository: `HKJoker-Z/personal-job-agent`
PR: [#56](https://github.com/HKJoker-Z/personal-job-agent/pull/56)
Branch: `fix/provider-deadline-enforcement`
PR #56 starting head: `9537eb7823dfc3c3e8042680aedb29ac47097a61`
Starting PR state: open, non-draft, mergeable; all required checks at that
head were successful. PR #56 was not merged.

## 2. Production baseline

- Stable production version: `v2.0.5`.
- Alembic current/head: `20260730_07`.
- JD normalization: `java`.
- Java policy: `jd-normalization-v1`.
- Skill dictionary: `skills-v1`.
- Version 2.0.6 remains unreleased.
- Production was not accessed or modified by this phase.

## 3. Scope and exclusions

The phase compared the approved Mihomo HTTP(S) path with selective
`NO_PROXY` and a dedicated direct HTTPX client, from both the candidate host
and a fresh disposable Backend container. It ran one gated ten-case
authenticated cohort through the selected path.

The phase did not modify production environment variables, Compose, routing,
Mihomo, containers, volumes, PostgreSQL, Redis, user data, Java, Alembic,
Provider acceptance behavior, Provider deadlines, retry/repair counts, token
budgets, model, application version, release images, tags, or GitHub Releases.
It did not merge PR #56 or call production `/api/analyze`.

## 4. Installed Provider HTTP client behavior

Installed versions:

- OpenAI-compatible SDK: `openai 2.44.0`.
- HTTP transport: `httpx 0.28.1`.
- Client type: synchronous `OpenAI` client using the repository's
  `DeadlineHttpxClient`, a synchronous `httpx.Client` subclass.
- The normal Provider path is blocking and does not use an async client,
  asyncio timeout, or AnyIO timeout wrapper.
- The deadline client runs the blocking transport operation in a bounded
  daemon worker, closes the client on expiry, and wraps response-body reads
  in a deadline-aware stream.
- SDK automatic retries are `0`; application retry/repair limits are
  unchanged.
- HTTPX default `trust_env` is `true`.
- With the inherited unsupported SOCKS `ALL_PROXY` category present, an
  ordinary HTTPX client cannot construct its SOCKS transport because the
  optional SOCKS dependency is not installed. The existing candidate
  process therefore clears only `ALL_PROXY`/`all_proxy` inside its own
  process before constructing the client. Production environment state was
  not changed.

The current production Provider builder still uses the normal environment
aware client. Path C below patches only the manual candidate runner to use a
dedicated `trust_env=False` client.

## 5. Provider origin and proxy-presence categories

The origin was read from the current candidate source configuration rather
than substituted by the harness. The validated origin category was HTTPS
`api.deepseek.com`, with no query credentials, system DNS resolution, IPv4
availability, no IPv6 result in this environment, CA certificates available,
valid system clock, and TLS verification enabled.

The host process had these presence categories, without recording values:

| Variable category | Present |
|---|---:|
| `HTTP_PROXY` | yes |
| `HTTPS_PROXY` | yes |
| `ALL_PROXY` | yes |
| `NO_PROXY` | yes |
| lowercase `http_proxy` | no |
| lowercase `https_proxy` | no |
| lowercase `all_proxy` | no |
| lowercase `no_proxy` | yes |

The disposable container received the same presence categories for the
unauthenticated comparison. The harness cleared only the unsupported SOCKS
category for the candidate process; it did not print or persist proxy values.

## 6. Paths under test

### Path A — approved proxy

Uses the existing HTTP(S) proxy behavior and the current `NO_PROXY` entries.
The candidate process clears unsupported `ALL_PROXY`/`all_proxy` only because
the installed HTTPX environment parser cannot construct that SOCKS transport.
HTTPX uses `trust_env=True`.

### Path B — selective NO_PROXY

Preserves the HTTP(S) proxy variables and all existing `NO_PROXY` entries,
then appends only `api.deepseek.com` to both `NO_PROXY` and `no_proxy`.
HTTPX uses `trust_env=True`; only the configured DeepSeek hostname bypasses
the proxy.

### Path C — dedicated direct client

Uses a candidate-only `DeadlineHttpxClient` with `trust_env=False` for the
DeepSeek client. It retains the same origin, model, API key mechanism, TLS
verification, monotonic deadline, per-attempt timeout derivation, JSON object
contract, token budgets, retry/repair limits, and maximum three Provider
calls. Other Backend clients and Job URL acquisition are not changed.

## 7. Mihomo usage and bypass proof

For every request the harness inspected the actual HTTPX transport selected
for the DeepSeek URL, rather than relying only on environment variables.
Path A selected the proxy transport on all 20 attempts. Paths B and C
selected the direct/base transport on all 20 attempts.

The host-wide `/proc/net/tcp*` observer saw existing Mihomo endpoint
connections during host B and C runs. That observer is not process-scoped and
was treated as ambient host activity, not as proof that the candidate request
used Mihomo. The stronger candidate-owned signal was the HTTPX transport
selection, and the isolated container supplied the final bypass proof:

- Container Path A selected the proxy transport 20/20 and could not reach the
  host-only Mihomo listener after the loopback proxy was rewritten for the
  container; it returned 20 connection-refused results.
- Container Path B selected no proxy transport, observed no Mihomo process or
  proxy connection, and returned 20/20 transport responses.
- Container Path C selected no proxy transport, observed no Mihomo process or
  proxy connection, and returned 20/20 transport responses. This is the
  selected path's direct-bypass proof.

No request body, API key, Authorization header, or response body was sent or
stored by preflight. A 401 response counted as transport success because DNS,
TCP, TLS, and HTTP response completion were verified without authentication.

## 8. Host Path A preflight — 20 sequential attempts

| Metric | Result |
|---|---:|
| Transport success | 20/20; HTTP 401: 20 |
| DNS / connect-timeout / refused / TLS / read failures | 0 / 0 / 0 / 0 / 0 |
| TCP connect min / median / p95 / max | 0.158 / 0.246 / 0.337 / 0.547 ms |
| TLS min / median / p95 / max | not separately exposed through proxy |
| Total min / median / p95 / max | 629.451 / 650.086 / 693.678 / 976.913 ms |
| Proxy transport selected | 20/20 |
| Proxy endpoint observation | 20/20; host Mihomo present |

## 9. Host Path B preflight — 20 sequential attempts

| Metric | Result |
|---|---:|
| Transport success | 20/20; HTTP 401: 20 |
| DNS / connect-timeout / refused / TLS / read failures | 0 / 0 / 0 / 0 / 0 |
| TCP connect min / median / p95 / max | 0.879 / 0.938 / 1.150 / 1.454 ms |
| TLS min / median / p95 / max | 162.802 / 167.412 / 198.193 / 483.407 ms |
| Total min / median / p95 / max | 654.653 / 689.072 / 759.765 / 1037.237 ms |
| Proxy transport selected | 0/20 |
| Host-wide proxy endpoint observation | 20/20; ambient, not process-scoped |

## 10. Host Path C preflight — 20 sequential attempts

| Metric | Result |
|---|---:|
| Transport success | 20/20; HTTP 401: 20 |
| DNS / connect-timeout / refused / TLS / read failures | 0 / 0 / 0 / 0 / 0 |
| TCP connect min / median / p95 / max | 0.916 / 1.067 / 1.346 / 1.805 ms |
| TLS min / median / p95 / max | 170.225 / 172.218 / 182.129 / 501.040 ms |
| Total min / median / p95 / max | 625.387 / 636.683 / 714.184 / 1003.878 ms |
| Proxy transport selected | 0/20 |
| Host-wide proxy endpoint observation | 20/20; ambient, not process-scoped |
| HTTPX `trust_env` | false |

## 11. Container Path A preflight — 20 sequential attempts

| Metric | Result |
|---|---:|
| Transport success | 0/20 |
| DNS / connect-timeout / refused / TLS / read failures | 0 / 0 / 20 / 0 / 0 |
| Total min / median / p95 / max | 23.562 / 25.965 / 45.001 / 142.347 ms |
| Proxy transport selected | 20/20 |
| Mihomo process / proxy connection observed | no / no |
| Container loopback proxy rewrite | yes |

The approved host proxy listener is not reachable from the disposable
container network. This is a bounded network-path result, not a production
change.

## 12. Container Path B preflight — 20 sequential attempts

| Metric | Result |
|---|---:|
| Transport success | 20/20; HTTP 401: 20 |
| DNS / connect-timeout / refused / TLS / read failures | 0 / 0 / 0 / 0 / 0 |
| TCP connect min / median / p95 / max | 1.125 / 1.328 / 2.180 / 3.423 ms |
| TLS min / median / p95 / max | 166.416 / 187.697 / 497.186 / 550.567 ms |
| Total min / median / p95 / max | 616.202 / 659.875 / 1072.072 / 1177.149 ms |
| Proxy transport selected | 0/20 |
| Mihomo process / proxy connection observed | no / no |
| Direct bypass proven | yes |

## 13. Container Path C preflight — 20 sequential attempts

| Metric | Result |
|---|---:|
| Transport success | 20/20; HTTP 401: 20 |
| DNS / connect-timeout / refused / TLS / read failures | 0 / 0 / 0 / 0 / 0 |
| TCP connect min / median / p95 / max | 1.189 / 1.312 / 1.496 / 1.549 ms |
| TLS min / median / p95 / max | 169.988 / 188.275 / 487.965 / 506.405 ms |
| Total min / median / p95 / max | 613.568 / 651.275 / 1015.524 / 1068.226 ms |
| Proxy transport selected | 0/20 |
| Mihomo process / proxy connection observed | no / no |
| HTTPX `trust_env` | false |
| Direct bypass proven | yes |

## 14. Direct-versus-proxy classification and selection

Classification: **A — direct path clearly more stable than proxy for the
candidate container**.

The host proxy preflight itself returned 20/20, but the proxy path was not
usable from the disposable Backend network, while both direct paths returned
20/20 with bounded TLS and total timings. Path C had the lower container
median, p95, and maximum total duration compared with Path B and has the
smallest scope of effect. Path C was selected for authenticated validation.

This result does not claim that direct always has lower latency. It gives
priority to successful completion, connection failures, bounded maximum, p95,
and then median, and it is consistent with the previous authenticated proxy
candidate's repeated connection-timeout failures.

## 15. Authenticated direct candidate

Path: C (`trust_env=False`)
Environment: fresh disposable Backend container
Execution count: **10**, sequential, exactly one cohort
Input: existing ten-case synthetic Resume/JD/Project Knowledge corpus only
Secret: approved candidate loading mechanism, never written to artifacts

The candidate retained model `deepseek-v4-pro`, thinking disabled, JSON object
output, primary/length-retry/repair budgets `1600/2400/1000`, configured
maximum `5000`, Provider deadline `130` seconds, Analyze safety deadline
`175` seconds, SDK retries `0`, one application retry, one repair, and maximum
three Provider calls.

## 16. Candidate result states

| State | Count |
|---|---:|
| complete | 4 |
| repaired | 0 |
| partial | 5 |
| fallback | 1 |

Accepted (`complete + repaired + partial`): 9/10. The one fallback was the
existing deterministic fallback after bounded Provider failure. No individual
case was rerun.

## 17. Retry, repair, timeout, and fallback categories

- Primary attempts: 19 total across 10 executions.
- Application retry count: 9.
- Format-only repair count: 0.
- Maximum Provider calls in one execution: 2.
- Timeout categories: `connect_timeout: 9`; `read_timeout: 0`,
  `write_timeout: 0`, `pool_timeout: 0`.
- Deadline-exhausted count: 0.
- Empty-content count: 0.
- Finish reasons: `stop: 9`, `other: 1`.
- Parse outcomes: `canonical: 9`, `invalid: 1`.
- Salvage action: `evidence_reference_cleanup: 5`.
- Fallback category: `provider_call_failed: 1`; that fallback record also had
  a bounded `connect_timeout` category.

The nine connect-timeout categories were bounded per-attempt events, not
requests that survived the authoritative deadline. No retry or repair was
started after the deadline, and no Provider operation remained active past
its allowed per-attempt lifetime.

## 18. Deadline and duration observations

| Metric | Result |
|---|---:|
| Provider duration median / p95 / max | 8073.530 / 10835.040 / 10835.040 ms |
| Analyze end-to-end median / p95 / max | 8095.550 / 10843.555 / 10843.555 ms |
| Maximum active Provider operation lifetime | 7570.320 ms |
| Analyze safety deadline | 175 s |
| External client bound | 180 s |

All ten executions completed before the external safety bound. The maximum
observed end-to-end duration was approximately 10.844 seconds; no
`provider_deadline_exhausted` result occurred.

## 19. Token observations

Aggregate token metadata only:

| Token category | Minimum | Maximum | Total |
|---|---:|---:|---:|
| input | 0 | 837 | 7324 |
| output | 0 | 382 | 2575 |
| total | 0 | 1202 | 9899 |

The zero values are fallback/no-accepted-Provider-output cases. No content,
prompt, reasoning, or response body was recorded.

## 20. Job Summary and Match Reasons

- Job Summary: present in 10/10; unavailable in 0/10.
- Match Reasons: present in 10/10; unavailable in 0/10.
- Deterministic fallback retained the existing Job Summary and Match Reasons
  contract.

## 21. Security, serialization, History, and idempotency

- Security rejection count: 0.
- Public contract/serialization failure count: 0.
- Safe-log inspection: passed; no API key, Authorization, proxy value,
  Provider body, reasoning content, prompt, synthetic text, or content hash
  appeared in the bounded logs/artifact.
- History: `not_applicable_isolated_runner`; the direct candidate runner did
  not connect to production PostgreSQL or persist production History.
- Idempotency: `not_applicable_isolated_runner`; the runner used disposable
  candidate storage and no production Redis or PostgreSQL. Existing
  deadline/idempotency regression tests remained green.
- Duplicate History finalization: 0 applicable events; no production side
  effect was possible.

## 22. Validation and CI

Offline focused validation before the real cohort:

```text
backend/.venv/bin/python -m unittest \
  test_deepseek_direct_connectivity_candidate \
  test_provider_deadline_enforcement \
  test_deepseek_provider_real_candidate
Ran 36 tests ... OK
```

The new tests cover Path A environment proxy selection, Path B selective
NO_PROXY preservation, Path C environment isolation, container loopback
rewriting, safe metadata output, bounded candidate client construction, and
zero SDK retries. No CI test calls a real LLM; the authenticated cohort was
manual, secret-dependent, and run outside GitHub Actions.

The complete local Backend suite was rerun in the CI-style environment with
the unsupported SOCKS proxy category absent from the test process:

```text
ALL_PROXY= all_proxy= .venv/bin/python -m unittest discover -p 'test_*.py'
Ran 548 tests ... OK (skipped=12)
```

The first local invocation inherited the host SOCKS category and failed only
at HTTPX client construction in existing Provider tests; that environment
artifact was not accepted as a code result. The sanitized rerun passed. The
candidate changes are under `backend/candidates` and do not alter shared
production networking.

At the final pushed head `180ceb99380ce25dca35032ceba13af89e9ecc8b`, PR #56
was open, non-draft, and mergeable. All 20 reported checks completed with no
failures: `backend-tests`, `complete-backend-tests`, `verify`,
`isolated-candidate`, `production-assets-and-java`, `frontend-build`,
`postgres-16-integration`, `container-smoke`, `backend-postgres`,
`local-mode-production-assets`, `normalization-only-no-database-smoke`,
`docker-build`, `postgres16-backup-restore`, `compose-validation`,
`production-runtime-regression`, `script-validation`, `repository-safety`,
and `docker-smoke-v2` succeeded. `publish-application-image` and
`publish-integrated-backend-image` were intentionally skipped. No workflow
published an image or called a real LLM.

## 23. Changed files

- `backend/candidates/deepseek_direct_connectivity_candidate.py` — manual-only
  A/B/C preflight and Path C candidate adapter; no production import.
- `backend/candidates/deepseek_provider_real_candidate.py` — bounded
  per-attempt Provider timing aggregate for candidate evidence only.
- `backend/test_deepseek_direct_connectivity_candidate.py` — isolated client
  and metadata-safety tests.
- `docs/work-reports/2026-08-07-deepseek-direct-connectivity-candidate-work-report.md`
  — this evidence report.
- `docs/work-reports/README.md` — report index link.

No Alembic migration, Java source/image/policy/dictionary, production Compose,
Project Knowledge, root README stable version, release image, tag, or release
file was changed.

## 24. Commits and PR

Logical commits created on the existing PR branch:

- `a68fbb5` — `test: add direct provider connectivity harness`.
- `b922232` — `test: cover direct provider transport isolation`.
- `180ceb9` — `docs: record direct connectivity candidate evidence`.
- The report/index delivery commit is the final report-bearing head shown by
  GitHub after push; it is intentionally not rewritten or squashed.

Updated PR: [Fix: Enforce bounded Analyze provider deadlines — PR #56](https://github.com/HKJoker-Z/personal-job-agent/pull/56)

## 25. Decision and exact next prerequisite

Decision: **GO_DIRECT** for a later implementation phase only.

Exact next prerequisite: **Implement DeepSeek Dedicated Direct Client** as a
separate reviewed phase. That phase must keep the direct mode scoped to the
DeepSeek client, preserve a configuration-only rollback to the approved
environment-proxy mode, and run a fresh isolated candidate followed by a
fresh production candidate while stable production remains Version 2.0.5.
No production deployment or Version 2.0.6 release is authorized by this
report.

## 26. Risks and rollback plan

Risks:

- Direct connectivity may vary by host, Docker network, geography, firewall,
  or Provider policy.
- The direct cohort still contained nine bounded connection-timeout
  categories, so direct connectivity is technically viable but not
  timeout-free.
- Path B changes environment routing for the configured DeepSeek hostname;
  an eventual production implementation must scope and review that behavior.
- The isolated runner does not prove production PostgreSQL/Redis persistence;
  that remains a prerequisite for a later candidate/deployment phase.

Rollback:

- Do not deploy this branch directly.
- For a later implementation, disable the DeepSeek direct-network mode through
  its reviewed configuration switch and restore the approved HTTP(S) proxy
  mode, then rerun health and candidate validation.
- If a later deployment is attempted and fails, use the preserved Version
  2.0.5 images, compose revision, configuration, and rollback assets. This
  phase did not alter any of them.

## 27. Required confirmations

- Production untouched: **confirmed**.
- Java and Alembic unchanged: **confirmed**.
- Production or user content inspected: **none**.
- Synthetic content only for authenticated testing: **confirmed**.
- Version bump: **none**.
- Image release: **none**.
- Deployment: **none**.
- Git tag: **none**.
- GitHub Release: **none**.
- PR #56 merge: **none**.
- Version 2.0.6: **not completed and remains unreleased**.
