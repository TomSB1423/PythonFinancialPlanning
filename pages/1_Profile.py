"""Profile — All financial data entry in a single tabbed view."""

from __future__ import annotations

from datetime import date

import streamlit as st

from components.charts import TimelineMilestone, bar_chart, format_gbp, milestone_timeline
from components.forms import asset_form, debt_form, goal_form
from models.assumptions import DEFAULT_ASSETS, DEFAULT_DEBTS, DEFAULT_GOALS
from models.financial_data import (
    Asset,
    Debt,
    GoalFunding,
    LifeGoal,
    UserProfile,
)

st.set_page_config(page_title="Profile", layout="wide")

# ── Ensure profile in session state ───────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile
ret = profile.retirement

# ── Auto-populate defaults ────────────────────────────────────────────────
if not profile.assets and not st.session_state.get("assets_initialised"):
    for cfg in DEFAULT_ASSETS:
        profile.assets.append(Asset(**cfg))
    st.session_state.assets_initialised = True

if not profile.debts and not st.session_state.get("debts_initialised"):
    for cfg in DEFAULT_DEBTS:
        profile.debts.append(Debt(**cfg))
    st.session_state.debts_initialised = True

if not profile.life_goals and not st.session_state.get("goals_initialised"):
    current_year = date.today().year
    for name, info in DEFAULT_GOALS.items():
        goal_kwargs: dict = {
            "name": name,
            "target_cost": info["cost"],
            "target_year": current_year + info["year_offset"],
            "funding_source": GoalFunding(info["funding"]),
            "annual_ongoing_cost": info.get("annual_ongoing", 0.0),
            "ongoing_years": info.get("ongoing_years", 0),
        }
        for field in (
            "deposit_percentage",
            "mortgage_rate",
            "mortgage_term_years",
            "loan_interest_rate",
            "loan_term_years",
        ):
            if field in info:
                goal_kwargs[field] = info[field]
        profile.life_goals.append(LifeGoal(**goal_kwargs))
    st.session_state.goals_initialised = True

# ── Page header ───────────────────────────────────────────────────────────
st.title("Your Financial Profile")

ta = sum(a.current_value for a in profile.assets)
td = sum(d.outstanding_balance for d in profile.debts)
c1, c2, c3 = st.columns(3)
c1.metric("Total Assets", format_gbp(ta))
c2.metric("Total Debts", format_gbp(td))
c3.metric("Net Worth", format_gbp(ta - td))

st.divider()

# ══════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════
tab_income, tab_assets, tab_goals, tab_retirement = st.tabs(
    ["Income & Pensions", "Assets & Debts", "Life Goals", "Retirement"]
)

# ── Tab 1: Income & Spending ──────────────────────────────────────────────
with tab_income:
    st.subheader("Income")
    profile.annual_salary = st.number_input(
        "Annual Salary (£)", 0.0, 500_000.0, float(profile.annual_salary), step=1000.0,
    )

    st.subheader("Recurring Spending")
    sc1, sc2 = st.columns(2)
    with sc1:
        monthly_living = st.number_input(
            "Monthly Living Costs (£)",
            0.0,
            100_000.0,
            float(profile.annual_living_expenses) / 12,
            step=100.0,
            help="Rent, utilities, food, transport, insurance.",
        )
    with sc2:
        monthly_holidays = st.number_input(
            "Monthly Holiday Budget (£)",
            0.0,
            20_000.0,
            float(profile.annual_holiday_budget) / 12,
            step=50.0,
            help="Monthly amount set aside for holidays and travel.",
        )
    profile.annual_living_expenses = monthly_living * 12
    profile.annual_holiday_budget = monthly_holidays * 12
    st.caption(
        f"Annualized spending: {format_gbp(profile.annual_living_expenses + profile.annual_holiday_budget)}"
    )



# ── Tab 2: Assets & Debts ────────────────────────────────────────────────
with tab_assets:
    # ── Assets ────────────────────────────────────────────────────────────
    st.subheader("Assets")
    if profile.assets:
        for i, asset in enumerate(profile.assets):
            with st.expander(
                f"{asset.name} — {format_gbp(asset.current_value)} ({asset.category.value})"
            ):
                st.write(
                    f"**Growth:** {asset.annual_growth_rate:.1%}  |  "
                    f"**Liquid:** {'Yes' if asset.is_liquid else 'No'}  |  "
                    f"**Wrapper:** {asset.tax_wrapper.value}  |  "
                    f"**Annual Contribution:** {format_gbp(asset.annual_contribution)}"
                )
                col_edit, col_del = st.columns([3, 1])
                with col_del:
                    if st.button("✕ Delete", key=f"del_asset_{i}"):
                        profile.assets.pop(i)
                        st.rerun()
    else:
        st.caption("No assets added yet.")

    with st.expander("Add New Asset", expanded=not profile.assets):
        new_asset = asset_form("add_asset")
        if new_asset:
            profile.assets.append(new_asset)
            st.rerun()

    st.divider()

    # ── Debts ─────────────────────────────────────────────────────────────
    st.subheader("Debts")
    if profile.debts:
        for i, debt in enumerate(profile.debts):
            with st.expander(
                f"{debt.name} — {format_gbp(debt.outstanding_balance)} ({debt.category.value})"
            ):
                st.write(
                    f"**Rate:** {debt.interest_rate:.2%}  |  "
                    f"**Monthly Payment:** {format_gbp(debt.monthly_payment)}  |  "
                    f"**Remaining:** {debt.remaining_term_months} months"
                )
                if debt.category.value == "Student Loan":
                    st.caption(
                        " | ".join([
                            f"Plan: {debt.student_loan_plan.value if debt.student_loan_plan else 'Plan 2'}",
                            f"Threshold: {format_gbp(debt.student_loan_repayment_threshold or 0)} / year",
                            f"Rate: {(debt.student_loan_repayment_rate or 0):.1%} above threshold",
                            f"Write-off: {debt.student_loan_write_off_years or 30} years",
                            f"Start Year: {debt.student_loan_start_year or 'n/a'}",
                        ])
                    )
                col_edit, col_del = st.columns([3, 1])
                with col_del:
                    if st.button("✕ Delete", key=f"del_debt_{i}"):
                        profile.debts.pop(i)
                        st.rerun()
    else:
        st.caption("No debts added yet.")

    with st.expander("Add New Debt", expanded=not profile.debts):
        new_debt = debt_form("add_debt")
        if new_debt:
            profile.debts.append(new_debt)
            st.rerun()

# ── Tab 3: Life Goals ────────────────────────────────────────────────────
with tab_goals:
    if profile.life_goals:
        _goals_current_year = date.today().year
        milestones: list[TimelineMilestone] = [
            {"event": g.name, "year": g.target_year, "age": ret.current_age + (g.target_year - _goals_current_year)}
            for g in profile.life_goals
        ]
        fig = milestone_timeline(milestones, title="Life Goals Timeline")
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Funding overview ──────────────────────────────────────────────
        st.subheader("Goal Costs")
        names = []
        total_costs = []
        for g in profile.life_goals:
            names.append(g.name)
            total_costs.append(g.target_cost + g.annual_ongoing_cost * g.ongoing_years)

        fig = bar_chart(names, total_costs, title="Total Cost per Goal (lump + ongoing)")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Summary")
            for g in profile.life_goals:
                total = g.target_cost + (g.annual_ongoing_cost * g.ongoing_years)
                st.write(
                    f"**{g.name}** — {format_gbp(g.target_cost)} lump"
                    + (
                        f" + {format_gbp(g.annual_ongoing_cost)}/yr x {g.ongoing_years}yr"
                        if g.ongoing_years > 0
                        else ""
                    )
                    + f" = **{format_gbp(total)} total**  (age {ret.current_age + (g.target_year - _goals_current_year)})"
                )
        with col2:
            grand_total = sum(
                g.target_cost + g.annual_ongoing_cost * g.ongoing_years for g in profile.life_goals
            )
            st.markdown("#### Grand Total")
            st.metric("All Goals Combined", format_gbp(grand_total))
            liquid_assets = sum(a.current_value for a in profile.assets if a.is_liquid)
            st.metric("Current Liquid Assets", format_gbp(liquid_assets))
            gap = grand_total - liquid_assets
            st.metric(
                "Funding Gap",
                format_gbp(max(0, gap)),
                delta=f"-{format_gbp(gap)}" if gap > 0 else "Fully funded!",
                delta_color="inverse",
            )

        st.divider()

    # ── Manage Goals ──────────────────────────────────────────────────────
    st.subheader("Manage Goals")
    if profile.life_goals:
        _current_year = date.today().year
        for i, goal in enumerate(profile.life_goals):
            _goal_age = ret.current_age + (goal.target_year - _current_year)
            with st.expander(f"{goal.name} — {format_gbp(goal.target_cost)} at age {_goal_age}"):
                updated = goal_form(f"edit_goal_{i}", defaults=goal)
                if updated:
                    profile.life_goals[i] = updated
                    st.rerun()
                if st.button("✕ Delete Goal", key=f"del_goal_{i}"):
                    profile.life_goals.pop(i)
                    st.rerun()
    else:
        st.caption("No goals set.")

    with st.expander("Add New Goal"):
        new_goal = goal_form("add_goal")
        if new_goal:
            profile.life_goals.append(new_goal)
            st.rerun()

# ── Tab 4: Retirement ────────────────────────────────────────────────────
with tab_retirement:
    st.subheader("Retirement Settings")
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        ret.current_age = st.number_input("Current Age", 18, 100, ret.current_age, key="ret_age")
        ret.target_retirement_age = st.number_input(
            "Target Retirement Age", 30, 100, ret.target_retirement_age, key="ret_target"
        )
    with rc2:
        ret.life_expectancy = st.number_input(
            "Life Expectancy", 60, 120, ret.life_expectancy, key="ret_life"
        )
        ret.desired_annual_income = st.number_input(
            "Desired Annual Income (£, today's money)",
            0.0,
            200_000.0,
            float(ret.desired_annual_income),
            step=1000.0,
            key="ret_income",
        )
    with rc3:
        ret.state_pension_age = st.number_input(
            "State Pension Age", 60, 75, ret.state_pension_age, key="ret_spa"
        )
        ret.expected_state_pension = st.number_input(
            "Expected State Pension (£/yr)",
            0.0,
            20_000.0,
            float(ret.expected_state_pension),
            step=500.0,
            key="ret_sp",
        )

    st.divider()

    hc1, hc2 = st.columns(2)
    with hc1:
        st.subheader("Healthcare / Care Costs")
        ret.estimated_healthcare_costs = st.number_input(
            "Estimated Annual Care Cost (£)",
            0.0,
            100_000.0,
            float(ret.estimated_healthcare_costs),
            step=1000.0,
            key="ret_hc",
        )
        ret.healthcare_start_age = st.number_input(
            "Care Costs Start Age", 60, 100, ret.healthcare_start_age, key="ret_hc_age"
        )

    with hc2:
        st.subheader("Retirement Lifestyle")
        monthly_ret_living = st.number_input(
            "Retirement Monthly Living Costs (£)",
            0.0,
            100_000.0,
            float(
                (
                    profile.annual_retirement_living_expenses
                    if profile.annual_retirement_living_expenses is not None
                    else profile.annual_living_expenses
                )
                / 12
            ),
            step=100.0,
            help="Monthly baseline spending after retirement.",
            key="ret_living",
        )
        monthly_ret_holidays = st.number_input(
            "Retirement Monthly Holiday Budget (£)",
            0.0,
            20_000.0,
            float(
                (
                    profile.annual_retirement_holiday_budget
                    if profile.annual_retirement_holiday_budget is not None
                    else profile.annual_holiday_budget
                )
                / 12
            ),
            step=50.0,
            help="Monthly amount for travel and leisure in retirement.",
            key="ret_holidays",
        )
        profile.annual_retirement_living_expenses = monthly_ret_living * 12
        profile.annual_retirement_holiday_budget = monthly_ret_holidays * 12
        st.caption(
            f"Annualized retirement spending: "
            f"{format_gbp(profile.annual_retirement_living_expenses + profile.annual_retirement_holiday_budget)}"
        )
