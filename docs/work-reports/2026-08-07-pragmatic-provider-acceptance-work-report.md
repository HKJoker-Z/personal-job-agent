# Pragmatic DeepSeek Provider Acceptance and Prompt Simplification

Date: 2026-08-07

Decision: **NO-GO** for a production candidate. The implementation and all
offline safety gates passed, but the one authorized real-provider cohort
accepted 6/10 and selected fallback 4/10, below the revised 7/10 and 3/10
gate. No second cohort was run.

## 1. Repository

Repository: <https://github.com/HKJoker-Z/personal-job-agent>

The work was based on the `main` branch and continued on
`fix/pragmatic-provider-acceptance`.

## 2. Starting main commit

Starting `main` commit:

`2e154b689de8deacbadb759a151dc027df8b4efe` — merge of Provider deadline
enforcement PR #56.

## 3. Treatment of PR #57

PR #57 was not merged or cherry-picked. At the time of this report it remained
open, CLEAN, and MERGEABLE at head
`db1cfac86bc393ac85a85b424688aa126a42dd19`:
<https://github.com/HKJoker-Z/personal-job-agent/pull/57>

The PR changes were classified as follows:

- dedicated direct-network production behavior: `backend/deepseek_client.py`,
  configuration, Compose/environment wiring, and Provider construction;
- bounded Provider error classification: Provider error, monitoring, deadline,
  adapter, and related test changes;
- candidate-only diagnostics: direct-connectivity, transport-attribution, and
  real-candidate runners and tests;
- documentation: DeepSeek reports, acceptance documentation, and report index.

This branch retained only the independent acceptance and prompt work. It does
not change production networking. Recommendation: reduce PR #57 to diagnostics
and an optional future networking experiment; do not merge its direct-network
production behavior on the current evidence.

## 4. Production baseline

- stable production version: `v2.0.5`;
- Alembic current/head: `20260730_07`;
- JD normalization mode: `java`;
- Java policy: `jd-normalization-v1`;
- skill dictionary: `skills-v1`;
- `/api/analyze` remains synchronous;
- Version 2.0.6 remains unreleased.

Production was not changed.

## 5. Reason for changing the acceptance philosophy

The previous direct-network evidence showed that safe imperfect Provider
responses were being counted against acceptance even when Backend-owned score,
evidence, Job Summary, Match Reasons, and deterministic fallback remained
valid. Product approval therefore changed the candidate target from accepted
Provider results of at least 8/10 to at least 7/10, with fallback at most
3/10, while retaining all hard safety and correctness gates.

The deterministic fallback is an intentional availability state, not a system
crash. This change makes that policy explicit and moves quality imperfections
from whole-response rejection to bounded field-level salvage.

## 6. Previous Provider schema

The previous prompt requested seven top-level model-owned fields:

`matched_skills`, `missing_skills`, `unknown_skills`,
`concise_dimension_assessments`, `evidence_references`,
`unsupported_claim_candidates`, and `concise_recommendations`.

This made the model responsible for reproducing deterministic skill state,
dimension scores, internal evidence IDs, unsupported-claim bookkeeping, and
recommendations in one nested object.

## 7. Simplified Provider schema

The active prompt now requests one shallow JSON object with four bounded
narrative fields:

```json
{
  "job_summary": "short summary",
  "match_reasons": ["short reason"],
  "recommendations": ["short recommendation"],
  "resume_improvements": ["short improvement"]
}
```

Bounds are 480 characters for the summary, at most five match reasons, at most
five recommendations, and at most four resume improvements, with bounded item
lengths. Legacy seven-field responses remain accepted as compatibility input,
but they are not authoritative in the active Analyze path.

## 8. Backend-owned fields removed from model authority

The model no longer determines final values for:

- matched, missing, and unknown skill state;
- final Match Score and scoring breakdown;
- ATS keyword overlap;
- evidence mapping and Project Knowledge source IDs;
- evidence validity and claim reconciliation;
- security decisions, retrieval metadata, and other Backend bookkeeping.

The Backend derives skill overlap from sanitized Resume/JD text, recalculates
scoring, validates evidence against the current request, and deterministically
completes safe Job Summary and Match Reasons values. User-visible legacy
sections remain in the public result shape.

## 9–10. Prompt size and A/B comparison

Using the same synthetic Resume, JD, and one Project Knowledge chunk, the
measured prompt comparison was:

| Measure | Previous prompt/schema | Simplified prompt/schema |
|---|---:|---:|
| Prompt characters | 3,120 | 1,782 |
| Approximate tokens (`characters / 4`) | 780 | 446 |
| Example object count | 4 | 1 |
| Requested active fields | 7 | 4 |
| Nested model-owned structures | dimension/evidence objects | none |

The old fixture corpus contained 23 cases and recorded the old distribution as
complete 5, repaired 7, partial 5, fallback 5, plus one security rejection.
The new 22-case pragmatic corpus recorded complete 1, repaired 2, partial 14,
and fallback 5. These are different synthetic corpora designed to exercise
different boundaries; the comparison validates parser behavior and contract
shape, not real Provider quality.

## 11. Prompt simplifications

The prompt order is now:

1. one short role statement;
2. the security and untrusted-data boundary;
3. Resume;
4. untrusted JD;
5. at most three short Project Knowledge evidence chunks;
6. one concise output instruction;
7. one small valid JSON example.

It retains JSON Output mode, thinking disabled by configuration, current model
selection, input sanitization, prompt-marker protection, and the established
security boundary. It removes repeated schema text, score/evidence-ID duties,
verbose reasoning requests, repeated input copies, and redundant negative
instructions.

## 12. Response normalization rules

The active response normalizer safely handles:

- missing narrative fields, null strings, null lists, and empty values;
- supported aliases such as `summary`, `reasons`, `suggestions`, and
  `improvements`;
- a scalar string where a list is expected;
- invalid individual list items while preserving valid peers;
- bounded text and list lengths;
- unknown harmless top-level or nested fields;
- legacy numeric strings and bounded score values for compatibility input;
- duplicate list entries;
- model-supplied scores as non-authoritative input;
- JSON surrounded by short prose or Markdown fences through existing local
  extraction.

The normalizer never evaluates model text as code and never relies on raw
exception or Provider content in monitoring metadata.

## 13. Hard-rejection rules

Whole-response rejection remains limited to:

- secret or credential leakage;
- system/developer prompt or internal-marker leakage;
- severe tool, role, or data-exfiltration manipulation;
- a root value that cannot be bounded into an object;
- no meaningful analysis field after local normalization and permitted repair;
- absolute safety-limit violations;
- public serialization failure.

Missing optional fields, bad individual items, invalid evidence IDs, mediocre
prose, harmless metadata, and model-score disagreement do not by themselves
cause fallback.

## 14. Field-level salvage rules

The active order is security screen, local JSON extraction, alias/type
normalization, valid-field salvage, invalid-evidence cleanup, deterministic
completion, state assignment, and only then the existing one format-only repair
when local salvage cannot recover useful content and the deadline permits it.

The implementation does not add a Provider call or increase the retry/call
limits. A useful response with bounded cleanup becomes `partial`.

## 15. Evidence-handling changes

The Backend remains the evidence authority. Model-generated evidence IDs are
optional compatibility input rather than a prerequisite for narrative
acceptance. Invalid or unsupported references are removed, independently
validated matches are retained, and the remaining result is marked `partial`.

Unsupported narrative claims are split into bounded sentences and removed only
when the existing claim validator cannot ground them in the sanitized Resume,
JD, or retrieved Project Knowledge. Safe peer sentences survive.

## 16. Scoring authority

Final Match Score and deterministic scoring breakdown remain Backend-owned. A
model-provided score is ignored as authority and cannot replace or compete with
the Backend score in the public result.

## 17. State semantics

- `complete`: useful canonical Provider content with no meaningful field-level
  salvage;
- `repaired`: bounded syntactic extraction or the existing format-only repair
  was required while useful content survived;
- `partial`: useful content survived normalization, deterministic completion,
  invalid-item/evidence cleanup, or unsupported-claim removal;
- `fallback`: no safe useful Provider analysis remained, the Provider calls
  failed, or severe output security required rejection.

## 18. Fallback product semantics

Fallback remains a stable graceful-degradation result. It supplies Backend-owned
score, matched/missing skills where deterministically available, stable Job
Summary and Match Reasons representations, recommendations when possible,
stable History persistence, and the same public shape. The frontend continues
to render the result state and major sections rather than treating fallback as
a crash.

## 19. Security guarantees retained

Input scanning, Resume/JD sanitization, the authoritative Java-normalized JD
second scan, Project Knowledge scanning, output secret scanning,
prompt/system-leakage blocking, evidence reconciliation, claim grounding,
safe metadata, and final serialization scanning remain enabled. No raw Resume,
JD, prompt, Provider body, reasoning content, API key, or proxy value was added
to logs or reports.

## 20. Deadline, retry, and call-limit guarantees retained

The implementation did not change the authoritative contracts:

- Provider phase deadline: 130 seconds;
- Analyze safety deadline: 175 seconds;
- external client safety assumption: 180 seconds;
- finalization reserve: 30 seconds;
- SDK automatic retries: zero;
- application retry: at most one;
- format-only repair: at most one;
- maximum Provider calls: three.

Each Provider attempt continues to derive its bounded timeout from the same
monotonic absolute deadline. No network mode, timeout, Java behavior, or
Alembic migration was changed.

## 21. Synthetic acceptance corpus results

The new corpus has 22 synthetic cases covering canonical output, missing and
null fields, aliases, scalar/list mismatches, unknown fields, invalid evidence,
unsupported claims, invalid items, score disagreement, malformed optional data,
minimal useful output, prose/fenced JSON, severe secret and prompt leakage,
root arrays, plain prose, and empty output.

Results: complete 1, repaired 2, partial 14, fallback 5. The five fallbacks
were the deliberate hard-rejection cases: severe secret leakage, system-marker
leakage, root array, prose with no recoverable JSON, and empty output.

## 22. Prompt A/B fixture comparison

The local comparison proved that the simplified prompt is 43% shorter by
characters, uses one root example object instead of four nested example
objects, requests four fields instead of seven, preserves all security
boundaries, and removes deterministic Backend fields from the model contract.
The parser corpus showed that safe imperfect values overwhelmingly became
`partial`; this does not claim improved real-provider reliability by itself.

## 23–24. Real candidate execution and states

Exactly one authorized sequential real-provider cohort was run using the
current main networking behavior, current model, JSON Output, thinking
disabled, existing token budgets, existing deadlines, and existing retry
limits. No production data was used and no individual failure was rerun.

| State | Count |
|---|---:|
| Complete | 5 |
| Repaired | 0 |
| Partial | 1 |
| Fallback | 4 |
| Accepted (`complete + repaired + partial`) | 6/10 |

## 25. Provider failure categories

The bounded aggregate reported seven `connect_timeout` retry observations and
four final `provider_call_failed` fallbacks. Four cases had an `invalid` parse
outcome after Provider failure; six had a canonical parse outcome. No format
repair was invoked. No response body or exception text was retained.

## 26. Retry and repair counts

The cohort used 7 application retries and 0 format repairs. The largest primary
attempt count was two, preserving the existing one-retry contract.

## 27. Maximum Provider calls

Maximum Provider calls per execution: 2. This is below the unchanged maximum
of 3.

## 28. Token observations

Only bounded aggregates were retained:

- input tokens: min 0, max 542, total 3,172;
- output tokens: min 0, max 225, total 1,133;
- total tokens: min 0, max 745, total 4,305.

The configured budgets remained 1,600 primary, 2,400 length retry, 1,000
repair, and 5,000 configured maximum.

## 29. Latency observations

Provider duration was median 6,415.687 ms, p95 8,229.208 ms, max 8,229.208
ms. End-to-end duration was median 6,417.258 ms, p95 8,244.054 ms, max
8,244.054 ms. No operation survived its deadline.

## 30. Job Summary result

Job Summary was present in 10/10 executions; no explicit-unavailable result
was needed.

## 31. Match Reasons result

Match Reasons was present in 10/10 executions; no explicit-unavailable result
was needed.

## 32. Security result

Security rejections: 0. The candidate safe-log inspection passed. No secret,
prompt-marker, body, or reasoning leakage was observed in bounded metadata.

## 33. Serialization result

Public contract failures: 0. All ten execution records remained safely
serializable, and the deterministic fallback shape remained valid.

## 34. Idempotency and History result

The existing idempotency and History regression tests remained green, including
completed replay with zero Provider calls and exactly-once finalization. The
isolated candidate runner itself does not persist product History or exercise a
replay, so those candidate fields were correctly not applicable.

## 35. Backend validation

- focused acceptance, resilience, prompt, and pragmatic tests: 59 passed;
- complete Backend suite: 555 passed, with 12 PostgreSQL-only tests skipped by
  opt-in in the SQLite run;
- Python compileall: passed;
- no CI or automated test called DeepSeek.

## 36. PostgreSQL validation

An isolated PostgreSQL 16.9 container and dedicated test database were used.
The PostgreSQL integration suite passed 12/12 with zero skips. The container
was stopped afterward; the production PostgreSQL container was not used.

## 37. Frontend validation

Vitest passed 70/70 tests. The production frontend build passed.

## 38. Java validation

`services/jd-normalization-service/./mvnw -B -ntp verify` passed with 46 tests,
zero failures, zero errors, and zero skipped tests. Java source and policy were
unchanged.

## 39. Frontend dependency warning status

The locked state remains React 19.2.7, React DOM 19.2.7, and
`react-router-dom` 7.18.1. Local `npm audit --omit=dev` reports the known high
severity React Router RSC CSRF advisory for the locked 7.12–8.2 range. The
audit suggested `react-router-dom` 7.11.0 rather than a patch-level update.
No unrelated downgrade, major migration, or dependency change was included;
this remains a separate security/dependency task.

## 40. Changed files

Implementation and validation changes:

- `.github/workflows/ci.yml`;
- `backend/analysis_contract.py`;
- `backend/candidates/deepseek_provider_real_candidate.py`;
- `backend/fixtures/deepseek_provider_acceptance_v2/corpus.json`;
- `backend/legacy_application.py`;
- `backend/safe_prompt.py`;
- `backend/test_analyze_idempotency.py`;
- `backend/test_deepseek_provider_acceptance.py`;
- `backend/test_pragmatic_provider_acceptance.py`;
- `backend/test_safe_prompt.py`;
- `docs/ARCHITECTURE.md`;
- `docs/DEEPSEEK_PROVIDER_ACCEPTANCE.md`;
- `frontend/src/pages/ArchitecturePage.jsx`;
- this report and `docs/work-reports/README.md`.

`docs/PROJECT_KNOWLEDGE.md`, Java sources, Alembic revisions, production
Compose networking, and production environment files were not changed.

## 41. Commits

- `62e9d6d` — `feat: simplify DeepSeek provider acceptance contract`;
- `0369598` — `fix: retain established prompt security boundary`;
- report/index commit: recorded after this report is added.

## 42. Pull request

PR #58: <https://github.com/HKJoker-Z/personal-job-agent/pull/58>

Title: `Fix: Simplify DeepSeek output contract and acceptance`

## 43. Decision

**NO-GO.** Offline implementation and safety validation passed, but the one
authorized real-provider cohort failed the revised product gate with accepted
6/10 and fallback 4/10. The cohort was not repeated.

## 44. Revised production gate

The later first-ten-production-request gate remains:

- accepted Provider results (`complete + repaired + partial`) at least 7/10;
- fallback at most 3/10;
- all ten inside the deadline;
- Job Summary and Match Reasons present or explicitly unavailable 10/10;
- zero security, secret-leakage, serialization, duplicate-History, and
  idempotency defects;
- maximum Provider calls at most three;
- Java and PostgreSQL schema unchanged.

After the first 20 production analyses, investigate or roll back if three
fallbacks occur consecutively, fallback exceeds 40%, public latency exceeds the
configured safety contract, or any security/serialization/duplicate-History
defect appears. A single occasional fallback is an allowed graceful-degradation
state.

## 45. Risks and accepted negative effects

- The smaller contract can produce less detailed narrative content.
- More outputs may be `partial` because cleanup is now visible in state
  metadata.
- Deterministic skill matching uses the repository’s bounded skill dictionary;
  unsupported vocabulary remains unavailable rather than invented.
- Unsupported narrative sentences can be removed, leaving a shorter result.
- The one real cohort used current main environment-proxy networking and
  recorded seven `connect_timeout` retry observations; this phase does not
  attribute or fix that independent networking issue.
- The React Router warning remains unresolved in this PR.

These effects are accepted only with the hard safety, deadline, serialization,
idempotency, History, and fallback guarantees retained.

## 46. Rollback plan

Do not deploy this branch. The immediate rollback is configuration-free because
production remains on v2.0.5/main. If the PR is later merged and needs to be
reverted, use a normal Git revert or return to the immutable v2.0.5 component
artifacts; no Alembic downgrade or data migration is required.

## 47. Recommendation for PR #57

Keep PR #57 open only as a separately reviewed diagnostics/optional networking
experiment, or reduce it to diagnostics-only. Do not make its dedicated direct
DeepSeek networking the production prerequisite for this acceptance change.

## 48. Production untouched confirmation

No production deployment, runtime replacement, Compose change, production
database access, or production configuration mutation occurred.

## 49. Java and Alembic unchanged confirmation

Java normalization behavior, `jd-normalization-v1`, `skills-v1`, Alembic
revision `20260730_07`, and the PostgreSQL schema were unchanged.

## 50. No production/user content inspected confirmation

Only repository code, synthetic fixtures, and bounded aggregate metadata were
used. No production Resume, JD, Project Knowledge content, History, Provider
body, or user content was inspected. The approved candidate secret mechanism
was used without printing or persisting the secret; its value was not inspected.

## 51. No release activity confirmation

No version bump, deployment, release image publication, tag, or GitHub Release
occurred. Version 2.0.6 remains unreleased.

## Next prerequisite

Before any production candidate, resolve or explicitly authorize an
environment-proxy/Provider availability investigation for the seven bounded
`connect_timeout` observations, then obtain a new ten-case authorization. Do
not rerun this cohort merely to replace its NO-GO result.
