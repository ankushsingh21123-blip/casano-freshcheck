"""Tests for the transparent heuristic verdict engine."""

from datetime import date

from app.verdict import (
    answer_only_analysis,
    evaluate_verdict,
    extract_claims,
    extract_dates,
)


def _evidence(snippet, date_value):
    return {
        "title": "Evidence",
        "url": "https://example.com/article",
        "date": date_value,
        "date_display": date_value or "date not provided",
        "date_source": "published_date" if date_value else "not_provided",
        "snippet": snippet,
        "score": 0.9,
    }


def test_fresh_when_evidence_corroborates_and_dates_close():
    outcome = evaluate_verdict(
        "The electric vehicle battery range is 400 miles in 2024.",
        date(2024, 6, 1),
        [_evidence(
            "Electric vehicle battery range reaches 400 miles in 2024 models.",
            "2024-06-15",
        )],
    )
    assert outcome["verdict"] == "FRESH"
    assert outcome["signals"]["keyword_overlap"] == 1.0
    assert outcome["signals"]["evidence_date_gap_days"] == 14
    assert outcome["reasons"]


def test_stale_when_evidence_far_newer_with_newer_year():
    outcome = evaluate_verdict(
        "The Falcons won the championship in 2021, scoring 98 points total.",
        date(2021, 6, 1),
        [_evidence(
            "Falcons championship hopes ended in 2025 as rivals won the title, "
            "scoring more points in total.",
            "2025-03-01",
        )],
    )
    assert outcome["verdict"] == "STALE"
    assert 2025 in outcome["signals"]["newer_years_in_evidence"]
    assert outcome["signals"]["evidence_date_gap_days"] > 180


def test_possibly_stale_when_evidence_over_90_days_newer():
    outcome = evaluate_verdict(
        "The electric vehicle battery range is 400 miles in 2024.",
        date(2024, 1, 1),
        [_evidence(
            "Electric vehicle battery range reaches 400 miles in 2024 models.",
            "2024-05-01",
        )],
    )
    assert outcome["verdict"] == "POSSIBLY_STALE"
    assert outcome["signals"]["evidence_date_gap_days"] == 121


def test_unknown_when_no_evidence():
    outcome = evaluate_verdict("Some answer about anything.", date(2024, 1, 1), [])
    assert outcome["verdict"] == "UNKNOWN"
    assert outcome["signals"]["evidence_count"] == 0


def test_unknown_when_evidence_does_not_match_topic():
    outcome = evaluate_verdict(
        "Quantum computing qubits maintain coherence for microseconds.",
        None,
        [_evidence(
            "Baking sourdough bread starter recipe with flour water salt oven.",
            "2024-05-01",
        )],
    )
    assert outcome["verdict"] == "UNKNOWN"
    assert outcome["signals"]["keyword_overlap"] == 0.0


def test_possibly_stale_when_overlap_weak():
    outcome = evaluate_verdict(
        "Photosynthesis chlorophyll sunlight carbon dioxide oxygen glucose "
        "plants leaves energy growth.",
        None,
        [_evidence(
            "Photosynthesis research shows plants convert sunlight in new "
            "study about oceans tides waves.",
            None,
        )],
    )
    assert outcome["verdict"] == "POSSIBLY_STALE"
    assert 0.15 <= outcome["signals"]["keyword_overlap"] < 0.30


def test_possibly_stale_when_claims_unverified_and_overlap_partial():
    outcome = evaluate_verdict(
        "The solar panel output reached 850.5 watts in 2023 across twelve "
        "rooftop installations nationwide today.",
        None,
        [_evidence(
            "Solar panel output and watts ratings discussed in 2023 energy "
            "report for homes gardens rivers.",
            None,
        )],
    )
    assert outcome["verdict"] == "POSSIBLY_STALE"
    assert "850.5" in outcome["signals"]["claims_not_found_in_evidence"]


def test_date_extraction_full_month_and_year():
    found = extract_dates(
        "Launched on 5 January 2024, updated March 2025, founded in 1998."
    )
    by_kind = {item["kind"]: item["date"] for item in found}
    assert by_kind["full"] == "2024-01-05"
    assert by_kind["month"] == "2025-03-01"
    assert by_kind["year"] == "1998-01-01"


def test_number_claim_mismatch_flagged_in_signals():
    outcome = evaluate_verdict(
        "The factory produces 1,200 units daily, up 45% since 2023.",
        None,
        [_evidence(
            "Factory produces units daily since 2023, output steady at the "
            "plant site.",
            None,
        )],
    )
    not_found = outcome["signals"]["claims_not_found_in_evidence"]
    assert "1,200" in not_found
    assert "45%" in not_found
    assert "2023" in outcome["signals"]["claims_found_in_evidence"]


def test_answer_only_analysis_labels_kind_and_extracts_claims():
    analysis = answer_only_analysis(
        "Revenue was 1,500 units in March 2023, up 12%."
    )
    assert analysis["analysis_kind"] == "answer_only"
    assert analysis["evidence_count"] == 0
    assert analysis["date_claims"]
    assert "12%" in analysis["number_claims"]


def test_extract_claims_separates_dates_and_numbers():
    claims = extract_claims("In 2022 the price was $1,250, a rise of 8.5%.")
    assert any(d["date"] == "2022-01-01" for d in claims["date_claims"])
    assert "$1,250" in claims["number_claims"]
    assert "8.5%" in claims["number_claims"]
