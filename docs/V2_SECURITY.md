# Version 2 Phase 1 Security Model

## Authentication and Sessions

- Passwords are hashed with Argon2 through `pwdlib`; plaintext passwords are never persisted.
- Login failures return one generic response for unknown accounts and incorrect passwords.
- Login throttling is stored in PostgreSQL and keyed by HMAC fingerprints of normalized email and client address.
- Session and CSRF values are generated with a cryptographic random source. Only SHA-256 hashes are stored.
- The Session Cookie is HttpOnly, `SameSite=Lax`, path `/`, and must be Secure in production.
- Session idle and absolute expirations are enforced server-side. Password changes, deactivation, logout, and logout-all revoke Sessions.
- CSRF tokens remain in frontend memory. They are not written to local storage, session storage, URLs, logs, or database plaintext.

## Request authorization

All `/api/*` routes except liveness/readiness, login, and Session bootstrap are default-deny when authentication is enabled. Unsafe methods require both a trusted Origin/Referer and the current Session-bound `X-CSRF-Token`. Query-string CSRF is rejected. Existing Monitoring destructive routes additionally retain their administrator role, explicit confirmation, local-only default, and separate admin-token controls.

Repositories scope Profile, Resume, Resume Version, and file queries to the authenticated owner. Cross-user identifiers return `404` so they cannot be used as an existence oracle. Profile revision conflicts return `409`; missing preconditions return `428`.

## File security

Only PDF and DOCX uploads with matching extension, media type, and signature are accepted. DOCX archives have file-count, expanded-size, compression-ratio, and required-member checks. Parser failures are converted to safe `400` responses. Storage rejects absolute paths, traversal, root escape, symlink roots, symlink parents, and symlink files. Stored names are UUID-based and unrelated to the submitted filename.

Backup verification rejects symlink backup roots, unexpected manifest entries, checksum mismatches, unsafe tar members, absolute paths, traversal, hardlinks, and symlinks. Restore requires an exact confirmation, an empty database, an empty non-symlink file target, and a nonexistent non-symlink Project Knowledge target.

## Configuration boundaries

Production requires PostgreSQL, a Secure Session Cookie, explicit trusted Origins, and a fingerprint key of at least 32 characters. Wildcard Origins are refused. Tests use `TEST_DATABASE_URL`; PostgreSQL test database names must contain `test`, and known production-like SQLite paths are refused.

Secrets belong in an ignored environment file or an external secret manager. Do not commit environment files, database dumps, uploaded resumes, runtime files, Smoke logs, Cookies, tokens, or backup directories. Request logging excludes bodies, query strings, authorization values, resumes, job descriptions, and prompts.

The Java normalization client defaults to `local`. Both `shadow` and `java`
require an absolute key-file path and a validated HTTP/HTTPS service origin;
the key is read from the file, bounded, and never included in configuration
errors or structured observations. The internal client does not inherit proxy
environment variables, follow redirects, retain/forward cookies, or copy
browser Session, CSRF, Origin, URL, Resume, or metadata fields. Its successful
and failed observations contain only bounded outcome, timing, version, count,
and equality fields—not text, hashes, URLs, headers, response bodies, or
exception messages.

The first FastAPI scan always runs before Java; blocked or unsanitized input is
never sent. In `shadow`, the second scan is observation-only and local text
remains authoritative. In `java`, a validated Java response must pass the
authoritative second scan before it can reach retrieval or prompt
construction. Rejection safely selects the already-sanitized local input.
Every new keyed attempt atomically binds its exact effective normalization
before RAG/provider work, protected by the current attempt token. The binding
contains no Request ID, key, attempt token, timestamp, raw text, or logged
fingerprint bytes. A different existing binding yields a stable execution
conflict. Completed legacy and new rows replay before either scan or Java work.

## Limitations

Phase 1 is a single-instance foundation, not a formal security certification.
It does not claim malware scanning, DLP completeness, high availability,
external identity federation, distributed rate limiting beyond the shared
PostgreSQL table, or a production deployment already completed. HTTPS must be
terminated by an intentionally configured production edge before Secure
Cookies are used over a public network. Phase IIIA is implemented for review
but is not released, deployed, or enabled in production. Candidate Compose and
production integration remain future work.
