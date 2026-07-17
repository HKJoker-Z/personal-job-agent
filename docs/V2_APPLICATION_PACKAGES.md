# Application Packages

An Application Package snapshots one owned Application, its Job revision, Profile revision, finalized source Resume Version, and Match Analysis. All sources must belong to the same user and Job. Creating a Package does not generate content automatically.

Packages move through `draft`, `in_review`, `approved`, and `archived`. Multiple historical Packages may exist, while PostgreSQL permits only one active approved Package per Application.

Approval requires an explicit confirmation string and current revision. At minimum the Package needs active Tailored Resume and Cover Letter Materials whose active Versions are validated, review-approved, finalized, and free of unresolved claims. Application Answers can remain question-specific Drafts.

This is a small Package-level review gate, not the general Approval Workflow planned for Version 2.0.4. No Package is sent, emailed, uploaded, or submitted automatically.
