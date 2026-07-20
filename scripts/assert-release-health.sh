#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s <health-url> <expected-version>\n' "$0" >&2
  exit 2
fi

HEALTH_URL=$1
EXPECTED_VERSION=$2
BODY="$(curl --noproxy '*' --fail --silent --show-error --max-time 10 "$HEALTH_URL")"
python3 - "$EXPECTED_VERSION" "$BODY" <<'PY'
import json
import sys

expected, raw = sys.argv[1:]
value = json.loads(raw)
if value.get("status") != "ok" or value.get("version") != expected:
    raise SystemExit(f"health release mismatch: expected {expected!r}")
print(f"health release verified: {expected}")
PY
