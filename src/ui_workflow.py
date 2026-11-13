"""Authenticated workflow controls shared by the Streamlit pages."""
from dataclasses import asdict, replace
from uuid import uuid4
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from src.access import authenticate
from src.agent import run_agent, review_case
from src.cases import encode_case
from src.claim_extraction import Claim
from src.settings import load_settings
from src.storage import Store, default_database_url


@st.cache_resource
def get_store(url):
    return Store(url)


def configure():
    try:
        try:
            secrets = st.secrets.to_dict()
        except FileNotFoundError:
            secrets = {}
        settings = load_settings(secrets)
    except (ValueError, TypeError):
        st.error("網站設定格式有誤，請管理者檢查 Secrets。")
        st.stop()
    st.session_state.settings = settings
    users = settings.users()
    owner = st.session_state.get("owner")
    if owner and st.session_state.get("login_digest") != users.get(owner):
        st.session_state.clear()
        st.rerun()
    if users and not owner:
        with st.sidebar.form("login"):
            username = st.text_input("授權帳號")
            code = st.text_input("存取碼", type="password")
            if st.form_submit_button("登入"):
                if authenticate(username, code, users):
                    st.session_state.clear()
                    st.session_state.owner = username
                    st.session_state.login_digest = users[username]
                    st.rerun()
                st.error("帳號或存取碼錯誤。")
    if owner:
        st.sidebar.caption(f"已登入：{owner}")
        if st.sidebar.button("登出並清除畫面資料"):
            st.session_state.clear()
            st.rerun()
        try:
            st.session_state.store = get_store(settings.database_url or default_database_url())
            st.session_state.cases = st.session_state.store.list_cases(owner)
        except (SQLAlchemyError, ValueError):
            st.error("案件資料庫暫時無法使用，請稍後再試。")
            st.stop()
    else:
        st.sidebar.caption("訪客可使用示範；付費 AI 需要授權登入。")
    st.session_state.setdefault("cases", [])


def save_case(case):
    owner = st.session_state.get("owner")
    try:
        saved = st.session_state.store.save(owner, case) if owner else replace(case, revision=case.revision + 1)
    except (SQLAlchemyError, ValueError):
        st.error("儲存失敗或案件已更新，請重新載入後再試。")
        st.stop()
    cases = st.session_state.cases
    st.session_state.cases = [item for item in cases if item.case_id != saved.case_id] + [saved]
    return saved


def execute(case):
    with st.status("Agent 正在執行…", expanded=True) as status:
        try:
            case = run_agent(case, st.session_state.settings,
                             owner=st.session_state.get("owner"),
                             store=st.session_state.get("store"),
                             progress=lambda event: st.write(f"{event.tool} · {event.status} · {event.detail}"))
        except SQLAlchemyError:
            case = replace(case, result=None, error="額度資料庫暫時無法使用，未完成分析。")
        status.update(label="執行失敗" if case.error else "Agent 完成", state="error" if case.error else "complete")
    return case


def controls(case):
    st.caption(f"模式：{case.mode} · 覆核：{case.review_status} · 版本：{case.revision}")
    if case.extraction:
        with st.expander("模型擷取與用量"):
            st.json(case.extraction.claim.model_dump())
            st.text(f"request_id：{case.extraction.request_id}；tool_call_id：{case.extraction.tool_call_id}")
            st.text(f"模型：{case.extraction.model}；輸入 tokens：{case.extraction.input_tokens}；輸出 tokens：{case.extraction.output_tokens}")
    if case.events:
        with st.expander("Agent 工具執行紀錄", expanded=bool(case.error)):
            st.dataframe([asdict(event) for event in case.events], hide_index=True)
    for problem in case.claim_issues:
        st.warning(problem)
    st.download_button("下載完整案件與證據 JSON", encode_case(case), file_name=f"{case.case_id}.json", mime="application/json", on_click="ignore")
    result = case.result
    report = f"# CarbonLens 分析報告\n\n案件：{case.case_id}\n\n模式：{case.mode}\n\n宣稱：{case.claim}\n\n判定：{case.status}\n\n覆核：{case.review_status}\n"
    if result:
        report += f"\n基金 WACI：{result.fund_waci}\n\n實際降低 (%)：{result.actual_reduction_pct}\n\n資料覆蓋率 (%)：{result.coverage_pct}\n"
    report += "\n## 覆核紀錄\n" + "\n".join(f"- {r.at.isoformat()} {r.action}：{r.comment}" for r in case.reviews)
    st.download_button("下載分析報告 Markdown", report, file_name=f"{case.case_id}.md", mime="text/markdown", on_click="ignore")
    with st.expander("人工覆核、修正或退回"):
        claim = case.extraction.claim if case.extraction else None
        with st.form(f"review_{case.case_id}_{case.revision}"):
            action = st.selectbox("覆核動作", ["確認", "修正", "退回"])
            comment = st.text_area("覆核意見（必填）")
            pct = st.text_input("修正降低比例 (%)", value=claim.reduction_pct or "" if claim else "")
            benchmark = st.text_input("修正比較基準（須出現在原文）", value=claim.benchmark or "" if claim else "")
            year = st.number_input("修正年度", min_value=1900, max_value=2200, value=claim.year if claim and claim.year and 1900 <= claim.year <= 2200 else 2024)
            evidence = st.text_area("修正證據原文", value=claim.evidence if claim else case.claim)
            if st.form_submit_button("儲存覆核"):
                try:
                    corrected = Claim(claim_type="relative_carbon_intensity", reduction_pct=pct, benchmark=benchmark, year=int(year), evidence=evidence, needs_confirmation=False, reason=comment) if action == "修正" else None
                    save_case(review_case(case, action, comment, st.session_state.settings, corrected))
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
    if case.mode != "人工輸入" and st.button("重新執行分析（Real 會使用額度）", key=f"retry_{case.case_id}"):
        pending = save_case(replace(case, run_id=uuid4().hex, result=None, review_status="執行中"))
        save_case(execute(pending))
        st.rerun()
