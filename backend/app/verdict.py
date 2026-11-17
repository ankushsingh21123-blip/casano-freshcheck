"""Transparent heuristic verdict engine.

This is a heuristic detector, NOT ground truth. Every signal used to reach
a verdict is returned to the caller so the reasoning can be inspected.

Signals:
  (a) newest evidence date vs the stored answer's date (when both known);
  (b) date/number claims extracted from the stored answer, checked against
      evidence snippets (present vs not found; newer years in evidence);
  (c) keyword overlap between the stored answer and the evidence text.

Decision rules (applied in order):
  1. No evidence -> UNKNOWN.
  2. Keyword overlap below 0.15 -> UNKNOWN (evidence does not match the
     answer topically, so date signals would be meaningless).
  3. Newest evidence date more than 180 days newer than the answer date
     AND evidence mentions a year newer than any year in the answer
     -> STALE.
  4. Newest evidence date more than 90 days newer than the answer date
     -> POSSIBLY_STALE.
  5. Keyword overlap below 0.30 -> POSSIBLY_STALE.
  6. At least one extracted claim not found in evidence AND overlap
     below 0.50 -> POSSIBLY_STALE (partial corroboration only).
  7. Otherwise -> FRESH.
"""

from __future__ import annotations

import re
from datetime import date

from .query import tokenize

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))

_ISO_DATE_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")
_MONTH_DAY_YEAR_RE = re.compile(
    rf"\b({_MONTH_NAMES})\s+(\d{{1,2}}),?\s+((?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})\s+((?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(
    rf"\b({_MONTH_NAMES})\s+((?:19|20)\d{{2}})\b", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_NUMBER_RE = re.compile(
    r"\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|\$\d+(?:\.\d+)?%?|\b\d+\.\d+%?|\b\d+%"
)

DATE_NOT_PROVIDED = "date not provided"


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_dates(text: str) -> list[dict]:
    """Extract date mentions from text.

    Returns a list of ``{"raw": str, "date": "YYYY-MM-DD", "kind": str}``
    where kind is "full", "month" (month + year, normalised to the 1st) or
    "year" (year only, normalised to 1 January). Overlapping matches are
    de-duplicated by span so a full date is not also counted as a year.
    """
    found: list[dict] = []
    used_spans: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in used_spans)

    def _add(start: int, end: int, raw: str, parsed: date | None, kind: str) -> None:
        if parsed is None or _overlaps(start, end):
            return
        used_spans.append((start, end))
        found.append({"raw": raw, "date": parsed.isoformat(), "kind": kind})

    for match in _ISO_DATE_RE.finditer(text):
        raw = match.group(0)
        year, month, day = (int(part) for part in raw.split("-"))
        _add(match.start(), match.end(), raw, _safe_date(year, month, day), "full")

    for match in _MONTH_DAY_YEAR_RE.finditer(text):
        month = MONTHS[match.group(1).lower()]
        _add(
            match.start(), match.end(), match.group(0),
            _safe_date(int(match.group(3)), month, int(match.group(2))), "full",
        )

    for match in _DAY_MONTH_YEAR_RE.finditer(text):
        month = MONTHS[match.group(2).lower()]
        _add(
            match.start(), match.end(), match.group(0),
            _safe_date(int(match.group(3)), month, int(match.group(1))), "full",
        )

    for match in _MONTH_YEAR_RE.finditer(text):
        month = MONTHS[match.group(1).lower()]
        _add(
            match.start(), match.end(), match.group(0),
            _safe_date(int(match.group(2)), month, 1), "month",
        )

    for match in _YEAR_RE.finditer(text):
        _add(
            match.start(), match.end(), match.group(0),
            _safe_date(int(match.group(1)), 1, 1), "year",
        )

    return found


def extract_number_claims(text: str) -> list[str]:
    """Extract figure-like claims (grouped numbers, decimals, percents).

    Plain years are date claims, not number claims, so bare 4-digit years
    are excluded here.
    """
    claims: list[str] = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(0)
        stripped = raw.lstrip("$")
        if re.fullmatch(r"(?:19|20)\d{2}", stripped):
            continue
        if raw not in claims:
            claims.append(raw)
    return claims


def extract_claims(text: str) -> dict:
    """All date + number claims found in a stored answer."""
    date_claims = extract_dates(text)
    return {
        "date_claims": date_claims,
        "number_claims": extract_number_claims(text),
    }


def parse_published_date(value: str | None) -> date | None:
    """Parse a Tavily ``published_date`` value, if present and ISO-like.

    Accepts ``YYYY-MM-DD`` and full ISO datetimes; returns None for
    anything else. Tavily does not guarantee this field on every result.
    """
    if not value or not isinstance(value, str):
        return None
    candidate = value.strip()[:10]
    if not re.fullmatch(r"(?:19|20)\d{2}-\d{2}-\d{2}", candidate):
        return None
    year, month, day = (int(part) for part in candidate.split("-"))
    return _safe_date(year, month, day)


def evidence_date_from_snippet(snippet: str) -> date | None:
    """Best-effort date for an evidence item from its snippet text.

    Uses the latest date mentioned in the snippet, preferring full dates
    over month/year-only mentions when both are present.
    """
    dates = extract_dates(snippet)
    if not dates:
        return None
    full = [d for d in dates if d["kind"] == "full"]
    pool = full if full else dates
    return max(date.fromisoformat(d["date"]) for d in pool)


def _normalize_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "", value.lower())


def _claim_found_in_evidence(claim: str, evidence_text_normalized: str) -> bool:
    normalized = _normalize_for_match(claim)
    if not normalized:
        return False
    return normalized in evidence_text_normalized


def keyword_overlap(answer: str, evidence_text: str) -> tuple[float, list[str]]:
    """Fraction of the answer's content terms that appear in the evidence."""
    answer_terms = set(tokenize(answer))
    if not answer_terms:
        return 0.0, []
    evidence_terms = set(tokenize(evidence_text))
    overlapping = sorted(answer_terms & evidence_terms)
    return len(overlapping) / len(answer_terms), overlapping


def evaluate_verdict(
    answer: str,
    answer_date: date | None,
    evidence: list[dict],
) -> dict:
    """Evaluate a verdict from the stored answer and evidence items.

    Each evidence item is a dict with at least ``snippet`` and ``date``
    (an ISO date string or None). Returns ``{"verdict", "reasons",
    "signals"}``; every signal used is included in ``signals``.
    """
    claims = extract_claims(answer)
    evidence_text = " ".join(item.get("snippet", "") for item in evidence)
    evidence_text_normalized = _normalize_for_match(evidence_text)

    evidence_dates = sorted(
        {item["date"] for item in evidence if item.get("date")}
    )
    newest_evidence_date = evidence_dates[-1] if evidence_dates else None

    overlap, overlapping_terms = keyword_overlap(answer, evidence_text)

    all_claim_strings = [d["raw"] for d in claims["date_claims"]]
    all_claim_strings += claims["number_claims"]
    claims_found = [
        c for c in all_claim_strings
        if _claim_found_in_evidence(c, evidence_text_normalized)
    ]
    claims_not_found = [
        c for c in all_claim_strings
        if c not in claims_found
    ]

    answer_years = {
        int(d["date"][:4]) for d in claims["date_claims"]
    }
    evidence_years: set[int] = set()
    for item in evidence:
        for found in extract_dates(item.get("snippet", "")):
            evidence_years.add(int(found["date"][:4]))
        if item.get("date"):
            evidence_years.add(int(item["date"][:4]))
    newer_years = sorted(y for y in evidence_years if answer_years and y > max(answer_years))

    gap_days: int | None = None
    if newest_evidence_date and answer_date:
        gap_days = (
            date.fromisoformat(newest_evidence_date) - answer_date
        ).days

    signals = {
        "newest_evidence_date": newest_evidence_date,
        "answer_date": answer_date.isoformat() if answer_date else None,
        "evidence_date_gap_days": gap_days,
        "evidence_count": len(evidence),
        "evidence_dates": evidence_dates,
        "keyword_overlap": round(overlap, 3),
        "overlapping_terms": overlapping_terms,
        "date_claims": claims["date_claims"],
        "number_claims": claims["number_claims"],
        "claims_found_in_evidence": claims_found,
        "claims_not_found_in_evidence": claims_not_found,
        "newer_years_in_evidence": newer_years,
    }

    reasons: list[str] = []

    if not evidence:
        return {
            "verdict": "UNKNOWN",
            "reasons": ["No evidence was returned, so freshness cannot be judged."],
            "signals": signals,
        }

    if overlap < 0.15:
        reasons.append(
            f"Keyword overlap between the answer and the evidence is low "
            f"({overlap:.0%}), so the evidence may not be about the same topic."
        )
        return {"verdict": "UNKNOWN", "reasons": reasons, "signals": signals}

    if (
        gap_days is not None
        and gap_days > 180
        and newer_years
    ):
        reasons.append(
            f"The newest evidence is dated {newest_evidence_date}, "
            f"{gap_days} days after the answer date "
            f"{answer_date.isoformat() if answer_date else 'unknown'}."
        )
        reasons.append(
            f"Evidence mentions newer year(s) {', '.join(map(str, newer_years))} "
            f"than any year in the answer."
        )
        if claims_not_found:
            reasons.append(
                "Some claims from the answer were not found in the evidence: "
                + ", ".join(claims_not_found) + "."
            )
        return {"verdict": "STALE", "reasons": reasons, "signals": signals}

    if gap_days is not None and gap_days > 90:
        reasons.append(
            f"The newest evidence is dated {newest_evidence_date}, "
            f"{gap_days} days after the answer date "
            f"{answer_date.isoformat() if answer_date else 'unknown'}; "
            f"the answer may predate newer information."
        )
        if claims_not_found:
            reasons.append(
                "Some claims from the answer were not found in the evidence: "
                + ", ".join(claims_not_found) + "."
            )
        return {"verdict": "POSSIBLY_STALE", "reasons": reasons, "signals": signals}

    if overlap < 0.30:
        reasons.append(
            f"Keyword overlap between the answer and the evidence is only "
            f"{overlap:.0%}; corroboration is weak."
        )
        return {"verdict": "POSSIBLY_STALE", "reasons": reasons, "signals": signals}

    if claims_not_found and overlap < 0.50:
        reasons.append(
            f"Keyword overlap is {overlap:.0%}, but some claims from the "
            f"answer were not found in the evidence: "
            + ", ".join(claims_not_found) + "."
        )
        return {"verdict": "POSSIBLY_STALE", "reasons": reasons, "signals": signals}

    reasons.append(
        f"Evidence corroborates the answer (keyword overlap {overlap:.0%})."
    )
    if newest_evidence_date and answer_date:
        reasons.append(
            f"The newest evidence date ({newest_evidence_date}) is within "
            f"90 days of the answer date ({answer_date.isoformat()})."
        )
    elif newest_evidence_date:
        reasons.append(
            f"Evidence is dated up to {newest_evidence_date}; no answer "
            f"date was supplied for comparison."
        )
    else:
        reasons.append(
            "No usable evidence dates were available; the verdict rests on "
            "content corroboration only."
        )
    if claims_not_found:
        reasons.append(
            "Note: some claims from the answer were not found in the "
            "evidence: " + ", ".join(claims_not_found) + "."
        )
    return {"verdict": "FRESH", "reasons": reasons, "signals": signals}


def answer_only_analysis(answer: str) -> dict:
    """Offline analysis: claim extraction on the answer alone.

    Labelled as answer-only everywhere it is surfaced; it never implies
    a live freshness verdict.
    """
    claims = extract_claims(answer)
    return {
        "analysis_kind": "answer_only",
        "date_claims": claims["date_claims"],
        "number_claims": claims["number_claims"],
        "evidence_count": 0,
        "keyword_overlap": None,
        "newest_evidence_date": None,
    }
