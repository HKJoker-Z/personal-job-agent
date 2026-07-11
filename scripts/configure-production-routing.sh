#!/usr/bin/env bash
set -Eeuo pipefail

readonly BRIDGE_INTERFACE="pja-br0"
readonly RULE_PREFERENCE="8999"
readonly FRONTEND_SOURCE_PORT="8080"
readonly DEFAULT_WAIT_SECONDS="120"
readonly MIN_WAIT_SECONDS="1"
readonly MAX_WAIT_SECONDS="600"

usage() {
  printf 'Usage: %s {install|remove|status}\n' "${0##*/}" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$1" >&2
    exit 1
  }
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    printf '%s\n' 'This operation must run as root.' >&2
    exit 1
  fi
}

wait_seconds() {
  local value="${PJA_ROUTING_WAIT_SECONDS:-${DEFAULT_WAIT_SECONDS}}"
  if [[ ! "${value}" =~ ^[0-9]+$ ]] \
    || (( value < MIN_WAIT_SECONDS || value > MAX_WAIT_SECONDS )); then
    printf 'PJA_ROUTING_WAIT_SECONDS must be an integer from %s through %s.\n' \
      "${MIN_WAIT_SECONDS}" "${MAX_WAIT_SECONDS}" >&2
    exit 2
  fi
  printf '%s\n' "${value}"
}

wait_for_bridge() {
  local timeout elapsed
  timeout="$(wait_seconds)"
  elapsed=0
  while ! ip link show dev "${BRIDGE_INTERFACE}" >/dev/null 2>&1; do
    if (( elapsed >= timeout )); then
      printf 'Bridge interface %s did not appear within %s seconds.\n' \
        "${BRIDGE_INTERFACE}" "${timeout}" >&2
      return 1
    fi
    sleep 1
    ((elapsed += 1))
  done
}

is_exact_project_rule() {
  local line="$1"
  [[ "${line}" =~ ^${RULE_PREFERENCE}:[[:space:]]+from[[:space:]]+all[[:space:]]+iif[[:space:]]+${BRIDGE_INTERFACE}[[:space:]]+ipproto[[:space:]]+tcp[[:space:]]+sport[[:space:]]+${FRONTEND_SOURCE_PORT}[[:space:]]+lookup[[:space:]]+main([[:space:]]+proto[[:space:]]+[^[:space:]]+)?[[:space:]]*$ ]]
}

read_preference_rules() {
  mapfile -t PREFERENCE_RULES < <(
    ip -4 -o rule show | awk -v preference="${RULE_PREFERENCE}:" '$1 == preference'
  )
}

classify_rule_state() {
  local line exact_count=0 conflict_count=0
  read_preference_rules
  for line in "${PREFERENCE_RULES[@]}"; do
    if is_exact_project_rule "${line}"; then
      ((exact_count += 1))
    else
      ((conflict_count += 1))
    fi
  done

  if (( conflict_count > 0 || exact_count > 1 )); then
    RULE_STATE="conflict"
  elif (( exact_count == 1 )); then
    RULE_STATE="installed"
  else
    RULE_STATE="not-installed"
  fi
}

install_rule() {
  require_root
  wait_for_bridge
  classify_rule_state
  case "${RULE_STATE}" in
    installed)
      printf '%s\n' 'installed: production frontend routing rule already exists.'
      return 0
      ;;
    conflict)
      printf 'conflict: IPv4 rule preference %s is occupied by a different or duplicate rule.\n' \
        "${RULE_PREFERENCE}" >&2
      return 1
      ;;
  esac

  ip -4 rule add pref "${RULE_PREFERENCE}" \
    iif "${BRIDGE_INTERFACE}" \
    ipproto tcp sport "${FRONTEND_SOURCE_PORT}" \
    lookup main
  classify_rule_state
  if [[ "${RULE_STATE}" != "installed" ]]; then
    printf '%s\n' 'The production frontend routing rule could not be verified after installation.' >&2
    return 1
  fi
  printf '%s\n' 'installed: production frontend routing rule added.'
}

remove_rule() {
  local line exact_count
  require_root

  while true; do
    read_preference_rules
    exact_count=0
    for line in "${PREFERENCE_RULES[@]}"; do
      if is_exact_project_rule "${line}"; then
        ((exact_count += 1))
      fi
    done
    if (( exact_count == 0 )); then
      break
    fi
    ip -4 rule del pref "${RULE_PREFERENCE}" \
      iif "${BRIDGE_INTERFACE}" \
      ipproto tcp sport "${FRONTEND_SOURCE_PORT}" \
      lookup main
  done

  printf '%s\n' 'not-installed: production frontend routing rule is absent.'
}

show_status() {
  classify_rule_state
  case "${RULE_STATE}" in
    installed)
      printf '%s\n' 'installed: production frontend routing rule is present.'
      return 0
      ;;
    not-installed)
      printf '%s\n' 'not-installed: production frontend routing rule is absent.'
      return 1
      ;;
    conflict)
      printf 'conflict: IPv4 rule preference %s contains a different or duplicate rule.\n' \
        "${RULE_PREFERENCE}" >&2
      return 2
      ;;
  esac
}

main() {
  require_command ip
  case "${1:-}" in
    install) install_rule ;;
    remove) remove_rule ;;
    status) show_status ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
