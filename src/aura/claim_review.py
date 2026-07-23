from __future__ import annotations

import datetime
import json
from pathlib import Path

from aura.review import _atomic_write


CLAIM_REVIEW_STATUSES = {"unreviewed", "confirmed", "rejected", "edited"}


def _summary_claims(session_dir: Path) -> list[dict]:
    try:
        payload = json.loads((session_dir / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read summary claims from {session_dir}") from exc
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    if not isinstance(claims, list):
        raise ValueError("summary.json claims must be a list")
    return [dict(claim) for claim in claims if isinstance(claim, dict)]


def _review_overrides(session_dir: Path) -> dict[str, dict[str, str]]:
    path = session_dir / "review_events.jsonl"
    if not path.exists():
        return {}
    overrides = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid review event in {path}") from exc
        claim_id = str(event.get("claim_id") or "")
        changes = event.get("changes", {})
        if not claim_id or not isinstance(changes, dict):
            continue
        override = overrides.setdefault(claim_id, {})
        status = changes.get("review_status", {}).get("to")
        text = changes.get("text", {}).get("to")
        if status in CLAIM_REVIEW_STATUSES:
            override["review_status"] = status
        if isinstance(text, str) and text.strip():
            override["text"] = text.strip()
    return overrides


def load_claims(session_dir: str | Path) -> list[dict]:
    directory = Path(session_dir)
    overrides = _review_overrides(directory)
    claims = _summary_claims(directory)
    for claim in claims:
        claim_id = str(claim.get("claim_id") or "")
        claim["review_status"] = "unreviewed"
        claim.update(overrides.get(claim_id, {}))
    return claims


def _append_event(session_dir: Path, event: dict) -> None:
    path = session_dir / "review_events.jsonl"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _atomic_write(
        path,
        existing + json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
    )


def record_claim_review(
    session_dir: str | Path,
    claim_id: str,
    review_status: str,
) -> dict:
    if review_status not in {"confirmed", "rejected"}:
        raise ValueError(f"unsupported claim review status: {review_status}")
    directory = Path(session_dir)
    claims = load_claims(directory)
    claim = next(
        (item for item in claims if str(item.get("claim_id") or "") == claim_id),
        None,
    )
    if claim is None:
        raise KeyError(claim_id)
    if review_status == "confirmed" and (
        claim.get("support_status") == "unsupported"
        or not claim.get("source_segment_ids")
    ):
        raise ValueError("A claim needs source evidence before confirmation")
    previous = str(claim.get("review_status") or "unreviewed")
    if previous == review_status:
        return claim
    event = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": f"claim.{review_status}",
        "claim_id": claim_id,
        "changes": {
            "review_status": {
                "from": previous,
                "to": review_status,
            }
        },
    }
    _append_event(directory, event)
    claim["review_status"] = review_status
    return claim


def record_claim_edit(
    session_dir: str | Path,
    claim_id: str,
    text: str,
) -> dict:
    replacement = str(text).strip()
    if not replacement:
        raise ValueError("claim text is required")
    directory = Path(session_dir)
    claim = next(
        (
            item
            for item in load_claims(directory)
            if str(item.get("claim_id") or "") == claim_id
        ),
        None,
    )
    if claim is None:
        raise KeyError(claim_id)
    previous = str(claim.get("text") or "")
    if previous == replacement:
        return claim
    previous_status = str(claim.get("review_status") or "unreviewed")
    _append_event(
        directory,
        {
            "timestamp": datetime.datetime.now()
            .astimezone()
            .isoformat(timespec="seconds"),
            "event": "claim.edited",
            "claim_id": claim_id,
            "changes": {
                "text": {"from": previous, "to": replacement},
                "review_status": {"from": previous_status, "to": "edited"},
            },
        },
    )
    claim["text"] = replacement
    claim["review_status"] = "edited"
    return claim
