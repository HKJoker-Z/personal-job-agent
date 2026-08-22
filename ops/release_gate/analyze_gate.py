#!/usr/bin/env python3
"""Evaluate one five-run production-equivalent Analyze release gate.

The evaluator is deliberately independent from application code.  It consumes
bounded release evidence, keeps availability/data/security checks hard, and
applies the statistical Java fallback policy documented in DEPLOYMENT.md.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


RUN_COUNT = 5
PRODUCTION_DIRECT_PATH = "production-actual-public-direct"

# Missing evidence is a hard failure.  Callers must positively attest every
# invariant; a successful Analyze response cannot bypass an infrastructure,
# backup, data, security, or artifact gate.
HARD_GATE_KEYS = (
    "root_capacity_6_gib",
    "authentication",
    "authorization",
    "security_boundary",
    "data_integrity",
    "application_delete_isolation",
    "migration",
    "alembic_revision",
    "postgresql",
    "redis",
    "backup",
    "backup_validation",
    "restore_validation",
    "rollback_assets",
    "immutable_images",
    "artifact_parity",
    "required_containers_healthy",
    "restart_count_zero",
    "oom_false",
    "health",
    "readiness",
    "no_persistent_runtime_errors",
)


@dataclass(frozen=True)
class GateResult:
    verdict: str
    release_allowed: bool
    fallback_count: int
    successful_http_count: int
    consecutive_fallback: bool
    hard_failures: tuple[str, ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _is_2xx(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 200 <= value < 300


def _direct_remote_is_target(value: dict[str, Any]) -> tuple[bool, str | None]:
    remote_ip = value.get("client_remote_ip", value.get("remote_ip"))
    if not isinstance(remote_ip, str) or not remote_ip:
        return False, "remote_ip_missing"
    try:
        address = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False, "remote_ip_invalid"
    if address.is_loopback:
        return False, "remote_is_loopback_proxy"
    resolved = value.get("target_resolved_ips")
    if not isinstance(resolved, list) or not resolved:
        return False, "resolved_target_missing"
    try:
        resolved_addresses = {ipaddress.ip_address(item) for item in resolved}
    except (TypeError, ValueError):
        return False, "resolved_target_invalid"
    if address not in resolved_addresses:
        return False, "remote_not_resolved_target"
    remote_port = value.get("client_remote_port", value.get("remote_port"))
    target_port = value.get("target_port")
    try:
        if int(remote_port) != int(target_port):
            return False, "remote_port_mismatch"
    except (TypeError, ValueError):
        return False, "remote_port_missing"
    local_ip = value.get("client_local_ip", value.get("local_ip"))
    target_source_ip = value.get("target_source_ip")
    if local_ip != target_source_ip or value.get("direct_local_source_verified") is not True:
        return False, "local_source_not_bound_interface"
    try:
        local_address = ipaddress.ip_address(str(local_ip))
    except ValueError:
        return False, "local_source_invalid"
    if local_address.is_loopback or local_address.is_unspecified:
        return False, "local_source_not_routable"
    direct_interface = value.get("direct_interface")
    if (
        not isinstance(direct_interface, str)
        or not direct_interface
        or direct_interface == "lo"
        or value.get("route_interface") != direct_interface
        or value.get("route_source_ip") != target_source_ip
        or value.get("direct_route_verified") is not True
    ):
        return False, "route_not_bound_interface"
    return True, None


def evaluate(evidence: dict[str, Any]) -> GateResult:
    hard_failures: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []
    direct_path_required = evidence.get("acceptance_path") == PRODUCTION_DIRECT_PATH

    if direct_path_required:
        probes = evidence.get("direct_path_probes")
        if not isinstance(probes, list) or len(probes) != 2:
            hard_failures.append("production_direct_probe_missing")
        else:
            probe_paths = {
                probe.get("path") for probe in probes if isinstance(probe, dict)
            }
            if probe_paths != {"/api/health", "/api/ready"}:
                hard_failures.append("production_direct_probe_paths_invalid")
            for index, probe in enumerate(probes, start=1):
                prefix = f"direct_probe_{index}"
                if not isinstance(probe, dict):
                    hard_failures.append(f"{prefix}:evidence_invalid")
                    continue
                socket_valid, socket_failure = _direct_remote_is_target(probe)
                if probe.get("direct_path_verified") is not True or not socket_valid:
                    hard_failures.append(
                        f"{prefix}:direct_path_not_verified:{socket_failure or 'assertion_failed'}"
                    )
                if probe.get("request_proxy_environment_removed") is not True:
                    hard_failures.append(f"{prefix}:proxy_environment_not_removed")
                if probe.get("https_scheme") is not True or probe.get("tls_verified") is not True:
                    hard_failures.append(f"{prefix}:https_tls_not_verified")
                if not _is_2xx(probe.get("http_status")):
                    hard_failures.append(f"{prefix}:public_non_2xx")
                response_bytes = probe.get("response_bytes")
                if (
                    not isinstance(response_bytes, (int, float))
                    or isinstance(response_bytes, bool)
                    or response_bytes <= 0
                ):
                    hard_failures.append(f"{prefix}:response_empty")

    hard_gates = evidence.get("hard_gates")
    if not isinstance(hard_gates, dict):
        hard_failures.append("hard_gate_evidence_missing")
        hard_gates = {}
    for key in HARD_GATE_KEYS:
        if hard_gates.get(key) is not True:
            hard_failures.append(f"hard_gate_failed:{key}")

    runs = evidence.get("runs")
    if not isinstance(runs, list) or len(runs) != RUN_COUNT:
        hard_failures.append(f"analyze_run_count_not_{RUN_COUNT}")
        runs = runs if isinstance(runs, list) else []

    request_ids: list[str] = []
    fallbacks: list[bool] = []
    successful_http_count = 0

    for index, run in enumerate(runs, start=1):
        prefix = f"run_{index}"
        if not isinstance(run, dict):
            hard_failures.append(f"{prefix}:evidence_invalid")
            fallbacks.append(False)
            continue

        request_id = run.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            hard_failures.append(f"{prefix}:request_id_missing")
        else:
            request_ids.append(request_id)

        if run.get("public_https") is not True:
            hard_failures.append(f"{prefix}:not_public_https")

        if direct_path_required:
            socket_valid, socket_failure = _direct_remote_is_target(run)
            if run.get("direct_path_required") is not True:
                hard_failures.append(f"{prefix}:direct_path_requirement_missing")
            if run.get("direct_path_verified") is not True or not socket_valid:
                hard_failures.append(
                    f"{prefix}:direct_path_not_verified:{socket_failure or 'assertion_failed'}"
                )
            if run.get("request_proxy_environment_removed") is not True:
                hard_failures.append(f"{prefix}:proxy_environment_not_removed")

        transport_error = run.get("transport_error")
        empty_reply = run.get("empty_reply") is True or transport_error == "empty_reply"
        if empty_reply:
            hard_failures.append(f"{prefix}:empty_reply")
        elif transport_error not in (None, "") or run.get("connection_failure") is True:
            hard_failures.append(f"{prefix}:connection_failure")

        status = run.get("http_status")
        if _is_2xx(status):
            successful_http_count += 1
        else:
            hard_failures.append(f"{prefix}:public_non_2xx")

        if run.get("response_complete") is not True:
            hard_failures.append(f"{prefix}:response_incomplete_or_corrupt")
        if run.get("response_request_id_matches") is not True:
            hard_failures.append(f"{prefix}:response_request_id_mismatch")
        if run.get("backend_final_status") != status:
            hard_failures.append(f"{prefix}:backend_status_mismatch_or_missing")

        fallback = run.get("java_fallback") is True
        fallbacks.append(fallback)
        if fallback and run.get("fallback_result_correct") is not True:
            failures.append(f"{prefix}:fallback_result_incorrect")
        if run.get("output_correct") is not True:
            failures.append(f"{prefix}:analyze_output_incorrect")
        if run.get("history_persisted") is not True:
            hard_failures.append(f"{prefix}:history_persistence_failed")
        if run.get("rag_enabled") is not True:
            hard_failures.append(f"{prefix}:rag_not_enabled")
        if run.get("metrics_persisted") is not True:
            hard_failures.append(f"{prefix}:metrics_persistence_failed")
        if run.get("java_observation_present") is not True:
            hard_failures.append(f"{prefix}:java_observation_missing")
        for layer in ("edge", "frontend", "backend", "java"):
            if run.get(f"{layer}_log_scanned") is not True:
                hard_failures.append(f"{prefix}:{layer}_log_scan_failed")
        for layer in ("edge", "frontend"):
            if run.get(f"{layer}_access_observation_present") is not True:
                hard_failures.append(f"{prefix}:{layer}_access_observation_missing")
            if run.get(f"{layer}_status") != status:
                hard_failures.append(f"{prefix}:{layer}_status_mismatch")
            if run.get(f"{layer}_upstream_status") != status:
                hard_failures.append(f"{prefix}:{layer}_upstream_status_mismatch")
            bytes_sent = run.get(f"{layer}_bytes_sent")
            if not isinstance(bytes_sent, (int, float)) or isinstance(bytes_sent, bool) or bytes_sent <= 0:
                hard_failures.append(f"{prefix}:{layer}_bytes_sent_missing")
        if run.get("persistent_runtime_error") is True:
            hard_failures.append(f"{prefix}:persistent_runtime_error")

        run_warnings = run.get("warnings", [])
        if isinstance(run_warnings, list):
            warnings.extend(
                f"{prefix}:{item}" for item in run_warnings if isinstance(item, str) and item
            )

    if len(request_ids) != len(set(request_ids)):
        hard_failures.append("request_ids_not_unique")

    fallback_count = sum(fallbacks)
    consecutive_fallback = any(left and right for left, right in zip(fallbacks, fallbacks[1:]))
    if fallback_count >= 2:
        failures.append("java_fallback_count_at_least_2_of_5")
    if consecutive_fallback:
        failures.append("two_consecutive_java_fallbacks")

    top_level_warnings = evidence.get("warnings", [])
    if isinstance(top_level_warnings, list):
        warnings.extend(item for item in top_level_warnings if isinstance(item, str) and item)

    if hard_failures:
        verdict = "HARD_FAIL"
        release_allowed = False
    elif failures:
        verdict = "FAIL"
        release_allowed = False
    elif fallback_count == 1:
        warnings.append("java_fallback_1_of_5")
        verdict = "PASS_WITH_WARNING"
        release_allowed = True
    else:
        verdict = "PASS"
        release_allowed = True

    return GateResult(
        verdict=verdict,
        release_allowed=release_allowed,
        fallback_count=fallback_count,
        successful_http_count=successful_http_count,
        consecutive_fallback=consecutive_fallback,
        hard_failures=_unique(hard_failures),
        failures=_unique(failures),
        warnings=_unique(warnings),
    )


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("release gate evidence must be a JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)

    result = asdict(evaluate(_load(args.evidence)))
    if args.result:
        _write(args.result, result)
    print(json.dumps(result, sort_keys=True))
    if result["verdict"] == "HARD_FAIL":
        return 2
    if result["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
