"""Year-by-year net worth projection engine."""

from __future__ import annotations

from datetime import date
from typing import TypedDict

import pandas as pd

from calculations.cashflow import annual_cash_flow
from calculations.instruments import (
    AssetState,
    MortgageGoalState,
    StandardDebtState,
    _mortgage_monthly_payment,
    create_debt_state,
    create_goal_state,
)
from models.assumptions import SALARY_GROWTH_RATE, SCENARIOS
from models.financial_data import DebtCategory, GoalFunding, UserProfile


class Milestone(TypedDict):
    event: str
    year: int
    age: int


class DecisionImpact(TypedDict):
    goal_name: str
    net_worth_delta_at_retirement: float
    net_worth_delta_at_end: float


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

    # ── Initialise state objects from profile ──────────────────────────
    assets: list[AssetState] = [
        AssetState.from_model(a, scenario_multiplier=multiplier)
        for a in profile.assets
    ]
    debts = [create_debt_state(d) for d in profile.debts]
    goals = [create_goal_state(g) for g in profile.life_goals]

    # Pre-compute goal lump / ongoing spending by year
    goal_spending: dict[int, float] = {}
    goal_ongoing: dict[int, float] = {}
    for g in goals:
        goal_spending[g.target_year] = goal_spending.get(g.target_year, 0) + g.lump_sum_cost()
        for y in range(years + 1):
            yr = current_year + y
            oc = g.ongoing_cost(yr)
            if oc > 0:
                goal_ongoing[yr] = goal_ongoing.get(yr, 0) + oc

    # Dynamic debts spawned by goal activation
    dynamic_debts: list[StandardDebtState] = []

    for yr_offset in range(years + 1):
        year = current_year + yr_offset
        is_retired = year >= retirement_year
        salary = profile.annual_salary * (1 + SALARY_GROWTH_RATE) ** yr_offset

        # ── Compute active debt payments (excl. credit cards) ──────────
        mortgage_payments = sum(
            d.annual_payment for d in debts
            if not d.is_cleared and d.category == DebtCategory.MORTGAGE.value
        ) + sum(
            d.annual_payment for d in dynamic_debts
            if not d.is_cleared
        )
        loan_payments = sum(
            d.annual_payment for d in debts
            if not d.is_cleared
            and d.category not in (DebtCategory.MORTGAGE.value, DebtCategory.STUDENT_LOAN.value, DebtCategory.CREDIT_CARD.value)
        )

        ongoing = goal_ongoing.get(year, 0)

        # ── Cash flow waterfall ────────────────────────────────────────
        cf = annual_cash_flow(
            profile,
            yr_offset=yr_offset,
            is_retired=is_retired,
            active_mortgage_payments=mortgage_payments,
            active_loan_payments=loan_payments,
            active_goal_ongoing=ongoing,
        )

        # ── Snapshot totals ────────────────────────────────────────────
        total_assets = sum(a.value for a in assets)
        total_debts = sum(d.balance for d in debts) + sum(d.balance for d in dynamic_debts)
        nw = total_assets - total_debts

        by_cat: dict[str, float] = {}
        for a in assets:
            by_cat[a.category] = by_cat.get(a.category, 0) + a.value

        lump = goal_spending.get(year, 0)
        total_goal_cost = lump + ongoing

        age = profile.retirement.current_age + yr_offset

        row: dict[str, int | float] = {
            "year": year,
            "age": age,
            "total_assets": round(total_assets, 2),
            "total_debts": round(total_debts, 2),
            "net_worth": round(nw, 2),
            "goal_spending": round(total_goal_cost, 2),
            "gross_salary": cf.gross_salary,
            "net_take_home": cf.net_take_home,
            "total_expenses": cf.total_outflows,
            "surplus": cf.surplus,
        }
        for cat, value in by_cat.items():
            row[f"asset_{cat}"] = round(value, 2)
        rows.append(row)

        if yr_offset == years:
            break

        # ── Grow assets ────────────────────────────────────────────────
        for a in assets:
            a.grow()
            a.contribute(is_retired)

        # ── Distribute surplus to liquid assets ────────────────────────
        if not is_retired and cf.surplus > 0:
            liquid_assets = [a for a in assets if a.is_liquid and a.value > 0]
            if liquid_assets:
                per_asset = cf.surplus / len(liquid_assets)
                for a in liquid_assets:
                    a.deposit(per_asset)

        # ── Pay down debts ─────────────────────────────────────────────
        for d in debts:
            d.accrue_and_pay(salary, is_retired, year)
        for d in dynamic_debts:
            d.accrue_and_pay(salary, is_retired, year)

        # ── Activate goals ─────────────────────────────────────────────
        for g in goals:
            if g.target_year == year:
                new_assets, new_debts = g.activate(multiplier)
                assets.extend(new_assets)
                dynamic_debts.extend(new_debts)

        # ── Deduct goal spending from liquid assets ────────────────────
        if total_goal_cost > 0:
            liquid_assets = [a for a in assets if a.is_liquid and a.value > 0]
            liquid_total = sum(a.value for a in liquid_assets)
            if liquid_total > 0:
                for a in liquid_assets:
                    share = a.value / liquid_total
                    a.withdraw(total_goal_cost * share)

    df = pd.DataFrame(rows)
    return df.fillna(0)


def find_milestones(projection: pd.DataFrame, profile: UserProfile) -> list[Milestone]:
    """Identify key milestones from a projection DataFrame."""
    milestones: list[Milestone] = []

    current_year = date.today().year
    current_age = profile.retirement.current_age

    def _age_for_year(yr: int) -> int:
        return current_age + (yr - current_year)

    # When net worth hits certain thresholds
    for target in [100_000, 250_000, 500_000, 1_000_000]:
        hits = projection[projection["net_worth"] >= target]
        if not hits.empty:
            yr = int(hits.iloc[0]["year"])
            milestones.append({
                "event": f"Net worth reaches £{target:,.0f}",
                "year": yr,
                "age": _age_for_year(yr),
            })

    # When debts hit zero
    if profile.debts:
        debt_free = projection[projection["total_debts"] <= 0]
        if not debt_free.empty:
            yr = int(debt_free.iloc[0]["year"])
            milestones.append({
                "event": "Debt free",
                "year": yr,
                "age": _age_for_year(yr),
            })

    # Mortgage payoff year (first year with zero mortgage debt)
    mortgage_payoff = mortgage_payoff_year(projection, profile)
    if mortgage_payoff is not None:
        milestones.append({
            "event": "Mortgage paid off",
            "year": mortgage_payoff,
            "age": _age_for_year(mortgage_payoff),
        })

    # Life goal years
    for g in profile.life_goals:
        milestones.append({
            "event": f"Goal: {g.name}",
            "year": g.target_year,
            "age": _age_for_year(g.target_year),
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

    # Original mortgage debts as state objects
    mortgages: list[StandardDebtState] = [
        StandardDebtState.from_model(d)
        for d in profile.debts
        if d.category == DebtCategory.MORTGAGE and d.outstanding_balance > 0
    ]
    had_mortgages = bool(mortgages)

    # Goals that will spawn mortgages
    mortgage_goals = [
        MortgageGoalState(g)
        for g in profile.life_goals
        if g.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED)
    ]

    for yr_offset in range(years + 1):
        year = current_year + yr_offset

        # Activate mortgage-funded goals in their target year
        for g in mortgage_goals:
            if g.target_year == year:
                _, new_debts = g.activate(1.0)
                mortgages.extend(new_debts)
                had_mortgages = True

        total = sum(m.balance for m in mortgages)
        if total <= 0 and yr_offset > 0 and had_mortgages:
            return year

        for m in mortgages:
            m.accrue_and_pay(0.0, False, year)

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


# ── Per-debt payoff projection ─────────────────────────────────────────────


def debt_payoff_projection(
    profile: UserProfile,
    years: int = 30,
) -> pd.DataFrame:
    """Year-by-year balance for each debt.

    Returns a DataFrame with columns: year, age, and one
    ``{debt_name}_balance`` column per debt.
    """
    current_year = date.today().year
    debt_states = [create_debt_state(d) for d in profile.debts]

    if not debt_states:
        return pd.DataFrame(columns=["year", "age"])

    rows: list[dict[str, int | float]] = []

    for yr_offset in range(years + 1):
        year = current_year + yr_offset
        age = profile.retirement.current_age + yr_offset
        retirement_year = current_year + max(
            0, profile.retirement.target_retirement_age - profile.retirement.current_age,
        )
        is_retired = year >= retirement_year

        row: dict[str, int | float] = {"year": year, "age": age}
        for ds in debt_states:
            row[f"{ds.name}_balance"] = round(ds.balance, 2)
        rows.append(row)

        if yr_offset == years:
            break

        salary = profile.annual_salary * (1 + SALARY_GROWTH_RATE) ** yr_offset
        for ds in debt_states:
            ds.accrue_and_pay(salary, is_retired, year)

    return pd.DataFrame(rows)
