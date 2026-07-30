"""Non-production candidate-only Java normalization fault stub."""

from __future__ import annotations

import hashlib
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    server_version = "candidate-fault-stub"
    sys_version = ""

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(
        self,
        status: int,
        value: object,
        *,
        request_id: str | None = None,
    ) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if request_id is not None:
            self.send_header("X-Request-ID", request_id)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "UP"})
        else:
            self._send_json(404, {"error": {"code": "NOT_FOUND"}})

    def do_POST(self) -> None:
        if self.path != "/api/v1/job-descriptions/normalize":
            self._send_json(404, {"error": {"code": "NOT_FOUND"}})
            return
        length = min(int(self.headers.get("Content-Length", "0") or "0"), 524288)
        raw = self.rfile.read(length)
        request_id = self.headers.get("X-Request-ID", "")
        mode = os.getenv("CANDIDATE_FAULT_MODE", "invalid_version")
        if mode == "timeout":
            time.sleep(3)
            return
        if mode == "malformed":
            body = b"{invalid-json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Request-ID", request_id)
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            supplied = json.loads(raw)
            supplied_text = str(supplied.get("raw_text") or "")
        except Exception:
            supplied_text = ""
        normalized_text = supplied_text
        policy = "unsupported-policy" if mode == "invalid_version" else "jd-normalization-v1"
        if mode == "second_scan_rejection":
            normalized_text = (
                "Synthetic role\n"
                + "DATA"
                + "BASE_URL="
                + "postgresql://"
                + "candidate:"
                + "synthetic-password@invalid.test/db"
            )
        response = {
            "normalized_text": normalized_text,
            "content_hash": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
            "normalization_policy_version": policy,
            "skill_dictionary_version": "skills-v1",
            "required_skills": [],
            "preferred_skills": [],
            "mentioned_skills": [],
            "metadata": {
                "title": None,
                "company": None,
                "location": None,
                "canonical_url": None,
            },
        }
        response_request_id = (
            "candidate-mismatched-request-id"
            if mode == "request_id_mismatch"
            else request_id
        )
        self._send_json(200, response, request_id=response_request_id)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
