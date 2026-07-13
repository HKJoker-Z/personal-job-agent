# Matching Evidence

Every evaluated confirmed requirement produces evidence with its dimension, Requirement ID, source type, source ID, source revision, kind, contribution, confidence, and safe explanation.

Evidence kinds are `matched`, `partial`, `missing`, `unknown`, `hard_filter`, and `contradictory`. Missing means the deterministic engine found no confirmed supporting fact. Unknown means the underlying requirement or user fact is not confirmed; it must not be described as a confirmed negative.

Profile facts remain distinct from Resume Versions and Job Requirements. Project Knowledge may be used only when it is curated and confirmed; retrieval relevance alone never becomes a Profile fact or numeric contribution. Alpha 3 does not copy retrieved chunks into Analysis rows.

Analysis history remains available after Profile/Job edits. A rerun creates a new immutable snapshot; identical input may reuse a completed snapshot unless `force_new=true`. Ownership checks prevent cross-user evidence lookup.
