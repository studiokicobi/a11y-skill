#!/usr/bin/env python3
"""
baseline.py — baseline helpers for normalized accessibility findings.

Builds stable baseline JSON from normalized report data and compares a current
set of findings against a saved baseline.
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASELINE_SCHEMA_VERSION = "1.0"
FINGERPRINT_VERSION = "1.0"


def _finding_clone(finding: dict) -> dict:
    return copy.deepcopy(finding)


def validate_baseline_schema(data: dict) -> None:
    required = {
        "schema_version": str,
        "fingerprint_version": str,
        "generated_at": str,
        "target": str,
        "framework": str,
        "records": list,
    }
    for field, field_type in required.items():
        if field not in data:
            raise ValueError(f"Missing baseline field: {field}")
        if not isinstance(data[field], field_type):
            raise ValueError(f"Baseline field {field} has wrong type")

    if data["schema_version"] != BASELINE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported baseline schema_version {data['schema_version']!r}; "
            f"expected {BASELINE_SCHEMA_VERSION!r}."
        )
    if data["fingerprint_version"] != FINGERPRINT_VERSION:
        raise ValueError(
            f"Unsupported fingerprint_version {data['fingerprint_version']!r}; "
            f"expected {FINGERPRINT_VERSION!r}."
        )

    for index, record in enumerate(data["records"]):
        if not isinstance(record, dict):
            raise ValueError(f"Baseline record {index} must be an object")
        for field in ("fingerprint", "rule_id", "scanner", "status", "finding"):
            if field not in record:
                raise ValueError(f"Baseline record {index} missing field: {field}")
        if not isinstance(record["finding"], dict):
            raise ValueError(f"Baseline record {index} field 'finding' must be an object")


def load_baseline(path_str: Optional[str]) -> Optional[dict]:
    if not path_str:
        return None
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    validate_baseline_schema(data)
    return data


def _baseline_record_for_finding(finding: dict) -> dict:
    fingerprint_data = copy.deepcopy(finding.get("fingerprint_data", {}))
    return {
        "fingerprint": finding["fingerprint"],
        "rule_id": finding["rule_id"],
        "origin_rule_id": finding.get("origin_rule_id", ""),
        "scanner": finding["scanner"],
        "status": finding["status"],
        "fingerprint_data": fingerprint_data,
        "location": copy.deepcopy(finding["location"]),
        "finding": _finding_clone(finding),
    }


def build_baseline(report: dict) -> dict:
    records = []
    for finding in report.get("findings", []):
        if finding.get("triage_group") == "not_checked":
            continue
        if finding.get("status") == "fixed":
            continue
        records.append(_baseline_record_for_finding(finding))

    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "generated_at": report.get("generated_at", ""),
        "target": report.get("target", ""),
        "framework": report.get("framework", ""),
        "records": records,
    }


def _historical_from_record(record: dict, status: str, comparison: str) -> dict:
    finding = _finding_clone(record["finding"])
    finding["status"] = status
    finding["comparison"] = comparison
    finding["waiver"] = finding.get("waiver") if status == "waived" else None
    return finding


def compare_findings(
    current_findings: Iterable[dict],
    baseline_data: Optional[dict],
) -> Tuple[List[dict], dict]:
    current_list = [_finding_clone(finding) for finding in current_findings]
    if not baseline_data:
        return current_list, {
            "baseline_present": False,
            "baseline_generated_at": "",
            "summary": {
                "new": 0,
                "unchanged": 0,
                "fixed": 0,
                "resolved": 0,
                "stale": 0,
                "waived": 0,
            },
        }

    records = list(baseline_data.get("records", []))
    baseline_by_fingerprint: Dict[str, dict] = {
        record.get("fingerprint", ""): record
        for record in records
        if record.get("fingerprint")
    }

    matched = set()
    summary = {
        "new": 0,
        "unchanged": 0,
        "fixed": 0,
        "resolved": 0,
        "stale": 0,
        "waived": 0,
    }

    for finding in current_list:
        if finding.get("triage_group") == "not_checked":
            continue

        record = baseline_by_fingerprint.get(finding.get("fingerprint", ""))
        if finding.get("status") == "waived":
            finding["comparison"] = "waived"
            summary["waived"] += 1
            if record:
                matched.add(record["fingerprint"])
            continue

        if record and record.get("status") in {"open", "waived", "stale"}:
            finding["comparison"] = "unchanged"
            summary["unchanged"] += 1
            matched.add(record["fingerprint"])
            continue

        finding["comparison"] = "new"
        summary["new"] += 1
        if record:
            matched.add(record["fingerprint"])

    historical = []
    for record in records:
        fingerprint = record.get("fingerprint", "")
        if not fingerprint or fingerprint in matched:
            continue

        record_status = record.get("status", "open")
        fingerprint_data = record.get("fingerprint_data", {})
        unstable = bool(fingerprint_data.get("unstable"))

        if record_status == "resolved":
            historical.append(_historical_from_record(record, "resolved", "resolved"))
            summary["resolved"] += 1
            continue

        if record_status == "waived":
            historical.append(_historical_from_record(record, "waived", "waived"))
            summary["waived"] += 1
            continue

        if unstable:
            historical.append(_historical_from_record(record, "stale", "stale"))
            summary["stale"] += 1
            continue

        historical.append(_historical_from_record(record, "fixed", "fixed"))
        summary["fixed"] += 1

    combined = current_list + historical
    return combined, {
        "baseline_present": True,
        "baseline_generated_at": baseline_data.get("generated_at", ""),
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build baseline JSON from a normalized report.")
    parser.add_argument("--report", required=True, help="Path to normalized report JSON")
    parser.add_argument("--output", required=True, help="Path to write baseline JSON")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    baseline = build_baseline(report)
    Path(args.output).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(baseline['records'])} baseline records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
