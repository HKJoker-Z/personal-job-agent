#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT_ROOT
readonly DEPLOY_HELPER="${SCRIPT_ROOT}/scripts/deploy-java-normalization.sh"

if [[ "${1:-}" != '--confirm-java-only' ]]; then
  printf '%s\n' 'usage: remove-java-normalization.sh --confirm-java-only --image IMAGE@sha256:DIGEST [--secret-file PATH]' >&2
  exit 2
fi
shift

exec "${DEPLOY_HELPER}" rollback "$@"
