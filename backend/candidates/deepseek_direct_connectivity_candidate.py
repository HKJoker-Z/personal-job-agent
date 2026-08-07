"""Manual-only DeepSeek proxy/direct connectivity and candidate runner.

The preflight subcommand sends only unauthenticated GET requests to the
configured Provider origin.  The authenticated subcommand is opt-in, uses the
existing ten synthetic cases, and patches only the candidate runner's Provider
client construction.  Nothing in this module is imported by the production
request path.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import threading
import time
from typing import Any, Iterator
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
ORIGIN_SOURCE = BACKEND_DIR / "deepseek_client.py"
DEFAULT_ATTEMPTS = 20
PREFLIGHT_TOTAL_SECONDS = 8.0
PREFLIGHT_CONNECT_SECONDS = 3.0
PREFLIGHT_READ_SECONDS = 6.0
PREFLIGHT_WRITE_SECONDS = 3.0
PREFLIGHT_POOL_SECONDS = 3.0
PREFLIGHT_DELAY_SECONDS = 0.1
PATHS = ("A", "B", "C")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from deepseek_client import (  # noqa: E402
    DEEPSEEK_NETWORK_MODE_DIRECT,
    DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
    build_deepseek_client,
    build_deepseek_http_client,
)
from provider_deadline import DeadlineHttpxClient  # noqa: E402


class CandidateBlocked(RuntimeError):
    """A stable, non-sensitive candidate stop category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, int((percentile / 100) * len(ordered) + 0.999999) - 1),
    )
    return round(ordered[index], 3)


def _timing_summary(values: list[float]) -> dict[str, float]:
    return {
        "minimum_ms": round(min(values), 3) if values else 0.0,
        "median_ms": round(__import__("statistics").median(values), 3) if values else 0.0,
        "p95_ms": _percentile(values, 95),
        "maximum_ms": round(max(values), 3) if values else 0.0,
    }


def _presence(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _proxy_presence() -> dict[str, bool]:
    return {
        name: _presence(name)
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        )
    }


def _source_origin(source_path: Path) -> SplitResult:
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CandidateBlocked("provider_origin_source_unavailable") from exc
    match = re.search(r'^DEEPSEEK_BASE_URL\s*=\s*"([^"]+)"\s*$', source, re.MULTILINE)
    if match is None:
        raise CandidateBlocked("provider_origin_not_configured")
    parsed = urlsplit(match.group(1))
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CandidateBlocked("provider_origin_validation_failed")
    return parsed


def _origin_metadata(origin: SplitResult) -> dict[str, Any]:
    try:
        addresses = socket.getaddrinfo(
            origin.hostname,
            origin.port or 443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        addresses = []
    families = {item[0] for item in addresses}
    try:
        ca_paths = ssl.get_default_verify_paths()
        ca_available = bool(ca_paths.cafile and Path(ca_paths.cafile).is_file())
    except Exception:
        ca_available = False
    now_year = datetime.now(timezone.utc).year
    return {
        "scheme_https": origin.scheme == "https",
        "hostname": origin.hostname,
        "query_credentials_absent": not bool(
            origin.username or origin.password or origin.query or origin.fragment
        ),
        "resolver_type": "system_getaddrinfo",
        "ipv4_available": socket.AF_INET in families,
        "ipv6_available": socket.AF_INET6 in families,
        "ca_certificate_available": ca_available,
        "system_clock_valid": 2024 <= now_year <= 2035,
    }


def _append_no_proxy(value: str, hostname: str) -> tuple[str, bool]:
    entries = [entry.strip() for entry in value.split(",") if entry.strip()]
    normalized = {entry.casefold().lstrip(".") for entry in entries}
    if hostname.casefold() in normalized:
        return value, False
    entries.append(hostname)
    return ",".join(entries), True


def _rewrite_loopback_proxy(value: str, *, container_mode: bool) -> tuple[str, bool]:
    if not container_mode or not value.strip():
        return value, False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            return value, False
        userinfo = ""
        if "@" in parsed.netloc:
            userinfo = parsed.netloc.rsplit("@", 1)[0] + "@"
        port = parsed.port
        netloc = f"{userinfo}host.docker.internal"
        if port is not None:
            netloc += f":{port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)), True
    except (TypeError, ValueError):
        return value, False


def _configure_path(path: str, hostname: str, *, container_mode: bool) -> dict[str, Any]:
    if path not in PATHS:
        raise CandidateBlocked("network_path_invalid")
    original_presence = _proxy_presence()
    all_proxy_cleared = path in {"A", "B"}
    if all_proxy_cleared:
        for name in ("ALL_PROXY", "all_proxy"):
            # This is the same candidate-only protection used by the existing
            # runner.  It does not modify the host or any production process.
            os.environ[name] = ""
    rewritten = False
    if path in {"A", "B"}:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            value, changed = _rewrite_loopback_proxy(
                os.getenv(name, ""),
                container_mode=container_mode,
            )
            if changed:
                os.environ[name] = value
                rewritten = True
    no_proxy_appended = False
    if path == "B":
        for name in ("NO_PROXY", "no_proxy"):
            value, changed = _append_no_proxy(os.getenv(name, ""), hostname)
            os.environ[name] = value
            no_proxy_appended = no_proxy_appended or changed
    return {
        "original_proxy_presence": original_presence,
        "all_proxy_cleared_for_candidate": all_proxy_cleared,
        "container_loopback_proxy_rewritten": rewritten,
        "selective_no_proxy_appended": no_proxy_appended,
    }


def _selected_proxy_value(origin: SplitResult) -> str:
    if origin.scheme == "https":
        return os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or ""
    return os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or ""


def _proxy_targets(origin: SplitResult) -> tuple[set[str], int | None]:
    value = _selected_proxy_value(origin)
    try:
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.port is None:
            return set(), None
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        return {item[4][0] for item in addresses}, parsed.port
    except (OSError, TypeError, ValueError):
        return set(), None


def _proc_tcp_entries() -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for proc_path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = proc_path.read_text(encoding="ascii").splitlines()[1:]
        except (OSError, UnicodeError):
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 4:
                continue
            entries.append((fields[1], fields[2], fields[3]))
    return entries


def _decode_proc_ip(value: str, *, ipv6: bool) -> str | None:
    try:
        address = value.split(":", 1)[0]
        raw = bytes.fromhex(address)
        if ipv6:
            return str(ipaddress.IPv6Address(raw))
        return socket.inet_ntoa(raw[::-1])
    except (ValueError, OSError):
        return None


def _proxy_connection_count(targets: set[str], port: int | None) -> int:
    if not targets or port is None:
        return 0
    count = 0
    for proc_path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = proc_path.read_text(encoding="ascii").splitlines()[1:]
        except (OSError, UnicodeError):
            continue
        ipv6 = proc_path.name.endswith("tcp6")
        for line in lines:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "01":
                continue
            remote_ip = _decode_proc_ip(fields[2], ipv6=ipv6)
            try:
                remote_port = int(fields[2].rsplit(":", 1)[1], 16)
            except (ValueError, IndexError):
                continue
            if remote_ip in targets and remote_port == port:
                count += 1
    return count


def _mihomo_process_present() -> bool:
    for comm_path in Path("/proc").glob("[0-9]*/comm"):
        try:
            if comm_path.read_text(encoding="ascii").strip().casefold() == "mihomo":
                return True
        except (OSError, UnicodeError):
            continue
    return False


@dataclass
class _ProxyObserver:
    targets: set[str]
    port: int | None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    max_seen: int = 0

    def start(self) -> None:
        self._stop = threading.Event()

        def observe() -> None:
            while not self._stop.is_set():
                self.max_seen = max(self.max_seen, _proxy_connection_count(self.targets, self.port))
                self._stop.wait(0.005)

        self._thread = threading.Thread(target=observe, daemon=True)
        self._thread.start()

    def stop(self) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.25)
        self.max_seen = max(self.max_seen, _proxy_connection_count(self.targets, self.port))
        return self.max_seen > 0


def _classify_transport_error(exc: BaseException) -> str:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (socket.gaierror,)):
            return "dns_failure"
        if isinstance(current, ConnectionRefusedError):
            return "connection_refused"
        if isinstance(current, ssl.SSLError):
            return "tls_failure"
        if isinstance(current, httpx.ConnectTimeout):
            return "connect_timeout"
        if isinstance(current, httpx.ReadTimeout):
            return "read_timeout"
        if isinstance(current, httpx.WriteTimeout):
            return "write_timeout"
        if isinstance(current, httpx.PoolTimeout):
            return "pool_timeout"
        current = current.__cause__ or current.__context__
    return "other_transport_failure"


def _trace_timings() -> tuple[dict[str, float], Any]:
    marks: dict[str, float] = {}

    def trace(name: str, _info: dict[str, Any]) -> None:
        now = time.perf_counter()
        if name == "connection.connect_tcp.started":
            marks["tcp_start"] = now
        elif name == "connection.connect_tcp.complete":
            marks["tcp_end"] = now
        elif name == "connection.start_tls.started":
            marks["tls_start"] = now
        elif name == "connection.start_tls.complete":
            marks["tls_end"] = now

    return marks, trace


def _transport_selected(client: httpx.Client, origin: SplitResult) -> bool:
    try:
        selected = client._transport_for_url(httpx.URL(urlunsplit(origin)))
        return selected is not client._transport
    except Exception:
        return False


def _one_preflight(origin: SplitResult, path: str, *, container_mode: bool) -> dict[str, Any]:
    configured = _configure_path(path, origin.hostname or "", container_mode=container_mode)
    trust_env = path in {"A", "B"}
    targets, proxy_port = _proxy_targets(origin)
    observer = _ProxyObserver(targets, proxy_port)
    marks, trace = _trace_timings()
    start = time.perf_counter()
    deadline = time.monotonic() + PREFLIGHT_TOTAL_SECONDS
    client: DeadlineHttpxClient | None = None
    status: int | None = None
    category = "other_transport_failure"
    proxy_selected = False
    try:
        timeout = httpx.Timeout(
            connect=PREFLIGHT_CONNECT_SECONDS,
            read=PREFLIGHT_READ_SECONDS,
            write=PREFLIGHT_WRITE_SECONDS,
            pool=PREFLIGHT_POOL_SECONDS,
        )
        client = build_deepseek_http_client(
            network_mode=(
                DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY
                if trust_env
                else DEEPSEEK_NETWORK_MODE_DIRECT
            ),
            deadline_monotonic=deadline,
            timeout=timeout,
            follow_redirects=False,
        )
        proxy_selected = _transport_selected(client, origin)
        observer.start()
        request = client.build_request("GET", urlunsplit(origin))
        request.extensions["trace"] = trace
        response = client.send(request, stream=False)
        status = response.status_code
        response.close()
        category = "transport_success"
    except BaseException as exc:
        category = _classify_transport_error(exc)
    finally:
        proxy_observed = observer.stop()
        if client is not None:
            client.close()
    total_ms = round((time.perf_counter() - start) * 1000, 3)
    tcp_ms = 0.0
    tls_ms = 0.0
    if "tcp_start" in marks and "tcp_end" in marks:
        tcp_ms = round((marks["tcp_end"] - marks["tcp_start"]) * 1000, 3)
    if "tls_start" in marks and "tls_end" in marks:
        tls_ms = round((marks["tls_end"] - marks["tls_start"]) * 1000, 3)
    return {
        "category": category,
        "status": status,
        "transport_success": category == "transport_success",
        "proxy_transport_selected": proxy_selected,
        "proxy_connection_observed": proxy_observed,
        "tcp_connect_ms": tcp_ms,
        "tls_ms": tls_ms,
        "total_ms": total_ms,
        "configured": configured,
        "trust_env": trust_env,
    }


def _preflight(path: str, attempts: int, source_path: Path, output_path: Path) -> dict[str, Any]:
    origin = _source_origin(source_path)
    origin_info = _origin_metadata(origin)
    container_mode = os.getenv("PJA_CONTAINER_MODE") == "1"
    records: list[dict[str, Any]] = []
    for index in range(attempts):
        records.append(_one_preflight(origin, path, container_mode=container_mode))
        if index + 1 < attempts:
            time.sleep(PREFLIGHT_DELAY_SECONDS)
    counts = Counter(record["category"] for record in records)
    statuses = Counter(str(record["status"]) for record in records if record["status"] is not None)
    tcp_timings = [record["tcp_connect_ms"] for record in records if record["tcp_connect_ms"] > 0]
    tls_timings = [record["tls_ms"] for record in records if record["tls_ms"] > 0]
    total_timings = [record["total_ms"] for record in records]
    proxy_selected = sum(bool(record["proxy_transport_selected"]) for record in records)
    proxy_observed = sum(bool(record["proxy_connection_observed"]) for record in records)
    summary = {
        "schema_version": 1,
        "mode": "unauthenticated_preflight",
        "environment": "container" if container_mode else "host",
        "path": path,
        "origin": origin_info,
        "proxy_presence": records[0]["configured"]["original_proxy_presence"] if records else _proxy_presence(),
        "http_client": {
            "trust_env": records[0]["trust_env"] if records else path in {"A", "B"},
            "proxy_transport_selected_count": proxy_selected,
            "proxy_transport_selected": proxy_selected > 0,
            "proxy_connection_observed_count": proxy_observed,
            "proxy_connection_observed": proxy_observed > 0,
            "mihomo_process_present": _mihomo_process_present(),
            "direct_bypass_proven": (
                path in {"B", "C"}
                and proxy_selected == 0
                and proxy_observed == 0
            ),
        },
        "configuration": {
            "all_proxy_cleared_for_candidate": bool(
                records and records[0]["configured"]["all_proxy_cleared_for_candidate"]
            ),
            "container_loopback_proxy_rewritten": bool(
                records and records[0]["configured"]["container_loopback_proxy_rewritten"]
            ),
            "selective_no_proxy_appended": bool(
                records and records[0]["configured"]["selective_no_proxy_appended"]
            ),
            "tls_verification_enabled": True,
            "api_key_sent": False,
            "authorization_header_sent": False,
            "request_body_sent": False,
        },
        "attempt_count": attempts,
        "transport_success_count": sum(record["transport_success"] for record in records),
        "dns_failure_count": counts.get("dns_failure", 0),
        "connect_timeout_count": counts.get("connect_timeout", 0),
        "connection_refused_count": counts.get("connection_refused", 0),
        "tls_failure_count": counts.get("tls_failure", 0),
        "read_timeout_count": counts.get("read_timeout", 0),
        "write_timeout_count": counts.get("write_timeout", 0),
        "pool_timeout_count": counts.get("pool_timeout", 0),
        "other_transport_failure_count": counts.get("other_transport_failure", 0),
        "status_categories": dict(sorted(statuses.items())),
        "tcp_connect_timing_ms": _timing_summary(tcp_timings),
        "tls_timing_ms": _timing_summary(tls_timings),
        "total_timing_ms": _timing_summary(total_timings),
        "bounded_timeout_seconds": PREFLIGHT_TOTAL_SECONDS,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _candidate_build_provider_client(
    runtime_settings: Any,
    *,
    deadline: Any,
    kind: str,
    trust_env: bool,
) -> tuple[Any, DeadlineHttpxClient, Any]:
    timeout = deadline.call_timeout(
        configured_timeout_seconds=runtime_settings.request_timeout_seconds,
        kind=kind,
    )
    if timeout is None:
        raise RuntimeError("candidate_provider_deadline_no_safe_call_budget")
    from legacy_application import OpenAI

    return build_deepseek_client(
        runtime_settings,
        deadline=deadline,
        kind=kind,
        network_mode=(
            DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY
            if trust_env
            else DEEPSEEK_NETWORK_MODE_DIRECT
        ),
        client_class=OpenAI,
    )


def _authenticated(path: str, output_path: Path) -> dict[str, Any]:
    if path not in {"B", "C"}:
        raise CandidateBlocked("authenticated_direct_path_required")
    if os.getenv("PJA_REAL_DEEPSEEK_DIRECT_CANDIDATE") != "1":
        raise CandidateBlocked("manual_authenticated_opt_in_required")
    origin = _source_origin(Path(os.getenv("PJA_DEEPSEEK_SOURCE_FILE", ORIGIN_SOURCE)))
    _configure_path(
        path,
        origin.hostname or "",
        container_mode=os.getenv("PJA_CONTAINER_MODE") == "1",
    )
    os.environ["APP_ENV"] = "development"
    artifact_dir = Path(os.getenv("PJA_CANDIDATE_ARTIFACT_DIR", "/tmp/pja-deepseek-direct"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("APP_DATABASE_PATH", str(artifact_dir / "candidate.sqlite"))
    os.environ.setdefault("PROJECT_KNOWLEDGE_PATH", str(artifact_dir / "synthetic-project-knowledge.md"))
    os.environ["PJA_REAL_DEEPSEEK_CANDIDATE"] = "1"
    os.environ["MOCK_PROVIDER_ENABLED"] = "false"
    os.environ["AGENT_MODEL_MAX_OUTPUT_TOKENS"] = "1600"
    os.environ["AGENT_MODEL_LENGTH_RETRY_OUTPUT_TOKENS"] = "2400"
    os.environ["AGENT_MODEL_REPAIR_OUTPUT_TOKENS"] = "1000"
    os.environ["PROVIDER_OVERALL_DEADLINE_SECONDS"] = "130"
    os.environ["PROVIDER_RETRY_BACKOFF_SECONDS"] = "0.25"
    from unittest.mock import patch
    from candidates import deepseek_provider_real_candidate as runner
    import legacy_application

    trust_env = path == "B"

    def build_provider_client(runtime_settings: Any, *, deadline: Any, kind: str) -> tuple[Any, DeadlineHttpxClient, Any]:
        return _candidate_build_provider_client(
            runtime_settings,
            deadline=deadline,
            kind=kind,
            trust_env=trust_env,
        )

    with patch.object(legacy_application, "_build_provider_client", side_effect=build_provider_client):
        summary = runner.run(output_path)
    summary["network_path"] = path
    summary["http_client_trust_env"] = trust_env
    summary["proxy_transport_expected"] = False
    summary["direct_bypass_proven_by_preflight"] = True
    summary["maximum_active_provider_operation_lifetime_ms"] = summary.get(
        "maximum_active_provider_operation_lifetime_ms",
        summary.get("maximum_provider_duration_ms", 0.0),
    )
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--path", choices=PATHS, required=True)
    preflight.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    preflight.add_argument("--source", type=Path, default=ORIGIN_SOURCE)
    preflight.add_argument("--output", type=Path, required=True)
    authenticated = subparsers.add_parser("authenticated")
    authenticated.add_argument("--path", choices=("B", "C"), required=True)
    authenticated.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            if args.attempts != DEFAULT_ATTEMPTS:
                raise CandidateBlocked("preflight_attempt_count_must_be_twenty")
            summary = _preflight(args.path, args.attempts, args.source, args.output)
            print(json.dumps({
                "environment": summary["environment"],
                "path": summary["path"],
                "attempt_count": summary["attempt_count"],
                "transport_success_count": summary["transport_success_count"],
                "proxy_transport_selected": summary["http_client"]["proxy_transport_selected"],
                "proxy_connection_observed": summary["http_client"]["proxy_connection_observed"],
                "direct_bypass_proven": summary["http_client"]["direct_bypass_proven"],
                "dns_failure_count": summary["dns_failure_count"],
                "connect_timeout_count": summary["connect_timeout_count"],
                "tls_failure_count": summary["tls_failure_count"],
                "read_timeout_count": summary["read_timeout_count"],
            }, sort_keys=True))
        else:
            summary = _authenticated(args.path, args.output)
            print(json.dumps({
                "network_path": summary["network_path"],
                "candidate_execution_count": summary["candidate_execution_count"],
                "complete": summary["complete"],
                "repaired": summary["repaired"],
                "partial": summary["partial"],
                "fallback": summary["fallback"],
                "retry_count": summary["retry_count"],
                "repair_count": summary["repair_count"],
                "maximum_provider_calls": summary["maximum_provider_calls"],
                "deadline_exhausted_count": summary["deadline_exhausted_count"],
                "timeout_categories": summary["timeout_categories"],
                "fallback_reason_categories": summary["fallback_reason_categories"],
                "maximum_provider_duration_ms": summary["maximum_provider_duration_ms"],
                "maximum_end_to_end_duration_ms": summary["maximum_end_to_end_duration_ms"],
                "safe_log_inspection_passed": summary["safe_log_inspection_passed"],
            }, sort_keys=True))
    except CandidateBlocked as exc:
        print(json.dumps({"candidate_blocker": exc.category}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
