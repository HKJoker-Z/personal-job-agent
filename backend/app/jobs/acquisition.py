"""Pinned-address HTTP acquisition with SSRF and decompression defenses."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import zlib
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlsplit

import urllib3
from bs4 import BeautifulSoup

from app.jobs.normalization import canonicalize_url, normalize_description, normalize_text


ALLOWED_MEDIA_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
MAX_REDIRECTS = 5
MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
USER_AGENT = "PersonalJobAgent/2.0-job-import (+security-contact:none)"
Resolver = Callable[[str, int], list[str]]


class UnsafeJobUrl(ValueError):
    pass


@dataclass(frozen=True)
class AcquiredJobPage:
    original_url: str
    canonical_url: str
    media_type: str
    http_status_summary: str
    title: str
    company: str
    location: str
    description: str
    published_at: str | None = None
    deadline: str | None = None


def _resolve(host: str, port: int) -> list[str]:
    return sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def _safe_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _looks_obfuscated_ip(host: str) -> bool:
    lowered = host.casefold().rstrip(".")
    if re.fullmatch(r"(?:0x[0-9a-f]+|0[0-7]+|\d+)", lowered):
        return True
    return bool(re.fullmatch(r"(?:0x[0-9a-f]+|0[0-7]+|\d+)(?:\.(?:0x[0-9a-f]+|0[0-7]+|\d+)){1,3}", lowered))


class SafeJobUrlFetcher:
    def __init__(self, resolver: Resolver | None = None):
        self.resolver = resolver or _resolve

    def _validated_target(self, url: str) -> tuple[str, str, int, list[str]]:
        try:
            canonical = canonicalize_url(url)
            parsed = urlsplit(canonical or "")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except (ValueError, TypeError) as exc:
            raise UnsafeJobUrl("Job URL is invalid or contains credentials.") from exc
        host = (parsed.hostname or "").rstrip(".").casefold()
        if not host or host == "localhost" or host.endswith(".localhost") or _looks_obfuscated_ip(host):
            raise UnsafeJobUrl("Job URL target is not allowed.")
        try:
            addresses = self.resolver(host, port)
        except OSError as exc:
            raise UnsafeJobUrl("Job URL host could not be resolved safely.") from exc
        test_host = os.getenv("JOB_IMPORT_TEST_ALLOWED_HOST", "").strip().casefold()
        test_override = os.getenv("APP_ENV", "").strip().casefold() == "test" and host == test_host and bool(test_host)
        if not addresses or (not test_override and any(not _safe_ip(item) for item in addresses)):
            raise UnsafeJobUrl("Job URL target is not allowed.")
        return canonical or url, host, port, addresses

    def _request(self, url: str, host: str, port: int, address: str) -> tuple[int, dict[str, str], bytes]:
        parsed = urlsplit(url)
        timeout = urllib3.Timeout(connect=3.0, read=7.0)
        pool_class = urllib3.HTTPSConnectionPool if parsed.scheme == "https" else urllib3.HTTPConnectionPool
        options: dict[str, object] = {"port": port, "timeout": timeout, "maxsize": 1, "block": True}
        if parsed.scheme == "https":
            options.update({"server_hostname": host, "assert_hostname": host})
        pool = pool_class(address, **options)
        target = parsed.path or "/"
        if parsed.query:
            target += f"?{parsed.query}"
        host_header = host if port in {80, 443} else f"{host}:{port}"
        try:
            response = pool.request(
                "GET",
                target,
                headers={"Host": host_header, "User-Agent": USER_AGENT, "Accept": "text/html,text/plain"},
                redirect=False,
                retries=False,
                preload_content=False,
                decode_content=False,
            )
            body = response.read(MAX_COMPRESSED_BYTES + 1, decode_content=False)
            headers = {key.casefold(): value for key, value in response.headers.items()}
            return int(response.status), headers, body
        except (urllib3.exceptions.HTTPError, OSError) as exc:
            raise UnsafeJobUrl("Job URL could not be fetched safely.") from exc
        finally:
            pool.close()

    def fetch(self, url: str) -> AcquiredJobPage:
        original = url
        current = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            current, host, port, addresses = self._validated_target(current)
            status, headers, compressed = self._request(current, host, port, addresses[0])
            if 300 <= status < 400:
                location = headers.get("location")
                if not location or redirect_count == MAX_REDIRECTS:
                    raise UnsafeJobUrl("Job URL redirected unsafely or too many times.")
                current = urljoin(current, location)
                continue
            if status < 200 or status >= 300:
                raise UnsafeJobUrl("Job URL returned an unsuccessful response.")
            if len(compressed) > MAX_COMPRESSED_BYTES:
                raise UnsafeJobUrl("Job URL response is too large.")
            encoding = headers.get("content-encoding", "identity").casefold().strip()
            if encoding in {"", "identity"}:
                body = compressed
            elif encoding == "gzip":
                try:
                    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    body = decompressor.decompress(compressed, MAX_RESPONSE_BYTES + 1)
                    if decompressor.unconsumed_tail or len(body) > MAX_RESPONSE_BYTES:
                        raise UnsafeJobUrl("Job URL expanded response is too large.")
                    body += decompressor.flush(MAX_RESPONSE_BYTES + 1 - len(body))
                except zlib.error as exc:
                    raise UnsafeJobUrl("Job URL compressed response is invalid.") from exc
            else:
                raise UnsafeJobUrl("Job URL response encoding is not supported.")
            if len(body) > MAX_RESPONSE_BYTES:
                raise UnsafeJobUrl("Job URL expanded response is too large.")
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().casefold()
            if media_type not in ALLOWED_MEDIA_TYPES:
                raise UnsafeJobUrl("Job URL response type is not allowed.")
            return _extract_page(original, current, media_type, status, body)
        raise UnsafeJobUrl("Job URL redirected too many times.")


def _extract_page(original: str, final_url: str, media_type: str, status: int, body: bytes) -> AcquiredJobPage:
    text = body.decode("utf-8", errors="replace")
    if media_type == "text/plain":
        description = normalize_description(text)
        title = company = location = ""
        published = deadline = None
    else:
        soup = BeautifulSoup(text, "html.parser")
        structured = list(soup.find_all("script", type="application/ld+json"))
        for node in soup(["style", "noscript", "iframe", "object", "embed", "svg"]):
            node.decompose()
        for node in soup.find_all("script"):
            if node not in structured:
                node.decompose()
        title = normalize_text((soup.find("meta", property="og:title") or {}).get("content") if soup.find("meta", property="og:title") else "")
        if not title and soup.title:
            title = normalize_text(soup.title.get_text(" ", strip=True))
        company = location = ""
        published = deadline = None
        for script in structured:
            try:
                payload = json.loads(script.string or "null")
            except (json.JSONDecodeError, TypeError):
                continue
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                    continue
                title = normalize_text(item.get("title")) or title
                organization = item.get("hiringOrganization") or {}
                company = normalize_text(organization.get("name") if isinstance(organization, dict) else "")
                address = item.get("jobLocation") or {}
                if isinstance(address, dict):
                    address = address.get("address") or {}
                if isinstance(address, dict):
                    location = normalize_text(", ".join(str(address.get(key) or "") for key in ("addressLocality", "addressRegion", "addressCountry") if address.get(key)))
                published = item.get("datePosted") if isinstance(item.get("datePosted"), str) else None
                deadline = item.get("validThrough") if isinstance(item.get("validThrough"), str) else None
                break
        for script in structured:
            script.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        description = normalize_description(main.get_text("\n", strip=True))
    if not description:
        raise UnsafeJobUrl("Job URL did not contain readable text.")
    return AcquiredJobPage(
        original_url=canonicalize_url(original) or original,
        canonical_url=canonicalize_url(final_url) or final_url,
        media_type=media_type,
        http_status_summary=f"HTTP {status}",
        title=title[:300],
        company=company[:300],
        location=location[:300],
        description=description[:200000],
        published_at=published,
        deadline=deadline,
    )
