#!/usr/bin/env bash
set -Eeuo pipefail

# Manual-only runner.  It deliberately creates a disposable database path and
# requires an explicit opt-in so real-provider calls cannot run in CI by
# accident.  The application loads the already-approved local operator secret
# through its normal development .env mechanism; this script never prints it.
if [[ "${PJA_REAL_DEEPSEEK_CANDIDATE:-}" != "1" ]]; then
  echo '{"candidate_blocker":"manual_opt_in_required"}'
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_dir="${PJA_CANDIDATE_ARTIFACT_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/deepseek-candidate.XXXXXX")}"
cleanup_artifact_dir=0
if [[ -z "${PJA_CANDIDATE_ARTIFACT_DIR:-}" ]]; then
  cleanup_artifact_dir=1
fi
mkdir -p "$artifact_dir"
trap 'if [[ "$cleanup_artifact_dir" == "1" ]]; then rm -rf "$artifact_dir"; fi' EXIT

export APP_ENV=development
# The host shell may expose a SOCKS ALL_PROXY without socksio installed in the
# pinned OpenAI/httpx environment.  Clear it only inside this disposable
# candidate process; production proxy configuration is not changed.
export ALL_PROXY=
export APP_DATABASE_PATH="$artifact_dir/candidate.sqlite"
export PROJECT_KNOWLEDGE_PATH="$artifact_dir/synthetic-project-knowledge.md"
export ANALYSIS_JD_NORMALIZATION_MODE=local
export MOCK_PROVIDER_ENABLED=false
export AGENT_MODEL_MAX_OUTPUT_TOKENS=1600
export AGENT_MODEL_LENGTH_RETRY_OUTPUT_TOKENS=2400
export AGENT_MODEL_REPAIR_OUTPUT_TOKENS=1000
export PROVIDER_OVERALL_DEADLINE_SECONDS=130
export PROVIDER_RETRY_BACKOFF_SECONDS=0.25

output_path="$artifact_dir/summary.json"
exec "$repo_root/backend/.venv/bin/python" \
  "$repo_root/backend/candidates/deepseek_provider_real_candidate.py" \
  --output "$output_path"
