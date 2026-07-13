# Job Ranking

Ranking is an explicit, synchronous operation over owned, non-archived Jobs selected by IDs or an allowlisted Job Library filter. Each Job receives or reuses a deterministic Match Analysis.

The stored rank score combines the Match score with bounded deadline, Application priority, and preparation-effort factors. Failed hard filters receive an explicit penalty and sort after non-failed candidates. Stable Job ID tie-breaking makes equal scores reproducible.

Every Rank Item records its position, Analysis ID, individual factor contributions, primary reasons, and primary gaps. The API never concatenates client sort/filter values into SQL. Ranking is decision support, not a hiring-success probability.

Rank Runs are immutable and ownership-scoped. The React `/job-ranking` page shows score, hard filter, recommendation, preparation effort, strengths, and gaps rather than a single unexplained percentage.
