"""Debts — Liability tracking and payoff projections."""

from __future__ import annotations

from datetime import date

import streamlit as st

from calculations.net_worth import total_debts
from calculations.projections import debt_payoff_projection
from components.charts import area_chart, format_gbp, line_chart
from models.financial_data import DebtCategory, UserProfile

st.set_page_config(page_title="Debts", layout="wide")

# ── Session state ─────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile

st.title("Debts")

if not profile.debts:
    st.success("No outstanding debts")
    st.stop()

# ── KPI Row ───────────────────────────────────────────────────────────────
td = total_debts(profile.debts)
total_monthly = sum(d.monthly_payment for d in profile.debts)
dti = (total_monthly * 12 / profile.annual_salary * 100) if profile.annual_salary > 0 else 0.0

# Find debt-free year from projection
payoff_df = debt_payoff_projection(profile, years=40)
balance_cols = [c for c in payoff_df.columns if c.endswith("_balance")]
if balance_cols:
    payoff_df["total_balance"] = payoff_df[balance_cols].sum(axis=1)
    debt_free_rows = payoff_df[payoff_df["total_balance"] <= 0]
    debt_free_year = int(debt_free_rows.iloc[0]["year"]) if not debt_free_rows.empty else None
    debt_free_age = int(debt_free_rows.iloc[0]["age"]) if not debt_free_rows.empty else None
else:
    debt_free_year = None
    debt_free_age = None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Debts", format_gbp(td))
c2.metric("Monthly Payments", format_gbp(total_monthly))
c3.metric("Debt-to-Income", f"{dti:.1f}%")
c4.metric("Debt-Free", f"Age {debt_free_age}" if debt_free_age else "40+ years")

st.divider()

# ── Debt Overview Cards ───────────────────────────────────────────────────
for debt in profile.debts:
    with st.expander(f"{debt.name} — {format_gbp(debt.outstanding_balance)} ({debt.category.value})"):
        dc1, dc2, dc3 = st.columns(3)
        dc1.metric("Balance", format_gbp(debt.outstanding_balance))
        dc2.metric("Rate", f"{debt.interest_rate:.2%}")
        if debt.category == DebtCategory.STUDENT_LOAN:
            dc3.metric("Plan", debt.student_loan_plan.value if debt.student_loan_plan else "Plan 2")
            sc1, sc2, sc3 = st.columns(3)
            sc1.write(f"Threshold: {format_gbp(debt.student_loan_repayment_threshold or 0)}/yr")
            sc2.write(f"Repayment: {(debt.student_loan_repayment_rate or 0.09):.0%} above threshold")
            write_off_year = (debt.student_loan_start_year or date.today().year) + (debt.student_loan_write_off_years or 30)
            sc3.write(f"Write-off: {write_off_year}")
        else:
            dc3.metric("Monthly Payment", format_gbp(debt.monthly_payment))
            term_years = debt.remaining_term_months / 12
            st.caption(f"Remaining term: {term_years:.1f} years")

st.divider()

# ── Debt Payoff Projection Chart ──────────────────────────────────────────
st.subheader("Payoff Projection")

if balance_cols and len(payoff_df) > 1:
    # Trim to when all debts are paid off (plus a buffer)
    if debt_free_year:
        display_df = payoff_df[payoff_df["year"] <= debt_free_year + 2].copy()
    else:
        display_df = payoff_df.copy()

    fig_payoff = area_chart(
        display_df,
        x="age",
        y_cols=balance_cols,
        title="Debt Balances Over Time",
        stacked=True,
    )
    st.plotly_chart(fig_payoff, use_container_width=True)

# ── Student Loan Detail ──────────────────────────────────────────────────
student_loans = [d for d in profile.debts if d.category == DebtCategory.STUDENT_LOAN]
if student_loans:
    st.divider()
    st.subheader("Student Loan Projection")
    for loan in student_loans:
        col_name = f"{loan.name}_balance"
        if col_name in payoff_df.columns:
            loan_df = payoff_df[["age", col_name]].copy()
            loan_df = loan_df[loan_df[col_name] > 0]
            if not loan_df.empty:
                fig_sl = line_chart(loan_df, x="age", y=col_name, title=f"{loan.name} Balance")
                # Add write-off annotation
                write_off_yr = (loan.student_loan_start_year or date.today().year) + (loan.student_loan_write_off_years or 30)
                write_off_age = profile.retirement.current_age + (write_off_yr - date.today().year)
                fig_sl.add_vline(
                    x=write_off_age, line_dash="dash", line_color="#D32F2F", opacity=0.7,
                    annotation_text="Write-off", annotation_position="top left",
                )
                st.plotly_chart(fig_sl, use_container_width=True)
