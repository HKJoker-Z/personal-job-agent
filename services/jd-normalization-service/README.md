# JD Normalization Service

The JD Normalization Service is a small, independent Java 21 portfolio service.
Phase 1 accepts bounded Job Description text and explicitly supplied metadata,
applies deterministic normalization, extracts lexical skill keywords from a
reviewed versioned dictionary, and returns a SHA-256 content hash.

The honest repository architecture is one existing FastAPI modular monolith
plus this one bounded Java portfolio service. The Java service does not replace
the FastAPI Analyze pipeline and does not share application state with it.

## Phase 1 scope

The only product endpoint is:

```text
POST /api/v1/job-descriptions/normalize
```

Phase 1 has no persistence, database, JPA, Flyway, idempotent create operation,
version history, pagination, Docker image, Compose service, scraping, URL
fetching, FastAPI integration, DeepSeek call, LLM use, ranking, job
application, task creation, or autonomous decision.

Future persistence and optional FastAPI HTTP integration are planned phases,
not implemented behavior. This service must not be exposed publicly without a
separately approved authentication and operations design.

## Requirements

- Java 21
- POSIX shell or Windows PowerShell/Command Prompt
- Internet access for the Maven Wrapper's first dependency download

The repository-safe Maven Wrapper downloads Maven 3.9.16. It does not require a
system Maven installation and does not commit a wrapper JAR.

## Safe local startup

Authentication is enabled by default. Generate a new local key with at least
32 random bytes and keep it only in the current shell:

```bash
export JD_NORMALIZATION_API_KEY="$(openssl rand -base64 32)"
./mvnw -B -ntp spring-boot:run
```

The default binding is `127.0.0.1:8091`. Do not put a real key in Git, command
history, screenshots, or examples.

Authentication can be disabled only for explicitly local development when the
active Spring profile is exactly `dev` and the server remains bound to a
loopback address:

```bash
SPRING_PROFILES_ACTIVE=dev \
JD_NORMALIZATION_AUTH_DISABLED=true \
JD_NORMALIZATION_BIND_ADDRESS=127.0.0.1 \
./mvnw -B -ntp spring-boot:run
```

This mode is unsafe for public or shared-network exposure. Browser session
cookies are not accepted as authentication, and CORS is disabled.

## Request

Requests must be UTF-8 JSON, no larger than 512 KiB:

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

`raw_text` is required and is limited to 100,000 Unicode code points.
`metadata` and each metadata field are optional. Title, company, and location
are each limited to 200 Unicode code points. Canonical URLs must normalize to
an absolute HTTPS URL of no more than 2,048 ASCII characters; normalization
never contacts the host.

With authentication enabled:

```bash
curl --fail-with-body \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-example-1" \
  --data '{"raw_text":"Required:\r\n- Java 21"}' \
  http://127.0.0.1:8091/api/v1/job-descriptions/normalize
```

## Response

```json
{
  "normalized_text": "Required:\n- Java 21",
  "content_hash": "ccfadb52dc7e1bb70d8700f4b1db1ed8055d0263990828da80b9ccbb5f12f68f",
  "normalization_policy_version": "jd-normalization-v1",
  "skill_dictionary_version": "skills-v1",
  "required_skills": [
    {
      "id": "java",
      "name": "Java"
    }
  ],
  "preferred_skills": [],
  "mentioned_skills": [],
  "metadata": {
    "title": null,
    "company": null,
    "location": null,
    "canonical_url": null
  }
}
```

The content hash is `SHA-256(UTF-8(normalized_text))`. Skill arrays contain
only canonical `id` and display `name`, are deduplicated, and are sorted by
canonical ID.

## Normalization policy

`jd-normalization-v1` performs these operations in order:

1. enforce the request-byte and Unicode code-point bounds;
2. remove U+0000 NUL;
3. normalize Unicode to NFC;
4. convert CRLF, CR, U+0085, U+2028, and U+2029 to LF;
5. collapse horizontal Unicode whitespace on each line to one ASCII space;
6. trim horizontal whitespace from each line;
7. preserve nonblank line boundaries, heading punctuation, and bullets;
8. collapse multiple blank lines to one;
9. remove leading and trailing blank lines; and
10. produce no trailing newline.

It does not lowercase the document, translate, spell-check, infer metadata,
rewrite headings, reorder lines, or claim semantic understanding. An empty
normalized value returns `422 EMPTY_JOB_DESCRIPTION`.

## Skill dictionary and classification

`src/main/resources/skills/skills-v1.json` is a small reviewed dictionary.
Startup fails if required fields are missing, IDs duplicate, normalized aliases
collide, a match type is unsupported, or the dictionary exceeds 256 entries.
Dictionary aliases are treated as quoted data, never executable regular
expressions.

Versioned lexical heading and line cues classify matches as `required`,
`preferred`, or `mentioned`. Required overrides preferred, and preferred
overrides mentioned. This deterministic keyword matching is not semantic or AI
understanding and can miss context, unfamiliar aliases, and nuanced prose.

## Request IDs and errors

Clients may send one `X-Request-ID` matching:

```text
[A-Za-z0-9][A-Za-z0-9._:-]{0,63}
```

The service otherwise creates a UUIDv4. The trusted value is returned on all
responses and placed in logging MDC. It is correlation metadata, not
authentication or deduplication.

Every API error uses this envelope:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "The request could not be processed.",
    "request_id": "local-example-1",
    "details": {}
  }
}
```

Errors and logs omit raw and normalized JD text, metadata values, canonical
URLs, API keys, authorization headers, request and response bodies, stack
traces, internal paths, and exception messages.

## Health and OpenAPI

Unauthenticated status-only probes:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

OpenAPI JSON is at `GET /v3/api-docs`. It is protected by the internal API key
outside the `dev` profile. The document includes only the approved normalize
endpoint, Bearer authentication, `X-Request-ID`, and the shared error schema.
Swagger UI is not included. No other Actuator endpoint is exposed.

## Tests

Run the complete Phase 1 suite:

```bash
./mvnw -B -ntp verify
```

Target only deterministic normalization:

```bash
./mvnw -B -ntp \
  -Dtest='TextNormalizerTest,UrlNormalizerTest,SkillDictionaryLoaderTest,SkillExtractorTest,JobDescriptionNormalizerTest' \
  test
```

Target the HTTP, security, and application-context tests:

```bash
./mvnw -B -ntp \
  -Dtest='NormalizationApiWebTest,RequestIdAndErrorWebTest,SecurityWebTest,JdNormalizationServiceApplicationTest' \
  test
```

Tests use no PostgreSQL, Redis, H2, Testcontainers, DeepSeek, production
configuration, or arbitrary external network call.

## Logging

The default console output uses Spring Boot structured ECS JSON. Request
completion records include the request ID, method, route template where
available, status, duration, and bounded response size. Normalization records
include only policy versions, counts, normalized code-point count, and
duration—not content or metadata.
