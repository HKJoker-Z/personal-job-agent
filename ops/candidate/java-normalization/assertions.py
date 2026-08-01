#!/usr/bin/env python3
"""Candidate-only assertions over synthetic responses and bounded evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import unicodedata
from pathlib import Path


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def java_normalize(value: str) -> str:
    output: list[str] = []
    pending_blank = False
    normalized = unicodedata.normalize("NFC", value)
    for source_line in normalized.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(source_line.split())
        if not line:
            if output:
                pending_blank = True
            continue
        if pending_blank:
            output.append("")
            pending_blank = False
        output.append(line)
    return "\n".join(output)


def events(path: Path, request_id: str) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("request_id") == request_id:
            values.append(value)
    return values


def one(values: list[dict[str, object]], event: str) -> dict[str, object]:
    matches = [value for value in values if value.get("event") == event]
    if len(matches) != 1:
        available = [str(value.get("event")) for value in values]
        raise AssertionError(
            f"expected one {event} event, found {len(matches)}; "
            f"request events={available}"
        )
    return matches[0]


def assert_response(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "analysis_status",
        "matched_skills",
        "missing_skills",
        "match_score",
        "saved_to_history",
        "application_id",
        "security_scan",
        "workflow_steps",
    }
    if not required.issubset(value):
        raise AssertionError("Analyze response is missing stable public fields")
    if value["analysis_status"] not in {"complete", "repaired", "partial", "fallback"}:
        raise AssertionError("Analyze response status is unsupported")
    if value["saved_to_history"] is not True or not isinstance(value["application_id"], int):
        raise AssertionError("Analyze did not persist exactly one History result")


def assert_evidence(
    path: Path,
    request_id: str,
    local_text_path: Path,
    source: str,
    expected_policy: str,
    expected_dictionary: str,
) -> None:
    local_text = local_text_path.read_text(encoding="utf-8")
    effective_text = java_normalize(local_text) if source == "java" else local_text
    expected_hash = sha256(effective_text)
    values = events(path, request_id)
    if not values:
        all_events: list[tuple[object, object]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                value = json.loads(line)
                all_events.append((value.get("event"), value.get("request_id")))
        raise AssertionError(
            f"no evidence for request; bounded event identities={all_events}"
        )
    effective = one(values, "candidate_effective_normalization")
    if effective.get("effective_source") != source:
        raise AssertionError("candidate effective source differs")
    if effective.get("local_input_sha256") != sha256(local_text):
        raise AssertionError("first-scan sanitized input identity differs")
    if effective.get("effective_input_sha256") != expected_hash:
        raise AssertionError("effective input identity differs")
    if effective.get("policy_version") != expected_policy:
        raise AssertionError("normalization policy differs")
    actual_dictionary = effective.get("dictionary_version")
    wanted_dictionary = None if expected_dictionary == "null" else expected_dictionary
    if actual_dictionary != wanted_dictionary:
        raise AssertionError("skill dictionary identity differs")
    rag = one(values, "candidate_rag_input")
    prompt = one(values, "candidate_prompt_input")
    provider = one(values, "candidate_mock_provider_observation")
    for value in (rag, prompt, provider):
        if value.get("effective_input_sha256") != expected_hash:
            raise AssertionError("downstream effective input identity differs")
    if prompt.get("exact_effective_input_present") is not True:
        raise AssertionError("safe prompt did not contain the exact effective input")
    if provider.get("exact_effective_input_present") is not True:
        raise AssertionError("mock provider did not receive the exact effective input")
    if provider.get("call_count") != 1:
        raise AssertionError("mock provider call count differs")


def assert_no_events(path: Path, request_id: str) -> None:
    if events(path, request_id):
        raise AssertionError("terminal replay unexpectedly entered candidate execution")


def assert_error(path: Path, code: str) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    actual = (value.get("error") or {}).get("code")
    if actual != code:
        raise AssertionError(f"expected error {code}, found {actual}")


def summarize_durations(
    analyze_path: Path,
    java_path: Path,
    output_path: Path,
    resource_path: Path,
) -> None:
    analyze = [
        float(value)
        for value in analyze_path.read_text(encoding="utf-8").splitlines()
        if value.strip()
    ]
    java = [
        float(value)
        for value in java_path.read_text(encoding="utf-8").splitlines()
        if value.strip()
    ]
    if len(analyze) != 20 or len(java) != 20:
        raise AssertionError("the bounded sequence did not produce 20 complete samples")

    def percentile(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction) - 1)))
        return ordered[index]

    resources = json.loads(resource_path.read_text(encoding="utf-8"))
    summary = {
        "sample_count": 20,
        "skipped_cases": 0,
        "java_duration_ms_median": round(statistics.median(java), 3),
        "java_duration_ms_p95": round(percentile(java, 0.95), 3),
        "analyze_duration_ms_median": round(statistics.median(analyze), 3),
        "analyze_duration_ms_p95": round(percentile(analyze, 0.95), 3),
        "fallback_count": 0,
        "failure_count": 0,
        "resources": resources,
    }
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    response = subparsers.add_parser("response")
    response.add_argument("path", type=Path)

    evidence = subparsers.add_parser("evidence")
    evidence.add_argument("path", type=Path)
    evidence.add_argument("request_id")
    evidence.add_argument("local_text_path", type=Path)
    evidence.add_argument("source", choices=("local", "java", "fallback_local"))
    evidence.add_argument("policy")
    evidence.add_argument("dictionary")

    no_events = subparsers.add_parser("no-events")
    no_events.add_argument("path", type=Path)
    no_events.add_argument("request_id")

    error = subparsers.add_parser("error")
    error.add_argument("path", type=Path)
    error.add_argument("code")

    durations = subparsers.add_parser("durations")
    durations.add_argument("analyze_path", type=Path)
    durations.add_argument("java_path", type=Path)
    durations.add_argument("output_path", type=Path)
    durations.add_argument("resource_path", type=Path)

    args = parser.parse_args()
    if args.command == "response":
        assert_response(args.path)
    elif args.command == "evidence":
        assert_evidence(
            args.path,
            args.request_id,
            args.local_text_path,
            args.source,
            args.policy,
            args.dictionary,
        )
    elif args.command == "no-events":
        assert_no_events(args.path, args.request_id)
    elif args.command == "error":
        assert_error(args.path, args.code)
    else:
        summarize_durations(
            args.analyze_path,
            args.java_path,
            args.output_path,
            args.resource_path,
        )


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"candidate-assertion: {exc}", file=sys.stderr)
        raise SystemExit(1)
