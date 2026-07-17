# Fact Grounding and Claim Validation

Fact grounding is enforced independently of the optional generation model. The validator splits a Material into claims, extracts factual markers, and compares them with owned immutable sources.

Markers include numbers, percentages, years/dates, named company/role/location phrases, technologies, education, certification, leadership/team size, work authorization, sponsorship, salary, and compensation. Each claim is `supported`, `partially_supported`, `unsupported`, `needs_user_input`, `user_confirmed`, or `not_applicable`.

Unsupported and partial claims are preserved and shown; they are never silently deleted. They contribute to `unsupported_claim_count`, lower evidence coverage, and block approval/finalization. Users can:

1. edit the Draft, which creates a new Version;
2. add/confirm the source fact through the Profile workflow and regenerate; or
3. explicitly confirm the individual claim for this Material Version using `CONFIRM CLAIM`.

Explicit claim confirmation writes a metadata-only audit event and does not change the original Profile, Resume, Job, or Match Analysis. Finalization still requires completed validation, zero unresolved claims, an active Version, explicit review approval, and `FINALIZE MATERIAL` confirmation.

Prompts, Resume/JD text, questions, generated text, review notes, and claim text are not written to ordinary logs. Evidence rows store a claim hash and safe summary rather than the full claim.
