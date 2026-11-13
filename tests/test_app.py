from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def browser_session():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="view").set_value("建立案件").run()
    assert not app.exception
    return app


def test_demo_cases_update_dashboard(browser_session):
    app = browser_session
    expected = [
        ("SYN001", "符合宣稱", ["50", "100", "30%", "50%", "100%"], 4),
        ("SYN002", "宣稱不一致，需人工覆核", ["95", "100", "30%", "5%", "100%"], 4),
        ("SYN003", "資料不足，無法判定", ["—", "100", "30%", "—", "60%"], 1),
    ]
    for fund, status, metrics, charts in expected:
        app.selectbox[0].select(fund).run()
        app.text_input[0].set_value("30")
        app.checkbox[0].set_value(True)
        app.button[0].click().run()

        assert not app.exception
        assert app.session_state.cases[-1].result.status.value == status
        assert [metric.value for metric in app.metric] == metrics
        assert len(app.get("plotly_chart")) == charts

    app.radio(key="view").set_value("分析總覽").run()
    assert [metric.value for metric in app.metric] == ["3", "1", "1", "1", "3"]
    assert len(app.dataframe[0].value) == 3


def test_target_requires_manual_confirmation(browser_session):
    app = browser_session
    app.text_input[0].set_value("30")
    app.button[0].click().run()

    assert not app.exception
    assert app.error
    assert app.session_state.cases == []

    app.text_input[0].set_value("")
    app.button[0].click().run()
    assert not app.exception
    assert app.info[0].value == "等待宣稱確認"
    assert app.session_state.cases[-1].result.fund_waci is None


def test_review_on_creation_page_survives_rerun(browser_session):
    app = browser_session
    app.text_input[0].set_value("30")
    app.checkbox[0].set_value(True)
    app.button[0].click().run()
    app.text_area[1].set_value("已核對原文與數值")
    next(button for button in app.button if button.label == "儲存覆核").click().run()
    assert not app.exception
    assert app.session_state.cases[-1].review_status == "已確認"
    assert app.session_state.cases[-1].revision == 2
