"""Tax — UK tax analysis and optimisation dashboard."""

from __future__ import annotations

import streamlit as st

from calculations.tax import (
    IHTResult,
    IncomeTaxResult,
    capital_gains_tax,
    income_tax,
    inheritance_tax,
    national_insurance,
)
from components.charts import bar_chart, donut_chart, format_gbp
from models.assumptions import (
    CGT_ANNUAL_EXEMPT,
    IHT_NIL_RATE_BAND,
    IHT_RESIDENCE_NIL_RATE_BAND,
    ISA_ANNUAL_ALLOWANCE,
    PENSION_ANNUAL_ALLOWANCE,
)
from models.financial_data import AssetCategory, TaxWrapper, UserProfile

st.set_page_config(page_title="Tax", layout="wide")

# ── Ensure profile ────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()
profile: UserProfile = st.session_state.profile

st.title("Tax Analysis")

# ── KPI row ───────────────────────────────────────────────────────────────
it: IncomeTaxResult = income_tax(profile.annual_salary)
ni = national_insurance(profile.annual_salary)
total_tax = it["tax"] + ni
take_home = profile.annual_salary - total_tax

k1, k2, k3, k4 = st.columns(4)
k1.metric("Gross Salary", format_gbp(profile.annual_salary))
k2.metric("Income Tax", format_gbp(it["tax"]))
k3.metric("National Insurance", format_gbp(ni))
k4.metric("Take-Home Pay", format_gbp(take_home))

st.divider()

# ══════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════
tab_income, tab_cgt, tab_iht, tab_wrappers = st.tabs(
    ["Income Tax & NI", "Capital Gains Tax", "Inheritance Tax", "Tax Wrappers"]
)

# ── Tab 1: Income Tax ─────────────────────────────────────────────────────
with tab_income:
    st.subheader("Income Tax Breakdown")
    if it["breakdown"]:
        bands = [b["band"] for b in it["breakdown"]]
        taxes = [b["tax"] for b in it["breakdown"]]
        fig = bar_chart(bands, taxes, title="Income Tax by Band")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Band Detail")
        for b in it["breakdown"]:
            st.write(
                f"**{b['band']}** — taxable {format_gbp(b['taxable'])} "
                f"× {b['rate']:.0%} = **{format_gbp(b['tax'])}**"
            )
    else:
        st.info("No income tax due at current salary.")

    st.divider()
    st.subheader("National Insurance")
    col1, col2 = st.columns(2)
    col1.metric("NI Contributions", format_gbp(ni))
    col2.metric(
        "Effective NI Rate",
        f"{ni / profile.annual_salary:.1%}" if profile.annual_salary > 0 else "0.0%",
    )

    st.divider()
    st.subheader("Take-Home Summary")
    labels = ["Income Tax", "National Insurance", "Take-Home"]
    values = [it["tax"], ni, take_home]
    fig = donut_chart(labels, values, title="Gross Salary Split")
    st.plotly_chart(fig, use_container_width=True)

    if profile.annual_salary > 0:
        st.markdown(
            f"**Effective income tax rate:** {it['effective_rate']:.1%}  |  "
            f"**Combined effective rate:** {total_tax / profile.annual_salary:.1%}"
        )
    else:
        st.caption("Enter a salary on the Profile page.")

# ── Tab 2: Capital Gains Tax ──────────────────────────────────────────────
with tab_cgt:
    st.subheader("Capital Gains Tax Estimate")
    st.info(
        f"The annual CGT exempt amount is {format_gbp(CGT_ANNUAL_EXEMPT)}. "
        "Gains above this threshold are taxed at 10% (basic rate) or 20% (higher/additional rate) "
        "for investments, or 18%/24% for residential property."
    )

    cgt_col1, cgt_col2 = st.columns(2)
    with cgt_col1:
        estimated_gain = st.number_input(
            "Estimated Realised Gain (£)", 0.0, 5_000_000.0, 0.0, step=1_000.0,
            help="Total capital gain you plan to realise this tax year.",
        )
        is_property_gain = st.checkbox("Gain is from residential property?")
        is_higher_rate_taxpayer = st.checkbox(
            "Higher / additional rate taxpayer?",
            value=profile.annual_salary > 50_270,
        )

    with cgt_col2:
        cgt_due = capital_gains_tax(estimated_gain, is_property_gain, is_higher_rate_taxpayer)
        st.metric("CGT Due", format_gbp(cgt_due))
        st.metric("Net Gain After Tax", format_gbp(max(0.0, estimated_gain - cgt_due)))
        if estimated_gain > 0:
            effective_cgt = cgt_due / estimated_gain
            st.metric("Effective CGT Rate", f"{effective_cgt:.1%}")

    if estimated_gain > 0:
        fig = bar_chart(
            ["Exempt (AEA)", "CGT Due", "Net Gain"],
            [min(estimated_gain, CGT_ANNUAL_EXEMPT), cgt_due, max(0.0, estimated_gain - cgt_due)],
            title="CGT Breakdown",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("CGT Planning Tips")
    st.markdown("""
- **Bed & ISA / Bed & SIPP**: Sell investments and re-buy inside an ISA or pension to shelter future gains.
- **Spouse transfers**: Assets transferred between spouses are free of CGT — use both allowances.
- **Losses**: Capital losses can be offset against gains in the same or future tax years.
- **Timing**: Spread disposals across tax years to use the annual exempt amount each year.
""")

# ── Tab 3: Inheritance Tax ────────────────────────────────────────────────
with tab_iht:
    st.subheader("Inheritance Tax Estimate")
    st.info(
        "IHT is charged at 40% on estates above the nil-rate band (£325,000) and residence "
        "nil-rate band (£175,000). Pensions are generally outside of your estate."
    )

    total_assets_val = sum(a.current_value for a in profile.assets)
    pension_assets = sum(
        a.current_value for a in profile.assets
        if a.category == AssetCategory.PENSION or a.tax_wrapper == TaxWrapper.PENSION
    )
    debts_val = sum(d.outstanding_balance for d in profile.debts)
    default_estate = max(0.0, total_assets_val - pension_assets - debts_val)

    iht_col1, iht_col2 = st.columns(2)
    with iht_col1:
        estate_value = st.number_input(
            "Estimated Estate Value (£)",
            0.0, 20_000_000.0,
            float(default_estate), step=10_000.0,
            help="Total estate value (assets minus debts, excluding pensions).",
        )
        has_property = st.checkbox("Owns residential property left to direct descendants?", value=True)
        spouse_transfer = st.checkbox(
            "Inheriting unused spousal nil-rate bands?",
            help="If your spouse died without using their allowances, you can inherit them (doubling both bands).",
        )
        charity_fraction = st.slider(
            "Fraction of estate left to charity", 0.0, 1.0, 0.0, step=0.01,
            help="Leaving 10%+ to charity reduces the IHT rate from 40% to 36%.",
        )

    result: IHTResult = inheritance_tax(estate_value, has_property, spouse_transfer, charity_fraction)

    with iht_col2:
        st.metric("Gross Estate", format_gbp(result["gross_estate"]))
        st.metric("Nil-Rate Band", format_gbp(result["nil_rate_band_used"]))
        st.metric("Residence NRB", format_gbp(result["residence_nil_rate_band_used"]))
        st.metric("Taxable Estate", format_gbp(result["taxable_estate"]))
        st.metric("IHT Due", format_gbp(result["iht_due"]))
        st.metric("Effective IHT Rate", f"{result['effective_rate']:.1%}")

    if estate_value > 0:
        exempt = estate_value - result["taxable_estate"] - result["iht_due"]
        fig = bar_chart(
            ["Exempt (bands)", "Taxable", "IHT Due"],
            [max(0.0, exempt), result["taxable_estate"], result["iht_due"]],
            title="Estate Split",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("IHT Planning Tips")
    total_band = IHT_NIL_RATE_BAND + (IHT_RESIDENCE_NIL_RATE_BAND if has_property else 0)
    st.markdown(f"""
- **Annual gift exemption**: You can give away up to £3,000 per year free of IHT.
- **7-year rule**: Gifts made more than 7 years before death are fully exempt.
- **Spouse / civil partner**: All assets passed to a spouse are 100% exempt from IHT.
- **Pension nomination**: Pension funds are generally outside your estate — nominate beneficiaries.
- **Life insurance in trust**: Writing a life policy in trust means the payout bypasses your estate.
- **Current threshold**: £{total_band:,.0f} (nil-rate band + residence nil-rate band).
""")

# ── Tab 4: Tax Wrappers ───────────────────────────────────────────────────
with tab_wrappers:
    st.subheader("Tax Wrapper Usage")
    st.info(
        "Maximising tax-efficient wrappers (ISA, pension) can significantly reduce your lifetime tax burden."
    )

    isa_contributions = sum(
        a.annual_contribution for a in profile.assets
        if a.tax_wrapper == TaxWrapper.ISA
    )
    pension_contributions = sum(
        a.annual_contribution for a in profile.assets
        if a.tax_wrapper == TaxWrapper.PENSION
    )

    w1, w2 = st.columns(2)
    with w1:
        st.markdown("#### ISA")
        isa_remaining = max(0.0, ISA_ANNUAL_ALLOWANCE - isa_contributions)
        st.metric("Annual ISA Allowance", format_gbp(ISA_ANNUAL_ALLOWANCE))
        st.metric("Current ISA Contributions", format_gbp(isa_contributions))
        st.metric("Remaining ISA Allowance", format_gbp(isa_remaining))
        if isa_contributions < ISA_ANNUAL_ALLOWANCE:
            st.info(f"You have {format_gbp(isa_remaining)} of ISA allowance remaining this year.")
        else:
            st.success("ISA allowance fully used.")

    with w2:
        st.markdown("#### Pension")
        pension_remaining = max(0.0, PENSION_ANNUAL_ALLOWANCE - pension_contributions)
        st.metric("Annual Pension Allowance", format_gbp(PENSION_ANNUAL_ALLOWANCE))
        st.metric("Current Pension Contributions", format_gbp(pension_contributions))
        st.metric("Remaining Pension Allowance", format_gbp(pension_remaining))
        if pension_contributions < PENSION_ANNUAL_ALLOWANCE:
            st.info(f"You have {format_gbp(pension_remaining)} of pension allowance remaining this year.")
        else:
            st.success("Pension allowance fully used.")

    st.divider()
    st.subheader("Asset Values by Tax Wrapper")
    wrapper_values: dict[str, float] = {}
    for a in profile.assets:
        w = a.tax_wrapper.value
        wrapper_values[w] = wrapper_values.get(w, 0.0) + a.current_value

    if wrapper_values:
        fig = donut_chart(
            list(wrapper_values.keys()),
            list(wrapper_values.values()),
            title="Current Assets by Tax Wrapper",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No assets to display.")

    st.markdown("""
#### Wrapper Comparison

| Wrapper | Tax on Growth | Tax on Withdrawal | Annual Limit |
|---------|--------------|-------------------|--------------|
| ISA | None | None | £20,000 |
| SIPP / Pension | None | Income tax on 75% | £60,000 |
| GIA | CGT on gains, income tax on dividends | None | Unlimited |
| Cash (non-ISA) | Income tax on interest | None | Unlimited |
""")
