"""Goals — Life goals with live net worth impact projections."""

from __future__ import annotations

from datetime import date

import streamlit as st

from calculations.projections import (
    compute_decision_impacts,
    find_milestones,
    project_net_worth,
    project_net_worth_filtered,
)
from components.charts import (
    GoalAnnotation,
    bar_chart,
    format_gbp,
    milestone_timeline,
    scenario_band_chart,
)
from models.assumptions import SCENARIOS
from models.financial_data import UserProfile

st.set_page_config(page_title="Goals", layout="wide")

# ── Session state ─────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile
ret = profile.retirement

st.title("Goals")

if not profile.life_goals:
    st.info("No life goals set. Add goals on the Profile page.")
    st.stop()

# ── Sidebar controls ─────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Projection Settings")
    projection_years = st.slider("Projection Years", 5, 50, 30, key="goal_years")
    scenario = st.selectbox("Scenario", list(SCENARIOS.keys()), index=1, key="goal_scenario")

# ── KPI Row ───────────────────────────────────────────────────────────────
current_year = date.today().year
total_goal_cost = sum(
    g.target_cost + g.annual_ongoing_cost * g.ongoing_years for g in profile.life_goals
)
upcoming = sorted(
    [g for g in profile.life_goals if g.target_year >= current_year],
    key=lambda g: g.target_year,
)
next_goal = upcoming[0] if upcoming else None

c1, c2, c3 = st.columns(3)
c1.metric("Total Goal Cost", format_gbp(total_goal_cost))
c2.metric("Next Goal", f"{next_goal.name} ({next_goal.target_year})" if next_goal else "None")
c3.metric("Number of Goals", str(len(profile.life_goals)))

st.divider()

# ── Milestone Timeline ───────────────────────────────────────────────────
milestones = find_milestones(
    project_net_worth(profile, years=projection_years, scenario=scenario),
    profile,
)
if milestones:
    fig_timeline = milestone_timeline(milestones)
    st.plotly_chart(fig_timeline, use_container_width=True)
    st.divider()

# ── Goal Toggles & Net Worth Projection ──────────────────────────────────
st.subheader("Goal Impact Analysis")

disabled_goals: set[str] = set()
cols = st.columns(min(len(profile.life_goals), 4))
for i, goal in enumerate(profile.life_goals):
    with cols[i % len(cols)]:
        enabled = st.checkbox(goal.name, value=True, key=f"goal_toggle_{i}")
        if not enabled:
            disabled_goals.add(goal.name)

# Run projections
if disabled_goals:
    base_proj = project_net_worth_filtered(profile, disabled_goals, years=projection_years, scenario="Base")
    pessimistic_proj = project_net_worth_filtered(profile, disabled_goals, years=projection_years, scenario="Pessimistic")
    optimistic_proj = project_net_worth_filtered(profile, disabled_goals, years=projection_years, scenario="Optimistic")
else:
    base_proj = project_net_worth(profile, years=projection_years, scenario="Base")
    pessimistic_proj = project_net_worth(profile, years=projection_years, scenario="Pessimistic")
    optimistic_proj = project_net_worth(profile, years=projection_years, scenario="Optimistic")

# Goal annotations for enabled goals
goal_annotations: list[GoalAnnotation] = [
    {"name": g.name, "age": ret.current_age + (g.target_year - current_year)}
    for g in profile.life_goals
    if g.name not in disabled_goals
]

fig_proj = scenario_band_chart(
    base_proj, pessimistic_proj, optimistic_proj,
    x="age", y="net_worth",
    goal_annotations=goal_annotations,
    retirement_annotation={"age": ret.target_retirement_age, "label": "Retirement"},
    title="Net Worth Projection",
)
st.plotly_chart(fig_proj, use_container_width=True)

# ── Decision Impact Cards ────────────────────────────────────────────────
if disabled_goals:
    impacts = compute_decision_impacts(profile, disabled_goals, years=projection_years, scenario=scenario)
    if impacts:
        st.subheader("Decision Impact")
        impact_cols = st.columns(len(impacts))
        for i, impact in enumerate(impacts):
            with impact_cols[i % len(impact_cols)]:
                st.markdown(f"**{impact['goal_name']}**")
                st.metric(
                    "Net Worth at Retirement",
                    format_gbp(abs(impact["net_worth_delta_at_retirement"])),
                    delta=f"-{format_gbp(impact['net_worth_delta_at_retirement'])}",
                    delta_color="inverse",
                )

st.divider()

# ── Goal Cost Breakdown ──────────────────────────────────────────────────
st.subheader("Goal Cost Breakdown")
names = [g.name for g in profile.life_goals]
costs = [g.target_cost + g.annual_ongoing_cost * g.ongoing_years for g in profile.life_goals]
fig_costs = bar_chart(names, costs, title="Total Cost per Goal")
st.plotly_chart(fig_costs, use_container_width=True)
