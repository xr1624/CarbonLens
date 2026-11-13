"""Deterministic WACI and claim comparison for a validated portfolio."""

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN
from enum import Enum
from fractions import Fraction

from src.validation import Holding, ValidationResult


class AnalysisStatus(str, Enum):
    MEETS_CLAIM = "符合宣稱"
    CLAIM_MISMATCH = "宣稱不一致，需人工覆核"
    INSUFFICIENT_DATA = "資料不足，無法判定"
    CLAIM_CONFIRMATION_REQUIRED = "等待宣稱確認"


@dataclass(frozen=True)
class HoldingContribution:
    holding: Holding
    weighted_carbon_intensity: Decimal


@dataclass(frozen=True)
class AnalysisResult:
    status: AnalysisStatus
    validation: ValidationResult
    claimed_reduction_pct: Decimal | None
    fund_waci: Decimal | None = None
    benchmark_waci: Decimal | None = None
    actual_reduction_pct: Decimal | None = None
    contributions: tuple[HoldingContribution, ...] = ()

    @property
    def coverage_pct(self) -> Decimal | None:
        return self.validation.coverage_pct


def _exact_decimal(value: Fraction) -> Decimal:
    """Convert a terminating fraction derived from decimal inputs."""
    # Bit lengths bound the integer digits and decimal scale of this result.
    precision = value.numerator.bit_length() + value.denominator.bit_length()
    return Context(prec=precision).divide(
        Decimal(value.numerator), Decimal(value.denominator)
    )


def analyze_portfolio(
    validation: ValidationResult, claimed_reduction_pct: Decimal | None
) -> AnalysisResult:
    """Compare validated data with a target already confirmed against its source.

    Pass None if the claim still needs confirmation. CSV answer keys are
    reserved for tests and are never used to obtain a target here.
    """
    if claimed_reduction_pct is not None and (
        not isinstance(claimed_reduction_pct, Decimal)
        or not claimed_reduction_pct.is_finite()
        or not Decimal(0) <= claimed_reduction_pct <= Decimal(100)
    ):
        raise ValueError("宣稱降低比例須為介於 0 至 100 的有限 Decimal 百分數。")

    if not validation.is_valid:
        return AnalysisResult(
            AnalysisStatus.INSUFFICIENT_DATA, validation, claimed_reduction_pct
        )

    if claimed_reduction_pct is None:
        return AnalysisResult(
            AnalysisStatus.CLAIM_CONFIRMATION_REQUIRED, validation, None
        )

    benchmark = validation.benchmark
    if benchmark is None or benchmark.waci is None:
        raise ValueError("通過驗證的案件須有基準 WACI。")

    fund_waci = Fraction()
    contributions = []
    for holding in validation.holdings:
        if holding.weight_pct is None or holding.carbon_intensity is None:
            raise ValueError("通過驗證的持股須有權重與碳強度。")
        weighted = Fraction(holding.weight_pct) * Fraction(holding.carbon_intensity) / 100
        fund_waci += weighted
        contributions.append(HoldingContribution(holding, _exact_decimal(weighted)))

    benchmark_waci = Fraction(benchmark.waci)
    actual_reduction = (benchmark_waci - fund_waci) / benchmark_waci * 100
    status = (
        AnalysisStatus.MEETS_CLAIM
        if actual_reduction >= claimed_reduction_pct
        else AnalysisStatus.CLAIM_MISMATCH
    )
    reduction_pct = Context(prec=28, rounding=ROUND_HALF_EVEN).divide(
        Decimal(actual_reduction.numerator), Decimal(actual_reduction.denominator)
    )
    return AnalysisResult(
        status=status,
        validation=validation,
        claimed_reduction_pct=claimed_reduction_pct,
        fund_waci=_exact_decimal(fund_waci),
        benchmark_waci=benchmark.waci,
        actual_reduction_pct=reduction_pct,
        contributions=tuple(contributions),
    )
