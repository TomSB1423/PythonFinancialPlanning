"""Mutable projection state for life goal instruments."""

from __future__ import annotations

from calculations.instruments.asset import AssetState
from calculations.instruments.debt import StandardDebtState
from calculations.instruments.helpers import mortgage_monthly_payment
from models.assumptions import GROWTH_RATES
from models.financial_data import DebtCategory, GoalFunding, LifeGoal


# ── Savings Goal ────────────────────────────────────────────────────────────


class SavingsGoalState:
    """Goal fully funded from savings — full cost deducted from liquid assets."""

    __slots__ = ("name", "target_year", "_target_cost", "_annual_ongoing_cost", "_ongoing_years")

    def __init__(self, model: LifeGoal) -> None:
        self.name = model.name
        self.target_year = model.target_year
        self._target_cost = model.target_cost
        self._annual_ongoing_cost = model.annual_ongoing_cost
        self._ongoing_years = model.ongoing_years

    def lump_sum_cost(self) -> float:
        return self._target_cost

    def ongoing_cost(self, year: int) -> float:
        if self._annual_ongoing_cost <= 0 or self._ongoing_years <= 0:
            return 0.0
        if self.target_year <= year < self.target_year + self._ongoing_years:
            return self._annual_ongoing_cost
        return 0.0

    def activate(self, scenario_multiplier: float) -> tuple[list[AssetState], list[StandardDebtState]]:
        return [], []


# ── Mortgage Goal ───────────────────────────────────────────────────────────


class MortgageGoalState:
    """Goal funded by mortgage — deposit deducted, spawns property + mortgage debt."""

    __slots__ = ("name", "target_year", "_model")

    def __init__(self, model: LifeGoal) -> None:
        self.name = model.name
        self.target_year = model.target_year
        self._model = model

    def lump_sum_cost(self) -> float:
        return self._model.target_cost * self._model.deposit_percentage

    def ongoing_cost(self, year: int) -> float:
        if self._model.annual_ongoing_cost <= 0 or self._model.ongoing_years <= 0:
            return 0.0
        if self.target_year <= year < self.target_year + self._model.ongoing_years:
            return self._model.annual_ongoing_cost
        return 0.0

    def activate(self, scenario_multiplier: float) -> tuple[list[AssetState], list[StandardDebtState]]:
        m = self._model
        mortgage_principal = m.target_cost * (1 - m.deposit_percentage)
        monthly_pmt = mortgage_monthly_payment(mortgage_principal, m.mortgage_rate, m.mortgage_term_years)

        new_asset = AssetState(
            name=m.name,
            category="Property",
            is_liquid=False,
            value=m.target_cost,
            growth_rate=GROWTH_RATES.get("Property", 0.04) * scenario_multiplier,
            annual_contribution=0.0,
        )
        new_debt = StandardDebtState(
            name=m.name,
            category=DebtCategory.MORTGAGE.value,
            balance=mortgage_principal,
            rate=m.mortgage_rate,
            annual_payment=monthly_pmt * 12,
            remaining_years=m.mortgage_term_years,
        )
        return [new_asset], [new_debt]


# ── Loan Goal ───────────────────────────────────────────────────────────────


class LoanGoalState:
    """Goal funded by a personal loan — deposit deducted, spawns loan debt."""

    __slots__ = ("name", "target_year", "_model")

    def __init__(self, model: LifeGoal) -> None:
        self.name = model.name
        self.target_year = model.target_year
        self._model = model

    def lump_sum_cost(self) -> float:
        return self._model.target_cost * self._model.deposit_percentage

    def ongoing_cost(self, year: int) -> float:
        if self._model.annual_ongoing_cost <= 0 or self._model.ongoing_years <= 0:
            return 0.0
        if self.target_year <= year < self.target_year + self._model.ongoing_years:
            return self._model.annual_ongoing_cost
        return 0.0

    def activate(self, scenario_multiplier: float) -> tuple[list[AssetState], list[StandardDebtState]]:
        m = self._model
        loan_principal = m.target_cost * (1 - m.deposit_percentage)
        monthly_pmt = mortgage_monthly_payment(loan_principal, m.loan_interest_rate, m.loan_term_years)

        new_debt = StandardDebtState(
            name=m.name,
            category=DebtCategory.LOAN.value,
            balance=loan_principal,
            rate=m.loan_interest_rate,
            annual_payment=monthly_pmt * 12,
            remaining_years=m.loan_term_years,
        )
        return [], [new_debt]


# ── Factory ─────────────────────────────────────────────────────────────────


def create_goal_state(goal: LifeGoal) -> SavingsGoalState | MortgageGoalState | LoanGoalState:
    if goal.funding_source in (GoalFunding.MORTGAGE, GoalFunding.MIXED):
        return MortgageGoalState(goal)
    if goal.funding_source == GoalFunding.LOAN:
        return LoanGoalState(goal)
    return SavingsGoalState(goal)
