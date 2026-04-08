"""FIRE — Financial Independence / Retire Early calculator."""

from __future__ import annotations

import streamlit as st

from calculations.projections import mortgage_info_at_retirement, project_net_worth
from calculations.retirement import (
    drawdown_simulation,
    get_fire_actions,
    investable_pot,
    required_pot_size,
    retirement_income_gap,
    retirement_readiness,
    savings_needed,
    years_to_fire,
)
from components.charts import (
    format_gbp,
    gauge_chart,
    line_chart,
    scenario_band_chart,
)
from models.assumptions import SCENARIOS
from models.financial_data import UserProfile

st.set_page_config(page_title="FIRE", layout="wide")

# ── Session state ─────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile
ret = profile.retirement

st.title("FIRE")

# ── Sidebar controls ─────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("FIRE Settings")
    override_retirement_age = st.slider(
        "Retirement Age", 30, 100, ret.target_retirement_age, key="fire_ret_age",
    )
    override_income = st.number_input(
        "Desired Annual Income (£)", 0.0, 200_000.0,
        float(ret.desired_annual_income), step=1000.0, key="fire_income",
    )
    scenario = st.selectbox("Scenario", list(SCENARIOS.keys()), index=1, key="fire_scenario")

# Apply overrides to a copy for calculations
fire_ret = ret.model_copy()
fire_ret.target_retirement_age = override_retirement_age
fire_ret.desired_annual_income = override_income

# ── Core calculations ─────────────────────────────────────────────────────
mortgage_info = mortgage_info_at_retirement(profile)
gap_result = retirement_income_gap(
    fire_ret,
    mortgage_annual_payment=mortgage_info["annual_mortgage_payment"],
    mortgage_years_in_retirement=mortgage_info["mortgage_years_in_retirement"],
)

years_in_retirement = max(0, fire_ret.life_expectancy - fire_ret.target_retirement_age)
fire_number = required_pot_size(
    gap_result["annual_gap"],
    years_in_retirement,
    mortgage_annual_payment=mortgage_info["annual_mortgage_payment"],
    mortgage_years_in_retirement=mortgage_info["mortgage_years_in_retirement"],
)

current_pot = investable_pot(profile.assets)
readiness = retirement_readiness(current_pot, fire_number)

ytf = years_to_fire(profile)
years_to_ret = max(0, fire_ret.target_retirement_age - fire_ret.current_age)
monthly_needed = savings_needed(fire_number, current_pot, years_to_ret)

# ── KPI Row ───────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("FIRE Number", format_gbp(fire_number))
c2.metric("Years to FIRE", str(ytf) if ytf is not None else "40+")
c3.metric("Readiness", f"{readiness:.0f}%")
c4.metric("Monthly Savings Needed", format_gbp(monthly_needed))

# ── Action Items ──────────────────────────────────────────────────────────
fire_actions = get_fire_actions(
    profile,
    fire_number=fire_number,
    current_pot=current_pot,
    readiness=readiness,
    years_to_fire_val=ytf,
    monthly_needed=monthly_needed,
)
if fire_actions:
    _severity_fn = {"error": st.error, "warning": st.warning, "info": st.info}
    for action in fire_actions:
        fn = _severity_fn.get(action["severity"], st.info)
        fn(f"**{action['title']}** \u2014 {action['message']}", icon=None)

st.divider()

# ── Readiness & Income Gap ────────────────────────────────────────────────
col_gauge, col_gap = st.columns([1, 2])

with col_gauge:
    fig_gauge = gauge_chart(readiness, title="Retirement Readiness")
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_gap:
    st.subheader("Income Gap Breakdown")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Phase 1: Pre-State Pension**")
        st.write(f"Duration: {gap_result['phase1_years']} years")
        st.write(f"Guaranteed income: {format_gbp(gap_result['phase1_guaranteed'])}/yr")
        st.write(f"Annual shortfall: {format_gbp(gap_result['phase1_gap'])}/yr")
    with g2:
        st.markdown("**Phase 2: Post-State Pension**")
        st.write(f"Duration: {gap_result['phase2_years']} years")
        st.write(f"Guaranteed income: {format_gbp(gap_result['phase2_guaranteed'])}/yr")
        st.write(f"Annual shortfall: {format_gbp(gap_result['phase2_gap'])}/yr")

    st.caption(
        f"Desired income: {format_gbp(gap_result['desired_annual_income_today'])}/yr · "
        f"State pension: {format_gbp(gap_result['state_pension'])}/yr"
    )

st.divider()

# ── FIRE Projection (Scenario Band) ──────────────────────────────────────
st.subheader("Investable Pot Projection")
projection_years = max(years_to_ret + 5, 20)

base_proj = project_net_worth(profile, years=projection_years, scenario="Base")
pessimistic_proj = project_net_worth(profile, years=projection_years, scenario="Pessimistic")
optimistic_proj = project_net_worth(profile, years=projection_years, scenario="Optimistic")

# Sum Pension + ISA + GIA into a single investable column
_inv_cols = ["asset_Pension", "asset_ISA", "asset_GIA"]
for df in [base_proj, pessimistic_proj, optimistic_proj]:
    for col in _inv_cols:
        if col not in df.columns:
            df[col] = 0.0
    df["investable_pot"] = df[_inv_cols].sum(axis=1)

fig_fire = scenario_band_chart(
    base_proj, pessimistic_proj, optimistic_proj,
    x="age", y="investable_pot",
    title="Investable Pot Growth (Pension + ISA + GIA)",
    retirement_annotation={"age": fire_ret.target_retirement_age, "label": "Retirement"},
)
# Add FIRE number line
fig_fire.add_hline(
    y=fire_number, line_dash="dash", line_color="#388E3C", opacity=0.7,
    annotation_text=f"FIRE Target: {format_gbp(fire_number)}",
    annotation_position="top left",
)
st.plotly_chart(fig_fire, use_container_width=True)

st.divider()

# ── Drawdown Simulation ──────────────────────────────────────────────────
st.subheader("Drawdown Simulation")

sp_starts_year = max(1, fire_ret.state_pension_age - fire_ret.target_retirement_age + 1)

drawdown_df = drawdown_simulation(
    pot=fire_number if current_pot < fire_number else current_pot,
    annual_withdrawal=gap_result["annual_gap"],
    years=years_in_retirement,
    state_pension=fire_ret.expected_state_pension,
    state_pension_starts_year=sp_starts_year,
    mortgage_annual_payment=mortgage_info["annual_mortgage_payment"],
    mortgage_years_remaining=mortgage_info["mortgage_years_in_retirement"],
    start_age=fire_ret.target_retirement_age,
)

if not drawdown_df.empty and "age" in drawdown_df.columns:
    fig_dd = line_chart(drawdown_df, x="age", y="end_balance", title="Pot Balance Through Retirement")
    # Depletion warning
    depleted = drawdown_df[drawdown_df["end_balance"] <= 0]
    if not depleted.empty:
        depletion_age = int(depleted.iloc[0]["age"])
        fig_dd.add_vline(
            x=depletion_age, line_dash="dash", line_color="#D32F2F", opacity=0.7,
            annotation_text=f"Pot depleted at age {depletion_age}",
            annotation_position="top left",
        )
    # State pension annotation
    if sp_starts_year > 1:
        fig_dd.add_vline(
            x=fire_ret.state_pension_age, line_dash="dot", line_color="#1565C0", opacity=0.5,
            annotation_text="State Pension starts",
            annotation_position="bottom right",
        )
    st.plotly_chart(fig_dd, use_container_width=True)

# ── Mortgage Overlap ─────────────────────────────────────────────────────
if mortgage_info["has_mortgage"]:
    st.divider()
    if mortgage_info["extends_into_retirement"]:
        st.warning(
            f"Mortgage extends {mortgage_info['mortgage_years_in_retirement']} years into retirement "
            f"({format_gbp(mortgage_info['annual_mortgage_payment'])}/yr)"
        )
    else:
        st.success("Mortgage will be paid off before retirement")
