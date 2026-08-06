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

## Token budget and retry contract

The previous Analyze candidate was `1200` output tokens. The current bounded
candidate is `1600`; a single `finish_reason=length` retry may use `2400`; the
format-only repair call is bounded at `1000`. The application upper bound is
`5000` tokens for every configured budget. The candidate values leave room for
the compact JSON contract and its evidence arrays, but they are not a claim of
better latency or Provider success.

There is one primary call, followed by at most one application-level retry for
connect/read timeout, HTTP 429, HTTP 5xx, documented resource exhaustion,
empty content, or `finish_reason=length`. The length retry is the only retry
that increases the output budget. Backoff is bounded by
`PROVIDER_RETRY_BACKOFF_SECONDS`, and the overall Provider deadline is bounded
by `PROVIDER_OVERALL_DEADLINE_SECONDS`.

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
fallback category, returned token usage, and duration. Prompts, Resume/JD
text, Provider bodies, reasoning content, credentials, arbitrary exception
text, request IDs, and content hashes are not recorded. Existing monitoring
tables are reused; no migration is required for this metadata.

## Rollback and deferred experiments

Rollback is configuration-only: restore the previous operator values for
`DEEPSEEK_MODEL`, `AGENT_MODEL_MAX_OUTPUT_TOKENS`, and the new retry/repair
variables, or set the model path to the previously approved bounded candidate.
No database downgrade is needed. The application version remains `2.0.5` in
this change; the provisional follow-up release is `v2.0.6`.

Strict Function Calling is deferred as a candidate experiment. Multi-call
response splitting is also deferred because it changes cost, ordering, and
semantic reconciliation. Neither is enabled by this patch.
