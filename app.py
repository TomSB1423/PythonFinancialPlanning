"""Financial Planning Playground — Main entry point."""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

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
            import json

            from pydantic_core import ValidationError

            data = json.loads(uploaded.read())
            st.session_state.profile = UserProfile.model_validate(data)
            st.success("✓ Profile loaded successfully!")
            st.rerun()
        except json.JSONDecodeError as e:
            st.error(f"**Invalid JSON file**\n{e}")
            st.caption("Make sure the file is valid JSON (exported from this app or valid format).")
        except ValidationError as e:
            st.error("**Profile validation error**")
            error_msg = str(e)
            # Extract key info from validation error
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
            st.success("Sample profile loaded!")
            st.rerun()
        except FileNotFoundError:
            st.error("Sample profile not found.")

    st.divider()
    st.caption(f"Last updated: {profile.last_updated}")

# ══════════════════════════════════════════════════════════════════════════
#  MAIN PAGE — Welcome
# ══════════════════════════════════════════════════════════════════════════
st.title("Financial Planning Playground")
st.markdown("""
Welcome to your personal financial planning tool.

- **Track your net worth** — assets, debts, liquidity, and diversification
- **Plan major life goals** — toggle goals on and off to see their impact on your finances
- **Model your retirement** — income needs, savings gap, drawdown strategy
- **Explore scenarios** — optimistic, base, and pessimistic projections with confidence bands

### Getting Started

1. **Profile** — Enter your income, assets, debts, goals, and retirement settings
2. **Plan** — Explore interactive projections, toggle goals, and compare scenarios

Use the sidebar to **import/export** your data as JSON, or **load a sample profile** to explore.
""")

# Quick stats if data exists
if profile.assets or profile.debts:
    st.divider()
    st.subheader("Quick Summary")
    ta = sum(a.current_value for a in profile.assets)
    td = sum(d.outstanding_balance for d in profile.debts)
    nw = ta - td

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Assets", f"£{ta:,.0f}")
    c2.metric("Debts", f"£{td:,.0f}")
    c3.metric("Net Worth", f"£{nw:,.0f}")
    c4.metric("Goals", str(len(profile.life_goals)))
else:
    st.info("Start by adding assets and debts on the Profile page, or load the sample profile from the sidebar.")
