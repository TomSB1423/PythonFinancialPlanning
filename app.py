"""Financial Planning Playground — Dashboard."""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

from calculations.cashflow import annual_cash_flow
from calculations.net_worth import asset_allocation, net_worth, total_assets, total_debts
from calculations.projections import project_net_worth
from calculations.tax import income_tax, national_insurance
from components.charts import (
    area_chart,
    cash_flow_sankey,
    cash_flow_waterfall,
    donut_chart,
    format_gbp,
)
from components.dashboard_warnings import get_financial_health_checks
from models.financial_data import UserProfile

st.set_page_config(
    page_title="Financial Planning Playground",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Initialise session state ──────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = UserProfile()

profile: UserProfile = st.session_state.profile

# ══════════════════════════════════════════════════════════════════════════
#  SIDEBAR — JSON Import / Export
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("Financial Planner")
    st.caption("Plan your net worth, retirement & life goals")

    st.divider()

    # Profile name
    profile.name = st.text_input("Plan Name", value=profile.name)

    st.divider()

    # ── Export ─────────────────────────────────────────────────────────────
    st.subheader("Save / Load")
    profile.last_updated = date.today()
    json_data = profile.model_dump_json(indent=2)
    st.download_button(
        label="Export Profile (JSON)",
        data=json_data,
        file_name=f"financial_plan_{date.today().isoformat()}.json",
        mime="application/json",
    )

    # ── Import ─────────────────────────────────────────────────────────────
    uploaded = st.file_uploader("Import Profile (JSON)", type=["json"])
    if uploaded is not None:
        try:
            from pydantic_core import ValidationError

            data = json.loads(uploaded.read())
            st.session_state.profile = UserProfile.model_validate(data)
            st.success("Profile loaded successfully")
            st.rerun()
        except json.JSONDecodeError as e:
            st.error(f"**Invalid JSON file**\n{e}")
            st.caption("Make sure the file is valid JSON (exported from this app or valid format).")
        except ValidationError as e:
            st.error("**Profile validation error**")
            error_msg = str(e)
            if "missing" in error_msg.lower():
                st.caption("Some required fields are missing. Check if the file structure is complete.")
            elif "type" in error_msg.lower():
                st.caption("One or more fields have incorrect data types.")
            else:
                st.caption("The file structure doesn't match the expected profile format.")
            with st.expander("Show error details"):
                st.code(error_msg, language="text")
        except Exception as e:
            st.error(f"**Failed to load profile**\n{type(e).__name__}: {e}")
            st.caption("Try exporting a valid profile from this app and checking the file format.")

    # ── Load sample ───────────────────────────────────────────────────────
    if st.button("Load Sample Profile"):
        try:
            with open("data/sample_profile.json") as f:
                data = json.load(f)
            st.session_state.profile = UserProfile.model_validate(data)
            st.success("Sample profile loaded")
            st.rerun()
        except FileNotFoundError:
            st.error("Sample profile not found.")

    st.divider()
    st.caption(f"Last updated: {profile.last_updated}")

# ══════════════════════════════════════════════════════════════════════════
#  MAIN PAGE — Dashboard
# ══════════════════════════════════════════════════════════════════════════
st.title("Dashboard")

if not profile.assets and not profile.debts:
    st.info("Start by adding assets and debts on the Profile page, or load the sample profile from the sidebar.")
    st.stop()

# ── KPI Row ───────────────────────────────────────────────────────────────
ta = total_assets(profile.assets)
td = total_debts(profile.debts)
nw = net_worth(profile.assets, profile.debts)

# Cash flow for current year
cf = annual_cash_flow(profile, yr_offset=0, is_retired=False)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Assets", format_gbp(ta))
c2.metric("Total Debts", format_gbp(td))
c3.metric("Net Worth", format_gbp(nw))
c4.metric("Take-Home Pay", format_gbp(cf.net_take_home))

st.divider()

# ── Cash Flow ─────────────────────────────────────────────────────────────
st.subheader("Cash Flow")
col_sankey, col_waterfall = st.columns(2)
with col_sankey:
    st.plotly_chart(cash_flow_sankey(cf), use_container_width=True)
with col_waterfall:
    st.plotly_chart(cash_flow_waterfall(cf), use_container_width=True)

surplus_label = format_gbp(cf.surplus)
if cf.surplus > 0:
    st.success(f"Annual surplus: {surplus_label} ({format_gbp(cf.surplus / 12)}/mo)")
else:
    st.warning(f"Annual surplus: {surplus_label} — expenses exceed take-home pay")

st.divider()

# ── Charts Row ────────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 2])

with col_left:
    allocation = asset_allocation(profile.assets)
    if allocation:
        labels = list(allocation.keys())
        values = [allocation[k]["value"] for k in labels]
        fig_donut = donut_chart(labels, values, title="Asset Allocation")
        st.plotly_chart(fig_donut, use_container_width=True)

with col_right:
    projection = project_net_worth(profile, years=10, scenario="Base")
    # Identify asset category columns for stacked area
    asset_cols = [c for c in projection.columns if c.startswith("asset_")]
    if asset_cols:
        fig_area = area_chart(projection, x="age", y_cols=asset_cols, title="10-Year Asset Projection", stacked=True)
    else:
        fig_area = area_chart(projection, x="age", y_cols=["net_worth"], title="10-Year Net Worth Projection", stacked=False)
    st.plotly_chart(fig_area, use_container_width=True)

# ── Financial Health Alerts ───────────────────────────────────────────────
alerts = get_financial_health_checks(profile)
if alerts:
    st.divider()
    st.subheader("Financial Health")
    for alert in alerts:
        message = f"**{alert.title}** — {alert.message}"
        if alert.severity == "error":
            st.error(message)
        elif alert.severity == "warning":
            st.warning(message)
        else:
            st.info(message)
