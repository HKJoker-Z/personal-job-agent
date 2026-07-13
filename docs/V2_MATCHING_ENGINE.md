# Deterministic Matching Engine

Matching uses confirmed facts only. The default weights total 100:

| Dimension | Weight |
| --- | ---: |
| Required Skills | 30 |
| Experience | 20 |
| Projects | 15 |
| Education | 10 |
| Location and Work Authorization | 10 |
| Languages | 5 |
| Seniority | 5 |
| User Preferences | 5 |

The engine rejects incomplete, negative, over-100, or non-100 weight configurations. Exact matches contribute 1.0, versioned synonyms 0.9, conservative related skills 0.5, and missing confirmed evidence 0. Unknown dimensions remain neutral snapshots and are not silently scored as a confirmed failure.

Confirmed Job Requirements participate. `needs_review` requirements produce an unknown result; rejected requirements are ignored. Confirmed Profile Skills, Experience, Projects, Education, Languages, Certifications, and Preferences are mapped to separate evidence source types. A source ID/revision prevents double counting and preserves explainability.

Hard filters are reported separately as `passed`, `warning`, `failed`, or `unknown`. They cover work authorization, mandatory location/language/certification, and explicit minimum experience. A failed hard filter affects recommendation/ranking but is never hidden inside the displayed score.

`scoring_version=deterministic-v1` and `synonym_map_version=skills-v1` make results reproducible. The overall score is a fit indicator from 0–100, not the probability of an interview, Offer, or hiring success. LLM output cannot set or modify any numeric result.
