#!/usr/bin/env bash
set -Eeuo pipefail

# Manual-only runner for the four-level authenticated attribution matrix.
# The application loads the approved local development secret through .env;
# this wrapper never prints it and never writes provider content.
if [[ "${PJA_REAL_DEEPSEEK_ATTRIBUTION:-}" != "1" ]]; then
  echo '{"attribution_blocker":"manual_opt_in_required"}'
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_dir="${PJA_ATTRIBUTION_ARTIFACT_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/deepseek-attribution.XXXXXX")}"
cleanup_artifact_dir=0
if [[ -z "${PJA_ATTRIBUTION_ARTIFACT_DIR:-}" ]]; then
  cleanup_artifact_dir=1
fi
mkdir -p "$artifact_dir"
trap 'if [[ "$cleanup_artifact_dir" == "1" ]]; then rm -rf "$artifact_dir"; fi' EXIT

export APP_ENV=development
export DEEPSEEK_NETWORK_MODE=direct
export DEEPSEEK_THINKING_ENABLED=false
# Clear only the disposable attribution process's unsupported SOCKS variable.
# The production process environment is not changed.
export ALL_PROXY=
export output_path="$artifact_dir/transport-attribution.json"

mode="${1:-matrix}"
if [[ "$mode" != "matrix" && "$mode" != "realistic" ]]; then
  echo '{"attribution_blocker":"mode_must_be_matrix_or_realistic"}'
  exit 2
fi
runner_args=(--output "$output_path")
if [[ "$mode" == "realistic" ]]; then
  runner_args+=(--realistic-control)
fi

exec "$repo_root/backend/.venv/bin/python" \
  "$repo_root/backend/candidates/deepseek_transport_attribution.py" \
  "${runner_args[@]}"
