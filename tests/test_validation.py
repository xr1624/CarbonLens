from decimal import Decimal
from io import BytesIO, StringIO

import pandas as pd
import pytest

from src.validation import CSVFormatError, load_csv, validate_portfolio


INTENSITY = "carbon_intensity_tco2e_per_usd_million_revenue"
SCOPE = "Scope 1 + Scope 2"
UNIT = "tCO₂e / USD million revenue"


@pytest.fixture
def portfolio():
    """An independent, fully comparable portfolio."""
    funds = load_csv(
        StringIO(
            "fund_id,fund_name,esg_claim,benchmark_id,report_year,claimed_reduction_pct\n"
            "001,合成測試基金,本基金 2025 年的投資組合碳強度較甲市場基準低 20%。,"
            "BM01,2025,\n"
        ),
        "funds",
    )
    holdings = load_csv(
        StringIO(
            f"fund_id,company_id,company_name,sector,weight_pct,{INTENSITY},"
            "data_year,emission_scope\n"
            f"001,01,合成甲公司,能源,60,80,2025,{SCOPE}\n"
            f"001,02,合成乙公司,公用事業,40,0,2025,{SCOPE}\n"
        ),
        "holdings",
    )
    benchmarks = load_csv(
        StringIO(
            "benchmark_id,benchmark_name,data_year,emission_scope,waci,waci_unit\n"
            f"BM01,甲市場基準,2025,{SCOPE},100,{UNIT}\n"
        ),
        "benchmarks",
    )
    return funds, holdings, benchmarks


def test_accepts_utf8_bom_and_preserves_original_claim():
    content = (
        "fund_id,fund_name,esg_claim,benchmark_id,report_year,claimed_reduction_pct\n"
        '001,合成基金,"2025 年宣稱,\n碳強度降低 20%。",BM01,2025,\n'
    )
    frame = load_csv(BytesIO(content.encode("utf-8-sig")), "funds")

    assert frame.loc[0, "fund_id"] == "001"
    assert frame.loc[0, "esg_claim"] == "2025 年宣稱,\n碳強度降低 20%。"
    assert frame.loc[0, "claimed_reduction_pct"] == ""


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (
            "fund_id,fund_name,esg_claim,benchmark_id,report_year\n",
            "missing_columns",
        ),
        (
            "fund_id,fund_id,fund_name,esg_claim,benchmark_id,report_year,claimed_reduction_pct\n",
            "duplicate_columns",
        ),
        (
            "fund_id,fund_name,esg_claim,benchmark_id,report_year,claimed_reduction_pct\n"
            "001,合成基金,欄位少一個,BM01,2025\n",
            "invalid_csv",
        ),
        (
            "fund_id,fund_name,esg_claim,benchmark_id,report_year,claimed_reduction_pct\n"
            '001,合成基金,"未閉合的引號,BM01,2025,20\n',
            "invalid_csv",
        ),
    ],
    ids=["missing-header", "duplicate-header", "short-record", "unclosed-quote"],
)
def test_rejects_malformed_csv(content, code):
    with pytest.raises(CSVFormatError) as error:
        load_csv(StringIO(content), "funds")

    assert error.value.issue.code == code
    assert error.value.issue.source_file == "funds.csv"


def test_rejects_invalid_utf8():
    with pytest.raises(CSVFormatError) as error:
        load_csv(BytesIO(b"\xff"), "funds")

    assert error.value.issue.code == "invalid_csv"


def test_source_file_and_physical_row_are_retained(portfolio, tmp_path):
    funds, _, benchmarks = portfolio
    source = tmp_path / "uploaded-holdings.csv"
    source.write_text(
        f"fund_id,company_id,company_name,sector,weight_pct,{INTENSITY},"
        "data_year,emission_scope\n"
        f'001,01,"合成\n甲公司",能源,60,80,2025,{SCOPE}\n'
        f"001,02,合成乙公司,公用事業,未知,0,2025,{SCOPE}\n",
        encoding="utf-8",
    )
    result = validate_portfolio(funds, load_csv(source, "holdings"), benchmarks, "001")

    issue = next(issue for issue in result.issues if issue.code == "invalid_weight")
    assert (issue.source_file, issue.row_number, issue.row_id) == (
        source.name,
        4,
        "02",
    )
    assert (issue.field, issue.value) == ("weight_pct", "未知")


def test_valid_portfolio_keeps_zero_carbon_and_excludes_answer_key(portfolio):
    funds, holdings, benchmarks = portfolio
    funds.loc[0, "claimed_reduction_pct"] = "99"
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert result.is_valid
    assert result.issues == ()
    assert result.coverage_pct == Decimal("100")
    assert result.holdings[1].carbon_intensity == Decimal("0")
    assert result.holdings[1].company_id == "02"
    assert not hasattr(result.fund, "claimed_reduction_pct")


def test_weight_total_is_exact_and_does_not_erase_diagnostic_coverage(portfolio):
    funds, holdings, benchmarks = portfolio
    holdings.loc[1, "weight_pct"] = "39.99"
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert {issue.code for issue in result.issues} == {"weight_total"}
    assert result.coverage_pct == Decimal("100")


def test_very_small_weight_does_not_round_into_a_valid_total(portfolio):
    funds, holdings, benchmarks = portfolio
    holdings["weight_pct"] = ["100", "0.00000000000000000000000000001"]
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid


@pytest.mark.parametrize("weight", ["-1", "101", "NaN", "Infinity", "文字", ""])
def test_invalid_weight_has_no_coverage(portfolio, weight):
    funds, holdings, benchmarks = portfolio
    holdings.loc[1, "weight_pct"] = weight
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == "invalid_weight" for issue in result.issues)
    assert result.coverage_pct is None


def test_duplicate_holding_has_no_coverage(portfolio):
    funds, holdings, benchmarks = portfolio
    holdings.loc[1, "company_id"] = "01"
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == "duplicate_holding" for issue in result.issues)
    assert result.coverage_pct is None


def test_zero_total_has_no_coverage(portfolio):
    funds, holdings, benchmarks = portfolio
    holdings.loc[:, "weight_pct"] = "0"
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == "weight_total" for issue in result.issues)
    assert result.coverage_pct is None


def test_empty_holdings_have_no_coverage(portfolio):
    funds, holdings, benchmarks = portfolio
    result = validate_portfolio(funds, holdings.iloc[0:0], benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == "holdings_missing" for issue in result.issues)
    assert result.coverage_pct is None


def test_duplicate_fund_identifier_is_ambiguous(portfolio):
    funds, holdings, benchmarks = portfolio
    duplicate = pd.concat([funds, funds], ignore_index=True)
    result = validate_portfolio(duplicate, holdings, benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == "duplicate_fund" for issue in result.issues)


@pytest.mark.parametrize(
    ("intensity", "code"),
    [
        ("", "missing_carbon_intensity"),
        ("NaN", "invalid_carbon_intensity"),
        ("Infinity", "invalid_carbon_intensity"),
        ("-0.01", "invalid_carbon_intensity"),
    ],
    ids=["missing", "nan", "infinite", "negative"],
)
def test_unavailable_intensity_reduces_weighted_coverage(portfolio, intensity, code):
    funds, holdings, benchmarks = portfolio
    holdings.loc[1, INTENSITY] = intensity
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert {issue.code for issue in result.issues} == {code}
    assert result.coverage_pct == Decimal("60")


def test_zero_weight_still_requires_reported_intensity(portfolio):
    funds, holdings, benchmarks = portfolio
    holdings["weight_pct"] = ["100", "0"]
    holdings.loc[1, INTENSITY] = ""
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == "missing_carbon_intensity" for issue in result.issues)
    assert result.coverage_pct == Decimal("100")


@pytest.mark.parametrize(
    ("dataset", "column", "value", "code"),
    [
        ("holdings", "data_year", "2024", "year_mismatch"),
        ("holdings", "emission_scope", "Scope 1 + Scope 2 + Scope 3", "scope_mismatch"),
        ("benchmarks", "data_year", "2024", "year_mismatch"),
        ("benchmarks", "emission_scope", "Scope 1", "scope_mismatch"),
        ("benchmarks", "benchmark_id", "BM02", "benchmark_not_found"),
        ("benchmarks", "waci_unit", "tCO₂e / TWD million revenue", "unit_mismatch"),
        ("benchmarks", "waci", "0", "invalid_benchmark_waci"),
        ("benchmarks", "waci", "-0.01", "invalid_benchmark_waci"),
        ("benchmarks", "waci", "Infinity", "invalid_benchmark_waci"),
    ],
    ids=[
        "holding-year",
        "holding-scope",
        "benchmark-year",
        "benchmark-scope",
        "unknown-benchmark",
        "benchmark-unit",
        "benchmark-zero",
        "benchmark-negative",
        "benchmark-infinite",
    ],
)
def test_comparability_errors_do_not_erase_carbon_coverage(
    portfolio, dataset, column, value, code
):
    funds, holdings, benchmarks = portfolio
    tables = {"holdings": holdings, "benchmarks": benchmarks}
    tables[dataset].loc[0, column] = value
    result = validate_portfolio(funds, holdings, benchmarks, "001")

    assert not result.is_valid
    assert any(issue.code == code for issue in result.issues)
    assert result.coverage_pct == Decimal("100")


def test_benchmark_selection_uses_year_and_scope(portfolio):
    funds, holdings, benchmarks = portfolio
    old_benchmark = benchmarks.assign(data_year="2024", waci="120")
    other_scope = benchmarks.assign(emission_scope="Scope 1", waci="80")
    combined = pd.concat([old_benchmark, other_scope, benchmarks], ignore_index=True)
    result = validate_portfolio(funds, holdings, combined, "001")

    assert result.is_valid
    assert result.benchmark.waci == Decimal("100")
    assert result.benchmark.data_year == 2025
    assert result.benchmark.emission_scope == SCOPE


def test_rejects_duplicate_benchmark_with_same_year_and_scope(portfolio):
    funds, holdings, benchmarks = portfolio
    duplicate = pd.concat([benchmarks, benchmarks], ignore_index=True)
    result = validate_portfolio(funds, holdings, duplicate, "001")

    assert not result.is_valid
    assert any(issue.code == "duplicate_benchmark" for issue in result.issues)
