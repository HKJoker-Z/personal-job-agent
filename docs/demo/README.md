# Version 2.0.3 Demo Script

This reproducible walkthrough uses only fictional material:

- [Fictional Resume](fictional-resume.md)
- [Fictional Job Description](fictional-job-description.md)

The fixtures contain no real person, employer, credentials, secrets, private
data, production addresses, or copied application content.

## Prerequisites

- A running Personal Job Agent Version 2.0.3 environment.
- An administrator-created demo account. Keep its credentials outside this
  repository and enter them only on the sign-in page.
- The reviewed Project Knowledge corpus initialized by the environment.

Provider-assisted wording and result state may vary. The backend-owned evidence
checks and scoring rules still apply, and a provider failure may produce a
`fallback` result instead.

## Walkthrough

1. Sign in with the prepared demo account.
2. Open **Resumes** and upload `docs/demo/fictional-resume.md`.
3. Confirm that the upload appears in the Resume Library with the **Primary**
   marker. A successful Resume-page upload makes it the account's Primary
   Resume.
4. Open **Project Knowledge** and confirm that the reviewed corpus is ready.
   Do not replace the runtime corpus during this demo.
5. Open **Analyze**. Confirm that the fictional Primary Resume is selected.
6. Keep **Paste Job Description** selected and paste the complete contents of
   `docs/demo/fictional-job-description.md`.
7. Enable **Project Knowledge** with top-k `5`, leave **Save to History**
   enabled, and run the analysis.
8. Review the returned analysis state, warnings, deterministic match score and
   breakdown, matched/missing skills, evidence mapping, Project Knowledge
   sources, and recommendations. Treat all advisory text as material for human
   review.
9. Open **History**, select the saved analysis, and verify that the normalized
   result and workflow audit details are available. The existing DOCX/PDF
   exports may be demonstrated from the saved History view.
10. If using an administrator account, optionally open **Monitoring** to show
    metadata-only workflow observations. Do not run destructive cleanup during
    the demo.
11. Open **Architecture** to explain the deterministic, advisory, retrieval,
    reconciliation, scoring, review, persistence, and production boundaries.

## Expected boundaries

The demonstration ends with a reviewed and optionally saved comparison. It
uses the synchronous `POST /api/analyze` path and does not enqueue an Agent Run.
It does not automatically apply for a job, contact an employer, guarantee an
ATS or interview outcome, or make an autonomous hiring decision. Any
next-action recommendation is advisory and remains the user's decision.
