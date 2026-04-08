"""Pydantic data models for the financial planning app."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.assumptions import (
    DEFAULT_ANNUAL_HOLIDAY_BUDGET,
    DEFAULT_ANNUAL_LIVING_EXPENSES,
    DEFAULT_ANNUAL_SALARY,
    STUDENT_LOAN_THRESHOLDS,
)

# ── Enums ──────────────────────────────────────────────────────────────────

class AssetCategory(str, Enum):
    CASH = "Cash"
    PENSION = "Pension"
    ISA = "ISA"
    GIA = "GIA"
    PROPERTY = "Property"
    OTHER = "Other"


class DebtCategory(str, Enum):
    MORTGAGE = "Mortgage"
    LOAN = "Loan"
    STUDENT_LOAN = "Student Loan"
    CREDIT_CARD = "Credit Card"
    OTHER = "Other"


class StudentLoanPlan(str, Enum):
    PLAN_2 = "Plan 2"
    PLAN_5 = "Plan 5"


class TaxWrapper(str, Enum):
    NONE = "None"
    PENSION = "Pension"
    ISA = "ISA"
    GIA = "GIA"


class GoalFunding(str, Enum):
    SAVINGS = "Savings"
    MORTGAGE = "Mortgage"
    MIXED = "Mixed"
    LOAN = "Loan"


# ── Core models ────────────────────────────────────────────────────────────

class Asset(BaseModel):
    name: str
    category: AssetCategory = AssetCategory.CASH
    current_value: float = Field(ge=0)
    annual_growth_rate: float = Field(default=0.04, description="Decimal, e.g. 0.07 = 7%")
    is_liquid: bool = True
    tax_wrapper: TaxWrapper = TaxWrapper.NONE
    annual_contribution: float = Field(default=0.0, ge=0, description="Annual amount added")


class Debt(BaseModel):
    name: str
    category: DebtCategory = DebtCategory.LOAN
    outstanding_balance: float = Field(ge=0)
    interest_rate: float = Field(default=0.05, description="Decimal, e.g. 0.05 = 5%")
    monthly_payment: float = Field(ge=0)
    remaining_term_months: int = Field(ge=0)
    student_loan_plan: StudentLoanPlan | None = None
    student_loan_repayment_threshold: float | None = Field(default=None, ge=0)
    student_loan_repayment_rate: float | None = Field(default=None, ge=0, le=1)
    student_loan_write_off_years: int | None = Field(default=None, ge=1, le=60)
    student_loan_start_year: int | None = Field(default=None, ge=1900, le=2200)

    @model_validator(mode="after")
    def apply_student_loan_defaults(self) -> Debt:
        """Normalize optional student-loan fields based on debt category."""
        if self.category == DebtCategory.STUDENT_LOAN:
            if self.student_loan_plan is None:
                self.student_loan_plan = StudentLoanPlan.PLAN_2
            if self.student_loan_repayment_threshold is None:
                plan_key = self.student_loan_plan.value if self.student_loan_plan else "Plan 2"
                self.student_loan_repayment_threshold = STUDENT_LOAN_THRESHOLDS.get(plan_key, 29_385)
            if self.student_loan_repayment_rate is None:
                self.student_loan_repayment_rate = 0.09
            if self.student_loan_write_off_years is None:
                self.student_loan_write_off_years = 30
            if self.student_loan_start_year is None:
                self.student_loan_start_year = date.today().year
            return self

        self.student_loan_plan = None
        self.student_loan_repayment_threshold = None
        self.student_loan_repayment_rate = None
        self.student_loan_write_off_years = None
        self.student_loan_start_year = None
        return self


class LifeGoal(BaseModel):
    name: str
    target_cost: float = Field(ge=0)
    target_year: int
    funding_source: GoalFunding = GoalFunding.SAVINGS
    priority: int = Field(default=1, ge=1, le=5)
    annual_ongoing_cost: float = Field(default=0.0, ge=0, description="Recurring annual cost (e.g. children)")
    ongoing_years: int = Field(default=0, ge=0, description="How many years the ongoing cost lasts")
    notes: str = ""
    deposit_percentage: float = Field(default=0.10, ge=0, le=1, description="Deposit as fraction of target_cost for mortgage-funded goals")
    mortgage_rate: float = Field(default=0.055, ge=0, description="Annual mortgage interest rate")
    mortgage_term_years: int = Field(default=25, ge=1, le=40, description="Mortgage repayment term in years")
    loan_interest_rate: float = Field(default=0.05, ge=0, description="Annual loan interest rate")
    loan_term_years: int = Field(default=5, ge=1, le=20, description="Loan repayment term in years")


class RetirementProfile(BaseModel):
    current_age: int = Field(default=30, ge=18, le=100)
    target_retirement_age: int = Field(default=65, ge=30, le=100)
    desired_annual_income: float = Field(default=30000.0, ge=0)
    state_pension_age: int = Field(default=67, ge=60, le=75)
    expected_state_pension: float = Field(default=11973.0, ge=0)
    life_expectancy: int = Field(default=90, ge=60, le=120)
    estimated_healthcare_costs: float = Field(default=0.0, ge=0, description="Annual later-life care costs")
    healthcare_start_age: int = Field(default=80, ge=60, le=100)


class UserProfile(BaseModel):
    name: str = "My Financial Plan"
    last_updated: date = Field(default_factory=date.today)
    assets: list[Asset] = Field(default_factory=list)
    debts: list[Debt] = Field(default_factory=list)
    life_goals: list[LifeGoal] = Field(default_factory=list)
    retirement: RetirementProfile = Field(default_factory=RetirementProfile)
    annual_salary: float = Field(default=DEFAULT_ANNUAL_SALARY, ge=0)
    annual_living_expenses: float = Field(default=DEFAULT_ANNUAL_LIVING_EXPENSES, ge=0)
    annual_holiday_budget: float = Field(default=DEFAULT_ANNUAL_HOLIDAY_BUDGET, ge=0)
    annual_retirement_living_expenses: float | None = Field(default=None, ge=0)
    annual_retirement_holiday_budget: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")
