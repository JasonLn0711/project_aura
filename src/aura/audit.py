from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import os
import platform
import re
import threading
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from aura.metadata import __version__


logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
AUDIT_DIR_ENV = "AURA_AUDIT_DIR"
AUDIT_ENABLED_ENV = "AURA_AUDIT_ENABLED"
AUDIT_RETENTION_DAYS_ENV = "AURA_AUDIT_RETENTION_DAYS"
DEFAULT_RETENTION_DAYS = 90
GENESIS_HASH = "GENESIS"
MAX_DETAIL_DEPTH = 4
MAX_DETAIL_ITEMS = 40
MAX_STRING_LENGTH = 256
EVENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

ALLOWED_ACTORS = {"user", "system", "model"}
ALLOWED_OUTCOMES = {"attempted", "success", "cancelled", "rejected", "error"}
ALLOWED_SEVERITIES = {"debug", "info", "warning", "error", "critical"}
SENSITIVE_KEYS = {
    "audio",
    "audio_path",
    "content",
    "credential",
    "error_message",
    "file_name",
    "filename",
    "message",
    "output_folder",
    "password",
    "prompt",
    "raw_text",
    "secret",
    "source_path",
    "summary_text",
    "text",
    "token",
    "transcript",
    "wav_path",
}

WORKFLOW_EVENTS = {
    "recording": {
        "start": "recording.started",
        "completed": {"recording.artifact_saved"},
        "terminal": {"recording.artifact_saved", "recording.save_skipped", "recording.failed"},
    },
    "import": {
        "start": "import.batch_started",
        "completed": {"import.batch_completed"},
        "terminal": {"import.batch_completed", "import.batch_cancelled", "import.batch_failed"},
    },
    "summary": {
        "start": "summary.started",
        "completed": {"summary.completed"},
        "terminal": {"summary.completed", "summary.runtime_failed", "summary.generation_failed"},
    },
    "splitter": {
        "start": "splitter.started",
        "completed": {"splitter.completed"},
        "terminal": {"splitter.completed", "splitter.failed", "splitter.cancelled"},
    },
}


def audit_enabled_from_env() -> bool:
    return os.environ.get(AUDIT_ENABLED_ENV, "true").strip().lower() not in {"0", "false", "no", "off"}


def retention_days_from_env() -> int:
    raw = os.environ.get(AUDIT_RETENTION_DAYS_ENV, str(DEFAULT_RETENTION_DAYS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def default_audit_dir() -> Path:
    configured = os.environ.get(AUDIT_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "ProjectAURA" / "audit"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "ProjectAURA" / "audit"
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "project_aura" / "audit"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in SENSITIVE_KEYS or normalized.endswith(("_path", "_token", "_secret", "_password"))


def _looks_like_path(value: str) -> bool:
    return value.startswith(("/", "~/", "file://")) or bool(WINDOWS_PATH_RE.match(value))


def sanitize_details(value, *, key: str = "", depth: int = 0):
    if _is_sensitive_key(key):
        return "[REDACTED]"
    if depth >= MAX_DETAIL_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _looks_like_path(value):
            return "[REDACTED_PATH]"
        compact = " ".join(value.split())
        return compact[:MAX_STRING_LENGTH]
    if isinstance(value, Path):
        return "[REDACTED_PATH]"
    if isinstance(value, dict):
        sanitized = {}
        for item_key, item_value in list(value.items())[:MAX_DETAIL_ITEMS]:
            normalized_key = str(item_key)[:64]
            sanitized[normalized_key] = sanitize_details(
                item_value,
                key=normalized_key,
                depth=depth + 1,
            )
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [sanitize_details(item, depth=depth + 1) for item in list(value)[:MAX_DETAIL_ITEMS]]
    return f"[{type(value).__name__}]"


def _canonical_hash(event: dict) -> str:
    payload = {key: value for key, value in event.items() if not str(key).startswith("_")}
    payload.pop("integrity", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AuditRecorder:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        enabled: bool | None = None,
        retention_days: int | None = None,
        session_id: str | None = None,
    ):
        self.root = Path(root) if root is not None else default_audit_dir()
        self.enabled = audit_enabled_from_env() if enabled is None else bool(enabled)
        self.retention_days = retention_days_from_env() if retention_days is None else max(0, retention_days)
        self.session_id = session_id or str(uuid.uuid4())
        self.sequence = 0
        self.previous_event_hash = GENESIS_HASH
        self.last_error = ""
        self._lock = threading.Lock()
        if self.enabled:
            self._prepare_root()

    def _prepare_root(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.prune_expired_files()
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.enabled = False
            logger.error("Audit trail disabled because its local directory is unavailable: %s", exc)
            return
        try:
            self.root.chmod(0o700)
        except OSError:
            pass

    def prune_expired_files(self):
        if not self.enabled or self.retention_days == 0:
            return
        cutoff = dt.datetime.now().timestamp() - (self.retention_days * 86400)
        for path in self.root.glob("audit-*.jsonl"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError as exc:
                logger.warning("Could not prune audit file %s: %s", path, exc)

    def record(
        self,
        name: str,
        *,
        category: str,
        actor: str = "system",
        workflow: str = "app",
        outcome: str = "success",
        severity: str = "info",
        details: dict | None = None,
        occurred_at: dt.datetime | None = None,
    ) -> dict | None:
        if not self.enabled:
            return None
        if not EVENT_NAME_RE.fullmatch(name) or not EVENT_NAME_RE.fullmatch(category):
            raise ValueError("Audit event names and categories must use stable lowercase dotted identifiers.")
        if actor not in ALLOWED_ACTORS:
            raise ValueError(f"Unsupported audit actor: {actor}")
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"Unsupported audit outcome: {outcome}")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"Unsupported audit severity: {severity}")

        timestamp = occurred_at or dt.datetime.now().astimezone()
        if timestamp.tzinfo is None:
            timestamp = timestamp.astimezone()
        with self._lock:
            event = {
                "schema_version": SCHEMA_VERSION,
                "event_id": str(uuid.uuid4()),
                "occurred_at": timestamp.isoformat(timespec="milliseconds"),
                "session_id": self.session_id,
                "sequence": self.sequence + 1,
                "app_version": __version__,
                "actor": actor,
                "category": category,
                "name": name,
                "workflow": workflow,
                "outcome": outcome,
                "severity": severity,
                "details": sanitize_details(details or {}),
            }
            event_hash = _canonical_hash(event)
            event["integrity"] = {
                "algorithm": "sha256",
                "previous_event_hash": self.previous_event_hash,
                "event_hash": event_hash,
            }
            path = self.root / f"audit-{timestamp:%Y-%m-%d}.jsonl"
            try:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                    handle.flush()
            except OSError as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.error("Audit event write failed: %s", exc)
                return None
            try:
                path.chmod(0o600)
            except OSError:
                pass
            self.sequence += 1
            self.previous_event_hash = event_hash
            self.last_error = ""
            return event


def _audit_paths(paths: Iterable[str | Path] | None = None) -> list[Path]:
    candidates = [Path(path) for path in paths] if paths is not None else [default_audit_dir()]
    resolved: list[Path] = []
    for candidate in candidates:
        if candidate.is_dir():
            resolved.extend(sorted(candidate.glob("audit-*.jsonl")))
        elif candidate.exists():
            resolved.append(candidate)
    return sorted(set(resolved))


def read_audit_events(paths: Iterable[str | Path] | None = None) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    issues: list[dict] = []
    for path in _audit_paths(paths):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            issues.append({"kind": "read_failure", "path": str(path), "error_class": type(exc).__name__})
            continue
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                issues.append({"kind": "parse_failure", "path": str(path), "line": line_number})
                continue
            if not isinstance(event, dict):
                issues.append({"kind": "invalid_event", "path": str(path), "line": line_number})
                continue
            event["_source_path"] = str(path)
            event["_source_line"] = line_number
            events.append(event)
    return events, issues


def verify_audit_integrity(events: Iterable[dict]) -> list[dict]:
    sessions: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        sessions[str(event.get("session_id", "missing"))].append(event)
    issues: list[dict] = []
    for session_id, session_events in sessions.items():
        ordered = sorted(session_events, key=lambda event: int(event.get("sequence", 0) or 0))
        expected_sequence = 1
        expected_previous = GENESIS_HASH
        for event in ordered:
            sequence = event.get("sequence")
            integrity = event.get("integrity") if isinstance(event.get("integrity"), dict) else {}
            if sequence != expected_sequence:
                issues.append(
                    {
                        "kind": "sequence_gap",
                        "session_id": session_id,
                        "expected": expected_sequence,
                        "actual": sequence,
                    }
                )
                expected_sequence = int(sequence or expected_sequence)
            if integrity.get("previous_event_hash") != expected_previous:
                issues.append({"kind": "previous_hash_mismatch", "session_id": session_id, "sequence": sequence})
            computed_hash = _canonical_hash(event)
            if integrity.get("event_hash") != computed_hash:
                issues.append({"kind": "event_hash_mismatch", "session_id": session_id, "sequence": sequence})
            expected_previous = str(integrity.get("event_hash", ""))
            expected_sequence += 1
    return issues


def _parse_timestamp(event: dict) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(event.get("occurred_at", "")))
    except ValueError:
        return None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


def _window_signals(
    events: list[dict],
    *,
    threshold: int,
    window_seconds: int,
    predicate,
    group_key,
    kind: str,
) -> list[dict]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for event in events:
        if predicate(event) and _parse_timestamp(event) is not None:
            grouped[group_key(event)].append(event)
    signals: list[dict] = []
    for key, grouped_events in grouped.items():
        ordered = sorted(grouped_events, key=lambda event: _parse_timestamp(event) or dt.datetime.min)
        start = 0
        for end, event in enumerate(ordered):
            end_time = _parse_timestamp(event)
            while start < end:
                start_time = _parse_timestamp(ordered[start])
                if start_time and end_time and (end_time - start_time).total_seconds() > window_seconds:
                    start += 1
                else:
                    break
            if end - start + 1 >= threshold:
                signals.append({"kind": kind, "group": list(key), "count": end - start + 1})
                break
    return signals


def analyze_audit_events(
    events: Iterable[dict],
    read_issues: Iterable[dict] | None = None,
    *,
    active_session_id: str | None = None,
) -> dict:
    event_list = [dict(event) for event in events]
    read_issue_list = list(read_issues or [])
    integrity_issues = verify_audit_integrity(event_list)
    names = Counter(str(event.get("name", "unknown")) for event in event_list)
    outcomes = Counter(str(event.get("outcome", "unknown")) for event in event_list)
    severities = Counter(str(event.get("severity", "unknown")) for event in event_list)
    categories = Counter(str(event.get("category", "unknown")) for event in event_list)
    workflows = Counter(str(event.get("workflow", "unknown")) for event in event_list)
    schemas = Counter(str(event.get("schema_version", "unknown")) for event in event_list)
    user_actions = Counter(
        str(event.get("name", "unknown")) for event in event_list if event.get("actor") == "user"
    )

    workflow_kpis = {}
    total_starts = 0
    total_completed = 0
    for workflow, contract in WORKFLOW_EVENTS.items():
        starts = names[contract["start"]]
        completed = sum(names[name] for name in contract["completed"])
        terminal = sum(names[name] for name in contract["terminal"])
        total_starts += starts
        total_completed += completed
        workflow_kpis[workflow] = {
            "started": starts,
            "completed": completed,
            "terminal": terminal,
            "completion_rate": round(completed / starts, 4) if starts else None,
        }

    duration_values = [
        float(event.get("details", {}).get("duration_ms"))
        for event in event_list
        if isinstance(event.get("details"), dict)
        and isinstance(event.get("details", {}).get("duration_ms"), (int, float))
    ]
    repeated_actions = _window_signals(
        event_list,
        threshold=5,
        window_seconds=120,
        predicate=lambda event: event.get("actor") == "user",
        group_key=lambda event: (str(event.get("session_id")), str(event.get("name"))),
        kind="repeated_action",
    )
    error_bursts = _window_signals(
        event_list,
        threshold=3,
        window_seconds=600,
        predicate=lambda event: event.get("severity") in {"error", "critical"},
        group_key=lambda event: (str(event.get("session_id")),),
        kind="error_burst",
    )

    incomplete_workflows: list[dict] = []
    uncontrolled_terminations: list[dict] = []
    by_session: dict[str, list[dict]] = defaultdict(list)
    for event in event_list:
        by_session[str(event.get("session_id", "missing"))].append(event)
    for session_id, session_events in by_session.items():
        session_names = Counter(str(event.get("name", "unknown")) for event in session_events)
        if not session_names["app.session_ended"]:
            if session_id != active_session_id:
                uncontrolled_terminations.append(
                    {"kind": "uncontrolled_termination_candidate", "session_id": session_id}
                )
            continue
        for workflow, contract in WORKFLOW_EVENTS.items():
            starts = session_names[contract["start"]]
            terminals = sum(session_names[name] for name in contract["terminal"])
            if starts > terminals:
                incomplete_workflows.append(
                    {
                        "kind": "incomplete_workflow",
                        "session_id": session_id,
                        "workflow": workflow,
                        "count": starts - terminals,
                    }
                )

    attempts = sum(1 for event in event_list if event.get("actor") == "user")
    friction_count = outcomes["cancelled"] + outcomes["rejected"] + len(repeated_actions)
    schema_issues = [
        {"kind": "unknown_schema", "schema_version": schema}
        for schema in schemas
        if schema != SCHEMA_VERSION
    ]
    anomalies = [
        *read_issue_list,
        *integrity_issues,
        *schema_issues,
        *error_bursts,
        *repeated_actions,
        *incomplete_workflows,
        *uncontrolled_terminations,
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "rule_version": "1.0",
        "event_count": len(event_list),
        "session_count": len(by_session),
        "schema_counts": dict(schemas.most_common()),
        "event_counts": dict(names.most_common()),
        "category_counts": dict(categories.most_common()),
        "workflow_counts": dict(workflows.most_common()),
        "outcome_counts": dict(outcomes.most_common()),
        "severity_counts": dict(severities.most_common()),
        "user_action_counts": dict(user_actions.most_common()),
        "kpis": {
            "workflow_completion_rate": round(total_completed / total_starts, 4) if total_starts else None,
            "recoverable_friction_rate": round(friction_count / attempts, 4) if attempts else None,
            "duration_ms_p50": _percentile(duration_values, 0.5),
            "duration_ms_p95": _percentile(duration_values, 0.95),
            "audit_integrity_pass": not read_issue_list and not integrity_issues,
            "workflow_breakdown": workflow_kpis,
        },
        "friction_signals": {
            "cancelled_events": outcomes["cancelled"],
            "rejected_events": outcomes["rejected"],
            "repeated_actions": repeated_actions,
        },
        "anomalies": anomalies,
    }


def render_audit_markdown(report: dict) -> str:
    kpis = report["kpis"]
    lines = [
        "# Project AURA 本機稽核摘要",
        "",
        f"- 產生時間：`{report['generated_at']}`",
        f"- 事件數：`{report['event_count']}`",
        f"- Session 數：`{report['session_count']}`",
        f"- Schema：`{json.dumps(report['schema_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- Integrity：`{'PASS' if kpis['audit_integrity_pass'] else 'REVIEW REQUIRED'}`",
        "",
        "## KPI",
        "",
        f"- 工作流完成率：`{kpis['workflow_completion_rate']}`",
        f"- 可恢復摩擦率：`{kpis['recoverable_friction_rate']}`",
        f"- Duration p50 / p95：`{kpis['duration_ms_p50']}` / `{kpis['duration_ms_p95']}` ms",
        "",
        "| Workflow | Started | Completed | Terminal | Completion rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for workflow, values in kpis["workflow_breakdown"].items():
        lines.append(
            f"| {workflow} | {values['started']} | {values['completed']} | {values['terminal']} | "
            f"{values['completion_rate']} |"
        )
    lines.extend(["", "## 使用者動作", ""])
    if report["user_action_counts"]:
        for name, count in report["user_action_counts"].items():
            lines.append(f"- `{name}`：{count}")
    else:
        lines.append("- 尚無可分析的使用者動作。")
    lines.extend(["", "## 異常與摩擦複核", ""])
    if report["anomalies"]:
        for anomaly in report["anomalies"]:
            lines.append(f"- `{anomaly.get('kind', 'unknown')}`：`{json.dumps(anomaly, ensure_ascii=False, sort_keys=True)}`")
    else:
        lines.append("- 本次規則未標記待複核訊號。")
    lines.extend(
        [
            "",
            "## Scope controls",
            "",
            "本報告只分析去內容化事件。異常是待複核訊號，不構成使用者惡意、人格、醫療或績效判定。",
            "",
        ]
    )
    return "\n".join(lines)


def write_audit_report(
    audit_root: str | Path | None = None,
    output_path: str | Path | None = None,
    *,
    active_session_id: str | None = None,
) -> tuple[Path, dict]:
    root = Path(audit_root) if audit_root is not None else default_audit_dir()
    events, read_issues = read_audit_events([root])
    report = analyze_audit_events(events, read_issues, active_session_id=active_session_id)
    if output_path is None:
        report_dir = root / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        output = report_dir / f"audit-report-{timestamp}.md"
    else:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_audit_markdown(report), encoding="utf-8")
    try:
        output.chmod(0o600)
    except OSError:
        pass
    return output, report
