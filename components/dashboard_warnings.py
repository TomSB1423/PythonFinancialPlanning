"""Financial health check engine for Dashboard warnings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from models.financial_data import DebtCategory, UserProfile


@dataclass
class HealthAlert:
    """Represents a financial health alert for the user."""

    severity: Literal["info", "warning", "error"]
    """Alert severity: 'info' (informational), 'warning' (potential issue), 'error' (critical)."""

    title: str
    """Alert title (e.g., 'High Debt Burden')."""

    message: str
    """Alert description with context and suggested action."""

    action_page: str | None = None
    """Target page name for navigation hint (e.g., 'Assets and Debts', 'Life Goals')."""

    query_param: str | None = None
    """Optional query parameter for scrolling to section (e.g., 'goals', 'retirement')."""


def get_financial_health_checks(profile: UserProfile) -> list[HealthAlert]:
    """
    Analyze user's financial profile and return list of health alerts.

    Checks for:
    - Debt-to-liquid-assets ratio
    - Unfunded goals
    - Retirement readiness (if retirement page would show concern)
    - Income/spending imbalance
    - Student loan default edge cases

    Args:
        profile: UserProfile instance to analyze

    Returns:
        List of HealthAlert objects (empty if no issues found). Alerts are ordered
        by severity (error → warning → info).
    """
    alerts: list[HealthAlert] = []

    # ── Check 1: Debt-to-Liquid Assets ────────────────────────────────────
    total_debts = sum(d.outstanding_balance for d in profile.debts)
    liquid_assets = sum(a.current_value for a in profile.assets if a.is_liquid)

    if liquid_assets > 0:
        debt_to_liquid_ratio = total_debts / liquid_assets
        if debt_to_liquid_ratio > 2.0:
            alerts.append(
                HealthAlert(
                    severity="error",
                    title="High Debt-to-Liquid Ratio",
                    message=f"Your debts (£{total_debts:,.0f}) exceed 2x your liquid assets "
                    f"(£{liquid_assets:,.0f}). Consider increasing savings or paying down high-interest debt.",
                    action_page="Assets and Debts",
                )
            )
        elif debt_to_liquid_ratio > 1.0:
            alerts.append(
                HealthAlert(
                    severity="warning",
                    title="Moderate Debt Burden",
                    message=f"Your debts (£{total_debts:,.0f}) exceed your liquid assets "
                    f"(£{liquid_assets:,.0f}). Build liquid reserves for emergencies.",
                    action_page="Assets and Debts",
                )
            )
    elif total_debts > 0:
        alerts.append(
            HealthAlert(
                severity="warning",
                title="No Liquid Assets",
                message=f"You have £{total_debts:,.0f} in debts but no liquid (accessible) assets. "
                "Create an emergency fund before taking on additional debt.",
                action_page="Assets and Debts",
            )
        )

    # ── Check 2: Unfunded Goals ────────────────────────────────────────
    total_goal_costs = sum(g.target_cost for g in profile.life_goals)
    unfunded_goals = [g for g in profile.life_goals if g.target_cost > liquid_assets]

    if unfunded_goals:
        unfunded_count = len(unfunded_goals)
        unfunded_amount = sum(g.target_cost for g in unfunded_goals)
        alerts.append(
            HealthAlert(
                severity="warning",
                title=f"{unfunded_count} Goal(s) Exceed Liquid Assets",
                message=f"You have {unfunded_count} goal(s) totaling £{unfunded_amount:,.0f} that exceed "
                f"your current liquid assets (£{liquid_assets:,.0f}). Check if these are fundable "
                "through projections or financing.",
                action_page="Life Goals",
            )
        )

    # ── Check 4: Income/Spending Imbalance ────────────────────────────────
    annual_expenses = (profile.annual_living_expenses or 0) + (profile.annual_holiday_budget or 0)
    annual_debt_service = sum(d.monthly_payment for d in profile.debts) * 12
    total_annual_needs = annual_expenses + annual_debt_service

    if profile.annual_salary and profile.annual_salary > 0:
        annual_surplus = profile.annual_salary - total_annual_needs
        if annual_surplus < 0:
            alerts.append(
                HealthAlert(
                    severity="error",
                    title="Annual Deficit",
                    message=f"Your annual expenses (£{total_annual_needs:,.0f}) exceed your salary "
                    f"(£{profile.annual_salary:,.0f}) by £{abs(annual_surplus):,.0f}. "
                    "Reduce expenses, increase income, or adjust savings goals.",
                    action_page="Assets and Debts",
                )
            )
    else:
        if total_annual_needs > 0:
            alerts.append(
                HealthAlert(
                    severity="warning",
                    title="No Income Recorded",
                    message=f"You have £{total_annual_needs:,.0f} in annual expenses but no salary set. "
                    "Update your income to enable retirement and goal projections.",
                    action_page="Assets and Debts",
                )
            )

    # ── Check 5: Mortgage Extending Into Retirement ──────────────────────
    from calculations.projections import mortgage_info_at_retirement

    _mort_info = mortgage_info_at_retirement(profile)
    if _mort_info["has_mortgage"] and _mort_info["payoff_year"] is not None:
        current_year = date.today().year
        retirement_year = current_year + max(
            0,
            profile.retirement.target_retirement_age - profile.retirement.current_age,
        )
        if _mort_info["extends_into_retirement"]:
            yrs = _mort_info["mortgage_years_in_retirement"]
            alerts.append(
                HealthAlert(
                    severity="warning",
                    title="Mortgage Extends Into Retirement",
                    message=f"Your mortgage is projected to be paid off in {_mort_info['payoff_year']}, "
                    f"which is {yrs} year(s) after your planned retirement in {retirement_year}. "
                    f"This adds £{_mort_info['annual_mortgage_payment']:,.0f}/yr to retirement withdrawals.",
                    action_page="Projections",
                )
            )
        else:
            alerts.append(
                HealthAlert(
                    severity="info",
                    title="Mortgage Paid Off Before Retirement",
                    message=f"Mortgage paid off in {_mort_info['payoff_year']} — "
                    f"£{_mort_info['annual_mortgage_payment']:,.0f}/yr freed up before retirement.",
                )
            )

    # ── Check 6: Student Loan Default Edge Case ────────────────────────────
    student_loans = [d for d in profile.debts if d.category == DebtCategory.STUDENT_LOAN]
    for loan in student_loans:
        if (
            loan.student_loan_plan is None
            or loan.student_loan_repayment_threshold is None
            or loan.student_loan_repayment_rate is None
        ):
            alerts.append(
                HealthAlert(
                    severity="info",
                    title="Student Loan Using Defaults",
                    message=f"'{loan.name}' is using default Plan 2 repayment settings "
                    "(£29,385 threshold, 9% rate, 30-year write-off). "
                    "Review and confirm these match your actual loan terms.",
                    action_page="Assets and Debts",
                )
            )
            break  # Only show once, even if multiple student loans

    # ── Sort by severity (error → warning → info) ──────────────────────────
    severity_order = {"error": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order[a.severity])

    return alerts
