"""Property — Property portfolio and mortgage deep dive."""

from __future__ import annotations

import streamlit as st

from calculations.property import (
    amortization_schedule,
    calculate_equity,
    calculate_ltv,
    equity_over_time,
    property_profit,
)
from components.charts import area_chart, bar_chart, format_gbp, line_chart
from models.financial_data import AssetCategory, DebtCategory, GoalFunding, UserProfile

st.set_page_config(page_title="Property", layout="wide")

# ── Session state ─────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile

st.title("Property")

# ── Gather property data ─────────────────────────────────────────────────
property_assets = [a for a in profile.assets if a.category == AssetCategory.PROPERTY]
mortgage_debts = [d for d in profile.debts if d.category == DebtCategory.MORTGAGE]

# Also consider mortgage-funded goals that haven't activated yet
mortgage_goals = [
    g for g in profile.life_goals
    if g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED)
]

if not property_assets and not mortgage_goals:
    st.info("No properties found. Add a property asset or mortgage-funded goal on the Profile page.")
    st.stop()

# ── KPI Row ───────────────────────────────────────────────────────────────
total_property_value = sum(a.current_value for a in property_assets)
total_mortgage_balance = sum(d.outstanding_balance for d in mortgage_debts)
total_equity = total_property_value - total_mortgage_balance
avg_ltv = calculate_ltv(total_mortgage_balance, total_property_value) if total_property_value > 0 else 0.0
total_monthly_payments = sum(d.monthly_payment for d in mortgage_debts)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Property Value", format_gbp(total_property_value))
c2.metric("Total Equity", format_gbp(total_equity))
c3.metric("Avg LTV", f"{avg_ltv:.1f}%")
c4.metric("Monthly Mortgage Payments", format_gbp(total_monthly_payments))

st.divider()

# ── Per-property detail ───────────────────────────────────────────────────
for prop in property_assets:
    # Find matching mortgage by name convention
    matching_mortgage = next(
        (d for d in mortgage_debts if d.name.lower().replace("mortgage", "").strip()
         in prop.name.lower() or prop.name.lower() in d.name.lower()),
        None,
    )
    if matching_mortgage is None and len(property_assets) == 1 and len(mortgage_debts) == 1:
        matching_mortgage = mortgage_debts[0]

    mortgage_balance = matching_mortgage.outstanding_balance if matching_mortgage else 0.0
    equity = calculate_equity(prop.current_value, mortgage_balance)
    ltv = calculate_ltv(mortgage_balance, prop.current_value)

    with st.expander(f"{prop.name} — {format_gbp(prop.current_value)}", expanded=True):
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("Value", format_gbp(prop.current_value))
        pc2.metric("Equity", format_gbp(equity))
        pc3.metric("LTV", f"{ltv:.1f}%")
        if matching_mortgage:
            pc4.metric("Monthly Payment", format_gbp(matching_mortgage.monthly_payment))
            rate = matching_mortgage.interest_rate
            term_months = matching_mortgage.remaining_term_months
            term_years = max(1, term_months // 12)

            st.caption(
                f"Mortgage balance: {format_gbp(mortgage_balance)} · "
                f"Rate: {rate:.2%} · "
                f"Remaining: {term_years} years"
            )

            # ── Equity growth chart ───────────────────────────────────────
            eq_df = equity_over_time(
                property_value=prop.current_value,
                growth_rate=prop.annual_growth_rate,
                mortgage_principal=mortgage_balance,
                mortgage_rate=rate,
                term_years=term_years,
                projection_years=term_years,
            )

            col_eq, col_ltv = st.columns(2)
            with col_eq:
                fig_eq = area_chart(
                    eq_df, x="year",
                    y_cols=["property_value", "mortgage_balance"],
                    title="Equity Growth",
                    stacked=False,
                )
                st.plotly_chart(fig_eq, use_container_width=True)

            with col_ltv:
                fig_ltv = line_chart(eq_df, x="year", y="ltv", title="LTV Over Time")
                fig_ltv.update_layout(yaxis_title="LTV (%)", yaxis_tickformat=".1f")
                st.plotly_chart(fig_ltv, use_container_width=True)

            # ── Amortization breakdown ────────────────────────────────────
            amort_df = amortization_schedule(mortgage_balance, rate, term_years)
            if not amort_df.empty:
                total_interest = amort_df["interest_paid"].sum()
                profit = property_profit(
                    prop.current_value * (1 + prop.annual_growth_rate) ** term_years,
                    prop.current_value,
                    total_interest,
                )
                st.metric("Estimated Profit (at end of term)", format_gbp(profit))

                fig_amort = bar_chart(
                    [f"Yr {int(r['year'])}" for _, r in amort_df.iterrows()],
                    amort_df["interest_paid"].tolist(),
                    title="Annual Interest Paid",
                )
                st.plotly_chart(fig_amort, use_container_width=True)
        else:
            pc4.metric("Mortgage", "None")
            st.caption("No mortgage linked to this property.")

# ── Upcoming mortgage-funded goals ────────────────────────────────────────
if mortgage_goals:
    st.divider()
    st.subheader("Planned Property Purchases")
    for g in mortgage_goals:
        deposit = g.target_cost * g.deposit_percentage
        mortgage_amount = g.target_cost - deposit
        st.write(
            f"**{g.name}** — {format_gbp(g.target_cost)} in {g.target_year} · "
            f"Deposit: {format_gbp(deposit)} ({g.deposit_percentage:.0%}) · "
            f"Mortgage: {format_gbp(mortgage_amount)} at {g.mortgage_rate:.2%} over {g.mortgage_term_years}yr"
        )
