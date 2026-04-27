#!/usr/bin/env python3
"""
cli.py — public audit and CI orchestration for accessibility reports.

Public workflows:
- `audit`: run scanners, package artifacts, and print a remediation handoff
- `ci`: run or consume scanner outputs, scope to changed files, and return CI exit codes

Legacy flat arguments are still supported for fixture coverage and advanced use.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from baseline import build_baseline, load_baseline
from report import (
    blocking_findings,
    build_scope_metadata,
    filter_report,
    load_changed_files,
    render_pr_summary,
)
from triage import (
    _build_message_lookup,
    _now_iso,
    _validate_scanner_payload,
    build_markdown_report,
    build_outcome_summary,
    build_report_data,
    deduplicate,
    generate_manual_review_items,
    load_status_records,
)


SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_SCANNER = SCRIPT_DIR / "a11y_scan.py"
RUNTIME_SCANNER = SCRIPT_DIR / "a11y_runtime.js"
STATEFUL_SCANNER = SCRIPT_DIR / "a11y_stateful.js"
TOKEN_SCANNER = SCRIPT_DIR / "tokens.py"
DEFAULT_ARTIFACT_ROOT = Path(".artifacts") / "a11y"


def _raw_issues(
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
) -> List[dict]:
    issues = []
    for payload in (static_data, runtime_data, stateful_data, token_data):
        if payload:
            issues.extend(payload.get("issues", []))
    return deduplicate(issues)


def _parse_detected_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _run_id(detected_at: str) -> str:
    try:
        return _parse_detected_at(detected_at).strftime("%Y%m%dT%H%M%SZ")
    except ValueError:
        fallback = "".join(ch if ch.isalnum() else "-" for ch in detected_at)
        return fallback.strip("-") or "run"


def _resolve_output_dir(output_dir: Optional[str], detected_at: str) -> Path:
    if output_dir:
        path = Path(output_dir)
    else:
        path = DEFAULT_ARTIFACT_ROOT / _run_id(detected_at)
    return path.resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _relative_artifact(output_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(output_dir.resolve()).as_posix()


def _prepare_output_tree(output_dir: Path) -> Dict[str, Path]:
    paths = {
        "root": output_dir,
        "scanners": output_dir / "scanners",
        "evidence": output_dir / "evidence",
        "screenshots": output_dir / "evidence" / "screenshots",
        "dom": output_dir / "evidence" / "dom",
        "focus": output_dir / "evidence" / "focus",
        "inputs": output_dir / "inputs",
        "report_md": output_dir / "report.md",
        "report_json": output_dir / "report.json",
        "summary_md": output_dir / "summary.md",
        "manifest_json": output_dir / "manifest.json",
    }
    for key in ("root", "scanners", "evidence", "screenshots", "dom", "focus", "inputs"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def _run_command(cmd: List[str], label: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    detail = stderr or stdout or f"exited with code {result.returncode}"
    raise RuntimeError(f"{label} failed: {detail}")


def _copy_json_input(source: Path, dest: Path) -> dict:
    shutil.copyfile(source, dest)
    return json.loads(dest.read_text(encoding="utf-8"))


def _ingest_scanner_input(source: Path, dest: Path, scanner: str) -> dict:
    """Validate a scanner JSON input, then copy it to the artifact tree.

    Uses the same shape/contract checks as `triage.py --static/--runtime/...`
    so ci and triage refuse the same malformed or mislabeled payloads.
    Validation failures are re-raised as RuntimeError to flow through
    cli.py's existing `Configuration error:` exit-2 path.
    """
    try:
        data = _validate_scanner_payload(str(source), scanner)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if data is None:
        # `_validate_scanner_payload` only returns None when the path is
        # empty; callers guard this, but keep a safety net.
        raise RuntimeError(f"--{scanner} path is empty")
    shutil.copyfile(source, dest)
    return data


REDACTION_MARKER = "[REDACTED by a11y-audit]"

# Keys under `auth` (or nested auth-like blocks) that are safe to copy. Anything
# else defaults to redaction — the allowlist is deliberately narrow because a
# new field name in a future config version should fail closed. env:/file:
# references are indirect pointers, not the secret itself, so they are safe.
_AUTH_SAFE_KEYS = frozenset({
    "mode",
    "env",
    "file",
    "storage_state_path",
    "cookies_path",
    "follow_redirects",
    # Login-flow shape: URLs and selectors aren't secrets; username/password
    # within `login` fall through to the generic leaf-value redaction rules.
    "url",
    "username_selector",
    "password_selector",
    "submit_selector",
    "success_url",
    "wait_until",
})


def _redact_auth_subtree(node):
    """Walk an auth-ish subtree and redact string leaves that aren't indirect
    references. Structural redaction — only applied to JSON-parsed configs.
    """
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            lowered = key.lower() if isinstance(key, str) else key
            if lowered in _AUTH_SAFE_KEYS:
                # Keep mode/env/file/paths verbatim so the artifact still
                # explains how the secret WOULD be resolved at runtime.
                result[key] = value
            elif isinstance(value, (dict, list)):
                result[key] = _redact_auth_subtree(value)
            elif isinstance(value, str) and value.startswith(("env:", "file:")):
                result[key] = value
            else:
                result[key] = REDACTION_MARKER
        return result
    if isinstance(node, list):
        return [_redact_auth_subtree(item) for item in node]
    return node


def _redact_auth_keys_anywhere(node):
    """Walk a parsed JSON value and redact any value under an `auth` key,
    no matter how deeply nested. Catches both nested config shapes
    (`{"runtime": {"auth": {...}}}`) and scalar auth values
    (`{"auth": "Bearer ..."}`) that the top-level-only check missed.
    """
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            if isinstance(key, str) and key.lower() == "auth":
                if isinstance(value, (dict, list)):
                    result[key] = _redact_auth_subtree(value)
                elif isinstance(value, str) and value.startswith(("env:", "file:")):
                    result[key] = value
                elif value is None or isinstance(value, bool):
                    result[key] = value
                else:
                    result[key] = REDACTION_MARKER
            elif isinstance(value, (dict, list)):
                result[key] = _redact_auth_keys_anywhere(value)
            else:
                result[key] = value
        return result
    if isinstance(node, list):
        return [_redact_auth_keys_anywhere(item) for item in node]
    return node


def _redact_config_text_json(raw: str) -> str:
    """Parse, recursively redact every `auth` subtree at any depth,
    re-serialize. Preserves a trailing newline if the source had one so
    file diffs stay minimal.
    """
    trailing_newline = raw.endswith("\n")
    data = _redact_auth_keys_anywhere(json.loads(raw))
    out = json.dumps(data, indent=2)
    return out + "\n" if trailing_newline else out


def _build_json_placeholder(reason: str, original_source: str) -> str:
    """Self-describing JSON placeholder for when the runtime/journey config
    can't be structurally redacted. Used for malformed JSON and unreadable
    bytes. Stays valid JSON so downstream tooling that walks artifact
    bundles doesn't crash on the placeholder.
    """
    payload = {
        "_redacted_by": "a11y-audit",
        "_reason": reason,
        "_original_source": original_source,
        "_note": (
            "Original JSON runtime config could not be structurally "
            "redacted. Fail closed: artifact bundles never contain raw "
            "auth payloads from configs the redactor could not parse."
        ),
    }
    return json.dumps(payload, indent=2) + "\n"


# Block-style YAML detection: matches the common config shape where `auth:`
# starts a line and is followed by indented children. Flow-style inline
# configs (e.g. `runtime: {auth: {...}}` on one line) won't match and will
# fall through to the verbatim copy — an acceptable limitation, since
# Path A (`resolveSecretValue` in the JS runtime) is the primary defense
# and unreadable bytes still fail closed via the read-error branch in
# `_copy_named_input`.
_YAML_AUTH_TOPLEVEL_RE = re.compile(r'^\s*auth\s*:', re.MULTILINE)

_YAML_PLACEHOLDER_TEMPLATE = (
    "# [REDACTED by a11y-audit]\n"
    "# Original YAML runtime config contained an `auth:` block.\n"
    "# YAML auth configs are not round-tripped into artifact bundles\n"
    "# because the skill ships stdlib-only and cannot parse YAML safely\n"
    "# for structural redaction. Use a JSON runtime config if you need\n"
    "# full artifact reproducibility.\n"
    "#\n"
    "# Original source: {original_source}\n"
)


def _safe_source_label(source_path: Path) -> str:
    """Repo-relative label when inside cwd, basename otherwise. Avoids
    leaking absolute machine-specific paths into manifest/placeholder text.
    """
    resolved = source_path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.name


# Secondary backstop only. As of H4 the YAML branch of `_copy_named_input`
# emits a placeholder file rather than attempting in-place redaction. This
# regex still runs over the placeholder bytes as a paranoid final pass —
# expected to be a no-op since the placeholder template contains no
# `auth:` block. Kept callable so future paths that genuinely need
# best-effort YAML scrubbing have something to reach for; do not rely on
# it as the primary defense.
_YAML_AUTH_BLOCK_RE = re.compile(
    r'(^[^\S\n]*auth\s*:[^\n]*\n)((?:[^\S\n]+[^\n]*\n?)*)',
    re.MULTILINE,
)
_YAML_SENSITIVE_KEY_RE = re.compile(
    r'^(\s*)([^#\s:][^:\n]*?)\s*:\s*(.*)$',
)


def _redact_config_text_yaml(raw: str) -> str:
    def redact_block(match: "re.Match[str]") -> str:
        header = match.group(1)
        body = match.group(2)
        redacted_lines = []
        for line in body.splitlines(keepends=True):
            stripped = line.rstrip("\n")
            if not stripped.strip() or stripped.lstrip().startswith("#"):
                redacted_lines.append(line)
                continue
            key_match = _YAML_SENSITIVE_KEY_RE.match(stripped)
            if not key_match:
                redacted_lines.append(line)
                continue
            indent, key, value = key_match.group(1), key_match.group(2).strip(), key_match.group(3)
            lowered = key.lower()
            if lowered in _AUTH_SAFE_KEYS:
                redacted_lines.append(line)
                continue
            if not value:
                # Nested block header like `headers:` — leave the header
                # line alone; descendant leaves are still inside this
                # auth block and get caught on their own lines.
                redacted_lines.append(line)
                continue
            trimmed_value = value.strip()
            if trimmed_value.startswith("env:") or trimmed_value.startswith("file:"):
                redacted_lines.append(line)
                continue
            newline = "\n" if line.endswith("\n") else ""
            redacted_lines.append(f'{indent}{key}: "{REDACTION_MARKER}"{newline}')
        return header + "".join(redacted_lines)

    return _YAML_AUTH_BLOCK_RE.sub(redact_block, raw)


def _copy_named_input(source: Optional[str], dest_dir: Path, dest_name: str):
    """Copy a named input into `dest_dir` with H4 redaction policy.

    Returns:
        - None when no source.
        - str (the dest filename) for verbatim/JSON-redacted copies.
        - dict {copied, mode, original_source, reason} when a YAML auth
          config triggered placeholder emission. Callers prepend
          `inputs/` to `copied` when building manifest paths.
    """
    if not source:
        return None
    source_path = Path(source).resolve()
    suffix = "".join(source_path.suffixes)
    dest_path = dest_dir / f"{dest_name}{suffix}"
    if dest_name in ("runtime.config", "journey.config"):
        # Runtime/journey configs may carry auth secrets. Redact (or in the
        # YAML case, emit a placeholder) before the copy so artifact bundles
        # can't leak even if a future caller bypasses the JS scanner's
        # inline-literal rejection.
        try:
            raw = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            raw = None
        lowered_suffix = suffix.lower()
        if lowered_suffix.endswith(".json"):
            source_label = _safe_source_label(source_path)
            if raw is None:
                # Unreadable as text — fail closed by emitting a placeholder.
                # Avoids any chance of binary or non-UTF-8 bytes carrying
                # secrets being copied verbatim.
                placeholder = _build_json_placeholder("json-unreadable", source_label)
                dest_path.write_text(placeholder, encoding="utf-8")
                if not dest_path.is_file():
                    return None
                return {
                    "copied": dest_path.name,
                    "mode": "placeholder",
                    "original_source": source_label,
                    "reason": "json-unreadable",
                }
            try:
                redacted = _redact_config_text_json(raw)
            except (ValueError, json.JSONDecodeError):
                # Parse error — fail closed. We can't structurally redact a
                # malformed config, so emit a placeholder rather than copy
                # raw bytes (which may carry an Authorization header next
                # to the syntax error).
                placeholder = _build_json_placeholder("json-parse-error", source_label)
                dest_path.write_text(placeholder, encoding="utf-8")
                if not dest_path.is_file():
                    return None
                return {
                    "copied": dest_path.name,
                    "mode": "placeholder",
                    "original_source": source_label,
                    "reason": "json-parse-error",
                }
            dest_path.write_text(redacted, encoding="utf-8")
            return dest_path.name if dest_path.is_file() else None
        if lowered_suffix.endswith((".yaml", ".yml")):
            # Stdlib-only constraint: no YAML parser available, so we can't
            # structurally redact. For block-style `auth:` blocks (and for
            # any unreadable text) we emit a placeholder file instead.
            # Auth-free YAML round-trips verbatim.
            if raw is None or _YAML_AUTH_TOPLEVEL_RE.search(raw):
                source_label = _safe_source_label(source_path)
                placeholder = _YAML_PLACEHOLDER_TEMPLATE.format(
                    original_source=source_label
                )
                # Defense-in-depth: regex backstop on the placeholder bytes.
                # Expected no-op since the template contains no `auth:`.
                placeholder = _redact_config_text_yaml(placeholder)
                dest_path.write_text(placeholder, encoding="utf-8")
                if not dest_path.is_file():
                    return None
                return {
                    "copied": dest_path.name,
                    "mode": "placeholder",
                    "original_source": source_label,
                    "reason": "yaml-auth-not-round-tripped",
                }
            dest_path.write_text(raw, encoding="utf-8")
            return dest_path.name if dest_path.is_file() else None
        # Other suffixes: copy raw text (or bytes when unreadable as text).
        if raw is None:
            shutil.copyfile(source_path, dest_path)
        else:
            dest_path.write_text(raw, encoding="utf-8")
        return dest_path.name if dest_path.is_file() else None
    shutil.copyfile(source_path, dest_path)
    return dest_path.name if dest_path.is_file() else None


def _run_static_scan(target_path: str, output_path: Path, framework: str) -> dict:
    cmd = [
        sys.executable,
        str(STATIC_SCANNER),
        target_path,
        "--quiet",
        "--output",
        str(output_path),
    ]
    if framework:
        cmd.extend(["--framework", framework])
    _run_command(cmd, "Static scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_runtime_scan(url: Optional[str], runtime_config: Optional[str], output_path: Path, screenshot_dir: Path) -> dict:
    cmd = [
        "node",
        str(RUNTIME_SCANNER),
        "--output",
        str(output_path),
        "--screenshot-dir",
        str(screenshot_dir),
    ]
    if url:
        cmd.extend(["--url", url])
    if runtime_config:
        cmd.extend(["--config", runtime_config])
    _run_command(cmd, "Runtime scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_stateful_scan(journey_config: str, output_path: Path, screenshot_dir: Path) -> dict:
    cmd = [
        "node",
        str(STATEFUL_SCANNER),
        "--config",
        journey_config,
        "--output",
        str(output_path),
        "--screenshot-dir",
        str(screenshot_dir),
    ]
    _run_command(cmd, "Stateful scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_token_scan(token_file: str, output_path: Path) -> dict:
    cmd = [
        sys.executable,
        str(TOKEN_SCANNER),
        token_file,
        "--output",
        str(output_path),
    ]
    _run_command(cmd, "Token scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _artifact_index(paths: Dict[str, Path], scanner_payloads: Dict[str, Optional[dict]]) -> List[str]:
    artifacts = [
        _relative_artifact(paths["root"], paths["report_json"]),
        _relative_artifact(paths["root"], paths["summary_md"]),
        _relative_artifact(paths["root"], paths["manifest_json"]),
    ]
    for scanner_name in ("static", "runtime", "stateful", "tokens"):
        if scanner_payloads.get(scanner_name):
            filename = "tokens.json" if scanner_name == "tokens" else f"{scanner_name}.json"
            artifacts.append(f"scanners/{filename}")
    if any(paths["screenshots"].iterdir()):
        artifacts.append(_relative_artifact(paths["root"], paths["screenshots"]))
    return artifacts


def _build_render_context(
    mode_label: str,
    artifact_paths: List[str],
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
    scope_metadata: Optional[dict] = None,
) -> dict:
    scanners_ran = []
    if static_data:
        scanners_ran.append("static")
    if runtime_data:
        scanners_ran.append("runtime")
    if stateful_data:
        scanners_ran.append("stateful")
    if token_data:
        scanners_ran.append("token")
    return {
        "mode": mode_label,
        "artifact_paths": artifact_paths,
        "scanners_ran": scanners_ran,
        "excluded_low_confidence_count": int((scope_metadata or {}).get("excluded_low_confidence_count", 0) or 0),
    }


def _render_outputs(
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
    baseline_data: Optional[dict],
    status_records: List[dict],
    changed_files,
    detected_at: str,
    output_dir: Path,
    mode_label: str,
    artifact_paths: List[str],
    fail_on_severity: str,
    fail_on_confidence: str,
    fail_on_any_new: bool,
    fail_on_manual_findings: bool,
    ci_mode: bool,
) -> dict:
    report = build_report_data(
        static_data,
        runtime_data,
        stateful_data,
        token_data,
        baseline_data,
        output_dir,
        detected_at,
        status_records,
    )
    scope_metadata = build_scope_metadata(report, changed_files)
    if changed_files:
        report = filter_report(report, changed_files)

    raw_issues = _raw_issues(static_data, runtime_data, stateful_data, token_data)
    message_lookup = _build_message_lookup(raw_issues)
    scanners_ran_for_checklist = [
        scanner
        for scanner, payload in (
            ("static", static_data),
            ("runtime", runtime_data),
            ("stateful", stateful_data),
            ("token", token_data),
        )
        if payload
    ]
    manual_items = generate_manual_review_items(
        report, stateful_data, scanners_ran=scanners_ran_for_checklist
    )
    step_failures = list((stateful_data or {}).get("step_failures", []))
    render_context = _build_render_context(
        mode_label,
        artifact_paths,
        static_data,
        runtime_data,
        stateful_data,
        token_data,
        scope_metadata=scope_metadata,
    )
    markdown_report = build_markdown_report(
        report,
        message_lookup,
        manual_items,
        step_failures,
        render_context=render_context,
    )

    blockers = blocking_findings(
        report,
        fail_on_severity=fail_on_severity,
        fail_on_confidence=fail_on_confidence,
        fail_on_any_new=fail_on_any_new,
        fail_on_manual_findings=fail_on_manual_findings,
    )
    summary = render_pr_summary(
        report,
        blockers,
        changed_files=changed_files,
        fail_on_severity=fail_on_severity,
        fail_on_confidence=fail_on_confidence,
        fail_on_any_new=fail_on_any_new,
        fail_on_manual_findings=fail_on_manual_findings,
        scope_metadata=scope_metadata,
        ci_mode=ci_mode,
    )
    return {
        "report": report,
        "markdown": markdown_report,
        "summary": summary,
        "blockers": blockers,
        "scope_metadata": scope_metadata,
        "manual_items": manual_items,
        "outcome_summary": build_outcome_summary(report, manual_items),
    }


def _recommended_first_step(outcome_summary: dict) -> Optional[str]:
    auto_count = int(outcome_summary.get("auto_count", 0) or 0)
    input_count = int(outcome_summary.get("input_count", 0) or 0)
    manual_review_count = int(outcome_summary.get("manual_review_count", 0) or 0)
    guided_check_count = int(outcome_summary.get("guided_check_count", 0) or 0)
    active_finding_count = int(outcome_summary.get("active_finding_count", 0) or 0)

    if active_finding_count == 0:
        return None
    if auto_count > 0:
        return 'Recommended first step: say "apply the safe fixes". Open the report for all available next actions.'
    if input_count > 0:
        return 'Recommended first step: say "walk me through the decisions". Open the report for all available next actions.'
    if manual_review_count > 0 and guided_check_count > 0:
        return (
            'Recommended first step: say "give me the checklist". Say "show me the manual findings" for just the '
            'scanner-flagged items. Open the report for the full action menu.'
        )
    if manual_review_count > 0:
        return 'Recommended first step: say "show me the manual findings". Open the report for all available next actions.'
    return None


def _write_manifest(
    manifest_path: Path,
    run_kind: str,
    mode_label: str,
    detected_at: str,
    output_dir: Path,
    report: dict,
    scanner_payloads: Dict[str, Optional[dict]],
    input_copies: Dict[str, str],
    scope_metadata: dict,
    baseline_output: Optional[str] = None,
    outcome: Optional[dict] = None,
) -> None:
    artifacts = {
        "report_markdown": "report.md",
        "report_json": "report.json",
        "summary_markdown": "summary.md",
        "scanner_outputs": {},
    }
    for scanner_name in ("static", "runtime", "stateful", "tokens"):
        if scanner_payloads.get(scanner_name):
            filename = "tokens.json" if scanner_name == "tokens" else f"{scanner_name}.json"
            artifacts["scanner_outputs"][scanner_name] = f"scanners/{filename}"
    if any((output_dir / "evidence" / "screenshots").iterdir()):
        artifacts["screenshots"] = "evidence/screenshots"

    manifest = {
        "run_id": output_dir.name,
        "run_kind": run_kind,
        "mode": mode_label,
        "generated_at": detected_at,
        "target": report.get("target", ""),
        "framework": report.get("framework", ""),
        "summary": report.get("summary", {}),
        "baseline_comparison": report.get("baseline_comparison", {}),
        "scope_metadata": scope_metadata,
        "artifacts": artifacts,
        "inputs": input_copies,
        "scanners_ran": [
            scanner_name
            for scanner_name in ("static", "runtime", "stateful", "tokens")
            if scanner_payloads.get(scanner_name)
        ],
    }
    if baseline_output:
        manifest["baseline_output"] = baseline_output
    if outcome:
        manifest["outcome"] = outcome
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _add_shared_source_args(parser: argparse.ArgumentParser, include_raw: bool, include_changed_files: bool) -> None:
    parser.add_argument("--path", type=str, help="Source path for static scanning")
    parser.add_argument("--url", type=str, help="Runtime URL to scan")
    parser.add_argument("--framework", type=str, default="auto", help="Static framework override")
    parser.add_argument("--runtime-config", type=str, help="Optional runtime JSON/YAML config")
    parser.add_argument("--journey-config", type=str, help="Optional stateful journey JSON/YAML config")
    parser.add_argument("--token-file", type=str, help="Optional token JSON input")
    parser.add_argument("--baseline-file", type=str, help="Optional baseline JSON")
    parser.add_argument("--status-file", type=str, help="Optional status/waiver JSON")
    if include_changed_files:
        parser.add_argument("--changed-files", type=str, help="Optional newline-delimited changed files list")
    parser.add_argument("--output-dir", type=str, help="Artifact output directory")
    parser.add_argument("--detected-at", type=str, help="ISO timestamp override")
    if include_raw:
        parser.add_argument("--static", type=str, help="Path to static scanner JSON")
        parser.add_argument("--runtime", type=str, help="Path to runtime scanner JSON")
        parser.add_argument("--stateful", type=str, help="Path to stateful scanner JSON")
        parser.add_argument("--tokens", type=str, help="Path to token scanner JSON")


def _build_public_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accessibility audit workflow orchestrator")
    subparsers = parser.add_subparsers(dest="command", metavar="{audit,ci,promote-baseline}")

    audit = subparsers.add_parser("audit", help="Run a local accessibility audit and package the results")
    _add_shared_source_args(audit, include_raw=False, include_changed_files=False)
    audit.add_argument("--mode", choices=("quick", "full"), default="quick")
    audit.add_argument("--write-baseline", type=str, help="Optional path to write a baseline JSON")
    audit.add_argument("--update-baseline", action="store_true", help="Write a fresh baseline back to --baseline-file (implicit overwrite)")
    audit.add_argument("--force-baseline", action="store_true", help="Overwrite an existing file at --write-baseline (no effect with --update-baseline, which always overwrites)")

    ci = subparsers.add_parser("ci", help="Run CI/PR-friendly audit output with deterministic exit codes")
    _add_shared_source_args(ci, include_raw=True, include_changed_files=True)
    ci.add_argument("--ci", action="store_true", help="Return CI exit codes")
    ci.add_argument("--fail-on-severity", choices=("minor", "moderate", "serious", "critical"), default="serious")
    ci.add_argument("--fail-on-confidence", choices=("low", "medium", "high"), default="high")
    ci.add_argument("--fail-on-any-new", action="store_true")
    ci.add_argument("--fail-on-manual-findings", action="store_true")

    # Promote a previously generated report into a baseline without re-scanning.
    # SKILL.md routes the "save the baseline" intent here; documenting it
    # publicly aligns the agent contract with the CLI surface.
    promote = subparsers.add_parser(
        "promote-baseline",
        help="Write a baseline JSON from an existing report (no re-scan)",
    )
    promote.add_argument("--report", required=True, help="Normalized report JSON")
    promote.add_argument("--baseline-file", required=True, help="Path to write baseline JSON")
    promote.add_argument("--force", action="store_true", help="Overwrite an existing baseline file at --baseline-file")

    return parser


def _atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` via a sibling tempfile + os.replace so a
    SIGKILL or disk-full mid-write cannot leave a half-written baseline.
    The dot-prefix on the tempfile keeps it out of plain `ls` output if
    something does interrupt the rename.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _write_baseline_or_error(path: Path, payload: dict, *, force: bool):
    """Atomic + overwrite-guarded baseline write. Returns None on success or
    a (exit_code, message) tuple on failure. force=True is intended only
    for paths where the user has explicitly opted in (audit --update-baseline,
    or an explicit --force / --force-baseline flag).
    """
    if path.exists() and not force:
        return (
            2,
            f"Configuration error: baseline file already exists at {path}. "
            f"Pass --force (promote-baseline) or --force-baseline (audit) "
            f"to overwrite, or pick a new path.",
        )
    try:
        _atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
    except OSError as exc:
        return (2, f"Configuration error: could not write baseline at {path}: {exc}")
    return None


def _load_baseline_or_error(path_str: Optional[str]):
    try:
        return load_baseline(path_str), None
    except FileNotFoundError as exc:
        return None, (2, f"Configuration error: {exc}")
    except ValueError as exc:
        return None, (3, f"Baseline error: {exc}")
    except json.JSONDecodeError as exc:
        return None, (3, f"Baseline error: {exc}")


def _load_status_or_error(path_str: Optional[str]):
    try:
        return load_status_records(path_str), None
    except FileNotFoundError as exc:
        return None, (2, f"Configuration error: {exc}")
    except json.JSONDecodeError as exc:
        return None, (2, f"Configuration error: {exc}")
    except ValueError as exc:
        return None, (2, f"Configuration error: {exc}")


def _collect_audit_payloads(args, paths: Dict[str, Path]) -> Dict[str, Optional[dict]]:
    payloads: Dict[str, Optional[dict]] = {
        "static": None,
        "runtime": None,
        "stateful": None,
        "tokens": None,
    }
    if args.path:
        payloads["static"] = _run_static_scan(args.path, paths["scanners"] / "static.json", args.framework)
    if args.url or args.runtime_config:
        payloads["runtime"] = _run_runtime_scan(
            args.url,
            args.runtime_config,
            paths["scanners"] / "runtime.json",
            paths["screenshots"],
        )
    if args.journey_config:
        payloads["stateful"] = _run_stateful_scan(
            args.journey_config,
            paths["scanners"] / "stateful.json",
            paths["screenshots"],
        )
    if args.token_file:
        payloads["tokens"] = _run_token_scan(args.token_file, paths["scanners"] / "tokens.json")
    if not any(payloads.values()):
        raise RuntimeError("Provide at least one of --path, --url, --runtime-config, --journey-config, or --token-file.")
    return payloads


def _collect_ci_payloads(args, paths: Dict[str, Path]) -> Dict[str, Optional[dict]]:
    payloads: Dict[str, Optional[dict]] = {
        "static": None,
        "runtime": None,
        "stateful": None,
        "tokens": None,
    }

    if args.static:
        payloads["static"] = _ingest_scanner_input(
            Path(args.static).resolve(), paths["scanners"] / "static.json", "static"
        )
    elif args.path:
        payloads["static"] = _run_static_scan(args.path, paths["scanners"] / "static.json", args.framework)

    if args.runtime:
        payloads["runtime"] = _ingest_scanner_input(
            Path(args.runtime).resolve(), paths["scanners"] / "runtime.json", "runtime"
        )
    elif args.url or args.runtime_config:
        payloads["runtime"] = _run_runtime_scan(
            args.url,
            args.runtime_config,
            paths["scanners"] / "runtime.json",
            paths["screenshots"],
        )

    if args.stateful:
        payloads["stateful"] = _ingest_scanner_input(
            Path(args.stateful).resolve(), paths["scanners"] / "stateful.json", "stateful"
        )
    elif args.journey_config:
        payloads["stateful"] = _run_stateful_scan(
            args.journey_config,
            paths["scanners"] / "stateful.json",
            paths["screenshots"],
        )

    if args.tokens:
        payloads["tokens"] = _ingest_scanner_input(
            Path(args.tokens).resolve(), paths["scanners"] / "tokens.json", "token"
        )
    elif args.token_file:
        payloads["tokens"] = _run_token_scan(args.token_file, paths["scanners"] / "tokens.json")

    if not any(payloads.values()):
        raise RuntimeError(
            "Provide scanner JSON via --static/--runtime/--stateful/--tokens or source inputs via --path/--url/--runtime-config/--journey-config/--token-file."
        )
    return payloads


def _write_outputs(paths: Dict[str, Path], markdown_report: str, report: dict, summary: str) -> None:
    paths["report_md"].write_text(markdown_report, encoding="utf-8")
    paths["report_json"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    paths["summary_md"].write_text(summary + "\n", encoding="utf-8")


def _audit_main(argv: List[str]) -> int:
    parser = _build_public_parser()
    args = parser.parse_args(argv)
    detected_at = args.detected_at or _now_iso()
    output_dir = _resolve_output_dir(args.output_dir, detected_at)
    paths = _prepare_output_tree(output_dir)

    baseline_data, baseline_error = _load_baseline_or_error(args.baseline_file)
    if baseline_error:
        print(baseline_error[1], file=sys.stderr)
        return baseline_error[0]

    status_records, status_error = _load_status_or_error(args.status_file)
    if status_error:
        print(status_error[1], file=sys.stderr)
        return status_error[0]

    try:
        payloads = _collect_audit_payloads(args, paths)
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    input_copies = {}
    for source, dest_name, key in (
        (args.runtime_config, "runtime.config", "runtime_config"),
        (args.journey_config, "journey.config", "journey_config"),
        (args.token_file, "tokens", "token_file"),
        (args.baseline_file, "baseline", "baseline_file"),
        (args.status_file, "status", "status_file"),
    ):
        copied = _copy_named_input(source, paths["inputs"], dest_name)
        if isinstance(copied, dict):
            entry = dict(copied)
            entry["copied"] = f"inputs/{entry['copied']}"
            input_copies[key] = entry
        elif copied:
            input_copies[key] = f"inputs/{copied}"

    artifact_paths = _artifact_index(paths, payloads)
    outputs = _render_outputs(
        payloads["static"],
        payloads["runtime"],
        payloads["stateful"],
        payloads["tokens"],
        baseline_data,
        status_records or [],
        set(),
        detected_at,
        paths["root"],
        args.mode,
        artifact_paths,
        fail_on_severity="serious",
        fail_on_confidence="high",
        fail_on_any_new=False,
        fail_on_manual_findings=False,
        ci_mode=False,
    )
    _write_outputs(paths, outputs["markdown"], outputs["report"], outputs["summary"])

    baseline_output_path = None
    # --update-baseline carries an implicit overwrite intent because the user
    # explicitly chose to rewrite the file pointed at by --baseline-file.
    # --write-baseline points at a (possibly new) destination, so a stray
    # invocation should not silently clobber an existing file there.
    baseline_force = False
    if args.write_baseline:
        baseline_output_path = Path(args.write_baseline).resolve()
        baseline_force = args.force_baseline
    elif args.update_baseline:
        if not args.baseline_file:
            print("Configuration error: --update-baseline requires --baseline-file", file=sys.stderr)
            return 2
        baseline_output_path = Path(args.baseline_file).resolve()
        baseline_force = True

    baseline_output_display = None
    if baseline_output_path:
        write_err = _write_baseline_or_error(
            baseline_output_path,
            build_baseline(outputs["report"]),
            force=baseline_force,
        )
        if write_err:
            print(write_err[1], file=sys.stderr)
            return write_err[0]
        baseline_output_display = _display_path(baseline_output_path)

    outcome_summary = outputs["outcome_summary"]
    recommended_first_step = _recommended_first_step(outcome_summary)
    outcome_payload = {
        "body": outcome_summary["outcome_body"],
        "recommended_first_step": recommended_first_step or "",
    }

    _write_manifest(
        paths["manifest_json"],
        run_kind="audit",
        mode_label=args.mode,
        detected_at=detected_at,
        output_dir=paths["root"],
        report=outputs["report"],
        scanner_payloads=payloads,
        input_copies=input_copies,
        scope_metadata=outputs["scope_metadata"],
        baseline_output=baseline_output_display,
        outcome=outcome_payload,
    )

    print(outcome_summary["outcome_body"])
    print(f"Full report: {_display_path(paths['report_md'])}")
    if recommended_first_step:
        print(recommended_first_step)
    if baseline_output_display:
        print(f"Baseline: {baseline_output_display}")
    return 0


def _ci_main(argv: List[str]) -> int:
    parser = _build_public_parser()
    args = parser.parse_args(argv)
    detected_at = args.detected_at or _now_iso()
    output_dir = _resolve_output_dir(args.output_dir, detected_at)
    paths = _prepare_output_tree(output_dir)

    baseline_data, baseline_error = _load_baseline_or_error(args.baseline_file)
    if baseline_error:
        print(baseline_error[1], file=sys.stderr)
        return baseline_error[0]

    status_records, status_error = _load_status_or_error(args.status_file)
    if status_error:
        print(status_error[1], file=sys.stderr)
        return status_error[0]

    try:
        payloads = _collect_ci_payloads(args, paths)
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    changed_files = load_changed_files(args.changed_files)
    input_copies = {}
    for source, dest_name, key in (
        (args.runtime_config, "runtime.config", "runtime_config"),
        (args.journey_config, "journey.config", "journey_config"),
        (args.token_file, "tokens", "token_file"),
        (args.baseline_file, "baseline", "baseline_file"),
        (args.status_file, "status", "status_file"),
        (args.changed_files, "changed-files", "changed_files"),
    ):
        copied = _copy_named_input(source, paths["inputs"], dest_name)
        if isinstance(copied, dict):
            entry = dict(copied)
            entry["copied"] = f"inputs/{entry['copied']}"
            input_copies[key] = entry
        elif copied:
            input_copies[key] = f"inputs/{copied}"

    artifact_paths = _artifact_index(paths, payloads)
    outputs = _render_outputs(
        payloads["static"],
        payloads["runtime"],
        payloads["stateful"],
        payloads["tokens"],
        baseline_data,
        status_records or [],
        changed_files,
        detected_at,
        paths["root"],
        "ci",
        artifact_paths,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
        ci_mode=True,
    )
    _write_outputs(paths, outputs["markdown"], outputs["report"], outputs["summary"])
    _write_manifest(
        paths["manifest_json"],
        run_kind="ci",
        mode_label="ci",
        detected_at=detected_at,
        output_dir=paths["root"],
        report=outputs["report"],
        scanner_payloads=payloads,
        input_copies=input_copies,
        scope_metadata=outputs["scope_metadata"],
    )

    print(f"Accessibility check: {len(outputs['blockers'])} blocking issue(s). Summary: {_display_path(paths['summary_md'])}")
    if args.ci:
        return 1 if outputs["blockers"] else 0
    return 0


def _promote_baseline_main(argv: List[str]) -> int:
    parser = _build_public_parser()
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(
            f"Configuration error: invalid JSON in --report {args.report}: {exc}",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    baseline = build_baseline(report)
    write_err = _write_baseline_or_error(
        Path(args.baseline_file).resolve(),
        baseline,
        force=args.force,
    )
    if write_err:
        print(write_err[1], file=sys.stderr)
        return write_err[0]
    print(f"Baseline written to {args.baseline_file}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _build_public_parser().print_help()
        return 0
    if argv[0] in {"-h", "--help"}:
        _build_public_parser().parse_args(argv)
        return 0
    if argv[0] == "audit":
        return _audit_main(argv)
    if argv[0] == "ci":
        return _ci_main(argv)
    if argv[0] == "promote-baseline":
        return _promote_baseline_main(argv)
    _build_public_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
