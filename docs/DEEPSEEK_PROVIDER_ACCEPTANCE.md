# DeepSeek Provider Acceptance v1

This document describes the synchronous `/api/analyze` Provider boundary. It
does not change Java JD normalization, Project Knowledge retrieval, scoring, or
the public `analysis_status` field.

The implementation follows the official [JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/),
[thinking-mode guide](https://api-docs.deepseek.com/guides/thinking_mode/),
[model documentation](https://api-docs.deepseek.com/quick_start/pricing), and
[error handling guidance](https://api-docs.deepseek.com/quick_start/error_codes/).

## Request contract

Analyze uses the configured `DEEPSEEK_MODEL` and the official non-Beta
OpenAI-compatible endpoint `https://api.deepseek.com`. The default documented
quality candidate is `deepseek-v4-pro`; an operator may select another bounded,
nonblank model identifier without the application silently rewriting it.
Deprecated `deepseek-chat` and `deepseek-reasoner` aliases are not used by the
active repository paths.

The structured request includes:

- `response_format={"type":"json_object"}`;
- a prompt containing the word `JSON`, one bounded valid JSON example, canonical
  field names, and short type/size guidance;
- `extra_body={"thinking":{"type":"disabled"}}` by default;
- an explicit positive `max_tokens` value;
- SDK automatic retries fixed at `max_retries=0`.

Thinking can be enabled only through `DEEPSEEK_THINKING_ENABLED=true` for an
isolated operator experiment or test. The request does not expose
`reasoning_content`; reasoning is never copied to logs, public responses,
History, monitoring, or repair prompts. Sampling controls are not used to
control thinking mode.

## DeepSeek network mode

The DeepSeek Provider client is the only Backend client that reads
`DEEPSEEK_NETWORK_MODE`:

- `direct` constructs the installed HTTPX client with `trust_env=False`. It
  ignores uppercase and lowercase `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and
  `NO_PROXY` variables while retaining system DNS and normal TLS certificate
  verification.
- `environment_proxy` constructs the same deadline-aware client with
  `trust_env=True`, preserving the existing approved HTTPX environment-proxy
  behavior. This is the configuration-only rollback and compatibility path.

Neither mode mutates `os.environ`, and the setting does not affect Job URL
acquisition, SSRF-safe fetches, Java normalization, Project Knowledge, the
Frontend, Worker/Outbox networking, or other Backend HTTP clients. The
configuration parser rejects unknown values. For backward compatibility, an
unset variable resolves to `environment_proxy`; the later production
candidate explicitly sets `DEEPSEEK_NETWORK_MODE=direct`.

## Token budget and retry contract

The previous Analyze candidate was `1200` output tokens. The current bounded
candidate is `1600`; a single `finish_reason=length` retry may use `2400`; the
format-only repair call is bounded at `1000`. The application upper bound is
`5000` tokens for every configured budget. The candidate values leave room for
the compact JSON contract and its evidence arrays, but they are not a claim of
better latency or Provider success.

There is one primary call, followed by at most one application-level retry for
the exact bounded timeout categories, an attempt deadline, transport failure,
HTTP 429, HTTP 5xx, documented resource exhaustion, empty content, or
`finish_reason=length`. The length retry is the only retry that increases the
output budget. Backoff is bounded by
`PROVIDER_RETRY_BACKOFF_SECONDS`, and the overall Provider deadline is bounded
by `PROVIDER_OVERALL_DEADLINE_SECONDS`. The deadline is one absolute
monotonic-clock deadline shared by both primary attempts and the optional
repair; each attempt receives a timeout derived from its remaining budget.

The default Provider deadline remains 130 seconds. A 30-second reserve is kept
for deterministic fallback construction, final output security processing,
History/idempotency finalization, and response serialization. The application
safety deadline is 175 seconds (the unchanged 180-second external client
contract with a five-second delivery margin). A primary attempt uses a maximum
60-second configured request budget with component limits of connect 5 seconds,
write 10 seconds, pool 5 seconds, and a read/total-body limit derived from the
remaining absolute deadline. The retry reserves the configured 0.25-second
backoff; repair reserves five seconds before the finalization reserve.

The stable Provider categories are `connect_timeout`, `read_timeout`,
`write_timeout`, `pool_timeout`, `provider_attempt_deadline_exhausted`,
`provider_phase_deadline_exhausted`, `transient_http_429`,
`transient_http_5xx`, `transport_error`, and
`unknown_bounded_provider_error`. The adapter walks only typed SDK/HTTPX
causes and explicit status codes. In particular, the SDK's broad
`APIConnectionError` is not treated as `connect_timeout`; a concrete HTTPX
transport cause is required. The effective attempt budget and effective
connect timeout are recorded only as bounded numeric metadata.

HTTPX read timeouts are per-read-operation, so the synchronous client also
wraps the response byte stream with the same absolute deadline. A Provider
response that drips chunks indefinitely cannot extend the phase by resetting a
per-read timeout. SDK automatic retries remain zero.

If the primary content is safe but cannot be parsed or validated, one
format-only repair call is allowed. It is never a second analysis request and
it is never used after a severe security finding. The absolute maximum for a
new Analyze execution is therefore three Provider calls: two primary attempts
and one repair. Completed idempotency replays make zero Provider calls.

Authentication failures, invalid request configuration, non-retryable 4xx
responses, deterministic local validation failures, severe output-security
findings, and completed replays are not retried. The bounded retry can increase
worst-case latency and token cost and may cause duplicate Provider billing after
an ambiguous timeout.

## Acceptance states

The backend preserves the public `analysis_status` field:

| State | Contract |
| --- | --- |
| `complete` | The primary content is canonical, required fields are present, it passes the minimum safe contract, and no meaningful warning is produced. |
| `repaired` | The primary content was recovered by bounded syntactic normalization or the one format-only repair call, and no material field was discarded. |
| `partial` | Safe Provider analysis remains the main source, but aliases, null/type coercion, bounded defaults, list-item removal, evidence cleanup, unsupported-claim cleanup, or another bounded salvage action was applied. |
| `fallback` | No Provider response met the minimum safe contract, the calls failed, or security policy required rejection; deterministic local analysis is used. |

The minimum safe contract is semantic rather than a field count. At least one
skill-state judgment, dimension assessment/score, or concise recommendation must
survive bounded normalization. The result must then pass output security,
evidence reconciliation, bounded serialization, and backend-owned scoring. A
JSON object with no meaningful analysis is not accepted as `partial`.

Field salvage is deterministic and named. It supports only known aliases,
null-to-default for bounded optional/list fields, scalar string to one-item
lists, bounded numeric strings, score clamping within product semantics,
invalid list-item removal while preserving valid items, bounded array/text
limits, evidence-ID cleanup, and removal of unsupported claims. Arbitrary
nested objects, dynamic aliases, executable content, secrets, role/tool
manipulation, prompt leakage, unbounded values, and unrecognizable roots are
not accepted.

## Summary and Match Reasons

Job Summary and Match Reasons are always represented in the public Analyze and
History views. Provider content is preserved when it is valid. When a field is
missing, the backend derives a bounded value only from validated local data:
the normalized JD for Job Summary, and matched/missing skills, validated
Resume/Project Knowledge evidence, and the backend-owned score breakdown for
Match Reasons. No additional LLM call is made. If local data is insufficient,
the UI shows an explicit unavailable explanation rather than hiding the
section. No employment history, years, leadership, scale, impact,
certification, or other unsupported claim is invented.

## Security ordering and observability

The ordering is:

1. receive bounded Provider content;
2. perform the required output security screen;
3. parse and locally normalize the JSON;
4. apply field-level salvage;
5. reconcile evidence and remove unsupported claims;
6. complete deterministic summary, reasons, and score fields;
7. scan the final serialized output and return or persist it.

Secrets, credentials, private keys, system/developer prompt leakage,
protected instructions, role/tool manipulation, serious exfiltration, and
other blocking categories remain rejected. A severe primary output is not sent
to repair.

Structured observations are bounded to model ID, thinking boolean, JSON mode,
attempt counts, finish reason, empty-content flag, fixed retry category, parse
outcome, fixed salvage categories, accepted/rejected field counts, state,
fallback category, exact timeout and Provider-error categories, effective
bounded timeout values, remaining-deadline bucket, deadline exhaustion,
retry/repair/fallback flags, finalization flags, client-disconnect flag,
returned token usage, bounded attempt durations, and duration. Prompts,
Resume/JD text, Provider bodies, reasoning content, credentials, arbitrary
exception text, request IDs, and content hashes are not recorded. Existing
monitoring tables are reused; no migration is required for this metadata.
The new timing fields remain internal to monitoring observations and
structured logs rather than the public Analyze body, preserving byte-for-byte
stability for equivalent local results and completed idempotency replays.

## Client disconnect and fallback

The request remains synchronous. Disconnects are checked at async boundaries;
the synchronous SDK call itself is not polled from another event loop. The
transport deadline still closes a stalled Provider response, and a disconnect
detected before Provider work selects the deterministic fallback without
starting a call. If a caller disconnects after Provider work has begun, the
server completes at most one bounded finalization so the idempotency record is
not left stale. A completed replay returns the stored result and makes zero
Provider calls. Attempt tokens continue to prevent stale workers from
finalizing a takeover.

## Rollback and deferred experiments

Rollback is configuration-only: set
`DEEPSEEK_NETWORK_MODE=environment_proxy`. No database downgrade is needed.
The application version remains `2.0.5` in this change; no release or version
bump is part of the implementation phase.

Strict Function Calling is deferred as a candidate experiment. Multi-call
response splitting is also deferred because it changes cost, ordering, and
semantic reconciliation. Neither is enabled by this patch.
