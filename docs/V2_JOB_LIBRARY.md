# Version 2 Job Library

The Job Library is an ownership-scoped store for imported and manually maintained Jobs. List responses contain a short description summary; only Job Detail returns the full description, rendered as plain text.

Normalization is deterministic and conservative:

- NFKC Unicode normalization, whitespace collapse, and line-ending normalization
- case-folded company/title/location search fields while retaining originals
- conservative company suffix removal without discarding distinct company words
- canonical HTTP(S) URL with fragments, credentials, sensitive query values, and common tracking parameters removed
- SHA-256 description hash and owner-isolated deduplication key

The library supports query, company, title, location, status, employment type, work mode, source, creation date, deadline, archive state, allowlisted sorting, and stable offset pagination. Client sort strings never become SQL fragments.

Jobs use optimistic revisions. Archive is a soft delete; restore does not recreate a row. Requirements store extraction source, confidence, review state, and exact evidence text/spans. LLM output is never considered confirmed until the user explicitly confirms it.

Sources preserve provenance without Cookie, Authorization, proxy credentials, complete headers, internal IPs, file content, or Job Description bodies. File sources link an owned private File Asset.

The Job Detail UI supports editing, plain-text description review, requirement confirmation/rejection, explicit extraction, duplicate resolution, Application creation, source review, and archive. This milestone does not calculate a Job/Profile match or success probability.
