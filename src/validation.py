"""Load CarbonLens CSV data and check one fund for a WACI comparison."""

from collections import Counter
import csv
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, ROUND_DOWN, localcontext
from fractions import Fraction
from io import StringIO
from pathlib import Path
import re
from typing import BinaryIO, Literal, TextIO

import pandas as pd


SCOPE = "Scope 1 + Scope 2"
WACI_UNIT = "tCO₂e / USD million revenue"
CARBON_INTENSITY = "carbon_intensity_tco2e_per_usd_million_revenue"
NUMBER_DIGITS = 128

TableKind = Literal["funds", "holdings", "benchmarks"]

REQUIRED_COLUMNS: dict[TableKind, tuple[str, ...]] = {
    "funds": (
        "fund_id", "fund_name", "esg_claim", "benchmark_id", "report_year",
        "claimed_reduction_pct",
    ),
    "holdings": (
        "fund_id", "company_id", "company_name", "sector", "weight_pct",
        CARBON_INTENSITY, "data_year", "emission_scope",
    ),
    "benchmarks": (
        "benchmark_id", "benchmark_name", "data_year", "emission_scope", "waci",
        "waci_unit",
    ),
}


@dataclass(frozen=True)
class Issue:
    code: str
    source_file: str
    message: str
    row_number: int | None = None
    row_id: str | None = None
    field: str | None = None
    value: object = None


class CSVFormatError(ValueError):
    """A CSV cannot be represented as a table with the required columns."""

    def __init__(self, issue: Issue):
        super().__init__(f"{issue.source_file}：{issue.message}")
        self.issue = issue
        self.issues = (issue,)


@dataclass(frozen=True)
class Fund:
    fund_id: str
    fund_name: str
    esg_claim: str
    benchmark_id: str
    report_year: int | None
    source_file: str
    row_number: int


@dataclass(frozen=True)
class Holding:
    fund_id: str
    company_id: str
    company_name: str
    sector: str
    weight_pct: Decimal | None
    carbon_intensity: Decimal | None
    data_year: int | None
    emission_scope: str
    source_file: str
    row_number: int


@dataclass(frozen=True)
class Benchmark:
    benchmark_id: str
    benchmark_name: str
    data_year: int
    emission_scope: str
    waci: Decimal | None
    waci_unit: str
    source_file: str
    row_number: int


@dataclass(frozen=True)
class ValidationResult:
    fund: Fund | None
    holdings: tuple[Holding, ...]
    benchmark: Benchmark | None
    issues: tuple[Issue, ...]
    coverage_pct: Decimal | None

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _column_issue(columns, kind: TableKind, source_file: str) -> Issue | None:
    duplicates = tuple(name for name, count in Counter(columns).items() if count > 1)
    if duplicates:
        return Issue(
            "duplicate_columns", source_file, "請移除重複欄名。",
            row_number=1, value=duplicates,
        )

    missing = tuple(name for name in REQUIRED_COLUMNS[kind] if name not in columns)
    if missing:
        return Issue(
            "missing_columns", source_file, f"請補上必要欄位 {', '.join(missing)}。",
            row_number=1, value=missing,
        )
    if any(not isinstance(name, str) or not name.strip() for name in columns):
        return Issue(
            "invalid_csv", source_file, "每個欄位都須有欄名。", row_number=1,
        )
    return None


def load_csv(source: str | Path | BinaryIO | TextIO, kind: TableKind) -> pd.DataFrame:
    """Read a UTF-8 CSV from a path or open stream, preserving source line numbers."""
    name = source if isinstance(source, (str, Path)) else getattr(source, "name", "")
    source_file = Path(name).name if isinstance(name, (str, Path)) and name else f"{kind}.csv"
    try:
        if isinstance(source, (str, Path)):
            with Path(source).open("rb") as stream:
                content = stream.read(10 * 1024 * 1024 + 1)
        else:
            content = source.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise CSVFormatError(Issue("file_too_large", source_file, "CSV 上限為 10 MB。"))
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.removeprefix("\ufeff")
    except (OSError, UnicodeError, ValueError) as error:
        raise CSVFormatError(Issue("invalid_csv", source_file, "請提供可讀取的 UTF-8 CSV。")) from error

    # Check widths and headings before constructing a DataFrame. Retain the starting
    # line of a logical record when a quoted cell spans several physical lines.
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    row_numbers: list[int] = []
    records: list[list[str]] = []
    line = 1
    try:
        columns = next(reader, [])
        issue = _column_issue(columns, kind, source_file)
        if issue:
            raise CSVFormatError(issue)

        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if not row:
                continue
            if len(row) != len(columns):
                raise CSVFormatError(Issue(
                    "invalid_csv", source_file, "這一列的欄數與標題不符。",
                    row_number=line, value=len(row),
                ))
            records.append(row)
            if len(records) > 10000:
                raise CSVFormatError(Issue("too_many_rows", source_file, "CSV 上限為 10,000 筆資料。"))
            row_numbers.append(line)
    except csv.Error as error:
        raise CSVFormatError(Issue(
            "invalid_csv", source_file, "CSV 格式錯誤，請檢查引號與分隔符號。",
            row_number=line,
        )) from error

    frame = pd.DataFrame.from_records(records, columns=columns)
    frame.attrs["source_file"] = source_file
    frame.attrs["row_numbers"] = dict(zip(frame.index, row_numbers))
    return frame


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_blank(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip()
    return pd.api.types.is_scalar(value) and bool(pd.isna(value))


def _decimal(value: object) -> Decimal | None:
    text = str(value).strip()
    if len(text) > NUMBER_DIGITS + 2:
        return None
    if isinstance(value, str):
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", text):
            return None
        if len(text.lstrip("+-").replace(".", "")) > NUMBER_DIGITS:
            return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite() or len(number.as_tuple().digits) > NUMBER_DIGITS:
        return None
    if abs(number.as_tuple().exponent) > NUMBER_DIGITS or number.adjusted() >= NUMBER_DIGITS:
        return None
    return number


def _year(value: object) -> int | None:
    text = str(value).strip()
    return int(text) if re.fullmatch(r"[1-9][0-9]{3}", text) else None


@dataclass(frozen=True)
class _Row:
    source_file: str
    number: int
    identifier: str
    values: dict

    def issue(self, code: str, field: str, message: str) -> Issue:
        return Issue(
            code, self.source_file, message, self.number, self.identifier,
            field, self.values[field],
        )


def _find_rows(frame: pd.DataFrame, key: str, identifier: str, source_file: str) -> list[_Row]:
    if not identifier:
        return []

    row_numbers = frame.attrs.get("row_numbers", {})
    if not frame.index.is_unique or len(frame) > len(row_numbers):
        row_numbers = {}
    return [
        _Row(source_file, row_numbers.get(index, line), identifier, row.to_dict())
        for line, (index, row) in enumerate(frame.iterrows(), start=2)
        if _text(row[key]) == identifier
    ]


def _require_text(row: _Row, field: str, issues: list[Issue]) -> str:
    value = _text(row.values[field])
    if not value:
        issues.append(row.issue("required_value", field, f"請填寫 {field}。"))
    return value


def _require_year(row: _Row, field: str, issues: list[Issue]) -> int | None:
    value = _year(row.values[field])
    if value is None:
        issues.append(row.issue("invalid_year", field, f"請在 {field} 填寫四位數西元年份。"))
    return value


def _validate_fund(
    frame: pd.DataFrame, source: str, fund_id: str, issues: list[Issue],
) -> Fund | None:
    rows = _find_rows(frame, "fund_id", fund_id, source)
    if not rows:
        issues.append(Issue(
            "fund_not_found", source, "找不到選擇的基金，請確認基金識別碼。",
            row_id=fund_id, field="fund_id", value=fund_id,
        ))
        return None
    if len(rows) > 1:
        issues.extend(
            row.issue("duplicate_fund", "fund_id", "同一基金識別碼應只有一筆。") for row in rows
        )
        return None

    row = rows[0]
    fund_name = _require_text(row, "fund_name", issues)
    _require_text(row, "esg_claim", issues)
    esg_claim = row.values["esg_claim"]
    benchmark_id = _require_text(row, "benchmark_id", issues)
    report_year = _require_year(row, "report_year", issues)
    return Fund(
        fund_id, fund_name, esg_claim if isinstance(esg_claim, str) else "",
        benchmark_id, report_year, source, row.number,
    )


def _validate_holding(
    row: _Row, fund_id: str, report_year: int | None, issues: list[Issue],
) -> Holding:
    company_id = _require_text(row, "company_id", issues)
    company_name = _require_text(row, "company_name", issues)
    sector = _require_text(row, "sector", issues)

    weight = _decimal(row.values["weight_pct"])
    if weight is None or not 0 <= weight <= 100:
        issues.append(row.issue("invalid_weight", "weight_pct", "請填寫介於 0 至 100 的有效持股權重。"))
        weight = None

    raw_intensity = row.values[CARBON_INTENSITY]
    intensity = _decimal(raw_intensity)
    if _is_blank(raw_intensity):
        issues.append(row.issue("missing_carbon_intensity", CARBON_INTENSITY, "請補上企業碳強度。"))
    elif intensity is None or intensity < 0:
        issues.append(row.issue(
            "invalid_carbon_intensity", CARBON_INTENSITY, "請填寫有限且非負的企業碳強度。",
        ))
        intensity = None

    data_year = _require_year(row, "data_year", issues)
    if data_year is not None and report_year is not None and data_year != report_year:
        issues.append(row.issue("year_mismatch", "data_year", f"持股年度須與報告年度 {report_year} 相同。"))

    scope = _text(row.values["emission_scope"])
    if scope != SCOPE:
        issues.append(row.issue("scope_mismatch", "emission_scope", f"持股排放範疇須為 {SCOPE}。"))

    return Holding(
        fund_id, company_id, company_name, sector, weight, intensity, data_year,
        scope, row.source_file, row.number,
    )


def _validate_holdings(
    frame: pd.DataFrame, source: str, fund_id: str, report_year: int | None,
    issues: list[Issue],
) -> tuple[tuple[Holding, ...], Decimal | None]:
    rows = _find_rows(frame, "fund_id", fund_id, source)
    if not rows:
        issues.append(Issue(
            "holdings_missing", source, "請補上此基金的持股資料。",
            row_id=fund_id, field="fund_id", value=fund_id,
        ))
        return (), None

    company_ids = Counter(_text(row.values["company_id"]) for row in rows)
    holdings = []
    for row in rows:
        company_id = _text(row.values["company_id"])
        company_row = _Row(row.source_file, row.number, company_id, row.values)
        if company_id and company_ids[company_id] > 1:
            issues.append(company_row.issue("duplicate_holding", "company_id", "同一基金不可有重複持股。"))
        holdings.append(_validate_holding(company_row, fund_id, report_year, issues))

    if not all(holding.company_id and holding.weight_pct is not None for holding in holdings):
        return tuple(holdings), None
    if any(count > 1 for count in company_ids.values()):
        return tuple(holdings), None

    # Exact fractions keep the weight test independent of Decimal context rounding.
    total_weight = sum(Fraction(holding.weight_pct) for holding in holdings)
    if total_weight != 100:
        with localcontext(Context(prec=NUMBER_DIGITS + len(str(len(holdings))) + 3)):
            total = Decimal(total_weight.numerator) / Decimal(total_weight.denominator)
        issues.append(Issue(
            "weight_total", source, "請將持股權重合計修正為 100%。",
            row_id=fund_id, field="weight_pct", value=total,
        ))
    if total_weight == 0:
        return tuple(holdings), None

    covered_weight = sum(
        Fraction(holding.weight_pct) for holding in holdings
        if holding.carbon_intensity is not None
    )
    coverage = covered_weight / total_weight * 100
    with localcontext(Context(prec=28, rounding=ROUND_DOWN)):
        coverage_pct = Decimal(coverage.numerator) / Decimal(coverage.denominator)
    return tuple(holdings), coverage_pct


def _validate_benchmark(
    frame: pd.DataFrame, source: str, fund: Fund, issues: list[Issue],
) -> Benchmark | None:
    if not fund.benchmark_id:
        return None
    rows = _find_rows(frame, "benchmark_id", fund.benchmark_id, source)
    if not rows:
        issues.append(Issue(
            "benchmark_not_found", source, "找不到指定基準，請補上對應基準資料。",
            row_id=fund.benchmark_id, field="benchmark_id", value=fund.benchmark_id,
        ))
        return None
    if fund.report_year is None:
        return None

    year_matches = [row for row in rows if _year(row.values["data_year"]) == fund.report_year]
    if not year_matches:
        for row in rows:
            if _require_year(row, "data_year", issues) is not None:
                issues.append(row.issue("year_mismatch", "data_year", f"請補上 {fund.report_year} 年的基準資料。"))
        return None

    matches = [row for row in year_matches if _text(row.values["emission_scope"]) == SCOPE]
    if not matches:
        issues.extend(
            row.issue("scope_mismatch", "emission_scope", f"基準排放範疇須為 {SCOPE}。")
            for row in year_matches
        )
        return None
    if len(matches) > 1:
        issues.extend(
            row.issue("duplicate_benchmark", "benchmark_id", "同一基準、年度與範疇應只有一筆。")
            for row in matches
        )
        return None

    row = matches[0]
    benchmark_name = _require_text(row, "benchmark_name", issues)
    waci = _decimal(row.values["waci"])
    if waci is None or waci <= 0:
        issues.append(row.issue("invalid_benchmark_waci", "waci", "基準 WACI 須為大於零的有限數值。"))
        waci = None

    unit = _text(row.values["waci_unit"])
    if unit != WACI_UNIT:
        issues.append(row.issue("unit_mismatch", "waci_unit", f"基準 WACI 單位須為 {WACI_UNIT}。"))

    return Benchmark(
        fund.benchmark_id, benchmark_name, fund.report_year, SCOPE, waci,
        unit, source, row.number,
    )


def validate_portfolio(
    funds: pd.DataFrame, holdings: pd.DataFrame, benchmarks: pd.DataFrame, fund_id: str,
) -> ValidationResult:
    """Validate the chosen fund, its holdings and its matching benchmark row."""
    tables = {"funds": funds, "holdings": holdings, "benchmarks": benchmarks}
    sources = {
        kind: frame.attrs.get("source_file", f"{kind}.csv") for kind, frame in tables.items()
    }
    issues = [
        issue for kind, frame in tables.items()
        if (issue := _column_issue(frame.columns, kind, sources[kind])) is not None
    ]
    if issues:
        return ValidationResult(None, (), None, tuple(issues), None)

    fund_id = fund_id.strip()
    fund = _validate_fund(funds, sources["funds"], fund_id, issues)
    selected_holdings, coverage = _validate_holdings(
        holdings, sources["holdings"], fund_id, fund.report_year if fund else None, issues,
    )
    benchmark = _validate_benchmark(benchmarks, sources["benchmarks"], fund, issues) if fund else None
    return ValidationResult(fund, selected_holdings, benchmark, tuple(issues), coverage)
