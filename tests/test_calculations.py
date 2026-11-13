from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from src.calculations import AnalysisStatus, analyze_portfolio
from src.validation import load_csv, validate_portfolio


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def synthetic_tables():
    return tuple(
        load_csv(DATA_DIR / f"{kind}.csv", kind)
        for kind in ("funds", "holdings", "benchmarks")
    )


@pytest.mark.parametrize(
    "fund_id, status, coverage, waci, reduction, contributions",
    [
        ("SYN001", AnalysisStatus.MEETS_CLAIM, 100, 50, 50, (24, 26)),
        ("SYN002", AnalysisStatus.CLAIM_MISMATCH, 100, 95, 5, (40, 55)),
        ("SYN003", AnalysisStatus.INSUFFICIENT_DATA, 60, None, None, ()),
    ],
)
def test_synthetic_funds(
    synthetic_tables, fund_id, status, coverage, waci, reduction, contributions
):
    validation = validate_portfolio(*synthetic_tables, fund_id)
    analysis = analyze_portfolio(validation, Decimal("30"))

    assert analysis.status is status
    assert analysis.coverage_pct == coverage
    assert analysis.fund_waci == waci
    assert analysis.benchmark_waci == (100 if waci is not None else None)
    assert analysis.actual_reduction_pct == reduction
    actual_contributions = tuple(
        row.weighted_carbon_intensity for row in analysis.contributions
    )
    assert actual_contributions == contributions


@pytest.mark.parametrize(
    "intensity, expected_reduction, status",
    [
        ("70", "30", AnalysisStatus.MEETS_CLAIM),
        ("70.001", "29.999", AnalysisStatus.CLAIM_MISMATCH),
        ("125", "-25", AnalysisStatus.CLAIM_MISMATCH),
        ("0", "100", AnalysisStatus.MEETS_CLAIM),
    ],
)
def test_comparison_boundaries(synthetic_tables, intensity, expected_reduction, status):
    funds, holdings, benchmarks = synthetic_tables
    carbon_column = "carbon_intensity_tco2e_per_usd_million_revenue"
    holdings.loc[holdings["fund_id"] == "SYN001", carbon_column] = intensity

    result = analyze_portfolio(
        validate_portfolio(funds, holdings, benchmarks, "SYN001"), Decimal("30")
    )

    assert result.status is status
    assert result.fund_waci == Decimal(intensity)
    assert result.actual_reduction_pct == Decimal(expected_reduction)


def test_exact_decision_when_reduction_rounds_to_target(synthetic_tables):
    funds, holdings, benchmarks = synthetic_tables
    carbon_column = "carbon_intensity_tco2e_per_usd_million_revenue"
    intensity = Decimal("70.00000000000000000000000000000000000001")
    holdings.loc[holdings["fund_id"] == "SYN001", carbon_column] = str(intensity)

    with localcontext() as context:
        context.prec = 6
        result = analyze_portfolio(
            validate_portfolio(funds, holdings, benchmarks, "SYN001"), Decimal("30")
        )

    assert result.status is AnalysisStatus.CLAIM_MISMATCH
    assert result.fund_waci == intensity
    assert result.actual_reduction_pct == Decimal("30")


def test_claim_confirmation_does_not_read_csv_answer(synthetic_tables):
    funds, holdings, benchmarks = synthetic_tables
    funds.loc[funds["fund_id"] == "SYN001", "claimed_reduction_pct"] = "100"
    validation = validate_portfolio(funds, holdings, benchmarks, "SYN001")

    pending = analyze_portfolio(validation, None)
    confirmed = analyze_portfolio(validation, Decimal("30"))

    assert pending.status is AnalysisStatus.CLAIM_CONFIRMATION_REQUIRED
    assert pending.fund_waci is None
    assert pending.actual_reduction_pct is None
    assert confirmed.status is AnalysisStatus.MEETS_CLAIM


def test_incomplete_data_precedes_unconfirmed_claim(synthetic_tables):
    result = analyze_portfolio(validate_portfolio(*synthetic_tables, "SYN003"), None)

    assert result.status is AnalysisStatus.INSUFFICIENT_DATA
    assert result.coverage_pct == 60


@pytest.mark.parametrize(
    "invalid_target",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01"), Decimal("100.01"), "30"],
)
def test_invalid_claim_target(synthetic_tables, invalid_target):
    validation = validate_portfolio(*synthetic_tables, "SYN001")

    with pytest.raises(ValueError, match="宣稱降低比例"):
        analyze_portfolio(validation, invalid_target)
