# Java JD Normalization Service Phase 1 Work Report

## 1. Repository

- Repository: `HKJoker-Z/personal-job-agent`
- Repository URL: <https://github.com/HKJoker-Z/personal-job-agent>
- Stable Personal Job Agent version at the start: `2.0.4`
- Existing Personal Job Agent Alembic head at the start: `20260724_06`
- Architecture after this work: one existing FastAPI modular monolith plus one
  small, bounded, independent Java portfolio service

This implementation does not describe the repository as a general microservice
architecture.

## 2. Design audit PR merge commit

The documentation-only design audit was pull request
[#25](https://github.com/HKJoker-Z/personal-job-agent/pull/25), merged with a
merge commit:

`1e8b3b4e2ea52393efc8e8ce8c7da09aadae5572`

The PR changed only:

- `docs/work-reports/2026-07-28-java-jd-normalization-service-design-audit-work-report.md`
- `docs/work-reports/README.md`

It changed no runtime behavior. All ten PR checks passed before merge. The
post-merge `main` CI run
[#30330425023](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30330425023)
also passed. The audit recommendation remained the bounded Phase 1 HTTP core
described in Sections 30 and 31 of that report.

## 3. Starting main commit

Implementation started from:

`1e8b3b4e2ea52393efc8e8ce8c7da09aadae5572`

Local `main` and `origin/main` both resolved to this commit after the
documentation merge. The pull used fast-forward-only behavior, and the
post-merge `main` workflow completed successfully.

## 4. Implementation branch

`feat/java-jd-normalization-service-phase-1`

## 5. Technology versions

| Component | Version |
|---|---|
| Java baseline | 21 |
| Local validation JDK | Eclipse Temurin 21.0.12+8 LTS |
| Spring Boot | 3.5.16 |
| Spring Framework / Spring MVC | 6.2.19, managed by Spring Boot |
| Spring Security | 6.5.11, managed by Spring Boot |
| Springdoc OpenAPI WebMVC API | 2.8.17 |
| Maven distribution | 3.9.16 through the Maven Wrapper |
| Maven Wrapper script | 3.3.4, `only-script` distribution |
| JUnit Jupiter | 5.12.2, managed by Spring Boot |
| Mockito | 5.17.0, test-only and managed by Spring Boot |

No Spring Boot-managed transitive dependency version was overridden.

## 6. Exact implemented scope

Phase 1 creates one independent service at:

`services/jd-normalization-service/`

Its only product endpoint is:

`POST /api/v1/job-descriptions/normalize`

The endpoint accepts bounded UTF-8 JSON, deterministically normalizes Job
Description text and explicitly supplied metadata, calculates a content hash,
extracts lexical skill matches from a reviewed dictionary, and returns a
bounded response. Request correlation, internal-key authentication, stable
errors, status-only health probes, JSON OpenAPI, structured console logging,
unit tests, MockMvc tests, and a path-filtered CI workflow are included.

## 7. Scope exclusions

This phase does not implement:

- PostgreSQL, JDBC, JPA, ORM entities, repositories, or Flyway;
- persistence, idempotent persistence, CRUD, version history, pagination,
  optimistic locking, ETag, or `If-Match`;
- Docker, Compose, image publication, release, deployment, or production
  configuration;
- FastAPI integration or changes to the existing Backend, Frontend, Redis,
  Worker, Outbox, Nginx, Alembic, release workflow, or production scripts;
- URL fetching, scraping, file upload, Resume matching, ranking, job
  applications, task creation, or autonomous decisions; or
- LLM, DeepSeek, Spring AI, or arbitrary network calls.

## 8. Package structure

The implementation uses the approved package-by-feature structure:

```text
services/jd-normalization-service/
  .env.example
  .gitignore
  README.md
  pom.xml
  mvnw
  mvnw.cmd
  .mvn/wrapper/maven-wrapper.properties
  src/main/java/io/github/hkjokerz/jobagent/jdnormalization/
    JdNormalizationServiceApplication.java
    config/ServiceProperties.java
    normalization/
      JobDescriptionNormalizer.java
      NormalizationPolicy.java
      NormalizationResult.java
      SkillDictionary.java
      SkillDictionaryLoader.java
      SkillExtractor.java
      TextNormalizer.java
      UrlNormalizer.java
    security/
      InternalApiKeyFilter.java
      SecurityConfiguration.java
    web/
      ApiExceptionHandler.java
      NormalizationController.java
      RequestIdFilter.java
      dto/
        ApiErrorResponse.java
        NormalizeJobDescriptionRequest.java
        NormalizeJobDescriptionResponse.java
  src/main/resources/
    application.yml
    skills/skills-v1.json
  src/test/java/io/github/hkjokerz/jobagent/jdnormalization/
    JdNormalizationServiceApplicationTest.java
    normalization/
      JobDescriptionNormalizerTest.java
      SkillDictionaryLoaderTest.java
      SkillExtractorTest.java
      TextNormalizerTest.java
      UrlNormalizerTest.java
    web/
      NormalizationApiWebTest.java
      RequestIdAndErrorWebTest.java
      SecurityWebTest.java
  src/test/resources/
    application-test.yml
    skills/invalid-duplicate-aliases.json
```

The only file outside the service and mandatory documentation paths is the
approved `.github/workflows/jd-normalization-service-ci.yml`.

## 9. Maven dependencies and plugins

Direct runtime dependencies are limited to:

- Spring Boot Web;
- Spring Boot Validation;
- Spring Boot Security;
- Spring Boot Actuator;
- Springdoc OpenAPI Starter WebMVC API; and
- the optional Spring Boot configuration processor.

Test dependencies are Spring Boot Test and Spring Security Test. Mockito is
used only at the HTTP exception boundary to prove the safe `500` contract.
The only explicitly declared build plugin is the Spring Boot Maven Plugin.

The dependency tree was inspected. It contains no JPA, JDBC, PostgreSQL,
Flyway, Testcontainers, H2, Redis, Kafka, RabbitMQ, Elasticsearch, Spring AI,
Lombok, MapStruct, or Docker dependency.

## 10. Normalization algorithm

The immutable policy is `jd-normalization-v1`. It applies:

1. request byte and source Unicode code-point limits;
2. U+0000 removal;
3. NFC normalization;
4. CRLF, CR, U+0085, U+2028, and U+2029 conversion to LF;
5. per-line horizontal Unicode whitespace collapse to one ASCII space;
6. per-line leading and trailing horizontal whitespace removal;
7. preservation of every nonblank line boundary, heading punctuation, and
   bullet marker;
8. collapse of multiple blank lines to one blank line;
9. removal of leading and trailing blank lines; and
10. production of no trailing newline.

It does not lowercase the document, translate, spell-check, infer metadata,
rewrite headings, reorder lines, remove bullets, use an LLM, or access a
network.

## 11. Unicode and code-point behavior

The request byte limit is 512 KiB. The request wrapper buffers at most the
bounded body, rejects an extra byte, strictly decodes UTF-8, and rejects raw
NUL byte patterns that could otherwise be auto-detected as UTF-16/UTF-32 JSON.
Escaped JSON `\u0000` remains valid input and is removed by the policy.

`raw_text` is limited to 100,000 Unicode code points using
`String.codePointCount`, not UTF-16 `String.length`. Tests prove acceptance of
100,000 supplementary emoji code points and rejection at 100,001. NFC, every
listed line separator, horizontal Unicode spaces, leading/trailing spaces,
blank-line collapse, bullet/heading preservation, empty-after-normalization,
and the no-trailing-newline rule are covered.

## 12. Metadata normalization

`metadata` is optional, and each field is independently optional. Title,
company, and location:

- are limited to 200 Unicode code points;
- have NUL removed;
- are normalized to NFC;
- have all internal Unicode whitespace collapsed to one ASCII space;
- are trimmed; and
- are rejected when explicitly supplied but blank after normalization.

No field is inferred from `raw_text`. Boundary tests use supplementary Unicode
characters to distinguish code points from UTF-16 code units.

## 13. URL normalization

An optional canonical URL must be an absolute HTTPS URI. The implementation:

- lowercases the scheme and IDNA ASCII host;
- removes default HTTPS port 443;
- removes the fragment;
- normalizes dot segments;
- converts an empty path to `/`;
- preserves path case and query order/meaning;
- uppercases percent-encoding hexadecimal digits;
- retains tracking parameters; and
- never contacts the host.

User information, relative URLs, non-HTTPS URLs, whitespace, malformed
percent-encoding, invalid ports, blank values, and normalized values over 2,048
ASCII characters return bounded validation errors without echoing the URL.

## 14. Content hash

`content_hash` is exactly:

`SHA-256(UTF-8(normalized_text))`

It is formatted as 64 lowercase hexadecimal characters. The known vector for
`abc` is tested as
`ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`.
Ten repeated normalizations of the same request are asserted equal.

## 15. Skill dictionary

`src/main/resources/skills/skills-v1.json` contains 26 reviewed entries for
the bounded portfolio target. It includes Java, Spring Boot, Python, FastAPI,
PostgreSQL, Redis, Docker, Kubernetes, React, TypeScript, JavaScript, Linux,
REST, Git, Maven, JPA, Hibernate, Flyway, AWS, Azure, CI/CD, C++, C#, .NET, and
Node.js, plus one explicit `C language` phrase.

Each record has a lowercase canonical ID, display name, one or more aliases,
and `TOKEN` or `PHRASE` match type. Startup rejects missing fields, invalid or
duplicate IDs, normalized alias collisions, unsupported match types, blank
aliases, the wrong dictionary version, and more than 256 entries. Aliases are
NFC/whitespace/case normalized and compiled with `Pattern.quote`. Unsafe
one-letter/common-word aliases such as `r`, `go`, and `js` are absent.

## 16. Skill classification rules

Classification is deterministic lexical matching, not semantic understanding.
The versioned required headings are `required`, `required skills`,
`requirements`, and `qualifications`, with an optional colon. Preferred
headings are `preferred`, `preferred skills`, `nice to have`, `bonus`, and
`desirable`, with an optional colon.

Bounded line cues include required/requirements/must-have/qualifications and
preferred/nice-to-have/bonus/desirable. A generic colon-terminated heading
resets classification to mentioned. Repeated aliases emit one canonical skill.
Precedence is required over preferred over mentioned. Every array is sorted by
canonical ID, and the total unique result is bounded at 256.

Tests cover Java, aliases, Unicode/case behavior, C++, C#, .NET, Node.js,
embedded-token false positives, precedence, deduplication, and deterministic
ordering.

## 17. Request contract

The endpoint consumes `application/json` containing:

```json
{
  "raw_text": "Senior Backend Engineer\r\nRequired:\r\n- Java 21",
  "metadata": {
    "title": "Senior Backend Engineer",
    "company": "Example Ltd",
    "location": "Hong Kong",
    "canonical_url": "https://jobs.example.test/backend-engineer"
  }
}
```

`raw_text` is required. Unknown JSON properties and malformed/non-UTF-8 JSON
are rejected. The body, text, metadata, and URL bounds are enforced as
described above.

## 18. Response contract

A successful response contains only:

- `normalized_text`;
- `content_hash`;
- `normalization_policy_version`;
- `skill_dictionary_version`;
- `required_skills`;
- `preferred_skills`;
- `mentioned_skills`; and
- `metadata`.

Each skill object contains only `id` and `name`. The response includes
`Cache-Control: no-store` and the trusted `X-Request-ID`.

## 19. Request ID

The service accepts exactly one `X-Request-ID` matching:

`[A-Za-z0-9][A-Za-z0-9._:-]{0,63}`

An absent value produces UUIDv4. Invalid, overlong, or multiple values produce
`400 INVALID_REQUEST_ID` with a new UUIDv4 in both the header and error body.
The trusted ID is placed in SLF4J MDC and cleared in a nested `finally`, even
when response finalization fails. It is correlation metadata only; it grants
no authority and performs no deduplication.

## 20. Authentication

Protected routes require:

`Authorization: Bearer <internal-api-key>`

The key is read from `JD_NORMALIZATION_API_KEY`. When authentication is
enabled, startup requires at least 32 UTF-8 bytes. The application hashes the
expected and candidate values to fixed-length SHA-256 arrays and compares them
with `MessageDigest.isEqual`. The bound plaintext property is cleared after
filter creation. The key and Authorization header are never logged or returned.

Authentication can be disabled only when the active profile list is exactly
`dev` and the configured server address is loopback. Startup tests prove
missing/short key rejection and rejection of disabled authentication outside
the exact dev-loopback mode. CORS, HTTP Basic, form login, request cache,
logout, and stateful sessions are disabled. Browser Session cookies are not
authentication.

## 21. Error envelope and codes

Every API error uses:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "The request could not be processed.",
    "request_id": "safe-request-id",
    "details": {}
  }
}
```

All four inner fields are mandatory, and `details` is always an object.
Implemented codes are:

- `INVALID_REQUEST`
- `INVALID_REQUEST_ID`
- `UNAUTHORIZED`
- `PAYLOAD_TOO_LARGE`
- `VALIDATION_FAILED`
- `EMPTY_JOB_DESCRIPTION`
- `UNSUPPORTED_MEDIA_TYPE`
- `METHOD_NOT_ALLOWED`
- `ROUTE_NOT_FOUND`
- `INTERNAL_ERROR`

Validation details contain only a safe field name, stable rule code, and a
configured maximum where relevant. Responses contain no stack trace, exception
message/class, raw text, metadata value, URL, key, Authorization header,
filesystem path, hostname, or internal configuration.

## 22. Actuator

The only exposed Actuator routes are unauthenticated, status-only:

- `/actuator/health`
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Health component/details output and the Actuator discovery page are disabled.
Tests and smoke checks prove `/actuator` and `/actuator/metrics` return the
stable route-not-found envelope. No env, configprops, beans, mappings, heapdump,
threaddump, loggers, or metrics endpoint is exposed.

## 23. OpenAPI

Springdoc exposes JSON at `/v3/api-docs`. It is protected by the internal key
outside the exact `dev` profile. The generated document contains one product
path, the Bearer security scheme, `X-Request-ID`, success DTOs, and the shared
error schema. `/v3/api-docs.yaml` is explicitly not exposed.

There is no Swagger UI dependency. `/swagger-ui/index.html` returns the stable
route-not-found envelope.

## 24. Logging and secret policy

Spring Boot ECS structured JSON console logging is enabled. The bounded HTTP
completion event contains timestamp, level, logger, event message, trusted
request ID, method, best route template when available, status, duration, and
bounded response size. The normalization event uses structured key/value
fields for policy/dictionary versions, category counts, normalized code-point
count, and duration.

Logs omit raw and normalized Job Description text, metadata values, canonical
URLs, hashes unless needed, API keys, Authorization headers, request/response
bodies, and exception messages that could contain input.

## 25. Unit tests

There are 28 normalization-focused unit tests:

- `TextNormalizerTest`: 11;
- `JobDescriptionNormalizerTest`: 3;
- `SkillDictionaryLoaderTest`: 4;
- `SkillExtractorTest`: 5; and
- `UrlNormalizerTest`: 5.

They cover the policy order and every listed text transformation, code-point
boundaries, metadata, URL behavior, known SHA-256 and repeatability vectors,
dictionary startup validation/quoting, aliases and special technology names,
false-positive boundaries, classification precedence, and deterministic
ordering.

## 26. MockMvc and web tests

There are 15 MockMvc/web tests plus one application-context test:

- `NormalizationApiWebTest`: 6;
- `RequestIdAndErrorWebTest`: 5;
- `SecurityWebTest`: 4; and
- `JdNormalizationServiceApplicationTest`: 1.

Coverage includes success, generated/accepted/invalid/multiple/overlong Request
IDs, missing/invalid keys, exact dev mode, unsafe startup rejection, malformed
JSON, unknown fields, invalid UTF-8 and UTF-16 input, wrong media type,
oversized payload, Bean Validation, empty normalized text, stable errors, 404,
405, safe 500, no response leakage, health probes, JSON-only OpenAPI, absent
Swagger UI, and absence of data-source/entity-manager beans.

## 27. Local smoke

A packaged JAR was started on loopback with an ephemeral
`openssl rand -base64 32` test key and no production configuration. Final
smoke checks proved:

| Check | Result |
|---|---|
| readiness | `200`, exactly `{"status":"UP"}` |
| authorized normalize | `200`, deterministic body/hash/skills/metadata |
| Request ID propagation | accepted ID matched response header |
| unauthorized normalize | `401 UNAUTHORIZED`, stable envelope |
| empty normalized text | `422 EMPTY_JOB_DESCRIPTION`, stable envelope |
| OpenAPI JSON | `200`, one product path, Bearer scheme, error schema, Request ID |
| OpenAPI YAML | `404 ROUTE_NOT_FOUND` |
| Swagger UI | `404 ROUTE_NOT_FOUND` |
| Actuator root/metrics | `404 ROUTE_NOT_FOUND` |

The generated key and a raw-text marker were also confirmed absent from the
structured service log. No production secret or endpoint was used.

## 28. CI workflow

`.github/workflows/jd-normalization-service-ci.yml` is path-filtered to the
service, workflow, and mandatory implementation report. It has `contents:
read`, no `pull_request_target`, and concurrency cancellation.

The job uses Java 21 and Maven caching, runs `./mvnw -B -ntp verify`, checks
patch whitespace, rejects tracked `target/`, scans the service for obvious
secrets, and uploads Surefire reports only on failure. It performs no Docker
build, Testcontainers run, image publication, release, deployment, or
production-secret access.

Third-party actions are pinned to immutable Node 24-runtime SHAs:

- `actions/checkout` v6.1.0;
- `actions/setup-java` v5.6.0; and
- `actions/upload-artifact` v6.0.0.

## 29. Changed files

The completed PR contains 41 changed files:

- one path-filtered Java workflow;
- the 38 approved service runtime/test/documentation files shown in Section 8;
- this mandatory Work Report; and
- the Work Report index update.

No pre-existing Backend, Frontend, Alembic, Compose, Nginx, Redis, Worker,
Outbox, release, deployment, production version, or Project Knowledge file was
changed.

## 30. Commit SHAs

Implementation and delivery commits before this report:

- `e55b889a6c9186c1670e681c23a0baae7414eb40` —
  `feat(java): add deterministic JD normalization core`
- `6db48c1984bcd8bfdd47e275b4fefeb293437aa5` —
  `test(java): secure and verify normalization HTTP API`
- `d9c3b407e83d7f2230ff06a8487f9aa47251c94f` —
  `fix(java): enforce bounded HTTP service surfaces`
- `815873a00d81213a628317ebbfc15c74671f81f9` —
  `ci(java): document and verify phase 1 service`
- `d177b4f5f1a09820a311307f66b03105fac60da5` —
  `ci(java): use Node 24 action runtimes`

The commit containing this report and index is the PR head after the list
above. A report cannot embed its own Git object ID because doing so changes
that ID; the immutable value is recorded by the PR history.

## 31. PR URL

Implementation PR:

<https://github.com/HKJoker-Z/personal-job-agent/pull/26>

Title:

`Java: Add deterministic JD normalization service core`

The implementation PR remains open and is not merged by this work.

## 32. Local validation results

| Validation | Result |
|---|---|
| `./mvnw -B -ntp verify` | passed, 44 tests, 0 failures/errors/skips |
| targeted normalization tests | passed, 28 tests |
| targeted web/security/context tests | passed |
| application context | passed; no DataSource or EntityManagerFactory |
| dependency tree | passed review; no forbidden Phase 2/infrastructure dependency |
| packaged loopback smoke | passed |
| OpenAPI generation/inspection | passed; one product path and JSON only |
| health surface inspection | passed; three probes only |
| `git diff --check` | passed |
| tracked `target/` check | passed |
| repository safety check | passed |
| obvious-secret scan | passed |
| approved changed-file scope | passed |

Local validation used Maven 3.9.16 and Eclipse Temurin Java 21.0.12. Tests made
no PostgreSQL, Redis, DeepSeek, production, or arbitrary external request.

## 33. GitHub CI results

At the report-authoring head `d177b4f5f1a09820a311307f66b03105fac60da5`:

- Java workflow run
  [#30412754358](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30412754358)
  passed in 27 seconds, including Java 21 setup, whitespace, tracked-output,
  secret-scan, and Maven verify steps.
- repository-wide CI run
  [#30412754352](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30412754352)
  passed all ten jobs: Backend, Frontend, PostgreSQL, backup/restore, script,
  repository-safety, production-regression, Compose, Docker build, and isolated
  mock-LLM smoke coverage.

The documentation commit containing this report triggers a final check cycle.
The final PR check rollup is authoritative because a Markdown report cannot
record the result of a workflow that is triggered by its own commit.

## 34. Risks and limitations

- Skill extraction is lexical and may miss unfamiliar aliases or misclassify
  nuanced prose and headings outside the bounded rules.
- The small reviewed dictionary is intentionally incomplete.
- Java/Unicode/URL library behavior is frozen operationally by the policy
  version; any behavior change requires a new version and regression vectors.
- A static API key represents one internal caller and is not a public
  authentication design.
- The service has no persistence or integration, so callers must retain any
  result they need.
- Public exposure still requires separately approved TLS, rate-limit, abuse,
  privacy, rotation, monitoring, and operations work.

## 35. Deviations from the approved file set

There are no runtime or test file deviations from the approved Phase 1 list.
No extra production class, interface, helper file, or test fixture was added.
Small byte-buffer/UTF-8 helper types are private nested implementation details
inside the approved `RequestIdFilter.java`.

The mandatory Work Report and index update are the only additional
documentation files, exactly as authorized.

## 36. Persistence confirmation

Persistence was not implemented. There is no database configuration,
repository, ORM entity, migration, create/read/list/update endpoint,
idempotency ledger, version history, pagination, or optimistic locking.

## 37. Docker confirmation

Docker was not implemented for the Java service. No Dockerfile, Compose file,
Docker dependency, Docker CI build, image publication, or registry action was
added.

## 38. FastAPI confirmation

FastAPI and all existing Backend/Frontend runtime files were not changed. No
HTTP client, feature flag, shared table, Session integration, Analyze routing,
or production application integration was implemented.

## 39. Production confirmation

Production was untouched. No production access, deployment, release, tag,
image publication, production secret use, runtime synchronization, or Project
Knowledge update occurred.

## 40. DeepSeek confirmation

Real DeepSeek was not called. The Java service contains no LLM dependency,
client, prompt, credential, or network-based normalization behavior.
