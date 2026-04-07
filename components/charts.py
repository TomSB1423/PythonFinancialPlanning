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
        xaxis_title="Year",
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
        xaxis_title="Year",
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

    years = [m["year"] for m in milestones]
    events = [m["event"] for m in milestones]

    fig = go.Figure(go.Scatter(
        x=years,
        y=[1] * len(years),
        mode="markers+text",
        marker=dict(size=14, color=MATERIAL_COLORS[:len(years)], symbol="diamond"),
        text=events,
        textposition="top center",
        hovertemplate="%{text} (%{x})<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Year",
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
    year: int


class RetirementAnnotation(TypedDict):
    year: int
    label: str


def scenario_band_chart(
    base_df: pd.DataFrame,
    pessimistic_df: pd.DataFrame,
    optimistic_df: pd.DataFrame,
    x: str = "year",
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
        first_year = int(base_df[x].iloc[0])
        last_year = int(base_df[x].iloc[-1])
        if first_year <= g["year"] <= last_year:
            fig.add_vline(
                x=g["year"], line_dash="dash", line_color="#D32F2F", opacity=0.5,
                annotation_text=g["name"], annotation_position="top left",
                annotation_font_size=10,
            )

    # Retirement annotation
    if retirement_annotation:
        first_year = int(base_df[x].iloc[0])
        last_year = int(base_df[x].iloc[-1])
        yr = retirement_annotation["year"]
        if first_year <= yr <= last_year:
            fig.add_vline(
                x=yr, line_dash="dot", line_color="#1565C0", opacity=0.7,
                annotation_text=retirement_annotation["label"],
                annotation_position="top right",
                annotation_font_size=10,
            )

    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title="Value (£)",
        yaxis_tickformat=",",
        hovermode="x unified",
        margin=dict(t=40, b=40, l=60, r=20),
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig
