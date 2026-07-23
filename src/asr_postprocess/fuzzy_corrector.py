from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz


DEFAULT_GLOSSARY_PATH = resources.files("asr_postprocess").joinpath(
    "domain_glossary.yaml"
)
DEFAULT_THRESHOLDS = {
    "organizations": 85.0,
    "medical_terms": 92.0,
    "technical_terms": 90.0,
    "people": 90.0,
}
GLOSSARY_CATEGORIES = tuple(DEFAULT_THRESHOLDS)
METHOD = "rapidfuzz"

ASCII_TOKEN_RE = re.compile(r"(?<![\w])(?:[A-Za-z][A-Za-z0-9]*(?:[-_/+.()][A-Za-z0-9()]+)*|[0-9]+\(k\))(?![\w])")
CJK_RE = re.compile(r"[\u3400-\u9fff]")


@dataclass(frozen=True)
class Correction:
    original: str
    corrected: str
    score: float
    category: str
    method: str
    accepted: bool
    start: int
    end: int
    review_status: str = "accepted"
    review_reason: str = ""

    @property
    def span(self) -> str:
        return self.original

    def to_log_entry(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["span"] = self.span
        return payload


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    category: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorrectionResult:
    raw_transcript: str
    corrected_transcript: str
    correction_log: list[dict[str, Any]]
    llm_verification: bool = False

    @property
    def changed(self) -> bool:
        return self.raw_transcript != self.corrected_transcript


def load_glossary(
    path: str | Path | Traversable = DEFAULT_GLOSSARY_PATH,
) -> dict[str, Any]:
    glossary = Path(path) if isinstance(path, (str, Path)) else path
    try:
        text = glossary.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Domain glossary not found: {glossary}") from None
    payload = yaml.safe_load(text) or {}
    if not isinstance(payload, dict):
        raise ValueError("Domain glossary must be a YAML mapping.")
    return payload


def glossary_entries(payload: dict[str, Any]) -> list[GlossaryEntry]:
    aliases = payload.get("aliases") or {}
    entries: list[GlossaryEntry] = []
    for category in GLOSSARY_CATEGORIES:
        terms = payload.get(category) or []
        if not isinstance(terms, list):
            raise ValueError(f"Glossary category `{category}` must be a list.")
        category_aliases = aliases.get(category) or {}
        for term in terms:
            if not isinstance(term, str) or not term.strip():
                continue
            normalized = term.strip()
            raw_aliases = category_aliases.get(normalized) or []
            if not isinstance(raw_aliases, list):
                raise ValueError(f"Aliases for `{normalized}` must be a list.")
            entries.append(
                GlossaryEntry(
                    term=normalized,
                    category=category,
                    aliases=tuple(alias.strip() for alias in raw_aliases if isinstance(alias, str) and alias.strip()),
                )
            )
    return entries


def glossary_thresholds(payload: dict[str, Any]) -> dict[str, float]:
    configured = ((payload.get("settings") or {}).get("thresholds") or {})
    thresholds = dict(DEFAULT_THRESHOLDS)
    for category, value in configured.items():
        if category in thresholds:
            thresholds[category] = float(value)
    return thresholds


def llm_verification_enabled(payload: dict[str, Any]) -> bool:
    return bool((payload.get("settings") or {}).get("llm_verification", False))


def correction_policy(payload: dict[str, Any]) -> dict[tuple[str, str, str], tuple[str, str]]:
    configured = payload.get("correction_policy") or {}
    policy: dict[tuple[str, str, str], tuple[str, str]] = {}
    for status in ("denylist", "manual_review_required"):
        categories = configured.get(status) or {}
        if not isinstance(categories, dict):
            continue
        for category, entries in categories.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                original = str(entry.get("original") or "").strip()
                corrected = str(entry.get("corrected") or "").strip()
                reason = str(entry.get("reason") or status).strip()
                if original and corrected:
                    policy[(str(category), original, corrected)] = (status, reason)
    return policy


def _is_ascii_term(term: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", term))


def _contains_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def _candidate_windows(text: str, term: str) -> set[tuple[int, int]]:
    windows: set[tuple[int, int]] = set()
    term_length = len(term)
    if term_length <= 1:
        return windows
    for length in range(max(2, term_length - 1), term_length + 2):
        if length > len(text):
            continue
        for start in range(0, len(text) - length + 1):
            span = text[start : start + length]
            if span == term or not _contains_cjk(span):
                continue
            if any(char.isspace() for char in span):
                continue
            windows.add((start, start + length))
    return windows


def _alias_matches(text: str, entry: GlossaryEntry) -> list[Correction]:
    matches: list[Correction] = []
    for alias in entry.aliases:
        if alias == entry.term:
            continue
        start = 0
        while True:
            index = text.find(alias, start)
            if index < 0:
                break
            matches.append(
                Correction(
                    original=alias,
                    corrected=entry.term,
                    score=100.0,
                    category=entry.category,
                    method=METHOD,
                    accepted=True,
                    start=index,
                    end=index + len(alias),
                )
            )
            start = index + len(alias)
    return matches


def _fuzzy_matches(text: str, entry: GlossaryEntry, threshold: float) -> list[Correction]:
    matches: list[Correction] = []
    if _is_ascii_term(entry.term):
        for token in ASCII_TOKEN_RE.finditer(text):
            span = token.group(0)
            if span == entry.term:
                continue
            score = float(fuzz.ratio(span.lower(), entry.term.lower()))
            if score >= threshold:
                matches.append(
                    Correction(
                        original=span,
                        corrected=entry.term,
                        score=round(score, 2),
                        category=entry.category,
                        method=METHOD,
                        accepted=True,
                        start=token.start(),
                        end=token.end(),
                    )
                )
        return matches

    for start, end in _candidate_windows(text, entry.term):
        span = text[start:end]
        score = float(fuzz.ratio(span, entry.term))
        if score >= threshold:
            matches.append(
                Correction(
                    original=span,
                    corrected=entry.term,
                    score=round(score, 2),
                    category=entry.category,
                    method=METHOD,
                    accepted=True,
                    start=start,
                    end=end,
                )
            )
    return matches


def _exact_term_spans(text: str, entries: list[GlossaryEntry]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for entry in entries:
        start = 0
        while True:
            index = text.find(entry.term, start)
            if index < 0:
                break
            spans.append((index, index + len(entry.term)))
            start = index + len(entry.term)
    return spans


def _select_non_overlapping(
    candidates: list[Correction],
    protected_spans: list[tuple[int, int]] | None = None,
) -> list[Correction]:
    ordered = sorted(
        candidates,
        key=lambda item: (item.start, -item.score, -(item.end - item.start), item.corrected),
    )
    accepted: list[Correction] = []
    occupied: list[tuple[int, int]] = list(protected_spans or [])
    for candidate in ordered:
        if candidate.original == candidate.corrected:
            continue
        if any(candidate.start < end and start < candidate.end for start, end in occupied):
            continue
        accepted.append(candidate)
        occupied.append((candidate.start, candidate.end))
    return accepted


def correct_transcript(
    transcript: str,
    glossary_path: str | Path | Traversable = DEFAULT_GLOSSARY_PATH,
) -> CorrectionResult:
    payload = load_glossary(glossary_path)
    thresholds = glossary_thresholds(payload)
    entries = glossary_entries(payload)
    policy = correction_policy(payload)

    candidates: list[Correction] = []
    for entry in entries:
        threshold = thresholds.get(entry.category, 90.0)
        candidates.extend(_alias_matches(transcript, entry))
        candidates.extend(_fuzzy_matches(transcript, entry, threshold))

    selected = _select_non_overlapping(candidates, protected_spans=_exact_term_spans(transcript, entries))
    corrections: list[Correction] = []
    rejected: list[Correction] = []
    for correction in selected:
        status, reason = policy.get((correction.category, correction.original, correction.corrected), ("accepted", ""))
        if status == "accepted":
            corrections.append(correction)
            continue
        rejected.append(
            Correction(
                original=correction.original,
                corrected=correction.corrected,
                score=correction.score,
                category=correction.category,
                method=correction.method,
                accepted=False,
                start=correction.start,
                end=correction.end,
                review_status=status,
                review_reason=reason,
            )
        )
    corrected_parts: list[str] = []
    cursor = 0
    for correction in corrections:
        corrected_parts.append(transcript[cursor : correction.start])
        corrected_parts.append(correction.corrected)
        cursor = correction.end
    corrected_parts.append(transcript[cursor:])
    corrected = "".join(corrected_parts)

    return CorrectionResult(
        raw_transcript=transcript,
        corrected_transcript=corrected,
        correction_log=[correction.to_log_entry() for correction in sorted(corrections + rejected, key=lambda item: item.start)],
        llm_verification=llm_verification_enabled(payload),
    )


def write_correction_log(path: str | Path, correction_log: list[dict[str, Any]]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(correction_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
