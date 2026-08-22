# Production-equivalent Analyze release gate

`collect_analyze.py` executes the real authenticated HTTPS/RAG/History/metrics/
Java/PostgreSQL path exactly five times. `analyze_gate.py` is the pure policy
evaluator. Neither module is imported by application runtime code.

The operator first creates a dedicated isolated account and a mode-0600
password file, deploys candidate or production, and produces a content-free
hard-gate JSON object with every key in `HARD_GATE_KEYS` set to `true` only
after that check has passed. Missing/false keys are HARD FAIL.

Example shape (use protected release paths, not the repository, for evidence):

```bash
python3 ops/release_gate/collect_analyze.py \
  --base-url https://candidate.example \
  --origin https://candidate.example \
  --email isolated-release@example.invalid \
  --password-file /run/pja-release/password \
  --ca-file /run/pja-release/candidate-ca.pem \
  --resume-file ops/release_gate/fixtures/synthetic_resume.json \
  --job-file ops/release_gate/fixtures/synthetic_jd.txt \
  --hard-gates /run/pja-release/hard-gates.json \
  --output /run/pja-release/analyze-evidence.json \
  --artifact-dir /run/pja-release/layer-logs \
  --request-prefix v220-candidate \
  --edge-container candidate-edge-1 \
  --frontend-container candidate-frontend-1 \
  --backend-container candidate-backend-1 \
  --java-container candidate-java-1 \
  --schedule-seconds 0,30,60,120,240
```

Exit 0 means `PASS` or `PASS_WITH_WARNING`, exit 1 means statistical `FAIL`,
and exit 2 means `HARD_FAIL` or evidence collection failure. On public
availability failure the collector writes bounded evidence, stops immediately,
and returns 2. Evidence includes curl exit code/stderr, status/bytes and
connect/start-transfer/total timing, correlated body-free Edge/Frontend access
observations, and a safe container/network snapshot. It never writes
credentials or response bodies.

After evidence is retained, delete the isolated account and all user-scoped
test rows with the release runbook cleanup, then verify exact zero remaining.
