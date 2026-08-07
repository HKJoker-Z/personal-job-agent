# Pragmatic DeepSeek Provider Acceptance

This document describes the synchronous /api/analyze Provider boundary. It
does not change Java JD normalization, Project Knowledge retrieval, the public
response schema, scoring, or persistence.

## Responsibility split

DeepSeek receives one short, security-bounded prompt and is asked for only
shallow narrative material:

- job_summary: a concise role summary;
- match_reasons: up to five concise narrative reasons;
- recommendations: up to five concise recommendations;
- resume_improvements: up to four concise improvement items.

The Backend remains authoritative for matched and missing technical skills,
normalized JD data, ATS overlap, evidence validity, Project Knowledge source
IDs, scoring and the final Match Score, security decisions, deterministic
fallback, next-action recommendation, persistence, and public serialization.
Cover Letter generation remains a separate material workflow; Analyze does not
ask DeepSeek to generate it.

Provider responses may contain older compact skill/dimension/evidence fields
for bounded compatibility. They are not requested by the active prompt and
are not authoritative in the active Analyze path.

## Request contract

Analyze uses the configured DEEPSEEK_MODEL and the official non-Beta
OpenAI-compatible endpoint https://api.deepseek.com. The request includes:

- response_format={"type":"json_object"};
- one short role statement, a strict untrusted-data boundary, the Resume,
  normalized JD, at most the most relevant Project Knowledge chunks, one
  concise output instruction, and one small valid JSON example;
- extra_body={"thinking":{"type":"disabled"}} by default;
- the existing operator-configured model and API-key handling;
- SDK automatic retries fixed at max_retries=0.

The prompt does not ask for scores, evidence IDs, source metadata, reasoning,
Resume/JD repetition, or Backend bookkeeping.

## Token, retry, and deadline contract

The existing budgets remain unchanged: primary output tokens 1600, one
length retry at 2400, format-only repair at 1000, configured maximum 5000.
The Provider phase remains 130 seconds, Analyze safety remains 175 seconds,
and the external client safety assumption remains 180 seconds. A 30-second
reserve remains available for fallback, finalization, security processing,
History/idempotency, and serialization.

There is one application retry and one optional format-only repair call. The
absolute maximum for a new Analyze execution remains three Provider calls.
Every attempt derives its timeout from the same monotonic absolute deadline.
Completed idempotency replay performs zero Provider calls.

No Provider networking change is part of this acceptance task. The branch
uses the networking behavior on main; PR #57 remains an independent direct
networking experiment.

## Pragmatic normalization

After the output security screen, the Backend extracts one bounded JSON
object, normalizes known aliases and types, and salvages valid peer fields.
Safe normalization includes:

- missing or null optional fields to empty values;
- scalar strings to one-item arrays;
- invalid list items removed while valid items remain;
- bounded text and array limits;
- duplicate removal;
- harmless unknown fields ignored;
- older evidence references cleaned against the current request;
- model-supplied scores ignored in favor of deterministic scoring.

Narrative sentences with unsupported candidate claims are removed individually
when safe content remains. A valid summary or recommendation is not discarded
because another optional field is malformed.

Whole-response rejection remains limited to:

- secret, credential, system/developer prompt, role/tool manipulation, or
  serious exfiltration findings;
- no recognizable object after bounded local extraction;
- no meaningful model-derived analysis after normalization;
- absolute output-size or public-serialization failure.

## State semantics

| State | Meaning |
| --- | --- |
| complete | Canonical shallow Provider narrative survived without meaningful salvage. |
| repaired | Bounded local JSON normalization or the one format-only repair recovered useful content. |
| partial | Useful Provider content remains, but fields were omitted, normalized, bounded, cleaned, or deterministically completed. |
| fallback | Provider calls failed, the response was fundamentally unusable, or blocking output security required deterministic local analysis. |

An occasional fallback is an intentional availability state. Fallback still
returns Backend-owned scoring, matched/missing skills where deterministically
available, Job Summary and Match Reasons or stable unavailable text,
recommendations where possible, and the stable History/public shape. The
Frontend displays the state and does not treat it as a server crash.

## Security and observability

The ordering is:

1. receive bounded Provider content;
2. scan output for secrets, prompt leakage, and protected instructions;
3. extract JSON and normalize fields;
4. remove invalid evidence and unsupported narrative claims;
5. derive skills, evidence, score, summary/reasons defaults, and ATS data;
6. scan the final serialized result before return or persistence.

Prompts, Resume/JD text, Provider bodies, reasoning content, credentials,
proxy values, request headers, and arbitrary exception text are not stored in
monitoring metadata. Observations use bounded state, category, token, timing,
and retry fields only.

## Candidate gate

The pragmatic candidate gate is:

- all ten executions finish inside the authoritative deadline;
- complete + repaired + partial >= 7/10;
- fallback <= 3/10;
- Job Summary and Match Reasons are present or explicitly unavailable 10/10;
- zero security, secret/prompt leakage, serialization, duplicate History, and
  idempotency regressions;
- maximum Provider calls <= 3;
- Java behavior and PostgreSQL schema remain unchanged.

The later first-ten-production recommendation uses the same 7/10 and
fallback <= 3/10 baseline. Investigate or roll back after three consecutive
fallbacks, fallback above 40% over the first 20 analyses, public latency
beyond the configured safety contract, or any security, serialization, or
duplicate History defect.
