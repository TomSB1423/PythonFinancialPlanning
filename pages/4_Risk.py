"""Risk — Insurance coverage and emergency fund dashboard."""

from __future__ import annotations

import streamlit as st

from components.charts import bar_chart, format_gbp
from models.financial_data import InsurancePolicy, InsuranceType, UserProfile

st.set_page_config(page_title="Risk", layout="wide")

# ── Ensure profile ────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile

st.title("Risk Management")
st.caption("Insurance coverage, emergency fund, and financial resilience.")

# ── KPI row ───────────────────────────────────────────────────────────────
ef = profile.emergency_fund
monthly_expenses = (profile.annual_living_expenses + profile.annual_holiday_budget) / 12
ef_target = monthly_expenses * ef.target_months
ef_coverage_months = ef.current_balance / monthly_expenses if monthly_expenses > 0 else 0.0
total_cover = sum(p.cover_amount for p in profile.insurance_policies)
annual_premiums = sum(p.monthly_premium * 12 for p in profile.insurance_policies)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Emergency Fund", format_gbp(ef.current_balance))
k2.metric("Months Covered", f"{ef_coverage_months:.1f} / {ef.target_months}")
k3.metric("Total Insurance Cover", format_gbp(total_cover))
k4.metric("Annual Premiums", format_gbp(annual_premiums))

st.divider()

tab_emergency, tab_insurance = st.tabs(["Emergency Fund", "Insurance"])

# ── Tab 1: Emergency Fund ─────────────────────────────────────────────────
with tab_emergency:
    st.subheader("Emergency Fund")

    e1, e2 = st.columns(2)
    with e1:
        ef.current_balance = st.number_input(
            "Current Emergency Fund Balance (£)",
            0.0, 500_000.0, float(ef.current_balance), step=500.0,
            key="ef_balance",
        )
        ef.target_months = st.number_input(
            "Target Months of Expenses",
            1, 24, ef.target_months,
            key="ef_months",
            help="Typical recommendation is 3–6 months for employed, 6–12 for self-employed.",
        )

    with e2:
        st.metric("Monthly Expenses", format_gbp(monthly_expenses))
        st.metric("Target Emergency Fund", format_gbp(ef_target))
        shortfall = max(0.0, ef_target - ef.current_balance)
        st.metric(
            "Shortfall",
            format_gbp(shortfall),
            delta=f"-{format_gbp(shortfall)}" if shortfall > 0 else "Target met",
            delta_color="inverse",
        )

    if ef.current_balance >= ef_target:
        st.success(f"Your emergency fund covers {ef_coverage_months:.1f} months of expenses.")
    elif ef_coverage_months >= 3:
        st.warning(
            f"Your emergency fund covers {ef_coverage_months:.1f} months. "
            f"Consider building to {ef.target_months} months ({format_gbp(ef_target)})."
        )
    else:
        st.warning(
            f"Your emergency fund only covers {ef_coverage_months:.1f} months. "
            "Aim for at least 3 months of expenses as a minimum buffer."
        )

    st.divider()
    st.subheader("What Should an Emergency Fund Cover?")
    st.markdown("""
- **Rent / mortgage payments** — typically the largest monthly commitment
- **Utility bills** — gas, electricity, water, broadband
- **Food and essential groceries**
- **Minimum debt repayments** — credit cards, loans
- **Insurance premiums** — essential cover you cannot let lapse
- **Transport costs** — fuel, public transport for work

A healthy emergency fund is held in an **easy-access savings account** (not investments), so it is available immediately without penalty.
""")

# ── Tab 2: Insurance ──────────────────────────────────────────────────────
with tab_insurance:
    st.subheader("Insurance Policies")

    if profile.insurance_policies:
        for i, pol in enumerate(profile.insurance_policies):
            with st.expander(
                f"{pol.name} — {pol.insurance_type.value} | "
                f"Cover: {format_gbp(pol.cover_amount)} | "
                f"Premium: {format_gbp(pol.monthly_premium)}/mo"
            ):
                st.write(
                    f"**Type:** {pol.insurance_type.value}  |  "
                    f"**Cover:** {format_gbp(pol.cover_amount)}  |  "
                    f"**Monthly Premium:** {format_gbp(pol.monthly_premium)}"
                )
                if pol.expiry_year:
                    st.caption(f"Expires: {pol.expiry_year}")
                if pol.notes:
                    st.caption(pol.notes)
                if st.button("✕ Remove", key=f"del_pol_{i}"):
                    profile.insurance_policies.pop(i)
                    st.rerun()
    else:
        st.caption("No insurance policies added yet.")

    st.divider()

    with st.expander("Add Insurance Policy", expanded=not profile.insurance_policies):
        p1, p2 = st.columns(2)
        with p1:
            new_name = st.text_input("Policy Name", key="new_pol_name")
            new_type = st.selectbox(
                "Type", [t.value for t in InsuranceType], key="new_pol_type"
            )
            new_cover = st.number_input(
                "Cover Amount (£)", 0.0, 10_000_000.0, 0.0, step=10_000.0, key="new_pol_cover"
            )
        with p2:
            new_premium = st.number_input(
                "Monthly Premium (£)", 0.0, 10_000.0, 0.0, step=5.0, key="new_pol_premium"
            )
            new_expiry = st.number_input(
                "Expiry Year (optional)", 2024, 2100, 2030, key="new_pol_expiry"
            )
            new_notes = st.text_input("Notes (optional)", key="new_pol_notes")

        if st.button("Add Policy", key="btn_add_pol"):
            if new_name:
                profile.insurance_policies.append(InsurancePolicy(
                    name=new_name,
                    insurance_type=InsuranceType(new_type),
                    cover_amount=new_cover,
                    monthly_premium=new_premium,
                    expiry_year=int(new_expiry) if new_expiry else None,
                    notes=new_notes,
                ))
                st.rerun()
            else:
                st.warning("Please enter a policy name.")

    # ── Coverage summary chart ─────────────────────────────────────────────
    if profile.insurance_policies:
        st.divider()
        st.subheader("Coverage by Type")
        type_cover: dict[str, float] = {}
        for pol in profile.insurance_policies:
            t = pol.insurance_type.value
            type_cover[t] = type_cover.get(t, 0.0) + pol.cover_amount
        fig = bar_chart(
            list(type_cover.keys()),
            list(type_cover.values()),
            title="Total Cover Amount by Insurance Type",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Insurance Checklist")
    st.markdown("""
Use this checklist to ensure you have adequate coverage:

| Insurance Type | Why It Matters | Typical Cover |
|----------------|---------------|---------------|
| Life | Replaces income for dependants | 10× salary or mortgage balance |
| Income Protection | Replaces income if unable to work | 50–70% of gross income |
| Critical Illness | Lump sum on serious diagnosis | Mortgage balance + living costs |
| Buildings | Required by mortgage lender | Rebuild cost of property |
| Contents | Replaces household belongings | Market value of possessions |
| Private Medical | Faster access to treatment | Varies |

**Rule of thumb for life cover:** At least enough to repay the mortgage plus 5–10 years of income for dependants.
""")
