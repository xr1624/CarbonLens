"""A single state-driven agent dispatching extraction, validation and calculation tools."""

from dataclasses import replace
from uuid import uuid4

from src.calculations import analyze_portfolio
from src.cases import Case, Event, Review, now, restore_tables
from src.claim_extraction import (
    Claim, Extraction, ExtractionError, check_claim, extract_claim, mock_claim,
)
from src.settings import Settings
from src.storage import QuotaError, Store
from src.validation import Issue, validate_portfolio


def run_agent(
    case: Case, settings: Settings, *, owner: str | None = None,
    store: Store | None = None, corrected: Claim | None = None, progress=None,
) -> Case:
    events = []

    def event(tool, detail, status="完成"):
        item = Event(tool, status, detail)
        events.append(item)
        if progress:
            progress(item)

    extraction = None
    try:
        event("read_case", "讀取基金、持股與基準輸入快照。")
        if corrected is not None:
            extraction = Extraction(corrected, "人工覆核")
            event("review_claim", "使用人工修正的擷取欄位。")
        elif case.mode == "Real":
            if not owner or owner not in settings.users() or store is None:
                raise ExtractionError("請登入授權帳號後啟動真實 AI 分析。")
            if not settings.api_key or not settings.model:
                raise ExtractionError("管理者需設定 OPENAI_API_KEY 與 OPENAI_MODEL。")
            if not case.claim.strip() or len(case.claim) > settings.max_claim_chars:
                raise ExtractionError(f"宣稱須為 1 至 {settings.max_claim_chars} 字元。")
            store.reserve_call(owner, case.run_id, settings.user_daily_calls, settings.global_daily_calls)
            event("extract_claim", "呼叫 OpenAI 結構化宣稱擷取。", "執行中")
            extraction = extract_claim(case.claim, settings)
            event("extract_claim", "模型已回傳結構化欄位與原文證據。")
            event("analyze_claim", f"執行模型請求的工具，call_id={extraction.tool_call_id}", "執行中")
        elif case.mode == "Mock Mode":
            extraction = mock_claim(case.claim)
            event("mock_claim", "執行明確標示的示範擷取。")
        else:
            raise ExtractionError("此案件模式不支援 Agent 重跑。")

        tables = restore_tables(case.snapshot)
        validation = validate_portfolio(
            tables["funds"], tables["holdings"], tables["benchmarks"], case.fund_id,
        )
        event("validate_portfolio", f"資料驗證完成，共 {len(validation.issues)} 項問題。")
        target, problems = check_claim(extraction.claim, case.claim)
        claim = extraction.claim
        mismatch = []
        benchmark = validation.benchmark
        if benchmark and claim.benchmark and claim.benchmark not in (
            benchmark.benchmark_id, benchmark.benchmark_name,
        ):
            mismatch.append(Issue(
                "claim_benchmark_mismatch", "宣稱原文", "宣稱比較基準與選用基準不一致，請補件或修正。",
                field="benchmark", value=claim.benchmark,
            ))
        if validation.fund and claim.year and claim.year != validation.fund.report_year:
            mismatch.append(Issue(
                "claim_year_mismatch", "宣稱原文", "宣稱年度與基金報告年度不一致，請補件或修正。",
                field="year", value=claim.year,
            ))
        validation = replace(validation, issues=validation.issues + tuple(mismatch))
        if not validation.is_valid:
            event("request_documents", "列出資料或比較基準問題，等待補件。")
        elif problems:
            event("request_confirmation", "擷取欄位需要人工確認。")
        else:
            event("calculate_waci", "以 Python 精確計算 WACI、降低比例及規則判定。")
        result = analyze_portfolio(validation, None if problems else target)
        event("assemble_evidence", "彙整原文、來源列、公式與運算結果。")
        return replace(
            case, extraction=extraction, result=result, events=tuple(events),
            claim_issues=tuple(problems), error="", review_status="待人工覆核",
        )
    except (ExtractionError, QuotaError) as error:
        event("agent", str(error), "失敗")
        return replace(
            case, result=None, extraction=extraction, events=tuple(events),
            error=str(error), review_status="待處理",
        )


def review_case(case: Case, action: str, comment: str, settings: Settings,
                corrected: Claim | None = None) -> Case:
    if action not in ("確認", "修正", "退回") or not comment.strip():
        raise ValueError("請選擇覆核動作並填寫意見。")
    if action == "確認" and case.result is None:
        raise ValueError("執行失敗的案件須先重新分析。")
    original = case.extraction.claim.model_dump() if case.extraction else {
        "reduction_pct": str(case.result.claimed_reduction_pct) if case.result else None
    }
    new_values = corrected.model_dump() if corrected else original
    review = Review(action, comment.strip(), original, new_values, case.run_id)
    updated = replace(case, reviews=case.reviews + (review,))
    if action == "修正":
        if corrected is None:
            raise ValueError("請填寫修正欄位。")
        _, problems = check_claim(corrected, case.claim)
        if problems:
            raise ValueError("；".join(problems))
        updated = replace(updated, run_id=uuid4().hex)
        return run_agent(updated, settings, corrected=corrected)
    return replace(updated, review_status="已確認" if action == "確認" else "已退回")
