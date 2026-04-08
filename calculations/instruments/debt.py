"""Mutable projection state for debt instruments."""

from __future__ import annotations

from datetime import date

from models.assumptions import STUDENT_LOAN_THRESHOLDS
from models.financial_data import Debt, DebtCategory


# ── Standard Debt ───────────────────────────────────────────────────────────


class StandardDebtState:
    """Fixed-payment amortising debt (mortgage, loan, credit card, other)."""

    __slots__ = ("name", "category", "_balance", "_rate", "_annual_payment", "_remaining_years")

    def __init__(
        self,
        *,
        name: str,
        category: str,
        balance: float,
        rate: float,
        annual_payment: float,
        remaining_years: int | None = None,
    ) -> None:
        self.name = name
        self.category = category
        self._balance = balance
        self._rate = rate
        self._annual_payment = annual_payment
        self._remaining_years = remaining_years

    @classmethod
    def from_model(cls, model: Debt) -> StandardDebtState:
        return cls(
            name=model.name,
            category=model.category.value,
            balance=model.outstanding_balance,
            rate=model.interest_rate,
            annual_payment=model.monthly_payment * 12,
        )

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def annual_payment(self) -> float:
        return self._annual_payment

    @property
    def is_cleared(self) -> bool:
        return self._balance <= 0

    def accrue_and_pay(self, salary: float, is_retired: bool, year: int) -> None:
        if self._balance <= 0:
            return

        payment = min(self._annual_payment, self._balance + self._balance * self._rate)
        principal_portion = payment - self._balance * self._rate
        avg_balance = self._balance - max(0, principal_portion) / 2
        interest = avg_balance * self._rate
        self._balance = max(0, self._balance + interest - payment)

        if self._remaining_years is not None:
            self._remaining_years -= 1
            if self._remaining_years <= 0 or self._balance <= 0:
                self._balance = 0


# ── Student Loan ────────────────────────────────────────────────────────────


class StudentLoanState:
    """Income-contingent student loan with write-off."""

    __slots__ = ("name", "category", "_balance", "_rate", "_threshold",
                 "_repayment_rate", "_write_off_year")

    def __init__(self, model: Debt) -> None:
        self.name = model.name
        self.category = model.category.value
        self._balance = model.outstanding_balance
        self._rate = model.interest_rate
        plan_key = model.student_loan_plan.value if model.student_loan_plan else "Plan 2"
        self._threshold = model.student_loan_repayment_threshold or STUDENT_LOAN_THRESHOLDS.get(plan_key, 29_385)
        self._repayment_rate = model.student_loan_repayment_rate or 0.09
        current_year = date.today().year
        start = model.student_loan_start_year or current_year
        write_off = model.student_loan_write_off_years or 30
        self._write_off_year = start + write_off

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def annual_payment(self) -> float:
        return 0.0

    @property
    def is_cleared(self) -> bool:
        return self._balance <= 0

    def accrue_and_pay(self, salary: float, is_retired: bool, year: int) -> None:
        if self._balance <= 0:
            return

        if year >= self._write_off_year:
            self._balance = 0
            return

        self._balance *= 1 + self._rate

        if not is_retired:
            repayment = max(0, (salary - self._threshold) * self._repayment_rate)
            self._balance = max(0, self._balance - repayment)


# ── Factory ─────────────────────────────────────────────────────────────────


def create_debt_state(debt: Debt) -> StandardDebtState | StudentLoanState:
    if debt.category == DebtCategory.STUDENT_LOAN:
        return StudentLoanState(debt)
    return StandardDebtState.from_model(debt)
