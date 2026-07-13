# Version 2 Job Import Security

## Manual and CSV

Manual import requires a bounded description and validates salary ranges, timezone-aware dates, enums, and URL length. CSV accepts only the documented UTF-8 header (UTF-8 BOM is allowed), at most 2 MiB and 500 rows, with bounded cells. Formula-like cells beginning with `=`, `+`, `-`, or `@` are rejected and never executed.

CSV validate-only creates an Import Run and row statuses but no Jobs. Confirmed import uses a nested transaction per row, retains successful rows, reports bounded row errors, and never echoes descriptions or complete CSV content.

## URL acquisition and SSRF boundary

Only HTTP and HTTPS are accepted. URL userinfo, localhost, loopback, private, link-local, multicast, reserved, unspecified, cloud metadata, IPv4-mapped IPv6, and obfuscated decimal/hex/octal IP forms are rejected. DNS results must be global; the selected address is pinned for the connection. Every redirect is canonicalized, resolved, and revalidated, with a maximum of five redirects.

The fetcher has connection/read timeouts, a 2 MiB compressed limit, a 4 MiB expanded limit, bounded gzip decompression, and an allowlist of HTML/XHTML/plain text. It sends only a product User-Agent, Host, and Accept header—never user Cookies, Authorization, proxy credentials, browser Session data, or PII. It does not execute JavaScript or follow instructions embedded in the page.

Automated tests use an isolated local Mock HTTP service. The private-target test override requires both `APP_ENV=test` and the exact `JOB_IMPORT_TEST_ALLOWED_HOST`; it is unavailable in development and production.

## PDF and DOCX

Uploads must have matching extension, MIME, and signature. Size is bounded. DOCX packages are checked for required parts, entry count, expanded size, and compression ratio. PDFs are strictly parsed with page and extracted-text limits. Files are atomically written with mode 0600 beneath a confined private `jobs/` namespace. Parse failure rolls back the database operation and removes the newly written file.

Errors disclose neither resolved IPs nor internal paths. Logs contain resource IDs, safe codes, counts, and duration only—not Job Description, CSV, file, Session, CSRF, or credential content.
