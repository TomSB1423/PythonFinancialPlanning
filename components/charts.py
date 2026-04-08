"""Reusable Plotly chart builders."""

from __future__ import annotations

from typing import TypedDict

import pandas as pd
import plotly.graph_objects as go

MATERIAL_BLUE = "#1976D2"
MATERIAL_COLORS = ["#1976D2", "#388E3C", "#F57C00", "#D32F2F", "#7B1FA2", "#0097A7", "#455A64"]


class TimelineMilestone(TypedDict):
    event: str
    year: int
    age: int


def format_gbp(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"£{value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"£{value / 1_000:,.0f}k"
    return f"£{value:,.0f}"


def donut_chart(labels: list[str], values: list[float], title: str = "") -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=MATERIAL_COLORS[:len(labels)]),
        textinfo="label+percent",
        hovertemplate="%{label}: £%{value:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        showlegend=True,
        margin=dict(t=40, b=20, l=20, r=20),
        height=350,
    )
    return fig


def area_chart(
    df: pd.DataFrame,
    x: str,
    y_cols: list[str],
    title: str = "",
    stacked: bool = True,
) -> go.Figure:
    fig = go.Figure()
    for i, col in enumerate(y_cols):
        if col not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df[x],
            y=df[col],
            name=col.replace("asset_", "").replace("_", " ").title(),
            fill="tonexty" if stacked and i > 0 else "tozeroy",
            mode="lines",
            line=dict(color=MATERIAL_COLORS[i % len(MATERIAL_COLORS)]),
            hovertemplate=f"%{{x}}: £%{{y:,.0f}}<extra>{col}</extra>",
        ))
    fig.update_layout(
        title=title,
        xaxis_title=x.title(),
        yaxis_title="Value (£)",
        yaxis_tickformat=",",
        hovermode="x unified",
        margin=dict(t=40, b=40, l=60, r=20),
        height=400,
    )
    return fig


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str = MATERIAL_BLUE,
) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=df[x],
        y=df[y],
        mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=4),
        hovertemplate="%{x}: £%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=x.title(),
        yaxis_title="Value (£)",
        yaxis_tickformat=",",
        margin=dict(t=40, b=40, l=60, r=20),
        height=350,
    )
    return fig


def bar_chart(
    labels: list[str],
    values: list[float],
    title: str = "",
    horizontal: bool = False,
) -> go.Figure:
    if horizontal:
        fig = go.Figure(go.Bar(
            y=labels, x=values, orientation="h",
            marker_color=MATERIAL_COLORS[:len(labels)],
            hovertemplate="%{y}: £%{x:,.0f}<extra></extra>",
        ))
    else:
        fig = go.Figure(go.Bar(
            x=labels, y=values,
            marker_color=MATERIAL_COLORS[:len(labels)],
            hovertemplate="%{x}: £%{y:,.0f}<extra></extra>",
        ))
    fig.update_layout(
        title=title,
        yaxis_tickformat=",",
        margin=dict(t=40, b=40, l=60, r=20),
        height=350,
    )
    return fig


def milestone_timeline(milestones: list[TimelineMilestone], title: str = "Key Milestones") -> go.Figure:
    if not milestones:
        return go.Figure().update_layout(title="No milestones to display")

    ages = [m["age"] for m in milestones]
    events = [m["event"] for m in milestones]

    fig = go.Figure(go.Scatter(
        x=ages,
        y=[1] * len(ages),
        mode="markers+text",
        marker=dict(size=14, color=MATERIAL_COLORS[:len(ages)], symbol="diamond"),
        text=events,
        textposition="top center",
        hovertemplate="%{text} (age %{x})<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Age",
        yaxis=dict(visible=False),
        showlegend=False,
        margin=dict(t=40, b=40, l=20, r=20),
        height=200,
    )
    return fig


def gauge_chart(value: float, title: str = "", max_val: float = 100) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title},
        number={"suffix": "%"},
        gauge=dict(
            axis=dict(range=[0, max_val]),
            bar=dict(color=MATERIAL_BLUE),
            steps=[
                dict(range=[0, max_val * 0.33], color="#FFCDD2"),
                dict(range=[max_val * 0.33, max_val * 0.66], color="#FFF9C4"),
                dict(range=[max_val * 0.66, max_val], color="#C8E6C9"),
            ],
        ),
    ))
    fig.update_layout(margin=dict(t=60, b=20, l=30, r=30), height=250)
    return fig


# ── Annotation helpers ─────────────────────────────────────────────────────

class GoalAnnotation(TypedDict):
    name: str
    age: int


class RetirementAnnotation(TypedDict):
    age: int
    label: str


def scenario_band_chart(
    base_df: pd.DataFrame,
    pessimistic_df: pd.DataFrame,
    optimistic_df: pd.DataFrame,
    x: str = "age",
    y: str = "net_worth",
    goal_annotations: list[GoalAnnotation] | None = None,
    retirement_annotation: RetirementAnnotation | None = None,
    title: str = "Net Worth Projection",
) -> go.Figure:
    """Render a net worth projection with a shaded confidence band.

    Shows the base scenario as a solid line with the pessimistic-to-optimistic
    range as a filled band behind it.  Goal and retirement annotations are drawn
    as vertical lines.
    """
    fig = go.Figure()

    # Optimistic upper bound (invisible line — needed for fill)
    fig.add_trace(go.Scatter(
        x=optimistic_df[x],
        y=optimistic_df[y],
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Pessimistic lower bound — filled to optimistic
    fig.add_trace(go.Scatter(
        x=pessimistic_df[x],
        y=pessimistic_df[y],
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(25, 118, 210, 0.12)",
        name="Pessimistic–Optimistic range",
        hoverinfo="skip",
    ))

    # Base scenario main line
    fig.add_trace(go.Scatter(
        x=base_df[x],
        y=base_df[y],
        mode="lines",
        line=dict(color=MATERIAL_BLUE, width=3),
        name="Base",
        hovertemplate="%{x}: £%{y:,.0f}<extra></extra>",
    ))

    # Goal annotations
    for g in goal_annotations or []:
        first_val = int(base_df[x].iloc[0])
        last_val = int(base_df[x].iloc[-1])
        if first_val <= g["age"] <= last_val:
            fig.add_vline(
                x=g["age"], line_dash="dash", line_color="#D32F2F", opacity=0.5,
                annotation_text=g["name"], annotation_position="top left",
                annotation_font_size=10,
            )

    # Retirement annotation
    if retirement_annotation:
        first_val = int(base_df[x].iloc[0])
        last_val = int(base_df[x].iloc[-1])
        val = retirement_annotation["age"]
        if first_val <= val <= last_val:
            fig.add_vline(
                x=val, line_dash="dot", line_color="#1565C0", opacity=0.7,
                annotation_text=retirement_annotation["label"],
                annotation_position="top right",
                annotation_font_size=10,
            )

    fig.update_layout(
        title=title,
        xaxis_title=x.title(),
        yaxis_title="Value (£)",
        yaxis_tickformat=",",
        hovermode="x unified",
        margin=dict(t=40, b=40, l=60, r=20),
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# ── Cash Flow Charts ───────────────────────────────────────────────────────

def cash_flow_sankey(breakdown: object) -> go.Figure:
    """Salary → Deductions → Bank Account → Expenses → Surplus Sankey chart.

    *breakdown* is a ``CashFlowBreakdown`` dataclass (imported lazily to
    avoid circular deps at module level).
    """
    # Node indices
    #  0: Gross Salary
    #  1: Pension (sacrifice)
    #  2: Income Tax
    #  3: National Insurance
    #  4: Student Loan
    #  5: Net Take-Home
    #  6: Mortgage
    #  7: Loans
    #  8: Living Expenses
    #  9: Holidays
    # 10: Goal Ongoing
    # 11: Contributions (ISA/GIA)
    # 12: Surplus

    labels = [
        "Gross Salary",         # 0
        "Pension",              # 1
        "Income Tax",           # 2
        "National Insurance",   # 3
        "Student Loan",         # 4
        "Net Take-Home",        # 5
        "Mortgage",             # 6
        "Loans",                # 7
        "Living Expenses",      # 8
        "Holidays",             # 9
        "Goal Costs",           # 10
        "Contributions",        # 11
        "Surplus",              # 12
    ]

    node_colors = [
        "#1976D2",  # Gross Salary — blue
        "#7B1FA2",  # Pension — purple
        "#D32F2F",  # Tax — red
        "#F57C00",  # NI — orange
        "#0097A7",  # Student Loan — teal
        "#388E3C",  # Net Take-Home — green
        "#D32F2F",  # Mortgage — red
        "#F57C00",  # Loans — orange
        "#D32F2F",  # Living — red
        "#F57C00",  # Holidays — orange
        "#7B1FA2",  # Goal — purple
        "#0097A7",  # Contributions — teal
        "#388E3C",  # Surplus — green
    ]

    b = breakdown
    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []
    link_colors: list[str] = []

    def _add(src: int, tgt: int, val: float, color: str = "rgba(200,200,200,0.4)") -> None:
        if val > 0:
            sources.append(src)
            targets.append(tgt)
            values.append(val)
            link_colors.append(color)

    # Salary → deductions
    _add(0, 1, b.pension_contribution, "rgba(123,31,162,0.25)")
    _add(0, 2, b.income_tax, "rgba(211,47,47,0.25)")
    _add(0, 3, b.national_insurance, "rgba(245,124,0,0.25)")
    _add(0, 4, b.student_loan_repayment, "rgba(0,151,167,0.25)")
    _add(0, 5, b.net_take_home, "rgba(56,142,60,0.25)")

    # Net Take-Home → expenses
    _add(5, 6, b.mortgage_payments, "rgba(211,47,47,0.25)")
    _add(5, 7, b.loan_payments, "rgba(245,124,0,0.25)")
    _add(5, 8, b.living_expenses, "rgba(211,47,47,0.25)")
    _add(5, 9, b.holiday_budget, "rgba(245,124,0,0.25)")
    _add(5, 10, b.goal_ongoing_costs, "rgba(123,31,162,0.25)")
    _add(5, 11, b.non_pension_contributions, "rgba(0,151,167,0.25)")
    _add(5, 12, b.surplus, "rgba(56,142,60,0.35)")

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=20,
            thickness=20,
            line=dict(color="#333", width=0.5),
            label=[f"{lbl}\n{format_gbp(v)}" if v else lbl for lbl, v in zip(
                labels,
                [b.gross_salary, b.pension_contribution, b.income_tax,
                 b.national_insurance, b.student_loan_repayment, b.net_take_home,
                 b.mortgage_payments, b.loan_payments, b.living_expenses,
                 b.holiday_budget, b.goal_ongoing_costs, b.non_pension_contributions,
                 b.surplus],
            )],
            color=node_colors,
        ),
        link=dict(source=sources, target=targets, value=values, color=link_colors),
    ))
    fig.update_layout(
        title="Annual Cash Flow",
        margin=dict(t=40, b=20, l=20, r=20),
        height=450,
    )
    return fig


def cash_flow_waterfall(breakdown: object) -> go.Figure:
    """Waterfall chart stepping from Gross Salary down to Surplus."""
    b = breakdown

    categories: list[str] = []
    amounts: list[float] = []
    measures: list[str] = []

    def _step(name: str, value: float, measure: str = "relative") -> None:
        if value != 0 or measure == "total":
            categories.append(name)
            amounts.append(value)
            measures.append(measure)

    _step("Gross Salary", b.gross_salary, "absolute")
    _step("Pension", -b.pension_contribution)
    _step("Income Tax", -b.income_tax)
    _step("Nat. Insurance", -b.national_insurance)
    _step("Student Loan", -b.student_loan_repayment)
    _step("Net Take-Home", b.net_take_home, "total")
    _step("Mortgage", -b.mortgage_payments)
    _step("Loans", -b.loan_payments)
    _step("Living Expenses", -b.living_expenses)
    _step("Holidays", -b.holiday_budget)
    _step("Goal Costs", -b.goal_ongoing_costs)
    _step("Contributions", -b.non_pension_contributions)
    _step("Surplus", b.surplus, "total")

    fig = go.Figure(go.Waterfall(
        x=categories,
        y=amounts,
        measure=measures,
        increasing=dict(marker_color="#388E3C"),
        decreasing=dict(marker_color="#D32F2F"),
        totals=dict(marker_color="#1976D2"),
        textposition="outside",
        text=[format_gbp(abs(v)) for v in amounts],
        hovertemplate="%{x}: £%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title="Salary Breakdown",
        yaxis_title="Value (£)",
        yaxis_tickformat=",",
        margin=dict(t=40, b=60, l=60, r=20),
        height=450,
        showlegend=False,
    )
    return fig
