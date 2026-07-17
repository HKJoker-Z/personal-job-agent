# Tailored Resume Drafts

Tailored Resume generation requires a finalized, owned source Resume Version plus the Package's confirmed Profile snapshot, confirmed Job Requirements, and Match Evidence. The source Resume is never modified.

Local code removes the contact header before any optional model call. The safe generator may only select, order, and rewrite facts from the supplied evidence. It cannot add years, metrics, team size, technologies, education, management, or authorization. Contact information is merged locally by the existing export path when appropriate.

The Draft records selected evidence IDs, keyword coverage, missing keywords, source Resume Version, provider/model/prompt metadata, and evidence coverage. Each edit creates a child Material Version; finalized Versions are immutable. Unsupported or partially supported claims block review approval and finalization.

Alpha 3 focuses on structured Draft content and export compatibility. It does not redesign final PDF/DOCX visual templates and never auto-submits a Resume.
