"""Plan — Interactive financial planning dashboard with scenario exploration."""

from __future__ import annotations

from datetime import date as _date

import streamlit as st

from calculations.net_worth import (
    asset_allocation,
    net_worth,
    total_assets,
    total_debts,
)
from calculations.projections import (
    compute_decision_impacts,
    find_milestones,
    mortgage_info_at_retirement,
    project_net_worth_filtered,
)
from calculations.retirement import (
    drawdown_simulation,
    healthcare_cost_projection,
    inflation_adjusted,
    required_pot_size,
    retirement_income_gap,
    retirement_readiness,
    savings_needed,
)
from calculations.tax import pension_drawdown_tax
from components.charts import (
    GoalAnnotation,
    RetirementAnnotation,
    area_chart,
    donut_chart,
    format_gbp,
    gauge_chart,
    line_chart,
    milestone_timeline,
    scenario_band_chart,
)
from components.dashboard_warnings import get_financial_health_checks
from models.assumptions import INFLATION_RATE
from models.financial_data import AssetCategory, UserProfile

st.set_page_config(page_title="Plan", layout="wide")

# ── Ensure profile ────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile

if not profile.assets and not profile.debts:
    st.info("Add assets and debts on the **Profile** page first, or load the sample profile from the sidebar.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════
#  SIDEBAR — Interactive Controls
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("Plan Controls")

    projection_years = st.slider("Projection Years", 5, 50, 30, key="plan_years")
    scenario = st.selectbox("Scenario", ["Pessimistic", "Base", "Optimistic"], index=1, key="plan_scenario")
    show_real = st.checkbox("Show inflation-adjusted (real) values", key="plan_real")

    st.divider()

    # ── Goal Toggles ──────────────────────────────────────────────────────
    st.subheader("Life Goals")
    if profile.life_goals:
        st.caption("Toggle goals to see their financial impact")
        enabled_goals: set[str] = set()
        for g in profile.life_goals:
            total_cost = g.target_cost + g.annual_ongoing_cost * g.ongoing_years
            checked = st.checkbox(
                f"{g.name} ({format_gbp(total_cost)})",
                value=True,
                key=f"goal_toggle_{g.name}",
            )
            if checked:
                enabled_goals.add(g.name)
        disabled_goals = {g.name for g in profile.life_goals} - enabled_goals
    else:
        enabled_goals = set()
        disabled_goals = set()
        st.caption("No goals defined yet")

    st.divider()

    # ── Retirement Overrides ──────────────────────────────────────────────
    st.subheader("Retirement")
    ret = profile.retirement
    plan_retirement_age = st.slider(
        "Retirement Age",
        min_value=30,
        max_value=80,
        value=ret.target_retirement_age,
        key="plan_ret_age",
    )
    plan_desired_income = st.number_input(
        "Desired Income (£/yr)",
        0.0,
        200_000.0,
        float(ret.desired_annual_income),
        step=1000.0,
        key="plan_ret_income",
    )

# ── Derived values ─────────────────────────────────────────────────────────
current_year = _date.today().year
retirement_year = current_year + max(0, plan_retirement_age - ret.current_age)

# Build an ephemeral retirement override for calculations
_ret_copy = ret.model_copy()
_ret_copy.target_retirement_age = plan_retirement_age
_ret_copy.desired_annual_income = plan_desired_income

# ══════════════════════════════════════════════════════════════════════════
#  KPI ROW
# ══════════════════════════════════════════════════════════════════════════
ta = total_assets(profile.assets)
td = total_debts(profile.debts)
nw = net_worth(profile.assets, profile.debts)

annual_contribs = sum(a.annual_contribution for a in profile.assets)
total_annual_saving = annual_contribs + profile.monthly_savings * 12
savings_rate = (total_annual_saving / profile.annual_salary) if profile.annual_salary > 0 else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Net Worth", format_gbp(nw))
k2.metric("Total Assets", format_gbp(ta))
k3.metric("Total Debts", format_gbp(td))
k4.metric("Savings Rate", f"{savings_rate:.0%}" if profile.annual_salary > 0 else "—")

st.divider()

# ══════════════════════════════════════════════════════════════════════════
#  HERO CHART — Net Worth Projection with Scenario Band
# ══════════════════════════════════════════════════════════════════════════
st.subheader("Net Worth Projection" + (" (Real)" if show_real else ""))

# Run projections for all three scenarios — filtered by enabled goals
base_proj = project_net_worth_filtered(profile, disabled_goals, projection_years, "Base")
pessimistic_proj = project_net_worth_filtered(profile, disabled_goals, projection_years, "Pessimistic")
optimistic_proj = project_net_worth_filtered(profile, disabled_goals, projection_years, "Optimistic")

# Apply inflation adjustment if requested
if show_real:
    for proj_df in [base_proj, pessimistic_proj, optimistic_proj]:
        base_year = proj_df.iloc[0]["year"]
        for col in ["net_worth", "total_assets", "total_debts", "goal_spending"]:
            if col in proj_df.columns:
                proj_df[col] = proj_df.apply(
                    lambda row, c=col, by=base_year: row[c] / ((1 + INFLATION_RATE) ** (row["year"] - by)),
                    axis=1,
                )
        for col in [c for c in proj_df.columns if c.startswith("asset_")]:
            proj_df[col] = proj_df.apply(
                lambda row, c=col, by=base_year: row[c] / ((1 + INFLATION_RATE) ** (row["year"] - by)),
                axis=1,
            )

# Build annotations for enabled goals only
goal_annotations: list[GoalAnnotation] = [
    {"name": g.name, "year": g.target_year}
    for g in profile.life_goals
    if g.name in enabled_goals
]
retirement_annotation: RetirementAnnotation | None = None
if base_proj.iloc[0]["year"] <= retirement_year <= base_proj.iloc[-1]["year"]:
    retirement_annotation = {"year": retirement_year, "label": f"Retirement (age {plan_retirement_age})"}

# Pick the selected scenario as the main line
scenario_map = {"Base": base_proj, "Pessimistic": pessimistic_proj, "Optimistic": optimistic_proj}
selected_proj = scenario_map[scenario]

fig = scenario_band_chart(
    base_df=selected_proj,
    pessimistic_df=pessimistic_proj,
    optimistic_df=optimistic_proj,
    goal_annotations=goal_annotations,
    retirement_annotation=retirement_annotation,
    title="",
)

# Annotate mortgage payoff on the chart
_mortgage_chart_info = mortgage_info_at_retirement(profile, projection_years)
if _mortgage_chart_info["payoff_year"] is not None:
    _payoff_yr = _mortgage_chart_info["payoff_year"]
    _first_yr = int(selected_proj.iloc[0]["year"])
    _last_yr = int(selected_proj.iloc[-1]["year"])
    if _first_yr <= _payoff_yr <= _last_yr:
        fig.add_vline(
            x=_payoff_yr, line_dash="dashdot", line_color="#388E3C", opacity=0.6,
            annotation_text=f"Mortgage paid off ({_payoff_yr})",
            annotation_position="bottom right",
            annotation_font_size=10,
        )

st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════
#  DECISION IMPACT CARDS
# ══════════════════════════════════════════════════════════════════════════
if disabled_goals:
    st.subheader("Decision Impact")
    st.caption("Savings from skipping these goals")
    impacts = compute_decision_impacts(profile, disabled_goals, projection_years, scenario)
    cols = st.columns(min(len(impacts), 4))
    for idx, impact in enumerate(impacts):
        with cols[idx % len(cols)]:
            delta_ret = impact["net_worth_delta_at_retirement"]
            st.metric(
                f"Skip: {impact['goal_name']}",
                format_gbp(delta_ret),
                delta=f"+{format_gbp(delta_ret)} at retirement",
                delta_color="normal",
            )

    st.divider()

# ══════════════════════════════════════════════════════════════════════════
#  ASSET BREAKDOWN + RETIREMENT READINESS
# ══════════════════════════════════════════════════════════════════════════
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Asset Breakdown")
    alloc = asset_allocation(profile.assets)
    if alloc:
        fig = donut_chart(
            labels=list(alloc.keys()),
            values=[v["value"] for v in alloc.values()],
            title="Current Allocation",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Stacked area over time
    asset_cols = [c for c in selected_proj.columns if c.startswith("asset_")]
    if asset_cols:
        fig = area_chart(selected_proj, x="year", y_cols=asset_cols, title="Assets Over Time")
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Retirement Readiness")

    # ── Mortgage-retirement overlap ──────────────────────────────────────
    _mortgage_info = mortgage_info_at_retirement(profile, projection_years)
    _mort_payment = _mortgage_info["annual_mortgage_payment"]
    _mort_yrs_in_ret = _mortgage_info["mortgage_years_in_retirement"]

    gap_info = retirement_income_gap(
        _ret_copy,
        mortgage_annual_payment=_mort_payment if _mortgage_info["extends_into_retirement"] else 0.0,
        mortgage_years_in_retirement=_mort_yrs_in_ret,
    )
    years_to_ret = max(0, plan_retirement_age - ret.current_age)
    years_in_ret = max(0, ret.life_expectancy - plan_retirement_age)
    pension_pot = sum(a.current_value for a in profile.assets if a.category == AssetCategory.PENSION)

    # Growth assumptions
    pre_ret_growth = 0.07
    in_ret_growth = 0.04
    sim_inflation = INFLATION_RATE

    target_pot = required_pot_size(
        gap_info["annual_gap"], years_in_ret, in_ret_growth, sim_inflation,
        mortgage_annual_payment=_mort_payment if _mortgage_info["extends_into_retirement"] else 0.0,
        mortgage_years_in_retirement=_mort_yrs_in_ret,
    )
    hc_total = 0.0
    if ret.estimated_healthcare_costs > 0:
        hc_total = healthcare_cost_projection(
            ret.estimated_healthcare_costs,
            ret.healthcare_start_age,
            ret.life_expectancy,
            inflation_rate=sim_inflation,
            growth_rate=in_ret_growth,
            retirement_age=plan_retirement_age,
        )
        target_pot += hc_total

    readiness_pct = retirement_readiness(pension_pot, target_pot)

    fig = gauge_chart(readiness_pct, title="Readiness")
    st.plotly_chart(fig, use_container_width=True)

    r1, r2 = st.columns(2)
    r1.metric("Years to Retirement", years_to_ret)
    r2.metric("Years in Retirement", years_in_ret)
    r3, r4 = st.columns(2)
    r3.metric("Current Pension Pot", format_gbp(pension_pot))
    r4.metric("Target Pension Pot", format_gbp(target_pot))

    monthly_needed = savings_needed(target_pot, pension_pot, years_to_ret, growth_rate=pre_ret_growth)
    current_monthly_pension = sum(
        a.annual_contribution / 12 for a in profile.assets if a.category == AssetCategory.PENSION
    )
    shortfall = max(0, monthly_needed - current_monthly_pension)

    m1, m2 = st.columns(2)
    m1.metric("Monthly Savings Needed", format_gbp(monthly_needed))
    m2.metric(
        "Monthly Shortfall",
        format_gbp(shortfall),
        delta=f"-{format_gbp(shortfall)}/mo" if shortfall > 0 else "On track!",
        delta_color="inverse",
    )

    # ── Mortgage status during retirement ────────────────────────────────
    if _mortgage_info["has_mortgage"]:
        if _mortgage_info["extends_into_retirement"]:
            st.warning(
                f"Mortgage extends **{_mort_yrs_in_ret} year(s)** into retirement "
                f"(paid off {_mortgage_info['payoff_year']}). "
                f"This adds {format_gbp(_mort_payment)}/yr to your required withdrawals."
            )
        elif _mortgage_info["payoff_year"] is not None:
            st.success(
                f"Mortgage paid off in {_mortgage_info['payoff_year']} "
                f"— {format_gbp(_mort_payment)}/yr freed up before retirement."
            )

st.divider()

# ══════════════════════════════════════════════════════════════════════════
#  FINANCIAL HEALTH ALERTS
# ══════════════════════════════════════════════════════════════════════════
health_alerts = get_financial_health_checks(profile)
if health_alerts:
    st.subheader("Financial Health")
    for alert in health_alerts:
        if alert.severity == "error":
            st.error(f"**{alert.title}**\n{alert.message}")
        elif alert.severity == "warning":
            st.warning(f"**{alert.title}**\n{alert.message}")
        else:
            st.info(f"**{alert.title}**\n{alert.message}")
    st.divider()

# ══════════════════════════════════════════════════════════════════════════
#  DETAIL EXPANDERS
# ══════════════════════════════════════════════════════════════════════════

# ── Student Loan Detail ───────────────────────────────────────────────────
if "student_loan_debt" in selected_proj.columns and float(selected_proj["student_loan_debt"].iloc[0]) > 0:
    with st.expander("Student Loan Detail"):
        student_loan_series = selected_proj["student_loan_debt"]
        start_balance = float(student_loan_series.iloc[0])
        peak_balance = float(student_loan_series.max())
        peak_year = int(selected_proj.loc[student_loan_series.idxmax(), "year"])

        total_repaid = float(selected_proj["student_loan_repayment"].sum())
        total_interest = float(selected_proj["student_loan_interest"].sum())
        written_off = float(selected_proj["student_loan_written_off"].max())

        write_off_or_paid = selected_proj[
            (selected_proj["student_loan_debt"] <= 0) & (selected_proj["year"] > selected_proj.iloc[0]["year"])
        ]
        _sl_debts = [d for d in profile.debts if d.category.value == "Student Loan"]
        _expected_write_off: int | None = None
        if _sl_debts:
            _sl = _sl_debts[0]
            _expected_write_off = (_sl.student_loan_start_year or _date.today().year) + (
                _sl.student_loan_write_off_years or 30
            )

        if not write_off_or_paid.empty:
            clear_year = int(write_off_or_paid.iloc[0]["year"])
            clear_text = f"Written off in {clear_year}" if written_off > 0 else f"Paid off by {clear_year}"
        elif _expected_write_off is not None:
            clear_text = f"Not cleared in horizon (write-off expected {_expected_write_off + 1})"
        else:
            clear_text = "Not cleared in selected horizon"

        sl1, sl2, sl3 = st.columns(3)
        sl1.metric("Starting Balance", f"£{start_balance:,.0f}")
        sl2.metric("Peak Balance", f"£{peak_balance:,.0f}", delta=f"Peak year: {peak_year}")
        sl3.metric("Loan Status", clear_text)

        sl4, sl5, sl6 = st.columns(3)
        sl4.metric("Total Repaid", f"£{total_repaid:,.0f}")
        sl5.metric("Total Interest", f"£{total_interest:,.0f}")
        sl6.metric("Written Off", f"£{written_off:,.0f}" if written_off > 0 else "£0 — fully repaid")

        fig_sl = line_chart(selected_proj, x="year", y="student_loan_debt", title="Student Loan Balance")
        if _expected_write_off is not None:
            wo_year = _expected_write_off + 1
            if selected_proj.iloc[0]["year"] <= wo_year <= selected_proj.iloc[-1]["year"]:
                fig_sl.add_vline(
                    x=wo_year, line_dash="dash", line_color="red", opacity=0.5,
                    annotation_text="Write-off", annotation_position="top left",
                )
        st.plotly_chart(fig_sl, use_container_width=True)

# ── Key Milestones ────────────────────────────────────────────────────────
with st.expander("Key Milestones"):
    milestones = find_milestones(selected_proj, profile)
    if milestones:
        fig = milestone_timeline(milestones)
        st.plotly_chart(fig, use_container_width=True)
        for m in milestones:
            st.write(f"**{m['year']}** — {m['event']}")
    else:
        st.caption("No milestones reached in this projection period.")

# ── Retirement Drawdown ───────────────────────────────────────────────────
with st.expander("Retirement Drawdown Simulation"):
    _db_schedule: list[tuple[int, float]] = []
    for db in _ret_copy.defined_benefit_pensions:
        if db.start_age > plan_retirement_age:
            start_yr = max(1, db.start_age - plan_retirement_age + 1)
            _db_schedule.append((start_yr, db.annual_income))

    sim = drawdown_simulation(
        pot=target_pot,
        annual_withdrawal=gap_info["desired_annual_income_today"],
        growth_rate=in_ret_growth,
        inflation_rate=sim_inflation,
        years=years_in_ret,
        other_income=gap_info["phase1_guaranteed"],
        state_pension=gap_info["state_pension"],
        state_pension_starts_year=gap_info["phase1_years"] + 1 if gap_info["phase1_years"] > 0 else 1,
        db_pension_schedule=_db_schedule,
        additional_annual_cost=ret.estimated_healthcare_costs,
        additional_cost_starts_year=max(1, ret.healthcare_start_age - plan_retirement_age + 1),
        mortgage_annual_payment=_mort_payment if _mortgage_info["extends_into_retirement"] else 0.0,
        mortgage_years_remaining=_mort_yrs_in_ret,
    )

    if not sim.empty:
        fig = line_chart(sim, x="year", y="end_balance", title="Pension Pot Over Retirement", color="#388E3C")
        if gap_info["phase1_years"] > 0:
            spa_year = gap_info["phase1_years"] + 1
            fig.add_vline(
                x=spa_year, line_dash="dash", line_color="#1565C0", opacity=0.7,
                annotation_text=f"State Pension (age {ret.state_pension_age})",
                annotation_position="top left",
            )
        st.plotly_chart(fig, use_container_width=True)

        depleted = sim[sim["end_balance"] <= 0]
        if not depleted.empty:
            st.warning(f"Pension pot depleted in year {int(depleted.iloc[0]['year'])} of retirement.")
        else:
            st.success(
                f"Pension pot lasts the full {years_in_ret} years with "
                f"{format_gbp(sim.iloc[-1]['end_balance'])} remaining."
            )

    # Tax summary
    st.markdown("##### Tax on Drawdown")
    sample_withdrawal = gap_info["phase1_gap"]
    tax_info = pension_drawdown_tax(sample_withdrawal, gap_info["phase1_guaranteed"])
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Annual Withdrawal", format_gbp(tax_info["withdrawal"]))
    t2.metric("Tax-Free (25%)", format_gbp(tax_info["tax_free_portion"]))
    t3.metric("Tax Payable", format_gbp(tax_info["tax"]))
    t4.metric("Net After Tax", format_gbp(tax_info["net_withdrawal"]))

    # Inflation impact
    st.markdown("##### Inflation Impact")
    today_income = plan_desired_income
    future_val = inflation_adjusted(today_income, years_to_ret, inflation_rate=sim_inflation)
    i1, i2 = st.columns(2)
    i1.metric(f"£{today_income:,.0f} today", "Current purchasing power")
    i2.metric(
        f"Worth {format_gbp(future_val)} in {years_to_ret} years",
        f"At {sim_inflation:.1%} inflation",
    )

# ── Raw Data ──────────────────────────────────────────────────────────────
with st.expander("Raw Projection Data"):
    display_cols = [c for c in [
        "year", "net_worth", "total_assets", "total_debts",
        "goal_spending",
    ] if c in selected_proj.columns]
    # Add any extra columns that exist
    for extra in [
        "student_loan_debt", "lifestyle_spending", "total_spending",
        "annual_income", "annual_surplus_deficit",
    ]:
        if extra in selected_proj.columns:
            display_cols.append(extra)

    fmt = {c: "£{:,.0f}" for c in display_cols if c != "year"}
    st.dataframe(selected_proj[display_cols].style.format(fmt), use_container_width=True)
