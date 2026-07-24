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

## Three-minute English demo

Use this exact three-minute speaking plan in a warmed Version 2.0.3
environment. Provider or network latency may extend the live wait without
changing the supported workflow or the narration sequence.

| Time | Action | English narration | Expected application state |
| --- | --- | --- | --- |
| 0:00–0:20 | Sign in and open **Resumes**. | “Personal Job Agent is a private Version 2.0.3 workspace for evidence-grounded Resume and Job Description comparison.” | The authenticated Resume Library is visible. |
| 0:20–0:45 | Upload `fictional-resume.md` and point to its Primary marker. | “This entirely fictional Resume is parsed, saved as a versioned private asset, and selected as the Primary Resume.” | The fictional Resume is listed and marked **Primary Resume**. |
| 0:45–1:05 | Open **Project Knowledge** and confirm its status. | “Project Knowledge is one reviewed project corpus. When enabled, retrieval supplies bounded evidence rather than invented experience.” | Project Knowledge reports that the reviewed corpus and index are ready. |
| 1:05–1:35 | Open **Analyze**, confirm the Primary Resume, paste `fictional-job-description.md`, enable Project Knowledge with top-k `5`, and keep **Save to History** enabled. | “The normal workflow compares one selected Resume with one fictional Job Description and optionally retrieves relevant Project Knowledge chunks.” | Analyze shows the saved Resume Version, pasted JD, RAG controls, and History option. |
| 1:35–2:05 | Run the analysis. | “This is a synchronous `/api/analyze` request. DeepSeek provides advisory judgments; tolerant parsing, repair or fallback, evidence reconciliation, and final scoring remain backend controlled.” | The request is in progress and then shows `complete`, `repaired`, `partial`, or `fallback`; no Agent Run is created. |
| 2:05–2:35 | Review status, warnings, score breakdown, skills, evidence mapping, sources, and recommendations. | “The score is calculated deterministically after evidence reconciliation. Warnings and sources stay visible so a person reviews the advisory output.” | The normalized result is visible with its actual state, evidence, and warnings; no particular score is promised. |
| 2:35–2:50 | Open **History** and select the saved result. | “History persistence is optional and keeps the normalized analysis and workflow audit details for later human review.” | The saved fictional comparison and workflow details are visible. |
| 2:50–3:00 | Open **Architecture**. | “The static overview separates synchronous analysis from retained asynchronous infrastructure. The product does not apply, contact employers, or make hiring decisions.” | The read-only Architecture page is visible. |

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
