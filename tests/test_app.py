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


# ── 3. Property page with empty profile ──────────────────────────────────

def test_property_handles_empty_profile(empty_profile: UserProfile) -> None:
    """Property page shows an info message when no properties exist."""
    at = AppTest.from_file("pages/2_Property.py")
    at.session_state.profile = empty_profile
    at.run()
    assert not at.error, [e.value for e in at.error]
    assert len(at.info) >= 1, "Expected an info message for empty profile"


# ── 4. Goals page with empty profile ─────────────────────────────────────

def test_goals_handles_empty_profile(empty_profile: UserProfile) -> None:
    """Goals page shows an info message when no goals exist."""
    at = AppTest.from_file("pages/5_Goals.py")
    at.session_state.profile = empty_profile
    at.run()
    assert not at.error, [e.value for e in at.error]
    assert len(at.info) >= 1, "Expected an info message for empty profile"


# ── 5. Dashboard KPI integration ─────────────────────────────────────────

def test_dashboard_net_worth_matches_calculation(sample_profile: UserProfile) -> None:
    """The net worth metric on the dashboard matches the calculation module."""
    expected_nw = net_worth(sample_profile.assets, sample_profile.debts)
    expected_label = format_gbp(expected_nw)

    at = AppTest.from_file("app.py")
    at.session_state.profile = sample_profile
    at.run()

    nw_metrics = [m for m in at.metric if m.label == "Net Worth"]
    assert nw_metrics, "Expected a Net Worth metric on the dashboard"
    assert nw_metrics[0].value == expected_label, (
        f"Dashboard shows {nw_metrics[0].value} but calculation gives {expected_label}"
    )
