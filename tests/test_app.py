"""UI integration tests — verify pages render and calculations integrate correctly."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from calculations.net_worth import net_worth
from components.charts import format_gbp
from models.financial_data import UserProfile

# ── 1. Main app loads ─────────────────────────────────────────────────────

def test_app_loads() -> None:
    """The welcome page renders without errors."""
    at = AppTest.from_file("app.py")
    at.run()
    assert not at.error, [e.value for e in at.error]


# ── 2. Profile page with sample data ─────────────────────────────────────

def test_profile_renders_with_sample_data(sample_profile: UserProfile) -> None:
    """Profile page renders KPI metrics when a populated profile is loaded."""
    at = AppTest.from_file("pages/1_Profile.py")
    at.session_state.profile = sample_profile
    at.session_state.assets_initialised = True
    at.session_state.debts_initialised = True
    at.session_state.goals_initialised = True
    at.run()
    assert not at.error, [e.value for e in at.error]
    assert len(at.metric) >= 3, "Expected at least 3 KPI metrics (assets, debts, net worth)"


# ── 3. Plan page with empty profile ──────────────────────────────────────

def test_plan_handles_empty_profile(empty_profile: UserProfile) -> None:
    """Plan page shows an info message instead of crashing when profile is empty."""
    at = AppTest.from_file("pages/2_Plan.py")
    at.session_state.profile = empty_profile
    at.run()
    assert not at.error, [e.value for e in at.error]
    assert len(at.info) >= 1, "Expected an info message for empty profile"


# ── 4. Plan page renders with sample data ─────────────────────────────────

def test_plan_renders_with_sample_data(sample_profile: UserProfile) -> None:
    """Plan page renders projections, KPIs, and charts with sample data."""
    at = AppTest.from_file("pages/2_Plan.py")
    at.session_state.profile = sample_profile
    at.run()
    assert not at.error, [e.value for e in at.error]
    assert len(at.metric) >= 4, "Expected at least 4 KPI metrics"


# ── 5. Calculation-to-UI integration ─────────────────────────────────────

def test_net_worth_calculations_match_plan(sample_profile: UserProfile) -> None:
    """The net worth metric displayed on the Plan page matches the calculation module."""
    expected_nw = net_worth(sample_profile.assets, sample_profile.debts)
    expected_label = format_gbp(expected_nw)

    at = AppTest.from_file("pages/2_Plan.py")
    at.session_state.profile = sample_profile
    at.run()

    nw_metric = at.metric[0]  # 1st metric is "Net Worth"
    assert nw_metric.label == "Net Worth"
    assert nw_metric.value == expected_label, (
        f"Plan shows {nw_metric.value} but calculation gives {expected_label}"
    )
