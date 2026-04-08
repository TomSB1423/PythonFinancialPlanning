"""Annual cash flow waterfall: salary → deductions → bank account → expenses → surplus."""

from __future__ import annotations

from dataclasses import dataclass

from calculations.tax import income_tax, national_insurance
from models.assumptions import INFLATION_RATE, SALARY_GROWTH_RATE
from models.financial_data import (
    AssetCategory,
    DebtCategory,
    TaxWrapper,
    UserProfile,
)


def student_loan_annual_repayment(
    salary: float,
    threshold: float,
    rate: float,
) -> float:
    """Income-contingent student loan repayment for a single year."""
    return max(0.0, (salary - threshold) * rate)


@dataclass(frozen=True, slots=True)
class CashFlowBreakdown:
    """All components of the annual cash flow waterfall."""

    gross_salary: float
    pension_contribution: float
    adjusted_gross: float
    income_tax: float
    national_insurance: float
    student_loan_repayment: float
    net_take_home: float

    mortgage_payments: float
    loan_payments: float
    living_expenses: float
    holiday_budget: float
    goal_ongoing_costs: float
    non_pension_contributions: float
    total_outflows: float
    surplus: float


def annual_cash_flow(
    profile: UserProfile,
    yr_offset: int = 0,
    is_retired: bool = False,
    *,
    active_mortgage_payments: float = 0.0,
    active_loan_payments: float = 0.0,
    active_goal_ongoing: float = 0.0,
) -> CashFlowBreakdown:
    """Compute the full cash flow waterfall for a single year.

    Parameters
    ----------
    profile:
        The user's financial profile.
    yr_offset:
        Years from today (0 = current year).  Used to inflate salary
        and expenses.
    is_retired:
        If ``True`` the salary side is zeroed out (retirement cash flow
        is handled elsewhere via drawdown).
    active_mortgage_payments:
        Total annual mortgage payments across all active mortgages
        (profile debts + goal-spawned).
    active_loan_payments:
        Total annual non-credit-card, non-mortgage loan payments.
    active_goal_ongoing:
        Annual ongoing goal costs for this year (e.g. children).
    """
    if is_retired:
        return CashFlowBreakdown(
            gross_salary=0.0,
            pension_contribution=0.0,
            adjusted_gross=0.0,
            income_tax=0.0,
            national_insurance=0.0,
            student_loan_repayment=0.0,
            net_take_home=0.0,
            mortgage_payments=active_mortgage_payments,
            loan_payments=active_loan_payments,
            living_expenses=0.0,
            holiday_budget=0.0,
            goal_ongoing_costs=active_goal_ongoing,
            non_pension_contributions=0.0,
            total_outflows=0.0,
            surplus=0.0,
        )

    # ── Salary (grows each year) ───────────────────────────────────────
    gross = profile.annual_salary * (1 + SALARY_GROWTH_RATE) ** yr_offset

    # ── Pension sacrifice (DC pensions) ────────────────────────────────
    pension_contribution = sum(
        a.annual_contribution
        for a in profile.assets
        if a.tax_wrapper == TaxWrapper.PENSION
    )
    adjusted_gross = max(0.0, gross - pension_contribution)

    # ── PAYE deductions on adjusted gross ──────────────────────────────
    tax = income_tax(adjusted_gross)["tax"]
    ni = national_insurance(adjusted_gross)

    # ── Student loan (based on full gross salary per HMRC rules) ───────
    sl_repayment = 0.0
    for d in profile.debts:
        if d.category == DebtCategory.STUDENT_LOAN and d.outstanding_balance > 0:
            threshold = d.student_loan_repayment_threshold or 29_385
            rate = d.student_loan_repayment_rate or 0.09
            sl_repayment += student_loan_annual_repayment(gross, threshold, rate)

    net_take_home = gross - pension_contribution - tax - ni - sl_repayment

    # ── Bank-account outflows ──────────────────────────────────────────
    inflation_factor = (1 + INFLATION_RATE) ** yr_offset
    living = profile.annual_living_expenses * inflation_factor
    holidays = profile.annual_holiday_budget * inflation_factor

    non_pension_contribs = sum(
        a.annual_contribution
        for a in profile.assets
        if a.tax_wrapper != TaxWrapper.PENSION and a.annual_contribution > 0
    )

    total_outflows = (
        active_mortgage_payments
        + active_loan_payments
        + living
        + holidays
        + active_goal_ongoing
        + non_pension_contribs
    )

    surplus = max(0.0, net_take_home - total_outflows)

    return CashFlowBreakdown(
        gross_salary=round(gross, 2),
        pension_contribution=round(pension_contribution, 2),
        adjusted_gross=round(adjusted_gross, 2),
        income_tax=round(tax, 2),
        national_insurance=round(ni, 2),
        student_loan_repayment=round(sl_repayment, 2),
        net_take_home=round(net_take_home, 2),
        mortgage_payments=round(active_mortgage_payments, 2),
        loan_payments=round(active_loan_payments, 2),
        living_expenses=round(living, 2),
        holiday_budget=round(holidays, 2),
        goal_ongoing_costs=round(active_goal_ongoing, 2),
        non_pension_contributions=round(non_pension_contribs, 2),
        total_outflows=round(total_outflows, 2),
        surplus=round(surplus, 2),
    )
