"""CarbonLens Streamlit interface for portfolio carbon claim analysis."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.calculations import AnalysisResult, AnalysisStatus, analyze_portfolio
from src.charts import contribution_chart, reduction_chart, sector_chart, waci_chart
from src.validation import CSVFormatError, SCOPE, WACI_UNIT, load_csv, validate_portfolio
from src.cases import Case, snapshot_tables
from src.ui_workflow import configure, controls, execute, save_case


ROOT = Path(__file__).resolve().parent
LOGO = ROOT / "assets" / "carbonlens.png"
TABLE_KINDS = ("funds", "holdings", "benchmarks")
SYNTHETIC = "Synthetic Data"
UPLOADED = "上傳 CSV"

STATUS_TONES = {
    AnalysisStatus.MEETS_CLAIM: "success",
    AnalysisStatus.CLAIM_MISMATCH: "warning",
    AnalysisStatus.INSUFFICIENT_DATA: "warning",
    AnalysisStatus.CLAIM_CONFIRMATION_REQUIRED: "info",
}


def show_header():
    st.html((ROOT / "assets" / "theme.css").read_text(encoding="utf-8"))
    st.logo(str(LOGO), size="large")
    st.html("""
        <header class="carbon-hero">
            <div class="carbon-hero-content">
                <p class="carbon-brand">CarbonLens <span>See Beyond the Green.</span></p>
                <h1>基金低碳宣稱驗證</h1>
                <p class="carbon-description">以持股碳強度與市場基準，核對永續基金的低碳宣稱。</p>
            </div>
            <div class="carbon-hero-art" aria-hidden="true"></div>
        </header>
    """)


def show_dashboard(cases):
    st.header("分析總覽")
    st.caption("統計目前瀏覽器工作階段建立的案件。")
    analyzed = {case.fund_id for case in cases
                if case.result and case.result.status != AnalysisStatus.CLAIM_CONFIRMATION_REQUIRED}
    metrics = (
        ("已分析基金", len(analyzed)),
        ("符合宣稱", sum(bool(case.result and case.result.status == AnalysisStatus.MEETS_CLAIM) for case in cases)),
        ("宣稱不一致", sum(bool(case.result and case.result.status == AnalysisStatus.CLAIM_MISMATCH) for case in cases)),
        ("資料不足", sum(bool(case.result and case.result.status == AnalysisStatus.INSUFFICIENT_DATA) for case in cases)),
        ("待人工覆核", sum(case.review_status == "待人工覆核" for case in cases)),
    )
    for column, (label, value) in zip(st.columns(len(metrics)), metrics):
        column.metric(label, value, border=True)

    st.subheader("案件清單")
    if not cases:
        st.info("目前沒有案件。請前往「建立案件」選擇示範基金或上傳 CSV。")
        return

    st.dataframe(pd.DataFrame([
        {
            "案件 ID": case.case_id,
            "基金": case.fund_name,
            "分析判定": case.status,
            "覆核狀態": case.review_status,
            "基金 WACI": format_number(case.result.fund_waci if case.result else None),
            "資料覆蓋率": format_number(case.result.coverage_pct if case.result else None, "%"),
            "資料來源": case.source,
            "建立時間（台北）": case.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for case in reversed(cases)
    ]), hide_index=True)


def upload_tables():
    st.caption(f"請使用 UTF-8 CSV。持股與基準的碳強度單位為 {WACI_UNIT}。")
    files = {}
    for column, kind in zip(st.columns(3), TABLE_KINDS):
        files[kind] = column.file_uploader(
            f"{kind}.csv", type="csv", max_upload_size=10, key=f"file_{kind}"
        )
        column.download_button(
            "下載欄位範本",
            data=(ROOT / "data" / f"{kind}.csv").read_bytes().splitlines(keepends=True)[0],
            file_name=f"CarbonLens_{kind}_template.csv",
            mime="text/csv",
            key=f"template_{kind}",
            on_click="ignore",
        )

    tables = {}
    for kind, file in files.items():
        if file is not None:
            try:
                tables[kind] = load_csv(file, kind)
            except CSVFormatError as error:
                row = f"第 {error.issue.row_number} 列。 " if error.issue.row_number else ""
                st.error(f"{error.issue.source_file}。 {row}{error.issue.message}")
            finally:
                file.seek(0)
    if len(tables) != len(TABLE_KINDS):
        st.info("請提供三份格式正確的 CSV，以選擇基金並建立案件。")
        return None

    fingerprints = [sha256(file.getvalue()).hexdigest() for file in files.values()]
    return tables, "".join(fingerprints)


def parse_target(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    if len(raw) > 128 or not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", raw):
        raise ValueError("宣稱比例請輸入 0 到 100 之間的數字，例如 30 或 30.5。")
    try:
        target = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError("無法讀取宣稱比例。") from error
    if not 0 <= target <= 100:
        raise ValueError("宣稱比例須介於 0 到 100。")
    return target


def show_case_form():
    st.header("建立案件")
    source = st.radio("資料來源", (SYNTHETIC, UPLOADED), horizontal=True)
    if source == SYNTHETIC:
        st.caption("內建示範為合成資料，供測試與教學使用。")
        tables = {kind: load_csv(ROOT / "data" / f"{kind}.csv", kind) for kind in TABLE_KINDS}
        fingerprint = "synthetic"
    else:
        if st.session_state.settings.public and not st.session_state.get("owner"):
            st.info("上傳自有資料請先登入授權帳號。")
            return
        uploaded = upload_tables()
        if uploaded is None:
            return
        tables, fingerprint = uploaded

    funds = tables["funds"]
    fund_names = {
        row.fund_id.strip(): row.fund_name.strip()
        for row in funds.itertuples(index=False)
        if row.fund_id.strip()
    }
    if not fund_names:
        st.error("基金 CSV 至少須包含一筆有 fund_id 的基金資料。")
        return
    fund_id = st.selectbox(
        "基金", list(fund_names),
        format_func=lambda key: f"{key} · {fund_names[key]}",
        key=f"fund_{fingerprint}",
    )
    source_fund = funds.loc[funds["fund_id"].str.strip() == fund_id].iloc[0]
    benchmark_id = source_fund["benchmark_id"].strip()
    report_year = source_fund["report_year"].strip()
    benchmarks = tables["benchmarks"]
    choices = list(dict.fromkeys(benchmarks["benchmark_id"].str.strip()))
    if benchmark_id not in choices:
        choices.insert(0, benchmark_id)
    benchmark_id = st.selectbox("市場基準指數", choices, index=choices.index(benchmark_id))
    mode = st.radio("分析模式", ("人工輸入", "Mock Mode", "Real"), horizontal=True)
    if mode == "Mock Mode":
        st.caption("Mock Mode 使用示範規則，不會呼叫模型。")
    elif mode == "Real":
        st.caption("Real 會將宣稱原文傳送至 OpenAI 擷取欄位，WACI 由 Python 計算。需要授權登入。")
    benchmark_rows = benchmarks.loc[
        (benchmarks["benchmark_id"].str.strip() == benchmark_id)
        & (benchmarks["data_year"].str.strip() == report_year)
        & (benchmarks["emission_scope"].str.strip() == SCOPE)
    ]
    benchmark_name = (
        benchmark_rows.iloc[0]["benchmark_name"] if len(benchmark_rows) == 1 else ""
    )
    benchmark_label = f"{benchmark_name}（{benchmark_id}）" if benchmark_name else benchmark_id
    form_key = sha256(f"{fingerprint}:{fund_id}".encode()).hexdigest()

    with st.form(f"case_{form_key}"):
        st.text(f"CSV 指定基準 {benchmark_label or '—'}　·　報告年度 {report_year or '—'}")
        claim = st.text_area("ESG 宣稱原文", value=source_fund["esg_claim"], height=105)
        raw_target = st.text_input(
            "宣稱降低比例 (%)", placeholder="例如 30",
            help="從原文核對後填入。宣稱模糊或缺少明確門檻時，請留空。",
        )
        confirmed = st.checkbox("我已核對宣稱比例、比較基準及適用年度。")
        submitted = st.form_submit_button("建立案件並分析", type="primary")

    if not submitted:
        latest_id = st.session_state.get("created_case_id")
        latest = next((case for case in st.session_state.cases if case.case_id == latest_id), None)
        if latest is not None:
            show_analysis(latest)
        return
    try:
        target = parse_target(raw_target) if mode == "人工輸入" else None
        if target is not None and not (confirmed and claim.strip()):
            raise ValueError("請先核對原文、比較基準與年度。若宣稱待確認，請將比例留空。")
    except ValueError as error:
        st.error(str(error))
        return

    # Keep the loaded frame's index and provenance when updating the case text.
    funds = funds.copy()
    funds.loc[funds["fund_id"].str.strip() == fund_id, "esg_claim"] = claim
    funds.loc[funds["fund_id"].str.strip() == fund_id, "benchmark_id"] = benchmark_id
    tables = {**tables, "funds": funds}
    with st.spinner("正在驗證資料與計算 WACI…"):
        validation = validate_portfolio(funds, tables["holdings"], tables["benchmarks"], fund_id)
        result = analyze_portfolio(validation, target)
    case = Case(
        f"CL-{uuid4().hex[:10].upper()}",
        fund_id,
        fund_names[fund_id] or fund_id,
        source,
        claim,
        datetime.now(ZoneInfo("Asia/Taipei")),
        result,
        snapshot=snapshot_tables(tables), mode=mode,
    )
    if mode != "人工輸入":
        case = execute(case)
    case = save_case(case)
    st.session_state.created_case_id = case.case_id
    st.success(f"已建立案件 {case.case_id}。")
    show_analysis(case)


def format_number(value: Decimal | None, suffix: str = "") -> str:
    if value is None:
        return "—"
    if value and (value.adjusted() > 9 or value.adjusted() < -3):
        return f"{value:.3E}{suffix}"
    return f"{value:,.4f}".rstrip("0").rstrip(".") + suffix


def show_analysis(case: Case):
    result = case.result
    if result is None:
        st.error(case.error or "尚未完成分析。")
        controls(case)
        return
    validation = result.validation
    st.subheader("分析結果")
    st.text(f"{case.fund_name} · {case.case_id}")
    st.caption(f"{case.source}　·　{case.mode}　·　{SCOPE}")
    tone = STATUS_TONES[result.status]
    getattr(st, tone)(result.status.value)

    benchmark = validation.benchmark
    metrics = (
        ("基金 WACI", format_number(result.fund_waci)),
        ("基準 WACI", format_number(benchmark.waci if benchmark else None)),
        ("宣稱降低", format_number(result.claimed_reduction_pct, "%")),
        ("實際降低", format_number(result.actual_reduction_pct, "%")),
        ("資料覆蓋率", format_number(result.coverage_pct, "%")),
    )
    for column, (label, value) in zip(st.columns(len(metrics)), metrics):
        column.metric(label, value, border=True)
    st.caption(f"WACI 單位 {WACI_UNIT}。顯示值可能經過捨入，判定採精確值。")

    if result.status == AnalysisStatus.CLAIM_MISMATCH:
        st.write("基金相對基準的實際降低比例低於宣稱門檻，需由分析師覆核。")
    elif result.status == AnalysisStatus.MEETS_CLAIM:
        st.write("基金相對基準的實際降低比例達到宣稱門檻。")
    elif result.status == AnalysisStatus.CLAIM_CONFIRMATION_REQUIRED:
        st.write("請依原文核對降低比例、比較基準與適用年度後建立分析。")
    if validation.issues:
        st.markdown("**資料問題與補件清單**")
        for issue in validation.issues:
            location = issue.source_file
            if issue.row_number is not None:
                location += f" 第 {issue.row_number} 列"
            st.text(f"{location} · {issue.message}")

    show_charts(result)
    show_evidence(case)
    controls(case)


def show_charts(result: AnalysisResult):
    st.subheader("碳強度與投資組合")
    first = st.columns(2)
    second = st.columns(2)
    panels = (
        (first[0], "基金與基準 WACI", waci_chart, "需有可比較的基金與基準 WACI。"),
        (first[1], "宣稱與實際降低比例", reduction_chart, "需有已確認宣稱與實際降低比例。"),
        (second[0], "持股產業分布", sector_chart, "需有可用的持股權重及產業資料。"),
        (second[1], "企業碳強度貢獻", contribution_chart, "通過驗證並計算 WACI 後顯示。"),
    )
    for column, title, make_chart, empty in panels:
        with column.container(border=True):
            st.markdown(f"**{title}**")
            figure = make_chart(result)
            if figure is None:
                st.caption(empty)
            else:
                if make_chart is contribution_chart and len(result.contributions) > 15:
                    st.caption("顯示碳強度貢獻最高的 15 筆。")
                st.plotly_chart(figure, theme=None, config={"displaylogo": False})


def show_evidence(case: Case):
    validation = case.result.validation
    with st.expander("證據來源與計算公式"):
        st.markdown("**基金原始宣稱**")
        st.text(case.claim or "未提供原始宣稱。")
        if validation.fund is not None:
            fund = validation.fund
            st.text(f"{fund.source_file} 第 {fund.row_number} 列 · 報告年度 {fund.report_year or '—'}")

        if validation.benchmark is not None:
            benchmark = validation.benchmark
            st.markdown("**市場基準**")
            st.text(f"{benchmark.benchmark_name}（{benchmark.benchmark_id}）")
            st.text(f"{benchmark.source_file} 第 {benchmark.row_number} 列 · "
                    f"{benchmark.data_year} · {benchmark.emission_scope} · {benchmark.waci_unit}")

        st.markdown("**持股明細**")
        contributions = {
            (row.holding.source_file, row.holding.row_number): row.weighted_carbon_intensity
            for row in case.result.contributions
        }
        if validation.holdings:
            st.dataframe(pd.DataFrame([
                {
                    "企業": row.company_name,
                    "持股代碼": row.company_id,
                    "產業": row.sector,
                    "權重 (%)": format_number(row.weight_pct),
                    "企業碳強度": format_number(row.carbon_intensity),
                    "加權貢獻": format_number(contributions.get((row.source_file, row.row_number))),
                    "年度": str(row.data_year or "—"),
                    "排放範疇": row.emission_scope,
                    "資料來源": f"{row.source_file} 第 {row.row_number} 列",
                }
                for row in validation.holdings
            ]), hide_index=True)
        st.code(
            "基金 WACI = Σ[(持股權重 ÷ 100) × 企業碳強度]\n"
            "實際降低 (%) = (基準 WACI − 基金 WACI) ÷ 基準 WACI × 100",
            language=None,
        )


def show_case_history(cases):
    st.header("案件分析")
    if not cases:
        st.info("請先前往「建立案件」執行分析。")
        return
    by_id = {case.case_id: case for case in reversed(cases)}
    chosen = st.selectbox(
        "選擇案件", list(by_id),
        format_func=lambda key: f"{key} · {by_id[key].fund_name}",
    )
    show_analysis(by_id[chosen])


def main():
    st.set_page_config(page_title="CarbonLens", page_icon=str(LOGO), layout="wide")
    configure()
    if "cases" not in st.session_state:
        st.session_state.cases = []
    show_header()
    page = st.radio(
        "導覽", ("分析總覽", "建立案件", "案件分析"),
        horizontal=True, label_visibility="collapsed", key="view",
    )
    if page == "分析總覽":
        show_dashboard(st.session_state.cases)
    elif page == "建立案件":
        show_case_form()
    else:
        show_case_history(st.session_state.cases)
    st.divider()
    st.caption("CarbonLens · 結果供低碳宣稱與漂綠風險初步篩選。訪客案件限目前工作階段；雲端展示版 SQLite 可能在重啟後清除，請下載報告保存。")


if __name__ == "__main__":
    main()
