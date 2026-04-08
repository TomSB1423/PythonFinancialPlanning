"""UK financial assumptions and default values (2025/26 tax year)."""

from __future__ import annotations

from typing import TypedDict

# ── Inflation & Growth ─────────────────────────────────────────────────────

INFLATION_RATE = 0.025  # 2.5% CPI target
SALARY_GROWTH_RATE = 0.03  # 3.0% nominal salary growth assumption

GROWTH_RATES: dict[str, float] = {
    "Cash": 0.015,
    "Pension": 0.07,
    "ISA": 0.07,
    "GIA": 0.07,
    "Property": 0.04,
    "Other": 0.04,
}

# ── UK Income Tax 2025/26 ─────────────────────────────────────────────────

PERSONAL_ALLOWANCE = 12_570
PERSONAL_ALLOWANCE_TAPER_THRESHOLD = 100_000  # £1 lost per £2 over this

TAX_BANDS: list[tuple[float, float, str]] = [
    # (upper_limit, rate, name)
    (12_570, 0.00, "Personal Allowance"),
    (50_270, 0.20, "Basic Rate"),
    (125_140, 0.40, "Higher Rate"),
    (float("inf"), 0.45, "Additional Rate"),
]

# ── National Insurance (Class 1, Employee) ─────────────────────────────────

NI_PRIMARY_THRESHOLD = 12_570
NI_UPPER_EARNINGS_LIMIT = 50_270
NI_RATE_MAIN = 0.08  # 8% between thresholds
NI_RATE_UPPER = 0.02  # 2% above UEL

# ── Capital Gains Tax ──────────────────────────────────────────────────────

CGT_ANNUAL_EXEMPT = 3_000  # 2025/26
CGT_BASIC_RATE = 0.10
CGT_HIGHER_RATE = 0.20
CGT_BASIC_RATE_PROPERTY = 0.18
CGT_HIGHER_RATE_PROPERTY = 0.24

# ── Pensions ───────────────────────────────────────────────────────────────

PENSION_ANNUAL_ALLOWANCE = 60_000
PENSION_TAX_FREE_LUMP_SUM_RATE = 0.25  # 25% can be taken tax-free
STATE_PENSION_FULL_RATE = 11_973  # 2025/26 full new state pension (triple lock)

# ── ISA ────────────────────────────────────────────────────────────────────

ISA_ANNUAL_ALLOWANCE = 20_000

# ── Scenario multipliers (applied to base growth rates) ───────────────────

SCENARIOS: dict[str, float] = {
    "Pessimistic": 0.5,
    "Base": 1.0,
    "Optimistic": 1.5,
}

# ── Default income & spending ──────────────────────────────────────────────

DEFAULT_ANNUAL_SALARY = 51_000
DEFAULT_MONTHLY_SAVINGS = 1_500
DEFAULT_ANNUAL_LIVING_EXPENSES = 24_000
DEFAULT_ANNUAL_HOLIDAY_BUDGET = 2_400

# ── Default assets & debts ─────────────────────────────────────────────────


class DefaultAssetConfig(TypedDict, total=False):
    name: str
    category: str
    current_value: float
    annual_growth_rate: float
    is_liquid: bool
    tax_wrapper: str
    annual_contribution: float


class DefaultDebtConfig(TypedDict, total=False):
    name: str
    category: str
    outstanding_balance: float
    interest_rate: float
    monthly_payment: float
    remaining_term_months: int
    student_loan_plan: str
    student_loan_repayment_threshold: float
    student_loan_repayment_rate: float
    student_loan_write_off_years: int
    student_loan_start_year: int


DEFAULT_ASSETS: list[DefaultAssetConfig] = [
    {
        "name": "Stocks & Shares ISA",
        "category": "ISA",
        "current_value": 60_000,
        "annual_growth_rate": 0.07,
        "is_liquid": True,
        "tax_wrapper": "ISA",
        "annual_contribution": 0,
    },
]

DEFAULT_DEBTS: list[DefaultDebtConfig] = [
    {
        "name": "Student Loan (Plan 2)",
        "category": "Student Loan",
        "outstanding_balance": 60_000,
        "interest_rate": 0.05,
        "monthly_payment": 0,
        "remaining_term_months": 0,
        "student_loan_plan": "Plan 2",
        "student_loan_repayment_threshold": 27_295,
        "student_loan_repayment_rate": 0.09,
        "student_loan_write_off_years": 30,
        "student_loan_start_year": 2021,
    },
]

# ── Inheritance Tax ────────────────────────────────────────────────────────

IHT_NIL_RATE_BAND = 325_000
IHT_RESIDENCE_NIL_RATE_BAND = 175_000
IHT_RATE = 0.40
IHT_CHARITY_RATE = 0.36  # reduced rate when 10%+ of estate left to charity
IHT_TAPER_THRESHOLDS: list[tuple[float, float]] = [
    # (years_since_gift, fraction_of_full_tax)
    (3, 1.00),
    (4, 0.80),
    (5, 0.60),
    (6, 0.40),
    (7, 0.20),
    (float("inf"), 0.0),
]

# ── Default life goal costs (GBP) ─────────────────────────────────────────



class DefaultGoalConfig(TypedDict, total=False):
    cost: float
    year_offset: int
    funding: str
    annual_ongoing: float
    ongoing_years: int
    deposit_percentage: float
    mortgage_rate: float
    mortgage_term_years: int
    loan_interest_rate: float
    loan_term_years: int


DEFAULT_GOALS: dict[str, DefaultGoalConfig] = {
    "Buy a house": {
        "cost": 350_000, "year_offset": 3, "funding": "Mortgage",
        "deposit_percentage": 0.10, "mortgage_rate": 0.045, "mortgage_term_years": 25,
    },
    "Build a cabin": {"cost": 80_000, "year_offset": 7, "funding": "Savings"},
    "Children (two)": {
        "cost": 30_000, "year_offset": 5, "funding": "Savings",
        "annual_ongoing": 15_000, "ongoing_years": 18,
    },
    "Renovate sailing boat": {"cost": 40_000, "year_offset": 15, "funding": "Savings"},
    "Buy a car": {
        "cost": 30_000, "year_offset": 2, "funding": "Loan",
        "deposit_percentage": 0.15, "loan_interest_rate": 0.0499, "loan_term_years": 5,
    },
}
