"""Retirement planning calculations."""

from __future__ import annotations

from typing import TypedDict

import pandas as pd

from calculations.tax import pension_drawdown_tax
from models.assumptions import INFLATION_RATE, PENSION_TAX_FREE_LUMP_SUM_RATE
from models.financial_data import Asset, AssetCategory, RetirementProfile, UserProfile

INVESTABLE_CATEGORIES: frozenset[AssetCategory] = frozenset({
    AssetCategory.PENSION,
    AssetCategory.ISA,
    AssetCategory.GIA,
})


class RetirementIncomeGapResult(TypedDict):
    desired_annual_income_today: float
    state_pension: float
    guaranteed_income: float
    annual_gap: float
    phase1_years: int
    phase1_guaranteed: float
    phase1_gap: float
    phase2_years: int
    phase2_guaranteed: float
    phase2_gap: float


class DrawdownRow(TypedDict):
    year: int
    start_balance: float
    withdrawal: float
    tax: float
    net_withdrawal: float
    growth: float
    other_income: float
    healthcare_cost: float
    end_balance: float


def inflation_adjusted(amount: float, years: int, inflation_rate: float = INFLATION_RATE) -> float:
    """What *amount* today is worth in *years* time (purchasing-power eroded)."""
    return round(amount / ((1 + inflation_rate) ** years), 2)


def future_value(amount: float, years: int, rate: float) -> float:
    """Compound an amount forward."""
    return round(amount * ((1 + rate) ** years), 2)


def retirement_income_gap(
    profile: RetirementProfile,
    mortgage_annual_payment: float = 0.0,
    mortgage_years_in_retirement: int = 0,
) -> RetirementIncomeGapResult:
    """Annual shortfall between desired income and guaranteed sources.

    Returns two phases for early retirees:
    - Phase 1: retirement age -> state pension age (no state pension)
    - Phase 2: state pension age -> life expectancy (with state pension)

    When *mortgage_annual_payment* > 0 and *mortgage_years_in_retirement* > 0,
    the mortgage cost is added to the gap for those early retirement years.
    """
    desired_real = profile.desired_annual_income  # in today's money

    # Phase 1: retirement to state pension age (no state pension)
    phase1_years = max(0, profile.state_pension_age - profile.target_retirement_age)
    phase1_guaranteed = 0.0
    phase1_gap = max(0, desired_real - phase1_guaranteed)

    # Phase 2: state pension age to life expectancy
    phase2_years = max(0, profile.life_expectancy - max(profile.target_retirement_age, profile.state_pension_age))
    state_pension = profile.expected_state_pension
    phase2_guaranteed = state_pension
    phase2_gap = max(0, desired_real - phase2_guaranteed)

    # Blended annual gap (weighted average for pot sizing)
    total_retirement_years = phase1_years + phase2_years
    if total_retirement_years > 0:
        blended_gap = (phase1_gap * phase1_years + phase2_gap * phase2_years) / total_retirement_years
    else:
        blended_gap = 0.0

    # Add mortgage cost for the years it overlaps with retirement
    if mortgage_annual_payment > 0 and mortgage_years_in_retirement > 0 and total_retirement_years > 0:
        mortgage_years_capped = min(mortgage_years_in_retirement, total_retirement_years)
        blended_gap += (mortgage_annual_payment * mortgage_years_capped) / total_retirement_years
        # Also bump phase gaps for the affected years
        if phase1_years > 0:
            mortgage_in_phase1 = min(mortgage_years_capped, phase1_years)
            phase1_gap += mortgage_annual_payment * mortgage_in_phase1 / phase1_years
        if phase2_years > 0:
            mortgage_in_phase2 = max(0, mortgage_years_capped - phase1_years)
            phase2_gap += mortgage_annual_payment * mortgage_in_phase2 / phase2_years

    return {
        "desired_annual_income_today": desired_real,
        "state_pension": state_pension,
        "guaranteed_income": phase2_guaranteed,
        "annual_gap": round(blended_gap, 2),
        # Phased detail
        "phase1_years": phase1_years,
        "phase1_guaranteed": phase1_guaranteed,
        "phase1_gap": round(phase1_gap, 2),
        "phase2_years": phase2_years,
        "phase2_guaranteed": phase2_guaranteed,
        "phase2_gap": round(phase2_gap, 2),
    }


def required_pot_size(
    annual_gap: float,
    years_in_retirement: int,
    growth_rate: float = 0.04,
    inflation_rate: float = INFLATION_RATE,
    mortgage_annual_payment: float = 0.0,
    mortgage_years_in_retirement: int = 0,
) -> float:
    """How large a DC pot is needed to bridge the annual gap for N years.

    Uses a growing-annuity present-value formula so that withdrawals
    increase with *inflation_rate* each year while the pot grows at
    *growth_rate*.

    When *mortgage_annual_payment* > 0 and *mortgage_years_in_retirement* > 0,
    a two-phase calculation is used: the first N mortgage years require a
    higher withdrawal, and the remaining years use the base gap.
    """
    if annual_gap <= 0 or years_in_retirement <= 0:
        return 0.0
    g = inflation_rate
    r = growth_rate

    def _pv_annuity(gap: float, n: int) -> float:
        if gap <= 0 or n <= 0:
            return 0.0
        if abs(r - g) < 1e-9:
            return gap * n / (1 + r)
        pv_factor = (1 - ((1 + g) / (1 + r)) ** n) / (r - g)
        return gap * pv_factor

    if mortgage_annual_payment > 0 and mortgage_years_in_retirement > 0:
        mortgage_yrs = min(mortgage_years_in_retirement, years_in_retirement)
        post_mortgage_yrs = years_in_retirement - mortgage_yrs
        # Phase 1: base gap + mortgage payment
        pv_mortgage_phase = _pv_annuity(annual_gap + mortgage_annual_payment, mortgage_yrs)
        # Phase 2: base gap only, discounted back from end of phase 1
        pv_post_raw = _pv_annuity(annual_gap, post_mortgage_yrs)
        # Discount the post-mortgage PV back to retirement start
        discount = ((1 + g) / (1 + r)) ** mortgage_yrs
        pv_post_phase = pv_post_raw * discount
        return round(pv_mortgage_phase + pv_post_phase, 2)

    return round(_pv_annuity(annual_gap, years_in_retirement), 2)


def savings_needed(
    target_pot: float,
    current_savings: float,
    years_to_retirement: int,
    growth_rate: float = 0.07,
) -> float:
    """Monthly savings needed to reach target_pot from current_savings.

    Uses monthly compounding for accuracy.
    """
    if years_to_retirement <= 0:
        return max(0, target_pot - current_savings)
    fv_current = current_savings * ((1 + growth_rate) ** years_to_retirement)
    shortfall = max(0, target_pot - fv_current)
    if shortfall == 0:
        return 0.0
    # Monthly compounding: convert annual rate to monthly rate
    monthly_rate = (1 + growth_rate) ** (1 / 12) - 1
    n_months = years_to_retirement * 12
    fv_annuity_factor = ((1 + monthly_rate) ** n_months - 1) / monthly_rate
    return float(round(shortfall / fv_annuity_factor, 2))


def drawdown_simulation(
    pot: float,
    annual_withdrawal: float,
    growth_rate: float = 0.04,
    inflation_rate: float = INFLATION_RATE,
    years: int = 30,
    other_income: float = 0.0,
    state_pension: float = 0.0,
    state_pension_starts_year: int = 0,
    additional_annual_cost: float = 0.0,
    additional_cost_starts_year: int = 0,
    use_tax_free_cash_on_first_withdrawal: bool = True,
    mortgage_annual_payment: float = 0.0,
    mortgage_years_remaining: int = 0,
    start_age: int | None = None,
) -> pd.DataFrame:
    """Year-by-year drawdown simulation accounting for inflation and tax.

    State pension phases in at *state_pension_starts_year* (1-indexed year
    within retirement).

    When *mortgage_annual_payment* > 0, the mortgage cost is added to the
    withdrawal for the first *mortgage_years_remaining* years of retirement.
    """
    rows: list[DrawdownRow] = []
    balance = pot

    # PCLS: 25% of the initial pot is available tax-free, capped at £268,275
    pcls_cap = 268_275.0
    if use_tax_free_cash_on_first_withdrawal:
        tax_free_remaining = min(pot * PENSION_TAX_FREE_LUMP_SUM_RATE, pcls_cap)
    else:
        tax_free_remaining = 0.0

    for year in range(1, years + 1):
        # Phase in state pension at the correct year
        if state_pension_starts_year > 0 and year >= state_pension_starts_year:
            year_other_income = other_income + state_pension
        else:
            year_other_income = other_income

        care_cost = 0.0
        if additional_annual_cost > 0 and additional_cost_starts_year > 0 and year >= additional_cost_starts_year:
            care_cost = additional_annual_cost * ((1 + inflation_rate) ** (year - additional_cost_starts_year))

        # The withdrawal needed from the pot reduces once state pension kicks in.
        # Add mortgage payment for the years it's still active.
        mortgage_cost = mortgage_annual_payment if (mortgage_annual_payment > 0 and year <= mortgage_years_remaining) else 0.0
        desired_total = annual_withdrawal * ((1 + inflation_rate) ** (year - 1)) + care_cost + mortgage_cost
        withdrawal_from_pot = max(0, desired_total - year_other_income)

        if balance <= 0:
            row: DrawdownRow = {
                "year": year,
                "start_balance": 0.0,
                "withdrawal": 0.0,
                "tax": 0.0,
                "net_withdrawal": 0.0,
                "growth": 0.0,
                "other_income": round(year_other_income, 2),
                "healthcare_cost": round(care_cost, 2),
                "end_balance": 0.0,
            }
            if start_age is not None:
                row["age"] = start_age + year - 1  # type: ignore[typeddict-unknown-key]
            rows.append(row)
            continue

        actual_withdrawal = min(withdrawal_from_pot, balance)
        year_tax_free = min(tax_free_remaining, actual_withdrawal)
        tax_info = pension_drawdown_tax(actual_withdrawal, year_other_income, tax_free_amount=year_tax_free)
        tax_free_remaining -= year_tax_free
        growth = (balance - actual_withdrawal) * growth_rate
        end_balance = balance - actual_withdrawal + growth

        row = {
            "year": year,
            "start_balance": round(balance, 2),
            "withdrawal": round(actual_withdrawal, 2),
            "tax": tax_info["tax"],
            "net_withdrawal": tax_info["net_withdrawal"],
            "growth": round(growth, 2),
            "other_income": round(year_other_income, 2),
            "healthcare_cost": round(care_cost, 2),
            "end_balance": round(max(0, end_balance), 2),
        }
        if start_age is not None:
            row["age"] = start_age + year - 1
        rows.append(row)
        balance = max(0, end_balance)

    return pd.DataFrame(rows)


def investable_pot(assets: list[Asset]) -> float:
    """Sum of current values for Pension, ISA, and GIA assets."""
    return sum(a.current_value for a in assets if a.category in INVESTABLE_CATEGORIES)


def retirement_readiness(current_pot: float, target_pot: float) -> float:
    """Simple percentage score of how funded retirement is."""
    if target_pot <= 0:
        return 100.0
    return round(min(100, current_pot / target_pot * 100), 1)


def healthcare_cost_projection(
    annual_cost: float,
    start_age: int,
    life_expectancy: int,
    inflation_rate: float = INFLATION_RATE,
    growth_rate: float = 0.04,
    retirement_age: int | None = None,
) -> float:
    """Present-value of healthcare costs discounted at portfolio growth rate.

    Costs start at *start_age*, grow with inflation each year, and are
    discounted back to retirement date using *growth_rate*.  If
    *retirement_age* is given the deferral period from retirement to
    *start_age* is accounted for; otherwise costs are valued as of
    *start_age*.
    """
    care_years = max(0, life_expectancy - start_age)
    if care_years == 0 or annual_cost <= 0:
        return 0.0
    defer = max(0, start_age - retirement_age) if retirement_age is not None else 0
    total = 0.0
    for y in range(care_years):
        future_cost = annual_cost * ((1 + inflation_rate) ** (defer + y))
        total += future_cost / ((1 + growth_rate) ** (defer + y))
    return round(total, 2)


# ── FIRE calculation ───────────────────────────────────────────────────────


def years_to_fire(
    profile: UserProfile,
    growth_rate: float = 0.04,
    inflation_rate: float = INFLATION_RATE,
) -> int | None:
    """Number of years until pension assets reach the required FIRE pot size.

    Returns ``None`` if the target is never reached within 60 years.
    """
    from calculations.projections import mortgage_info_at_retirement

    mortgage_info = mortgage_info_at_retirement(profile)
    gap_result = retirement_income_gap(
        profile.retirement,
        mortgage_annual_payment=mortgage_info["annual_mortgage_payment"],
        mortgage_years_in_retirement=mortgage_info["mortgage_years_in_retirement"],
    )
    years_in_retirement = max(
        0,
        profile.retirement.life_expectancy - profile.retirement.target_retirement_age,
    )
    target = required_pot_size(
        gap_result["annual_gap"],
        years_in_retirement,
        growth_rate=growth_rate,
        inflation_rate=inflation_rate,
        mortgage_annual_payment=mortgage_info["annual_mortgage_payment"],
        mortgage_years_in_retirement=mortgage_info["mortgage_years_in_retirement"],
    )
    if target <= 0:
        return 0

    # Simulate investable pot growth year by year
    inv_assets = [
        a for a in profile.assets if a.category in INVESTABLE_CATEGORIES
    ]
    pot = sum(a.current_value for a in inv_assets)
    annual_contribution = sum(a.annual_contribution for a in inv_assets)

    # If no explicit pension contribution, estimate from cash flow surplus
    if annual_contribution == 0:
        from calculations.cashflow import annual_cash_flow

        cf = annual_cash_flow(profile, yr_offset=0, is_retired=False)
        if cf.surplus > 0:
            annual_contribution = cf.surplus * 0.5  # assume half of surplus to pension

    for yr in range(61):
        if pot >= target:
            return yr
        pot = pot * (1 + growth_rate) + annual_contribution

    return None


# ── Action items ───────────────────────────────────────────────────────────


class FireAction(TypedDict):
    severity: str  # "error" | "warning" | "info"
    title: str
    message: str


def get_fire_actions(
    profile: UserProfile,
    fire_number: float,
    current_pot: float,
    readiness: float,
    years_to_fire_val: int | None,
    monthly_needed: float,
) -> list[FireAction]:
    """Return actionable FIRE warnings/suggestions based on current state."""
    actions: list[FireAction] = []
    ret = profile.retirement

    # 1. No investable assets at all
    if current_pot <= 0:
        actions.append({
            "severity": "error",
            "title": "No investable assets",
            "message": (
                "You have no Pension, ISA, or GIA assets. "
                "Add assets on the Profile page to start tracking retirement progress."
            ),
        })
        return actions  # other checks are meaningless with £0

    # 2. Pot shortfall
    shortfall = fire_number - current_pot
    if shortfall > 0:
        actions.append({
            "severity": "warning",
            "title": f"Pot shortfall: {_fmt(shortfall)}",
            "message": (
                f"Your investable pot ({_fmt(current_pot)}) is "
                f"{_fmt(shortfall)} short of your FIRE number ({_fmt(fire_number)})."
            ),
        })

    # 3. Contribution gap
    if monthly_needed > 0:
        actions.append({
            "severity": "warning",
            "title": f"Save {_fmt(monthly_needed)}/month to reach FIRE",
            "message": (
                f"To bridge the gap by retirement at age {ret.target_retirement_age}, "
                f"you need to save {_fmt(monthly_needed)} per month across your "
                "Pension, ISA, and GIA accounts."
            ),
        })

    # 4. FIRE age overshoot
    years_to_ret = ret.target_retirement_age - ret.current_age
    if years_to_fire_val is not None and years_to_fire_val > years_to_ret:
        fire_age = ret.current_age + years_to_fire_val
        actions.append({
            "severity": "warning",
            "title": f"FIRE age is {fire_age}, not {ret.target_retirement_age}",
            "message": (
                f"At current savings rates you won\u2019t reach financial independence "
                f"until age {fire_age}\u2014{years_to_fire_val - years_to_ret} years "
                f"after your target retirement age."
            ),
        })
    elif years_to_fire_val is None:
        actions.append({
            "severity": "error",
            "title": "FIRE target unreachable at current rate",
            "message": (
                "At your current savings rate, the FIRE target will not be reached "
                "within 60 years. Consider increasing contributions or adjusting "
                "your desired retirement income."
            ),
        })

    # 5. Income adjustment suggestion (readiness < 50%)
    if 0 < readiness < 50 and ret.desired_annual_income > 0:
        affordable = ret.desired_annual_income * (readiness / 100)
        actions.append({
            "severity": "info",
            "title": "Consider adjusting income target",
            "message": (
                f"Your current pot would support roughly {_fmt(affordable)}/yr. "
                f"Reducing your desired income from {_fmt(ret.desired_annual_income)}/yr "
                "would improve your readiness score and reduce the savings gap."
            ),
        })

    return actions


def _fmt(value: float) -> str:
    """Format a number as £X,XXX."""
    return f"\u00a3{value:,.0f}"
