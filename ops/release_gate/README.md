# Production-equivalent Analyze release gate

`collect_analyze.py` executes the real authenticated HTTPS/RAG/History/metrics/
Java/PostgreSQL path exactly five times. `analyze_gate.py` is the pure policy
evaluator. Neither module is imported by application runtime code. Candidate
uses `candidate-public-equivalent` semantics. Production must explicitly select
`production-actual-public-direct`; there is no implicit production default.

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

For Production add:

```bash
  --acceptance-path production-actual-public-direct \
  --direct-interface eth0
```

That mode parses only the hostname and port from `--base-url`, resolves the
target, and performs direct `/api/health` and `/api/ready` HTTPS probes before
login or Analyze. The reviewed physical interface is explicit, not inferred
from a potentially TUN-modified default route. Every production curl uses
`--noproxy <exact-target-host> --interface <physical-interface>`;
only that curl child has all uppercase/lowercase `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, and `NO_PROXY` variables removed. The authenticated urllib client
also uses a no-proxy opener bound to the physical interface's single global
IPv4 source address. Host proxy configuration and unrelated release commands
are unchanged.

The probes and all five Analyze runs must report a non-loopback remote socket
whose IP is one of the freshly resolved target IPs and whose port matches the
Production URL. The local socket and `ip route get ... from <source>` must also
match the reviewed physical interface/source address. A loopback/Mihomo socket,
TUN source such as `198.18.0.1`, missing TLS verification, or any silent
fallback to a proxy/transparent route is `HARD_FAIL`.

Exit 0 means `PASS` or `PASS_WITH_WARNING`, exit 1 means statistical `FAIL`,
and exit 2 means `HARD_FAIL` or evidence collection failure. On public
availability failure the collector writes bounded evidence, stops immediately,
and returns 2. Evidence includes curl exit code/stderr, status/bytes and
connect/start-transfer/total timing, direct target/resolution and local/remote
socket evidence, correlated body-free Edge/Frontend access observations, and a
safe container/network snapshot. Proxy variable names may be recorded, but
their potentially sensitive values never are. The collector never writes
credentials or response bodies.

After evidence is retained, delete the isolated account and all user-scoped
test rows with the release runbook cleanup, then verify exact zero remaining.
