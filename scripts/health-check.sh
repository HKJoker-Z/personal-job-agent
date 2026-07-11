#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${1:-http://127.0.0.1:8080}"
BASE_URL="${BASE_URL%/}"

check_endpoint() {
  local path="$1"
  python3 - "$BASE_URL" "$path" <<'PY'
import sys
import urllib.error
import urllib.request

base_url, path = sys.argv[1:]
try:
    with urllib.request.urlopen(base_url + path, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError("unexpected status")
except (OSError, urllib.error.URLError, RuntimeError):
    raise SystemExit(1)
PY
  printf 'ok %s\n' "$path"
}

check_endpoint "/"
check_endpoint "/api/health"
check_endpoint "/api/ready"
check_endpoint "/api/monitoring/status"
check_endpoint "/api/security/policy"
check_endpoint "/api/project-knowledge/status"
