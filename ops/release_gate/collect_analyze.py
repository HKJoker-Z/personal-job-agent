#!/usr/bin/env python3
"""Collect a five-run production-equivalent Analyze release-gate sample.

This is operations tooling, not application runtime code.  It uses a dedicated
test account, normal HTTPS authentication, RAG, History, monitoring, Java, and
PostgreSQL-backed APIs.  Response bodies and credentials are never written to
the evidence report.  Bounded raw container logs are retained mode 0600 for
diagnosis, especially if a public connection closes without a response.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from functools import partial
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

try:
    from ops.release_gate.analyze_gate import RUN_COUNT, evaluate
except ModuleNotFoundError:  # Direct execution from this directory.
    from analyze_gate import RUN_COUNT, evaluate


ALLOWED_ANALYSIS_STATES = {"complete", "repaired", "partial", "fallback"}
ERROR_PATTERN = re.compile(
    r"connection reset|broken pipe|premature(?:ly)? close|upstream timed out|"
    r"empty reply|traceback|\bfatal\b|\bpanic\b|\boom\b|uncaught|\bcritical\b",
    re.IGNORECASE,
)
PROXY_ENVIRONMENT_NAMES = {
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
}
PRODUCTION_DIRECT_PATH = "production-actual-public-direct"
CANDIDATE_EQUIVALENT_PATH = "candidate-public-equivalent"


class CollectionFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class DirectTarget:
    hostname: str
    port: int
    resolved_ips: tuple[str, ...]
    interface: str
    source_ip: str


def proxy_environment_names(environment: dict[str, str] | None = None) -> tuple[str, ...]:
    """Return proxy variable names only; values may contain credentials."""
    source = os.environ if environment is None else environment
    return tuple(sorted(key for key in source if key.lower() in PROXY_ENVIRONMENT_NAMES))


def direct_request_environment(
    environment: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an environment for one direct request without mutating the host."""
    source = os.environ if environment is None else environment
    return {
        key: value
        for key, value in source.items()
        if key.lower() not in PROXY_ENVIRONMENT_NAMES
    }


def direct_curl_options(
    target_hostname: str, direct_interface: str | None = None
) -> list[str]:
    # --noproxy is scoped to this URL's exact host. Removing the curl child
    # environment too prevents case/precedence surprises and silent fallback.
    options = ["--noproxy", target_hostname]
    if direct_interface:
        options.extend(("--interface", direct_interface))
    return options


def production_target(base_url: str) -> tuple[str, int]:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise CollectionFailure("production_direct_base_url_must_be_plain_https_origin")
    return parsed.hostname, parsed.port or 443


def resolve_target(hostname: str, port: int) -> tuple[str, ...]:
    try:
        values = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise CollectionFailure("production_direct_target_resolution_failed") from error
    addresses = tuple(sorted({str(value[4][0]) for value in values if value[4]}))
    if not addresses:
        raise CollectionFailure("production_direct_target_resolution_empty")
    return addresses


def interface_source_ip(interface: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", interface) or interface == "lo":
        raise CollectionFailure("production_direct_interface_invalid")
    process = subprocess.run(
        ["ip", "-j", "address", "show", "dev", interface],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
    )
    try:
        values = json.loads(process.stdout)
        addresses = [
            item["local"]
            for value in values
            for item in value.get("addr_info", [])
            if item.get("family") == "inet" and item.get("scope") == "global"
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        addresses = []
    if process.returncode != 0 or len(addresses) != 1:
        raise CollectionFailure("production_direct_interface_ipv4_unavailable")
    try:
        address = ipaddress.ip_address(addresses[0])
    except ValueError as error:
        raise CollectionFailure("production_direct_interface_ip_invalid") from error
    if address.is_loopback or address.is_unspecified:
        raise CollectionFailure("production_direct_interface_ip_not_routable")
    return str(address)


def direct_route_observation(target: DirectTarget, remote_ip: str) -> dict[str, Any]:
    process = subprocess.run(
        ["ip", "-j", "route", "get", remote_ip, "from", target.source_ip],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
    )
    try:
        value = json.loads(process.stdout)[0]
    except (IndexError, TypeError, ValueError, json.JSONDecodeError):
        value = {}
    route_interface = value.get("dev")
    route_source = value.get("prefsrc") or value.get("src") or value.get("from")
    verified = bool(
        process.returncode == 0
        and route_interface == target.interface
        and route_source == target.source_ip
    )
    return {
        "route_interface": route_interface,
        "route_source_ip": route_source,
        "route_gateway": value.get("gateway"),
        "direct_route_verified": verified,
    }


def direct_remote_assertion(
    remote_ip: object,
    remote_port: object,
    resolved_ips: tuple[str, ...],
    target_port: int,
) -> tuple[bool, str | None]:
    if not isinstance(remote_ip, str) or not remote_ip:
        return False, "direct_remote_ip_missing"
    try:
        address = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False, "direct_remote_ip_invalid"
    if address.is_loopback:
        return False, "direct_remote_is_loopback_proxy"
    try:
        parsed_resolved = {ipaddress.ip_address(value) for value in resolved_ips}
    except ValueError:
        return False, "direct_resolved_ip_invalid"
    if address not in parsed_resolved:
        return False, "direct_remote_not_resolved_target"
    try:
        port = int(remote_port)
    except (TypeError, ValueError):
        return False, "direct_remote_port_missing"
    if port != target_port:
        return False, "direct_remote_port_mismatch"
    return True, None


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def rfc3339(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def atomic_json(path: Path, value: dict[str, Any]) -> None:
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


def read_secret(path: Path) -> str:
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise CollectionFailure("password_file_permissions_not_0600")
    value = path.read_text(encoding="utf-8").strip("\r\n")
    if not value:
        raise CollectionFailure("password_file_empty")
    return value


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"pja_release_gate_{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class SourceAddressHTTPSHandler(HTTPSHandler):
    """HTTPS handler bound to the reviewed physical source address."""

    def __init__(self, *, context: ssl.SSLContext, source_ip: str):
        super().__init__(context=context)
        self.source_ip = source_ip

    def https_open(self, request: Request) -> Any:
        connection = partial(
            http.client.HTTPSConnection,
            source_address=(self.source_ip, 0),
        )
        return self.do_open(connection, request, context=self._context)


class PublicClient:
    def __init__(
        self,
        base_url: str,
        origin: str,
        ca_file: Path | None,
        timeout: float,
        *,
        direct: bool = False,
        direct_source_ip: str | None = None,
    ):
        context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        self.cookies = CookieJar()
        handlers: list[object] = []
        if direct:
            handlers.append(ProxyHandler({}))
        if direct_source_ip:
            handlers.append(
                SourceAddressHTTPSHandler(context=context, source_ip=direct_source_ip)
            )
        else:
            handlers.append(HTTPSHandler(context=context))
        handlers.append(HTTPCookieProcessor(self.cookies))
        self.opener = build_opener(*handlers)
        self.base_url = base_url.rstrip("/")
        self.origin = origin
        self.ca_file = ca_file
        self.timeout = timeout
        self.direct = direct
        self.direct_source_ip = direct_source_ip
        self.csrf = ""

    def call(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[int | None, bytes, dict[str, str], str | None]:
        headers = {
            "Accept": "application/json",
            "Origin": self.origin,
            "User-Agent": "PJA-production-equivalent-release-gate/1",
            "X-Request-ID": request_id,
        }
        if self.csrf and method not in {"GET", "HEAD"}:
            headers["X-CSRF-Token"] = self.csrf
        if content_type:
            headers["Content-Type"] = content_type
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.status, response.read(), dict(response.headers.items()), None
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers.items()), None
        except http.client.RemoteDisconnected:
            return None, b"", {}, "empty_reply"
        except (URLError, TimeoutError, ssl.SSLError, ConnectionError, OSError) as error:
            message = str(error).lower()
            category = (
                "empty_reply"
                if "remote end closed" in message or "empty reply" in message
                else "connection_failure"
            )
            return None, b"", {}, category

    def json_call(
        self,
        path: str,
        *,
        method: str = "GET",
        value: object | None = None,
        request_id: str,
    ) -> tuple[int | None, object | None, bytes, dict[str, str], str | None]:
        body = None
        content_type = None
        if value is not None:
            body = json.dumps(value, separators=(",", ":")).encode()
            content_type = "application/json"
        status, raw, headers, error = self.call(
            path,
            method=method,
            body=body,
            content_type=content_type,
            request_id=request_id,
        )
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return status, parsed, raw, headers, error

    def cookie_header(self) -> str:
        return "; ".join(f"{cookie.name}={cookie.value}" for cookie in self.cookies)


def _curl_json_number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def curl_direct_probe(
    base_url: str,
    *,
    path: str,
    ca_file: Path | None,
    timeout: float,
    direct_interface: str,
) -> dict[str, Any]:
    """Prove HTTPS connectivity to the resolved production endpoint directly."""
    hostname, target_port = production_target(base_url)
    resolved_ips = resolve_target(hostname, target_port)
    target = DirectTarget(
        hostname=hostname,
        port=target_port,
        resolved_ips=resolved_ips,
        interface=direct_interface,
        source_ip=interface_source_ip(direct_interface),
    )
    response_fd, response_name = tempfile.mkstemp(prefix=".pja-direct-probe-")
    os.close(response_fd)
    response_path = Path(response_name)
    os.chmod(response_path, 0o600)
    command = [
        "curl",
        "--silent",
        "--show-error",
        *direct_curl_options(hostname, direct_interface),
        "--request",
        "GET",
        "--url",
        base_url.rstrip("/") + path,
        "--header",
        "Accept: application/json",
        "--header",
        "User-Agent: PJA-production-direct-path-probe/1",
        "--output",
        str(response_path),
        "--connect-timeout",
        "15",
        "--max-time",
        str(timeout),
        "--write-out",
        "%{json}\n",
    ]
    if ca_file is not None:
        command.extend(("--cacert", str(ca_file)))
    detected_proxy_names = proxy_environment_names()
    process = subprocess.run(
        command,
        env=direct_request_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 10,
        check=False,
    )
    try:
        response_bytes = response_path.stat().st_size
    finally:
        response_path.unlink(missing_ok=True)
    try:
        metrics = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        metrics = {}
    if not isinstance(metrics, dict):
        metrics = {}
    try:
        status = int(metrics.get("http_code") or 0) or None
    except (TypeError, ValueError):
        status = None
    remote_verified, remote_failure = direct_remote_assertion(
        metrics.get("remote_ip"), metrics.get("remote_port"), resolved_ips, target_port
    )
    local_verified = metrics.get("local_ip") == target.source_ip
    route = direct_route_observation(target, str(metrics.get("remote_ip") or hostname))
    scheme = str(metrics.get("scheme") or "").lower()
    tls_verified = bool(
        process.returncode == 0
        and scheme == "https"
        and _curl_json_number(metrics.get("ssl_verify_result")) == 0
    )
    verified = bool(
        process.returncode == 0
        and isinstance(status, int)
        and 200 <= status < 300
        and response_bytes > 0
        and tls_verified
        and remote_verified
        and local_verified
        and route["direct_route_verified"]
    )
    return {
        "path": path,
        "target_hostname": hostname,
        "target_port": target_port,
        "target_resolved_ips": list(resolved_ips),
        "host_proxy_environment_names": list(detected_proxy_names),
        "request_proxy_environment_removed": True,
        "curl_noproxy_target": hostname,
        "direct_interface": direct_interface,
        "target_source_ip": target.source_ip,
        "curl_exit_code": process.returncode,
        "curl_stderr": process.stderr[-4096:],
        "http_status": status,
        "response_bytes": response_bytes,
        "local_ip": metrics.get("local_ip"),
        "local_port": metrics.get("local_port"),
        "remote_ip": metrics.get("remote_ip"),
        "remote_port": metrics.get("remote_port"),
        "connect_time_ms": (
            round(value * 1000, 3)
            if (value := _curl_json_number(metrics.get("time_connect"))) is not None
            else None
        ),
        "start_transfer_time_ms": (
            round(value * 1000, 3)
            if (value := _curl_json_number(metrics.get("time_starttransfer"))) is not None
            else None
        ),
        "total_time_ms": (
            round(value * 1000, 3)
            if (value := _curl_json_number(metrics.get("time_total"))) is not None
            else None
        ),
        "https_scheme": scheme == "https",
        "tls_verified": tls_verified,
        "direct_remote_verified": remote_verified,
        "direct_remote_failure": remote_failure,
        "direct_local_source_verified": local_verified,
        "direct_path_verified": verified,
        **route,
    }


def curl_analyze(
    client: PublicClient,
    *,
    resume_version_id: str,
    job_file: Path,
    request_id: str,
    idempotency_key: str,
    artifact_dir: Path,
    timeout: float,
    direct_target: DirectTarget | None = None,
) -> tuple[int | None, bytes, dict[str, str], str | None, dict[str, Any]]:
    """Run Analyze with curl while retaining bounded, body-free client diagnostics."""
    artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    response_fd, response_name = tempfile.mkstemp(prefix=".analyze-response-", dir=artifact_dir)
    headers_fd, headers_name = tempfile.mkstemp(prefix=".analyze-headers-", dir=artifact_dir)
    os.close(response_fd)
    os.close(headers_fd)
    response_path = Path(response_name)
    headers_path = Path(headers_name)
    os.chmod(response_path, 0o600)
    os.chmod(headers_path, 0o600)
    cookie = client.cookie_header()
    if not cookie or not client.csrf:
        raise CollectionFailure("curl_authentication_material_missing")
    # Secrets are supplied on stdin, never in argv, process listings, logs, or evidence.
    secret_config = (
        f'header = "X-CSRF-Token: {client.csrf}"\n'
        f'header = "Cookie: {cookie}"\n'
    )
    command = [
        "curl",
        "--silent",
        "--show-error",
        *(
            direct_curl_options(direct_target.hostname, direct_target.interface)
            if direct_target
            else []
        ),
        "--request",
        "POST",
        "--url",
        client.base_url + "/api/analyze",
        "--header",
        "Accept: application/json",
        "--header",
        f"Origin: {client.origin}",
        "--header",
        "User-Agent: PJA-production-equivalent-release-gate/2",
        "--header",
        f"X-Request-ID: {request_id}",
        "--header",
        f"Idempotency-Key: {idempotency_key}",
        "--form",
        f"resume_version_id={resume_version_id}",
        "--form",
        f"job_text=<{job_file}",
        "--form",
        "save_to_history=true",
        "--form",
        "use_project_knowledge=true",
        "--form",
        "project_knowledge_top_k=5",
        "--config",
        "-",
        "--dump-header",
        str(headers_path),
        "--output",
        str(response_path),
        "--connect-timeout",
        "15",
        "--max-time",
        str(timeout),
        "--write-out",
        "%{json}\n",
    ]
    if client.ca_file is not None:
        command.extend(("--cacert", str(client.ca_file)))
    process = subprocess.run(
        command,
        env=direct_request_environment() if direct_target else None,
        input=secret_config,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 10,
        check=False,
    )
    try:
        raw = response_path.read_bytes()
        raw_headers = headers_path.read_text(encoding="utf-8", errors="replace")
    finally:
        response_path.unlink(missing_ok=True)
        headers_path.unlink(missing_ok=True)
    try:
        metrics = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        metrics = {}
    if not isinstance(metrics, dict):
        metrics = {}
    status_value = metrics.get("http_code")
    try:
        status = int(status_value) if int(status_value) > 0 else None
    except (TypeError, ValueError):
        status = None
    headers: dict[str, str] = {}
    for line in raw_headers.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    stderr = process.stderr[-4096:]
    if process.returncode == 0:
        transport_error = None
    elif process.returncode == 52 or (status is None and not raw):
        transport_error = "empty_reply"
    else:
        transport_error = "connection_failure"
    direct_verified: bool | None = None
    direct_failure: str | None = None
    if direct_target:
        direct_verified, direct_failure = direct_remote_assertion(
            metrics.get("remote_ip"),
            metrics.get("remote_port"),
            direct_target.resolved_ips,
            direct_target.port,
        )
        local_verified = metrics.get("local_ip") == direct_target.source_ip
        route = direct_route_observation(
            direct_target, str(metrics.get("remote_ip") or direct_target.hostname)
        )
        direct_verified = bool(
            direct_verified and local_verified and route["direct_route_verified"]
        )
        if not local_verified:
            direct_failure = "direct_local_source_not_bound_interface"
        elif route["direct_route_verified"] is not True:
            direct_failure = "direct_route_not_bound_interface"
        if not direct_verified:
            transport_error = "proxy_path_detected"
    else:
        local_verified = None
        route = {}
    diagnostics = {
        "client_exit_code": process.returncode,
        "client_stderr": stderr,
        "client_http_status": status,
        "client_response_bytes": len(raw),
        "client_size_download": _curl_json_number(metrics.get("size_download")),
        "client_connect_time_ms": (
            round(value * 1000, 3)
            if (value := _curl_json_number(metrics.get("time_connect"))) is not None
            else None
        ),
        "client_start_transfer_time_ms": (
            round(value * 1000, 3)
            if (value := _curl_json_number(metrics.get("time_starttransfer"))) is not None
            else None
        ),
        "client_total_time_ms": (
            round(value * 1000, 3)
            if (value := _curl_json_number(metrics.get("time_total"))) is not None
            else None
        ),
        "client_remote_ip": metrics.get("remote_ip"),
        "client_remote_port": metrics.get("remote_port"),
        "client_local_ip": metrics.get("local_ip"),
        "client_local_port": metrics.get("local_port"),
        "client_raw_error": stderr,
        "direct_path_required": direct_target is not None,
        "direct_path_verified": direct_verified,
        "direct_path_failure": direct_failure,
        "target_hostname": direct_target.hostname if direct_target else None,
        "target_port": direct_target.port if direct_target else None,
        "target_resolved_ips": list(direct_target.resolved_ips) if direct_target else [],
        "direct_interface": direct_target.interface if direct_target else None,
        "target_source_ip": direct_target.source_ip if direct_target else None,
        "direct_local_source_verified": local_verified,
        "request_proxy_environment_removed": direct_target is not None,
        **route,
    }
    return status, raw, headers, transport_error, diagnostics


def docker_logs(container: str, start: dt.datetime, end: dt.datetime) -> tuple[bool, str]:
    process = subprocess.run(
        [
            "docker",
            "logs",
            "--since",
            rfc3339(start),
            "--until",
            rfc3339(end),
            container,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return process.returncode == 0, process.stdout


def json_lines(raw: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def matching(values: list[dict[str, Any]], request_id: str, message: str) -> list[dict[str, Any]]:
    return [
        value
        for value in values
        if str(value.get("request_id") or "") == request_id
        and str(value.get("message") or "") == message
    ]


def nginx_number(value: object, *, milliseconds: bool = False) -> float | int | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if milliseconds:
        return round(number * 1000, 3)
    return int(number) if number.is_integer() else number


def runtime_snapshot(containers: dict[str, str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for layer, container in containers.items():
        process = subprocess.run(
            ["docker", "inspect", container],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
            check=False,
        )
        if process.returncode != 0:
            snapshot[layer] = {"inspect_ok": False, "container": container}
            continue
        try:
            value = json.loads(process.stdout)[0]
            state = value.get("State") or {}
            networks = (value.get("NetworkSettings") or {}).get("Networks") or {}
            snapshot[layer] = {
                "inspect_ok": True,
                "container": container,
                "container_id": str(value.get("Id") or "")[:12],
                "image": value.get("Image"),
                "started_at": state.get("StartedAt"),
                "restart_count": value.get("RestartCount"),
                "oom_killed": state.get("OOMKilled"),
                "health": (state.get("Health") or {}).get("Status"),
                "networks": {
                    name: {"ip_address": details.get("IPAddress")}
                    for name, details in networks.items()
                },
            }
        except (IndexError, TypeError, ValueError, json.JSONDecodeError):
            snapshot[layer] = {"inspect_ok": False, "container": container}
    return snapshot


def response_is_complete(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = {
        "analysis_status",
        "application_id",
        "saved_to_history",
        "workflow_id",
        "workflow_duration_ms",
        "workflow_steps",
        "used_knowledge_base",
        "retrieval_count",
        "rag_sources",
        "analysis_warnings",
        "scoring_breakdown",
        "security_status",
    }
    return required.issubset(value)


def output_is_correct(value: object) -> bool:
    if not response_is_complete(value):
        return False
    assert isinstance(value, dict)
    return bool(
        value.get("analysis_status") in ALLOWED_ANALYSIS_STATES
        and isinstance(value.get("application_id"), int)
        and value.get("saved_to_history") is True
        and isinstance(value.get("workflow_id"), str)
        and value.get("workflow_id")
        and isinstance(value.get("workflow_duration_ms"), (int, float))
        and value.get("used_knowledge_base") is True
        and isinstance(value.get("retrieval_count"), int)
        and value.get("retrieval_count") > 0
        and isinstance(value.get("rag_sources"), list)
        and value.get("rag_sources")
        and isinstance(value.get("analysis_warnings"), list)
        and isinstance(value.get("scoring_breakdown"), dict)
        and isinstance(value.get("workflow_steps"), list)
        and value.get("workflow_steps")
    )


def safe_request_id(prefix: str, label: str) -> str:
    value = f"{prefix}-{label}-{secrets.token_hex(6)}"
    if len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value):
        raise CollectionFailure("request_prefix_invalid")
    return value


def require_json_success(
    client: PublicClient,
    path: str,
    *,
    method: str,
    value: object | None,
    request_id: str,
) -> dict[str, Any]:
    status, parsed, _raw, _headers, error = client.json_call(
        path, method=method, value=value, request_id=request_id
    )
    if error or not isinstance(status, int) or not 200 <= status < 300 or not isinstance(parsed, dict):
        raise CollectionFailure(f"setup_request_failed:{path}")
    return parsed


def collect(args: argparse.Namespace) -> dict[str, Any]:
    hard_gates = json.loads(args.hard_gates.read_text(encoding="utf-8"))
    if not isinstance(hard_gates, dict):
        raise CollectionFailure("hard_gates_not_object")
    resume_content = json.loads(args.resume_file.read_text(encoding="utf-8"))
    job_text = args.job_file.read_text(encoding="utf-8")
    if not isinstance(resume_content, dict) or not 1_500 <= len(json.dumps(resume_content)) <= 30_000:
        raise CollectionFailure("resume_fixture_not_production_equivalent_length")
    if not 1_500 <= len(job_text) <= 20_000:
        raise CollectionFailure("job_fixture_not_production_equivalent_length")

    direct_path = args.acceptance_path == PRODUCTION_DIRECT_PATH
    direct_probes: list[dict[str, Any]] = []
    direct_target: DirectTarget | None = None
    if direct_path:
        if not args.direct_interface:
            raise CollectionFailure("production_direct_interface_required")
        hostname, target_port = production_target(args.base_url)
        resolved_ips = resolve_target(hostname, target_port)
        direct_target = DirectTarget(
            hostname=hostname,
            port=target_port,
            resolved_ips=resolved_ips,
            interface=args.direct_interface,
            source_ip=interface_source_ip(args.direct_interface),
        )
        for path in ("/api/health", "/api/ready"):
            probe = curl_direct_probe(
                args.base_url,
                path=path,
                ca_file=args.ca_file,
                timeout=min(args.timeout, 30.0),
                direct_interface=args.direct_interface,
            )
            direct_probes.append(probe)
            atomic_json(
                args.output,
                {
                    "schema_version": 2,
                    "acceptance_path": args.acceptance_path,
                    "direct_path_probes": direct_probes,
                    "hard_gates": hard_gates,
                    "runs": [],
                },
            )
            if probe.get("direct_path_verified") is not True:
                raise CollectionFailure(f"production_direct_probe_failed:{path}")

    password = read_secret(args.password_file)
    client = PublicClient(
        args.base_url,
        args.origin,
        args.ca_file,
        args.timeout,
        direct=direct_path,
        direct_source_ip=direct_target.source_ip if direct_target else None,
    )
    prefix = args.request_prefix

    login = require_json_success(
        client,
        "/api/auth/login",
        method="POST",
        value={"email": args.email, "password": password, "remember_me": False},
        request_id=safe_request_id(prefix, "login"),
    )
    password = ""
    csrf = login.get("csrf_token")
    if login.get("authenticated") is not True or not isinstance(csrf, str) or not csrf:
        raise CollectionFailure("authentication_contract_failed")
    client.csrf = csrf

    resume = require_json_success(
        client,
        "/api/resumes",
        method="POST",
        value={
            "title": "Isolated release acceptance resume",
            "language": "en",
            "target_role": "Senior Platform Engineer",
        },
        request_id=safe_request_id(prefix, "resume"),
    )
    resume_id = str(resume.get("id") or "")
    version = require_json_success(
        client,
        f"/api/resumes/{resume_id}/versions",
        method="POST",
        value={"content": resume_content, "change_summary": "Release acceptance fixture"},
        request_id=safe_request_id(prefix, "version"),
    )
    version_id = str(version.get("id") or "")
    require_json_success(
        client,
        f"/api/resumes/{resume_id}/versions/{version_id}/finalize",
        method="POST",
        value=None,
        request_id=safe_request_id(prefix, "finalize"),
    )
    require_json_success(
        client,
        "/api/project-knowledge/rebuild",
        method="POST",
        value=None,
        request_id=safe_request_id(prefix, "rag"),
    )

    containers = {
        "edge": args.edge_container,
        "frontend": args.frontend_container,
        "backend": args.backend_container,
        "java": args.java_container,
    }
    schedule = tuple(float(item) for item in args.schedule_seconds.split(","))
    if len(schedule) != RUN_COUNT or any(item < 0 for item in schedule):
        raise CollectionFailure("schedule_must_contain_five_nonnegative_seconds")
    if any(left > right for left, right in zip(schedule, schedule[1:])):
        raise CollectionFailure("schedule_must_be_nondecreasing")

    evidence: dict[str, Any] = {
        "schema_version": 2,
        "started_at": rfc3339(utc_now()),
        "base_url": args.base_url,
        "acceptance_path": args.acceptance_path,
        "direct_path_probes": direct_probes,
        "production_equivalent": {
            "public_https": True,
            "path_semantics": args.acceptance_path,
            "actual_public_direct": direct_path,
            "authentication": True,
            "rag": True,
            "history": True,
            "metrics": True,
            "java": True,
            "postgresql_persistence": True,
            "production_length_fixtures": True,
        },
        "hard_gates": hard_gates,
        "runs": [],
        "warnings": [],
        "schedule_seconds": schedule,
        "runtime_snapshot_before": runtime_snapshot(containers),
        "test_resources": {"resume_id": resume_id, "resume_version_id": version_id},
    }
    atomic_json(args.output, evidence)

    error_run_indexes: list[int] = []
    gate_started = time.monotonic()
    for index in range(1, RUN_COUNT + 1):
        wait_seconds = gate_started + schedule[index - 1] - time.monotonic()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        request_id = safe_request_id(prefix, f"analyze{index}")
        idempotency_key = f"release-gate-{secrets.token_urlsafe(32)}"
        started = utc_now()
        start_monotonic = time.monotonic()
        status, raw, headers, transport_error, client_diagnostics = curl_analyze(
            client,
            resume_version_id=version_id,
            job_file=args.job_file,
            request_id=request_id,
            idempotency_key=idempotency_key,
            artifact_dir=args.artifact_dir,
            timeout=args.timeout,
            direct_target=direct_target,
        )
        duration_ms = round((time.monotonic() - start_monotonic) * 1000, 3)
        ended = utc_now()
        try:
            response: object = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            response = None

        time.sleep(0.25)
        log_end = utc_now()
        log_scan: dict[str, bool] = {}
        raw_logs: dict[str, str] = {}
        for layer, container in containers.items():
            scanned, log_value = docker_logs(container, started - dt.timedelta(seconds=1), log_end)
            log_scan[layer] = scanned
            raw_logs[layer] = log_value
            destination = args.artifact_dir / f"run-{index}-{request_id}-{layer}.log"
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_text(log_value, encoding="utf-8")
            os.chmod(destination, 0o600)

        backend_values = json_lines(raw_logs["backend"])
        normalization = matching(
            backend_values, request_id, "jd_normalization_execution_observation"
        )
        backend_completed = matching(backend_values, request_id, "http_request_completed")
        backend_completed = [
            value for value in backend_completed if value.get("route") == "/api/analyze"
        ]
        observation = normalization[-1] if len(normalization) == 1 else {}
        completion = backend_completed[-1] if len(backend_completed) == 1 else {}

        edge_access = [
            value
            for value in json_lines(raw_logs["edge"])
            if value.get("message") == "nginx_access"
            and value.get("layer") == "edge"
            and value.get("request_id") == request_id
        ]
        frontend_access = [
            value
            for value in json_lines(raw_logs["frontend"])
            if value.get("message") == "nginx_access"
            and value.get("layer") == "frontend"
            and value.get("request_id") == request_id
        ]
        edge_observation = edge_access[-1] if len(edge_access) == 1 else {}
        frontend_observation = frontend_access[-1] if len(frontend_access) == 1 else {}

        java_values = json_lines(raw_logs["java"])
        java_completed = matching(java_values, request_id, "http_request_completed")
        java_completed = [
            value
            for value in java_completed
            if "normalize" in str(value.get("route") or "")
        ]

        relevant_errors = [
            layer for layer, log_value in raw_logs.items() if ERROR_PATTERN.search(log_value)
        ]
        if relevant_errors:
            error_run_indexes.append(index - 1)

        response_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        response_request_id = response_headers.get("x-request-id")
        complete = response_is_complete(response)
        correct = output_is_correct(response)
        workflow_id = response.get("workflow_id") if isinstance(response, dict) else None
        history_id = response.get("application_id") if isinstance(response, dict) else None

        history_persisted = False
        metrics_persisted = False
        if isinstance(history_id, int):
            history_status, history_value, *_ = client.json_call(
                f"/api/history/{history_id}",
                request_id=safe_request_id(prefix, f"history{index}"),
            )
            history_persisted = bool(
                history_status == 200
                and isinstance(history_value, dict)
                and history_value.get("id") == history_id
            )
        if isinstance(workflow_id, str) and workflow_id:
            metric_status, metric_value, *_ = client.json_call(
                f"/api/monitoring/traces/{workflow_id}",
                request_id=safe_request_id(prefix, f"metrics{index}"),
            )
            metrics_persisted = bool(metric_status == 200 and isinstance(metric_value, dict))

        warnings: list[str] = []
        java_duration = observation.get("duration_ms")
        if isinstance(java_duration, (int, float)) and java_duration >= args.latency_warning_ms:
            warnings.append("single_java_latency_spike")
        if relevant_errors and status is not None and 200 <= status < 300:
            warnings.append("transient_runtime_warning_recovered")

        run = {
            "request_id": request_id,
            "timestamp_started": rfc3339(started),
            "timestamp_completed": rfc3339(ended),
            "public_https": args.base_url.lower().startswith("https://"),
            "http_status": status,
            "backend_final_status": completion.get("status_code"),
            "transport_error": transport_error,
            "empty_reply": transport_error == "empty_reply",
            "connection_failure": transport_error not in (None, "", "empty_reply"),
            "response_bytes": len(raw),
            "response_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
            "response_request_id_matches": response_request_id == request_id,
            "response_complete": complete,
            "output_correct": correct and response_request_id == request_id,
            "end_to_end_duration_ms": duration_ms,
            "java_duration_ms": java_duration,
            "java_fallback": observation.get("fallback") is True,
            "java_outcome": observation.get("normalization_outcome"),
            "fallback_result_correct": (
                correct if observation.get("fallback") is True else True
            ),
            "java_observation_present": len(normalization) == 1,
            "java_http_status": (
                java_completed[-1].get("status") if len(java_completed) == 1 else None
            ),
            "rag_enabled": bool(
                isinstance(response, dict)
                and response.get("used_knowledge_base") is True
                and int(response.get("retrieval_count") or 0) > 0
            ),
            "history_persisted": history_persisted,
            "metrics_persisted": metrics_persisted,
            "edge_log_scanned": log_scan["edge"],
            "frontend_log_scanned": log_scan["frontend"],
            "backend_log_scanned": log_scan["backend"],
            "java_log_scanned": log_scan["java"],
            "relevant_errors": relevant_errors,
            "persistent_runtime_error": False,
            "warnings": warnings,
            "edge_access_observation_present": len(edge_access) == 1,
            "edge_status": nginx_number(edge_observation.get("status")),
            "edge_upstream_status": nginx_number(edge_observation.get("upstream_status")),
            "edge_request_time_ms": nginx_number(
                edge_observation.get("request_time"), milliseconds=True
            ),
            "edge_upstream_response_time_ms": nginx_number(
                edge_observation.get("upstream_response_time"), milliseconds=True
            ),
            "edge_bytes_sent": nginx_number(edge_observation.get("bytes_sent")),
            "frontend_access_observation_present": len(frontend_access) == 1,
            "frontend_status": nginx_number(frontend_observation.get("status")),
            "frontend_upstream_status": nginx_number(
                frontend_observation.get("upstream_status")
            ),
            "frontend_request_time_ms": nginx_number(
                frontend_observation.get("request_time"), milliseconds=True
            ),
            "frontend_upstream_response_time_ms": nginx_number(
                frontend_observation.get("upstream_response_time"), milliseconds=True
            ),
            "frontend_bytes_sent": nginx_number(frontend_observation.get("bytes_sent")),
            "backend_response_completion_ms": completion.get("duration_ms"),
            **client_diagnostics,
        }
        evidence["runs"].append(run)
        atomic_json(args.output, evidence)

        # Preserve all evidence and stop immediately on a public availability
        # hard failure.  The evaluator will classify the partial group HARD_FAIL.
        if transport_error or not isinstance(status, int) or not 200 <= status < 300 or not complete:
            evidence["hard_failure_runtime_snapshot"] = runtime_snapshot(containers)
            atomic_json(args.output, evidence)
            break

    if len(error_run_indexes) >= 2:
        for index in error_run_indexes:
            evidence["runs"][index]["persistent_runtime_error"] = True

    evidence["completed_at"] = rfc3339(utc_now())
    result = evaluate(evidence)
    evidence["gate_result"] = asdict(result)
    atomic_json(args.output, evidence)
    return evidence


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--base-url", required=True)
    value.add_argument("--origin", required=True)
    value.add_argument("--email", required=True)
    value.add_argument("--password-file", type=Path, required=True)
    value.add_argument("--ca-file", type=Path)
    value.add_argument("--resume-file", type=Path, required=True)
    value.add_argument("--job-file", type=Path, required=True)
    value.add_argument("--hard-gates", type=Path, required=True)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--artifact-dir", type=Path, required=True)
    value.add_argument("--request-prefix", required=True)
    value.add_argument("--backend-container", required=True)
    value.add_argument("--java-container", required=True)
    value.add_argument("--frontend-container", required=True)
    value.add_argument("--edge-container", required=True)
    value.add_argument("--timeout", type=float, default=240.0)
    value.add_argument("--latency-warning-ms", type=float, default=500.0)
    value.add_argument(
        "--direct-interface",
        help=(
            "Physical interface used only by production direct acceptance requests; "
            "required with production-actual-public-direct (for example eth0)."
        ),
    )
    value.add_argument(
        "--acceptance-path",
        choices=(CANDIDATE_EQUIVALENT_PATH, PRODUCTION_DIRECT_PATH),
        default=CANDIDATE_EQUIVALENT_PATH,
        help=(
            "Candidate keeps its isolated public-equivalent route. Production must use "
            f"{PRODUCTION_DIRECT_PATH}, which performs direct HTTPS probes and proxy bypass."
        ),
    )
    value.add_argument(
        "--schedule-seconds",
        default="0,0,0,0,0",
        help="Five nondecreasing offsets from gate start, for example 0,30,60,120,240",
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        evidence = collect(args)
    except Exception as error:
        failure: dict[str, Any] = {}
        if args.output.exists():
            try:
                loaded = json.loads(args.output.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    failure = loaded
            except (OSError, json.JSONDecodeError):
                pass
        failure.update(
            {
                "schema_version": 2,
                "collection_failure": type(error).__name__,
                "failure_code": (
                    str(error)
                    if isinstance(error, CollectionFailure)
                    else "unexpected_collection_error"
                ),
            }
        )
        failure.setdefault("runs", [])
        failure.setdefault("hard_gates", {})
        atomic_json(args.output, failure)
        print(json.dumps(failure, sort_keys=True))
        return 2
    result = evidence["gate_result"]
    print(json.dumps(result, sort_keys=True))
    if result["verdict"] == "HARD_FAIL":
        return 2
    if result["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
