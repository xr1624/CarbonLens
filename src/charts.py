"""Plotly views of portfolio data and computed analysis results."""

from collections import defaultdict
from decimal import Decimal
from html import escape

import plotly.graph_objects as go

from src.calculations import AnalysisResult
from src.validation import WACI_UNIT


FOREST = "#123C35"
MINT = "#A6E4C6"


def _bars(labels, values, unit, *, colors=FOREST, height=260):
    numbers = [float(value) for value in values]
    labels = [escape(label) for label in labels]
    figure = go.Figure(go.Bar(
        x=numbers,
        y=labels,
        orientation="h",
        marker_color=colors,
        hovertemplate="%{y}<br>%{x:.6g} " + unit + "<extra></extra>",
    ))
    figure.update_layout(
        height=height,
        margin=dict(l=12, r=18, t=12, b=50),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#202B28", size=13),
        barcornerradius=4,
    )
    figure.update_xaxes(title_text=unit, gridcolor="#DDE6DC", zerolinecolor="#AABCB2")
    figure.update_yaxes(autorange="reversed", automargin=True)
    return figure


def waci_chart(result: AnalysisResult) -> go.Figure | None:
    if result.fund_waci is None or result.benchmark_waci is None:
        return None
    return _bars(
        ["基金", "市場基準"],
        [result.fund_waci, result.benchmark_waci],
        WACI_UNIT,
        colors=[FOREST, MINT],
    )


def reduction_chart(result: AnalysisResult) -> go.Figure | None:
    if result.actual_reduction_pct is None or result.claimed_reduction_pct is None:
        return None
    return _bars(
        ["宣稱門檻", "實際降低"],
        [result.claimed_reduction_pct, result.actual_reduction_pct],
        "%",
        colors=[MINT, FOREST],
    )


def sector_chart(result: AnalysisResult) -> go.Figure | None:
    holdings = result.validation.holdings
    if not holdings or any(row.weight_pct is None or not row.sector for row in holdings):
        return None
    if len({row.company_id for row in holdings}) != len(holdings):
        return None
    weights = defaultdict(Decimal)
    for row in holdings:
        weights[row.sector] += row.weight_pct
    rows = sorted(weights.items(), key=lambda row: (-row[1], row[0]))
    return _bars(
        [label for label, _ in rows],
        [value for _, value in rows],
        "持股權重 (%)",
        height=min(660, max(260, 36 * len(rows) + 75)),
    )


def contribution_chart(result: AnalysisResult) -> go.Figure | None:
    if not result.contributions:
        return None
    rows = sorted(
        result.contributions,
        key=lambda row: row.weighted_carbon_intensity,
        reverse=True,
    )[:15]
    return _bars(
        [f"{row.holding.company_name}（{row.holding.company_id}）" for row in rows],
        [row.weighted_carbon_intensity for row in rows],
        WACI_UNIT,
        height=min(660, max(260, 36 * len(rows) + 75)),
    )
