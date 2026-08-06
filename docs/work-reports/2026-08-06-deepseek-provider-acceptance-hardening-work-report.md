# DeepSeek Provider Acceptance Hardening v1 Work Report

Date: 2026-08-06
Repository: HKJoker-Z/personal-job-agent
Scope: synchronous /api/analyze Provider acceptance only. No production traffic,
deployment, migration, release, or version bump was performed.

## 1. Repository

The implementation was made in the local checkout of
https://github.com/HKJoker-Z/personal-job-agent.

## 2. Starting commit

The starting commit was
aff52b3e276f314063c9445ca4450e8d74758d93 (docs: record v2.0.5 closeout audit
delivery). The work started from a clean worktree on
docs/v2.0.5-closeout-audit and was developed on
fix/deepseek-provider-acceptance-hardening.

## 3. Production baseline

The reported baseline was stable release v2.0.5, Alembic head 20260730_07, Java
JD normalization mode java, Java policy jd-normalization-v1, skill dictionary
skills-v1, synchronous /api/analyze, and deterministic fallback preserving
availability. The implementation does not change any of those Java, database,
mode, policy, or dictionary settings.

## 4. Reported symptom

Several recent Analyze requests reached fallback. Java JD normalization was
successful, while failures were observed in the Provider call/output
acceptance path. Existing fallback data did not consistently populate Job
Summary and Match Reasons in public Analyze and History views.

## 5. Current model configuration

At the starting commit, the active Analyze client used the repository default
model alias deepseek-chat. The hard-coded active paths were audited before
editing, including backend/legacy_application.py, job extraction, material
generation, and agent-run metadata. Current official DeepSeek documentation
lists deepseek-v4-pro and deepseek-v4-flash as current model IDs and says the
legacy deepseek-chat and deepseek-reasoner aliases are deprecated. The new
documented quality-oriented candidate is therefore deepseek-v4-pro, while
DEEPSEEK_MODEL remains operator-configurable and bounded. An unknown
operator-supplied nonblank model is validated but never silently rewritten. No
production environment was changed.

References: [DeepSeek model list](https://api-docs.deepseek.com/api/list-models),
[DeepSeek pricing and current model IDs](https://api-docs.deepseek.com/quick_start/pricing).

## 6. Current Provider request parameters before this change

The audited Analyze path used:

- base URL https://api.deepseek.com;
- configured request timeout, default 60 seconds;
- OpenAI SDK max_retries=0;
- model deepseek-chat from the starting repository default;
- temperature=0.2;
- max_tokens=1200;
- response_format={"type":"json_object"};
- no explicit thinking-mode request;
- one primary Provider call and no application-level transient retry.

The request already used JSON Output, but the prompt/schema contract and local
acceptance behavior did not make JSON mode sufficient for schema correctness.

## 7. Current response contract before this change

The compact Provider contract was the seven canonical fields:
matched_skills, missing_skills, unknown_skills,
concise_dimension_assessments, evidence_references,
unsupported_claim_candidates, and concise_recommendations. The active path
performed response extraction, local Markdown/JSON normalization, Pydantic
validation, evidence reconciliation, unsupported-claim cleanup, output
security scanning, deterministic scoring, History finalization, and public
serialization. Job Summary and Match Reasons were result-level fields, but were
not reliably completed on fallback.

The audit covered client construction and model configuration in
backend/legacy_application.py, request and prompt construction in
backend/legacy_application.py and backend/safe_prompt.py, contract parsing and
validation in backend/analysis_contract.py, fallback in
backend/analysis_fallback.py, monitoring in backend/monitoring_service.py,
idempotency and History finalization in the Analyze workflow, and rendering in
frontend/src/legacy-workspace.jsx.

## 8. Current rejection paths before this change

The old path could select fallback after Provider exceptions, empty content,
length-truncated content, malformed JSON, an unrecognized root, schema
validation failure, evidence/grounding failure, or unusable repair output.
Format extraction was available, but field-level normalization was limited, so
a single malformed or mistyped field could reject the whole compact response.
The old path also had no bounded primary retry for stable transient errors and
no explicit observability for the distinction between empty, length, parse,
salvage, and fallback categories.

## 9. Confirmed root causes and contributing causes

Confirmed or materially contributing repository causes were:

1. A transient, empty, or length-limited Provider response had no explicit
   application-level retry even though SDK retries were already disabled.
2. JSON Output was requested, but JSON mode was not treated as a schema
   guarantee; prompt instructions were not a single bounded canonical
   contract.
3. Whole-response validation rejected recoverable aliases, nulls, scalar/list
   mismatches, numeric strings, invalid list members, and unknown evidence IDs.
4. finish_reason=length and empty content were terminally classified without a
   distinct length/resource retry budget.
5. Fallback completion did not consistently provide Job Summary and Match
   Reasons, and frontend rendering could hide null/legacy values.
6. Thinking mode was implicit rather than explicitly disabled for structured
   Analyze calls.
7. The default active model alias was deprecated by current official model
   documentation.
8. Provider metadata did not expose bounded acceptance outcomes without risking
   response-body, prompt, reasoning, or exception leakage.

The full unit suite also exposed two pre-existing test-path configuration
references that used an undefined local settings variable in job extraction and
material generation. They were corrected to load the existing validated
configuration; this did not change Java or production configuration.

## 10. Chosen acceptance policy

The new policy performs security screening before parsing, then bounded local
format normalization, deterministic field salvage, evidence reconciliation,
deterministic completion, and a final serialized-output scan. Salvage is
accepted only when safe analysis remains the main source and the semantic
minimum safe contract is met. Severe security findings remain blocking and are
never converted into partial.

## 11. Result-state contract

The public analysis_status field is preserved:

- complete: primary Provider content is canonical, required fields are present,
  the minimum safe contract passes, and no meaningful warning was produced.
- repaired: content was recovered by bounded syntactic normalization or the
  existing single format-only repair request; no material field was discarded.
- partial: safe Provider analysis remains the main source, but bounded
  alias/type/default/list/evidence/claim/deterministic-completion salvage was
  applied.
- fallback: Provider calls produced no safe usable analysis, all available
  responses failed the minimum safe contract, or security policy required
  rejection. Deterministic local analysis remains the result source.

The state is assigned after downstream evidence cleanup as well as after
parsing, so a cleanup that materially changes a complete response promotes it
to partial.

## 12. JSON Output implementation

The structured request uses the official non-Beta endpoint and
response_format={"type":"json_object"}. The prompt explicitly contains JSON,
says the final content must be exactly one JSON object, prohibits Markdown
fences and prose outside the object, contains one bounded valid JSON example,
names the seven canonical fields once, and briefly explains their types and
limits. Local parsing and validation remain mandatory.

References: [DeepSeek JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/),
[DeepSeek chat completion API](https://api-docs.deepseek.com/api/create-chat-completion).

Strict Function Calling was not enabled. It remains a future candidate
experiment only.

## 13. Thinking-mode decision

Structured Analyze calls now send the official SDK option
extra_body={"thinking":{"type":"disabled"}} by default. Setting
DEEPSEEK_THINKING_ENABLED=true exercises the validated enabled path in
isolated tests and operator-controlled experiments. reasoning_content is never
copied to logs, public responses, History, monitoring, or repair prompts.
Sampling controls are not used as a thinking-mode switch.

Reference: [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode).

## 14. Model-name decision

The current documented candidate is deepseek-v4-pro. The model remains
operator-configurable through DEEPSEEK_MODEL; configuration rejects blank,
overlong, or unsafe model identifiers but does not rewrite unknown values. No
production model setting was changed.

## 15. Token-budget decision

The old candidate was 1200 output tokens. The new candidate is 1600, the
single length-triggered retry is 2400, and the format-only repair call is
1000. Every value is positive, cross-validated, and bounded by an
application-level maximum of 5000. finish_reason=length is recorded and
classified separately; visibly truncated JSON is not silently accepted.

These values are a capacity/acceptance candidate based on the existing compact
result schema and fixtures, not a performance claim. The negative effect is a
higher worst-case token cost and latency when a length retry or repair is used.

## 16. Retry contract

SDK automatic retries remain max_retries=0. The application permits one
primary retry only for connect timeout, read timeout, HTTP 429, HTTP 5xx,
documented transient resource exhaustion, empty content, or
finish_reason=length. Backoff and an overall deadline are bounded by
configuration. Authentication failures, invalid request configuration,
non-retryable 4xx errors, deterministic local validation errors, severe
security findings, and completed replays are not retried.

The accepted negative effects are increased worst-case latency and token cost,
and possible duplicate Provider billing after an ambiguous timeout.

Reference: [DeepSeek error handling](https://api-docs.deepseek.com/quick_start/error_codes/).

## 17. Maximum Provider calls

One new synchronous Analyze execution allows at most two primary attempts and
one format-only repair call: an absolute maximum of three Provider calls. A
primary retry and multiple repair calls cannot occur. A completed idempotency
replay performs zero Provider calls.

## 18. Field-level salvage rules

Salvage is deterministic, bounded, and emits stable warning codes. The rules
are limited to known canonical aliases; null optional strings/lists to safe
defaults; scalar strings to one-item lists; bounded numeric strings; score
clamping to the existing 0–100 semantics; invalid list-item removal while
preserving valid items; bounded text/list sizes; removal of unknown evidence
IDs; removal of unsupported or unverifiable claim candidates; and ignoring
bounded unknown top-level fields where compatibility permits it. Valid legacy
Provider job_summary and match_reason strings are retained as optional
result-level narrative compatibility fields and still pass the normal final
grounding/security path.

Dynamic aliases, arbitrary nested objects in string positions, unbounded
arrays/strings, executable content, secrets, prompt leakage, role/tool
manipulation, and unrecognizable roots are rejected. Every salvage action
causes partial, except format-only normalization/repair with no discarded
material, which causes repaired.

## 19. Minimum safe acceptance contract

The threshold is semantic, not a field count. After bounded normalization, at
least one of these must survive: a skill-state judgment through matched,
missing, or unknown skills; a dimension assessment or score; or a concise
recommendation. The accepted result must also pass output security scanning,
evidence reconciliation, bounded type/size validation, backend-owned scoring,
and public serialization. An empty object, plain prose, root array, or
unrecognizable structure cannot become partial.

## 20. Job Summary behavior

Complete and repaired results preserve a valid Provider Job Summary when one is
supplied. Partial results preserve valid Provider content and otherwise derive
a bounded deterministic sentence from already validated normalized JD content
and a known title when present. Fallback uses the same validated local inputs,
or the stable explicit unavailable explanation when insufficient data exists.
No unsupported employment, tenure, leadership, scale, impact, certification,
or candidate claim is generated.

## 21. Match Reasons behavior

Complete and repaired results preserve valid Provider Match Reasons. Partial
results preserve valid content and otherwise derive a bounded deterministic
explanation from matched/missing skills, validated Resume/Project Knowledge
evidence, and the backend-owned score breakdown. Fallback uses those same
inputs or a stable explicit unavailable explanation. No additional LLM call is
made.

## 22. Deterministic fallback changes

local_fallback_result now creates stable Job Summary and Match Reasons where
validated local data is sufficient and explicit unavailable values otherwise.
The public Analyze and History views always render both sections, including for
fallback, rather than silently treating null/empty/legacy malformed values as
a reason to hide them.

## 23. Prompt reductions

The prompt was reduced only where content was clearly duplicated: repeated
schema instructions, repeated format examples, duplicated safety language, and
redundant evidence framing. The effective sanitized Resume, Java-normalized JD,
relevant Project Knowledge chunks, evidence identifiers, and security
boundaries remain. Tests assert that each important evidence/safety section is
present once and that the canonical JSON example remains.

## 24. Security boundary

The exact ordering is:

1. receive bounded Provider content;
2. perform the required output security screen;
3. parse and locally normalize JSON;
4. apply field-level salvage;
5. reconcile evidence and remove unsupported claims;
6. complete deterministic summary, reasons, and score fields;
7. scan the final serialized output and serialize/persist it.

Credentials, API keys, private keys, system/developer prompt leakage, protected
instructions, role/tool manipulation, serious exfiltration, and other
currently blocking categories remain rejected. A severely unsafe primary
response is not sent to repair. The final result is scanned again after local
completion.

## 25. Observability

Existing structured monitoring/logging paths now retain bounded metadata for
model ID, thinking-enabled boolean, JSON response mode, primary and repair
attempt counts, finish reason, empty-content flag, fixed retry category, parse
outcome, fixed salvage categories, rejected/accepted field counts, result
state, fixed fallback reason, returned token usage, and Provider duration.
Provider bodies, prompts, Resume/JD text, reasoning content, credentials,
authorization/session data, request IDs, hashes, arbitrary exception strings,
and other high-cardinality secret-bearing data are excluded. Existing metrics
storage is reused; no migration is required for this metadata.

## 26. Synthetic acceptance corpus

backend/fixtures/deepseek_provider_acceptance_v1/corpus.json contains 23
bounded synthetic cases with no user data: canonical JSON, fenced JSON, outer
wrapper, aliases, missing/null fields, scalar/list mismatch, numeric strings,
score clamping, invalid list members, invalid evidence IDs, unsupported claims,
unknown fields, empty content, length finish reason, truncated and malformed
JSON, root array, prose, repair success/failure, severe unsafe output, and
transient success/failure sequences.

The acceptance test uses mocked Provider transports only. It does not call
DeepSeek.

## 27. Before/after fixture results

The deterministic fixture summary is:

| Result | Previous behavior | New behavior |
| --- | ---: | ---: |
| complete | 5 | 2 |
| repaired | 7 | 7 |
| partial | 5 | 9 |
| fallback | 5 | 4 |
| security rejections | 1 | 1 |

The four result-state counts cover 22 corpus cases; one case is the explicit
security rejection. The corpus demonstrates policy behavior only and is not a
production acceptance-rate estimate. The maximum Provider-call contract is
three, tested independently with two primary attempts plus one repair.

## 28. Backend tests

Focused acceptance tests cover JSON Output parameters and prompt contract,
thinking disabled/enabled, model validation, token bounds and length
classification, empty/timeout/429/5xx retry, non-retryable 4xx, maximum call
count, repair success/failure and severe-output blocking, aliases/nulls/
scalar-to-list/numeric/list/evidence/claim salvage, state assignment,
deterministic narratives, safe observability, idempotency replay, History
round-trip, provider-indeterminate behavior, and Java-authoritative/local
fallback preservation. Tests use mock transports/providers only.

The focused Provider/RAG/resilience/idempotency/config set passed 100 tests; the
new acceptance corpus/provider module passed 11 tests. The final complete
backend suite result is recorded in the delivery evidence section below.

## 29. Frontend tests

frontend/src/pages/V201Pages.test.jsx now covers complete, repaired, partial,
and fallback Job Summary/Match Reasons, explicit unavailable values,
malformed/null legacy values, state badges, Analyze/History consistency, and
accessibility-visible sections. The full Frontend suite passed 9 files and 70
tests. The production build passed with Vite.

## 30. PostgreSQL tests

The PostgreSQL integration suite was run against an ephemeral local Compose
database using synthetic credentials and a test database. It passed 12 tests
with zero skips. The database/container/volume were removed after the test;
production was not contacted.

## 31. Java regression validation

services/jd-normalization-service/./mvnw -B -ntp verify passed 46 tests with
zero failures, errors, or skips. The normalization-only container smoke and the
full-profile container smoke passed using ephemeral local resources. The
candidate integration job also passed its local, shadow, authority, replay,
fallback, restart, persistence, and synthetic-sample validations. Java source,
policy, dictionary, and runtime configuration were unchanged.

## 32. Full CI results

Local final checks passed as follows:

- Backend complete suite: 509 tests passed, 12 existing PostgreSQL opt-in
  tests skipped when the suite was run without PostgreSQL.
- Focused Provider acceptance module: 12 tests passed.
- Frontend: 9 test files and 70 tests passed; production build passed.
- PostgreSQL integration: 12 tests passed with zero skips against an ephemeral
  local PostgreSQL database.
- Java Maven verify: 46 tests passed with zero failures, errors, or skips;
  normalization-only, full-profile, and candidate smoke validations passed.
- OpenAPI inspection: OpenAPI 3.1.0, 39 paths, and POST /api/analyze present.
- Python dependency inspection: pip check reported no broken requirements.
- Shell validation: bash -n and ShellCheck passed; repository tracked-output
  and credential scans passed with the synthetic unsafe-output fixture
  explicitly excluded by path.
- git diff --check passed.

The GitHub PR check results are recorded after the PR is pushed. No deployment
is part of this work.

## 33. Changed files

The implementation changes are grouped as follows:

- Provider/configuration: .env.example, backend/config.py,
  backend/legacy_application.py, backend/monitoring_service.py,
  backend/safe_prompt.py, backend/analysis_contract.py,
  backend/analysis_fallback.py.
- Existing model-path references and documentation: job/material/agent-run
  files, README.md, docs/ARCHITECTURE.md, and docs/ANALYZE_IDEMPOTENCY.md.
- Regression tests and synthetic corpus: backend/test_deepseek_provider_acceptance.py,
  modified backend tests, backend/fixtures/deepseek_provider_acceptance_v1/.
- Frontend: frontend/src/legacy-workspace.jsx,
  frontend/src/pages/V201Pages.test.jsx, and frontend/src/styles.css.
- Candidate test adapter: ops/candidate/java-normalization/candidate_runtime.py.
- Documentation: docs/DEEPSEEK_PROVIDER_ACCEPTANCE.md, this report, and the
  Work Report index.

No Java runtime source or Alembic migration is in the changed-file set.

## 34. Commit SHAs

The four implementation commits are:

1. 8b4fe51 — feat: add structured DeepSeek provider acceptance path
2. aeb7473 — test: add acceptance corpus and narrative coverage
3. 0ae5fd8 — test: add backend and frontend acceptance regressions
4. db180eb — docs: record DeepSeek acceptance hardening

The final delivery-evidence update commit is added after PR creation.

## 35. Pull request URL

The final pull request URL is recorded after the PR is created and pushed.

## 36. Risks and negative effects

The bounded retry and repair paths can increase worst-case latency and token
cost. An ambiguous timeout may result in duplicate Provider billing. Salvage
can accept lower-fidelity but safe analysis as partial, so consumers must
respect the state and warning metadata. Changing the documented default away
from a deprecated alias may require operator review of model availability.
Explicit unavailable narrative text is intentionally more visible than the
previous null/hidden behavior.

## 37. Rollback plan

Rollback is configuration- and code-revert based. Restore the previous operator
model and output-token settings, disable thinking, or revert the PR; no
database downgrade is required. The application version remains 2.0.5 and the
provisional eventual patch release v2.0.6 was not bumped here.

## 38. Deferred items

Strict Function Calling and multi-call response splitting are deferred
candidate experiments. They are not enabled by this patch. A future
experiment would need separate cost, latency, ordering, security, and
reconciliation evidence.

## 39. Migration confirmation

No Alembic migration was added or edited. Existing monitoring/history storage
was reused.

## 40. Java confirmation

Java source, Java normalization mode, policy, dictionary, image, and runtime
configuration were unchanged.

## 41. Production confirmation

Production was not modified, deployed, queried, or used for traffic generation.

## 42. User-content confirmation

No production Resume, JD, prompt, History, Provider body, or other user content
was inspected. All new fixtures are synthetic.

## 43. External-LLM confirmation

No DeepSeek or other external LLM was called. Provider behavior was tested with
mocks and local synthetic responses.

## 44. Image/deployment/release confirmation

No image was published, no deployment was performed, no tag or Release was
created, and no application version was bumped.

## Delivery evidence

Local evidence is complete as documented in section 32. The PR URL, final
delivery-evidence commit SHA, and required GitHub check results are added after
the branch is pushed and the checks complete.
