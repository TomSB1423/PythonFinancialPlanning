"""Year-by-year net worth projection engine."""

from __future__ import annotations

from datetime import date
from typing import TypedDict

import numpy_financial as npf
import pandas as pd

from models.assumptions import GROWTH_RATES, SCENARIOS
from models.financial_data import DebtCategory, GoalFunding, UserProfile


class MortgageState(TypedDict):
    balance: float
    rate: float
    annual_payment: float
    remaining_years: int


class Milestone(TypedDict):
    event: str
    year: int


class DecisionImpact(TypedDict):
    goal_name: str
    net_worth_delta_at_retirement: float
    net_worth_delta_at_end: float


def _mortgage_monthly_payment(principal: float, annual_rate: float, term_years: int) -> float:
    """Calculate monthly mortgage repayment using numpy-financial."""
    if principal <= 0 or term_years <= 0:
        return 0.0
    if annual_rate <= 0:
        return principal / (term_years * 12)
    return float(-npf.pmt(annual_rate / 12, term_years * 12, principal))


def project_net_worth(
    profile: UserProfile,
    years: int = 40,
    scenario: str = "Base",
) -> pd.DataFrame:
    """Project net worth year by year, incorporating growth, debt paydown,
    contributions, salary savings, and life-goal spending events."""
    multiplier = SCENARIOS.get(scenario, 1.0)
    current_year = date.today().year
    retirement_year = current_year + max(0, profile.retirement.target_retirement_age - profile.retirement.current_age)
    rows: list[dict[str, int | float]] = []

    # Snapshot asset values (mutable copies)
    asset_values = {i: a.current_value for i, a in enumerate(profile.assets)}
    asset_contribs = {i: a.annual_contribution for i, a in enumerate(profile.assets)}
    asset_growth = {
        i: GROWTH_RATES.get(a.category.value, 0.04) * multiplier
        for i, a in enumerate(profile.assets)
    }
    asset_cats = {i: a.category.value for i, a in enumerate(profile.assets)}
    asset_liquid = {i: a.is_liquid for i, a in enumerate(profile.assets)}

    # Snapshot debt balances
    debt_balances = {i: d.outstanding_balance for i, d in enumerate(profile.debts)}
    debt_rates = {i: d.interest_rate for i, d in enumerate(profile.debts)}
    debt_payments = {i: d.monthly_payment * 12 for i, d in enumerate(profile.debts)}
    debt_cats = {i: d.category for i, d in enumerate(profile.debts)}

    # Track dynamically added mortgages: {goal_name: {balance, rate, annual_payment, remaining_years}}
    dynamic_mortgages: dict[str, MortgageState] = {}

    # Life goals indexed by year — separate mortgage vs savings goals
    goal_spending: dict[int, float] = {}   # cash to deduct from liquid assets
    goal_ongoing: dict[int, float] = {}

    for g in profile.life_goals:
        if g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED):
            # Only the deposit comes from savings
            deposit = g.target_cost * g.deposit_percentage
            goal_spending[g.target_year] = goal_spending.get(g.target_year, 0) + deposit
        else:
            goal_spending[g.target_year] = goal_spending.get(g.target_year, 0) + g.target_cost

        for y in range(g.target_year, g.target_year + g.ongoing_years):
            goal_ongoing[y] = goal_ongoing.get(y, 0) + g.annual_ongoing_cost

    # Annual savings from salary (distributed across liquid assets)
    annual_salary_savings = profile.annual_salary * 0 if profile.annual_salary <= 0 else (
        # Use the explicit monthly_savings from the profile if we can find it,
        # otherwise distribute proportionally. We read it from the model.
        getattr(profile, "monthly_savings", 0) * 12
    )

    for yr_offset in range(years + 1):
        year = current_year + yr_offset
        is_retired = year >= retirement_year

        # Sum current values
        total_assets = sum(asset_values.values())
        mortgage_debt = sum(m["balance"] for m in dynamic_mortgages.values())
        total_debts = sum(debt_balances.values()) + mortgage_debt
        nw = total_assets - total_debts

        # Per-category breakdown
        by_cat: dict[str, float] = {}
        for i, val in asset_values.items():
            cat = asset_cats[i]
            by_cat[cat] = by_cat.get(cat, 0) + val

        # Goal spending this year
        lump = goal_spending.get(year, 0)
        ongoing = goal_ongoing.get(year, 0)
        total_goal_cost = lump + ongoing

        row: dict[str, int | float] = {
            "year": year,
            "total_assets": round(total_assets, 2),
            "total_debts": round(total_debts, 2),
            "net_worth": round(nw, 2),
            "goal_spending": round(total_goal_cost, 2),
        }
        for cat, value in by_cat.items():
            row[f"asset_{cat}"] = round(value, 2)
        rows.append(row)

        if yr_offset == years:
            break

        # ── Grow assets for next year ──────────────────────────────────
        for i in asset_values:
            asset_values[i] *= (1 + asset_growth[i])
            # Add contributions only while working
            if not is_retired:
                asset_values[i] += asset_contribs.get(i, 0)

        # Distribute salary savings across liquid assets (while working)
        # Deduct active mortgage payments from the savings pool first
        if not is_retired and annual_salary_savings > 0:
            original_mortgage_payments = sum(
                debt_payments[i] for i in debt_balances
                if debt_balances[i] > 0 and debt_cats.get(i) == DebtCategory.MORTGAGE
            )
            dynamic_mortgage_payments = sum(
                m["annual_payment"] for m in dynamic_mortgages.values() if m["balance"] > 0
            )
            effective_savings = max(0, annual_salary_savings - original_mortgage_payments - dynamic_mortgage_payments)
            liquid_ids = [i for i in asset_values if asset_liquid.get(i, False) and asset_values[i] > 0]
            if liquid_ids and effective_savings > 0:
                per_asset = effective_savings / len(liquid_ids)
                for i in liquid_ids:
                    asset_values[i] += per_asset

        # ── Pay down original debts ────────────────────────────────────
        for i in list(debt_balances.keys()):
            if debt_balances[i] <= 0:
                continue
            payment = min(debt_payments[i], debt_balances[i] + debt_balances[i] * debt_rates[i])
            # Approximate mid-year interest: interest accrues on the average balance
            principal_portion = payment - debt_balances[i] * debt_rates[i]
            avg_balance = debt_balances[i] - max(0, principal_portion) / 2
            interest = avg_balance * debt_rates[i]
            debt_balances[i] = max(0, debt_balances[i] + interest - payment)

        # ── Pay down dynamic mortgages ─────────────────────────────────
        for name in list(dynamic_mortgages.keys()):
            m = dynamic_mortgages[name]
            if m["balance"] <= 0:
                del dynamic_mortgages[name]
                continue
            payment = min(m["annual_payment"], m["balance"] + m["balance"] * m["rate"])
            principal_portion = payment - m["balance"] * m["rate"]
            avg_balance = m["balance"] - max(0, principal_portion) / 2
            interest = avg_balance * m["rate"]
            m["balance"] = max(0, m["balance"] + interest - m["annual_payment"])
            m["remaining_years"] -= 1
            if m["remaining_years"] <= 0 or m["balance"] <= 0:
                m["balance"] = 0

        # ── Handle goal spending ───────────────────────────────────────
        # Create mortgage debts for mortgage-funded goals in their target year
        for g in profile.life_goals:
            if g.target_year == year and g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED):
                mortgage_principal = g.target_cost * (1 - g.deposit_percentage)
                monthly_pmt = _mortgage_monthly_payment(mortgage_principal, g.mortgage_rate, g.mortgage_term_years)
                dynamic_mortgages[g.name] = {
                    "balance": mortgage_principal,
                    "rate": g.mortgage_rate,
                    "annual_payment": monthly_pmt * 12,
                    "remaining_years": g.mortgage_term_years,
                }
                # Add the property as an asset
                next_asset_id = max(asset_values.keys(), default=-1) + 1
                asset_values[next_asset_id] = g.target_cost
                asset_growth[next_asset_id] = GROWTH_RATES.get("Property", 0.04) * multiplier
                asset_cats[next_asset_id] = "Property"
                asset_contribs[next_asset_id] = 0
                asset_liquid[next_asset_id] = False

        # Deduct cash goal spending from liquid assets (proportionally)
        if total_goal_cost > 0:
            liquid_ids = [
                i for i in asset_values
                if asset_liquid.get(i, False) and asset_values.get(i, 0) > 0
            ]
            liquid_total = sum(asset_values[i] for i in liquid_ids)
            if liquid_total > 0:
                for i in liquid_ids:
                    share = asset_values[i] / liquid_total
                    deduction = min(asset_values[i], total_goal_cost * share)
                    asset_values[i] -= deduction

    df = pd.DataFrame(rows)
    # Fill NaN category columns with 0
    return df.fillna(0)


def find_milestones(projection: pd.DataFrame, profile: UserProfile) -> list[Milestone]:
    """Identify key milestones from a projection DataFrame."""
    milestones: list[Milestone] = []

    # When net worth hits certain thresholds
    for target in [100_000, 250_000, 500_000, 1_000_000]:
        hits = projection[projection["net_worth"] >= target]
        if not hits.empty:
            milestones.append({
                "event": f"Net worth reaches £{target:,.0f}",
                "year": int(hits.iloc[0]["year"]),
            })

    # When debts hit zero
    if profile.debts:
        debt_free = projection[projection["total_debts"] <= 0]
        if not debt_free.empty:
            milestones.append({
                "event": "Debt free",
                "year": int(debt_free.iloc[0]["year"]),
            })

    # Mortgage payoff year (first year with zero mortgage debt)
    mortgage_payoff = mortgage_payoff_year(projection, profile)
    if mortgage_payoff is not None:
        milestones.append({
            "event": "Mortgage paid off",
            "year": mortgage_payoff,
        })

    # Life goal years
    for g in profile.life_goals:
        milestones.append({
            "event": f"Goal: {g.name}",
            "year": g.target_year,
        })

    milestones.sort(key=lambda m: m["year"])
    return milestones


def mortgage_payoff_year(projection: pd.DataFrame, profile: UserProfile) -> int | None:
    """Return the first projected year where all mortgage debt reaches zero.

    Considers both original mortgage debts and mortgage-funded life goals.
    Returns ``None`` if no mortgage exists or it doesn't pay off within the
    projection horizon.
    """
    has_mortgage = any(d.category == DebtCategory.MORTGAGE for d in profile.debts) or any(
        g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED) for g in profile.life_goals
    )
    if not has_mortgage:
        return None

    # Re-run a lightweight simulation to track mortgage-specific balances.
    # We reuse the full projection's total_debts as a proxy: the first year
    # where total_debts equals zero (or only non-mortgage debt remains) is
    # what we want.  However, total_debts also includes student loans etc.
    # Instead, we compute it by running the projection engine and tracking
    # mortgage balances directly.  Since the projection is already computed,
    # we look for the debt-free milestone as an upper bound.  For a more
    # precise answer we run a dedicated tracking loop below.
    return _track_mortgage_payoff(profile, len(projection) - 1)


# ── Filtered projections & decision impact ─────────────────────────────────


def _track_mortgage_payoff(profile: UserProfile, years: int) -> int | None:
    """Simulate mortgage-only paydown to find the payoff year."""
    current_year = date.today().year

    # Original mortgage debts
    mortgage_balances: dict[str, float] = {}
    mortgage_rates: dict[str, float] = {}
    mortgage_payments: dict[str, float] = {}

    for d in profile.debts:
        if d.category == DebtCategory.MORTGAGE and d.outstanding_balance > 0:
            mortgage_balances[d.name] = d.outstanding_balance
            mortgage_rates[d.name] = d.interest_rate
            mortgage_payments[d.name] = d.monthly_payment * 12

    # Dynamic mortgages from life goals
    dynamic: dict[str, MortgageState] = {}
    had_mortgages = bool(mortgage_balances)

    for yr_offset in range(years + 1):
        year = current_year + yr_offset

        # Check if a mortgage-funded goal triggers this year
        for g in profile.life_goals:
            if g.target_year == year and g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED):
                principal = g.target_cost * (1 - g.deposit_percentage)
                monthly_pmt = _mortgage_monthly_payment(principal, g.mortgage_rate, g.mortgage_term_years)
                dynamic[g.name] = {
                    "balance": principal,
                    "rate": g.mortgage_rate,
                    "annual_payment": monthly_pmt * 12,
                    "remaining_years": g.mortgage_term_years,
                }
                had_mortgages = True

        # Total mortgage balance this year
        total = sum(mortgage_balances.values()) + sum(m["balance"] for m in dynamic.values())
        if total <= 0 and yr_offset > 0 and had_mortgages:
            return year

        # Pay down original mortgages
        for name in list(mortgage_balances.keys()):
            bal = mortgage_balances[name]
            if bal <= 0:
                del mortgage_balances[name]
                continue
            pmt = min(mortgage_payments[name], bal + bal * mortgage_rates[name])
            principal_portion = pmt - bal * mortgage_rates[name]
            avg_bal = bal - max(0, principal_portion) / 2
            interest = avg_bal * mortgage_rates[name]
            mortgage_balances[name] = max(0, bal + interest - pmt)
            if mortgage_balances[name] <= 0:
                del mortgage_balances[name]

        # Pay down dynamic mortgages
        for name in list(dynamic.keys()):
            m = dynamic[name]
            if m["balance"] <= 0:
                del dynamic[name]
                continue
            pmt = min(m["annual_payment"], m["balance"] + m["balance"] * m["rate"])
            principal_portion = pmt - m["balance"] * m["rate"]
            avg_bal = m["balance"] - max(0, principal_portion) / 2
            interest = avg_bal * m["rate"]
            m["balance"] = max(0, m["balance"] + interest - m["annual_payment"])
            m["remaining_years"] -= 1
            if m["remaining_years"] <= 0 or m["balance"] <= 0:
                del dynamic[name]

    return None


class MortgageRetirementInfo(TypedDict):
    has_mortgage: bool
    payoff_year: int | None
    extends_into_retirement: bool
    mortgage_years_in_retirement: int
    annual_mortgage_payment: float


def mortgage_info_at_retirement(profile: UserProfile, projection_years: int = 40) -> MortgageRetirementInfo:
    """Compute how a user's mortgage intersects with their retirement.

    Returns the payoff year, whether it extends into retirement, how many
    retirement years have mortgage payments, and the total annual payment.
    """
    current_year = date.today().year
    retirement_year = current_year + max(
        0, profile.retirement.target_retirement_age - profile.retirement.current_age,
    )

    has_mortgage = any(d.category == DebtCategory.MORTGAGE for d in profile.debts) or any(
        g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED) for g in profile.life_goals
    )

    if not has_mortgage:
        return {
            "has_mortgage": False,
            "payoff_year": None,
            "extends_into_retirement": False,
            "mortgage_years_in_retirement": 0,
            "annual_mortgage_payment": 0.0,
        }

    # Sum annual mortgage payments (original + future dynamic)
    annual_payment = sum(
        d.monthly_payment * 12 for d in profile.debts
        if d.category == DebtCategory.MORTGAGE and d.outstanding_balance > 0
    )
    for g in profile.life_goals:
        if g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED):
            principal = g.target_cost * (1 - g.deposit_percentage)
            annual_payment += _mortgage_monthly_payment(principal, g.mortgage_rate, g.mortgage_term_years) * 12

    payoff = _track_mortgage_payoff(profile, projection_years)
    extends = payoff is not None and payoff > retirement_year
    mortgage_years_in_ret = max(0, (payoff or retirement_year) - retirement_year) if extends else 0

    return {
        "has_mortgage": True,
        "payoff_year": payoff,
        "extends_into_retirement": extends,
        "mortgage_years_in_retirement": mortgage_years_in_ret,
        "annual_mortgage_payment": round(annual_payment, 2),
    }


# ── Filtered projections & decision impact ─────────────────────────────────


def project_net_worth_filtered(
    profile: UserProfile,
    excluded_goals: set[str],
    years: int = 40,
    scenario: str = "Base",
) -> pd.DataFrame:
    """Run a projection with a subset of life goals excluded by name."""
    filtered = profile.model_copy(deep=True)
    filtered.life_goals = [g for g in filtered.life_goals if g.name not in excluded_goals]
    return project_net_worth(filtered, years=years, scenario=scenario)


def compute_decision_impacts(
    profile: UserProfile,
    disabled_goal_names: set[str],
    years: int = 40,
    scenario: str = "Base",
) -> list[DecisionImpact]:
    """For each disabled goal, compute the net worth impact of re-enabling it.

    Returns a list of DecisionImpact dicts — one per disabled goal — showing how
    much net worth would *decrease* at retirement and at the end of the projection
    if that goal were included.
    """
    if not disabled_goal_names:
        return []

    # Baseline: projection with the disabled goals excluded (current view)
    baseline = project_net_worth_filtered(profile, disabled_goal_names, years, scenario)
    retirement_year = (
        date.today().year
        + max(0, profile.retirement.target_retirement_age - profile.retirement.current_age)
    )

    results: list[DecisionImpact] = []
    for goal_name in sorted(disabled_goal_names):
        # Re-enable just this one goal
        with_goal = project_net_worth_filtered(
            profile, disabled_goal_names - {goal_name}, years, scenario,
        )
        # Delta at retirement year
        base_at_ret = baseline.loc[baseline["year"] == retirement_year, "net_worth"]
        with_at_ret = with_goal.loc[with_goal["year"] == retirement_year, "net_worth"]
        delta_ret = (
            float(base_at_ret.iloc[0]) - float(with_at_ret.iloc[0])
            if not base_at_ret.empty and not with_at_ret.empty
            else 0.0
        )
        # Delta at end of projection
        delta_end = float(baseline.iloc[-1]["net_worth"]) - float(with_goal.iloc[-1]["net_worth"])
        results.append({
            "goal_name": goal_name,
            "net_worth_delta_at_retirement": delta_ret,
            "net_worth_delta_at_end": delta_end,
        })
    return results
