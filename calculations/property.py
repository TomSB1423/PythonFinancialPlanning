"""Property and mortgage calculation functions."""

from __future__ import annotations

import pandas as pd

from calculations.instruments.helpers import mortgage_monthly_payment


def calculate_ltv(mortgage_balance: float, property_value: float) -> float:
    """Loan-to-value ratio as a percentage."""
    if property_value <= 0:
        return 0.0
    return round(mortgage_balance / property_value * 100, 2)


def calculate_equity(property_value: float, mortgage_balance: float) -> float:
    """Equity in a property (value minus outstanding mortgage)."""
    return round(property_value - mortgage_balance, 2)


def amortization_schedule(
    principal: float,
    annual_rate: float,
    term_years: int,
) -> pd.DataFrame:
    """Year-by-year amortization schedule for a repayment mortgage.

    Returns a DataFrame with columns: year, payment, principal_paid,
    interest_paid, remaining_balance.
    """
    if principal <= 0 or term_years <= 0:
        return pd.DataFrame(columns=["year", "payment", "principal_paid", "interest_paid", "remaining_balance"])

    monthly = mortgage_monthly_payment(principal, annual_rate, term_years)
    monthly_rate = annual_rate / 12 if annual_rate > 0 else 0.0
    balance = principal
    rows: list[dict[str, int | float]] = []

    for year in range(1, term_years + 1):
        year_interest = 0.0
        year_principal = 0.0
        year_payment = 0.0

        for _ in range(12):
            if balance <= 0:
                break
            interest = balance * monthly_rate
            payment = min(monthly, balance + interest)
            principal_part = payment - interest
            balance = max(0, balance - principal_part)
            year_interest += interest
            year_principal += principal_part
            year_payment += payment

        rows.append({
            "year": year,
            "payment": round(year_payment, 2),
            "principal_paid": round(year_principal, 2),
            "interest_paid": round(year_interest, 2),
            "remaining_balance": round(balance, 2),
        })

    return pd.DataFrame(rows)


def equity_over_time(
    property_value: float,
    growth_rate: float,
    mortgage_principal: float,
    mortgage_rate: float,
    term_years: int,
    projection_years: int,
) -> pd.DataFrame:
    """Project property value, mortgage balance, equity, and LTV over time.

    Returns a DataFrame with columns: year, property_value, mortgage_balance,
    equity, ltv.
    """
    if projection_years <= 0:
        return pd.DataFrame(columns=["year", "property_value", "mortgage_balance", "equity", "ltv"])

    monthly = mortgage_monthly_payment(mortgage_principal, mortgage_rate, term_years)
    monthly_rate = mortgage_rate / 12 if mortgage_rate > 0 else 0.0
    balance = mortgage_principal
    value = property_value
    rows: list[dict[str, int | float]] = []

    # Year 0 snapshot
    rows.append({
        "year": 0,
        "property_value": round(value, 2),
        "mortgage_balance": round(balance, 2),
        "equity": round(value - balance, 2),
        "ltv": round(balance / value * 100, 2) if value > 0 else 0.0,
    })

    for year in range(1, projection_years + 1):
        value *= 1 + growth_rate

        for _ in range(12):
            if balance <= 0:
                break
            interest = balance * monthly_rate
            payment = min(monthly, balance + interest)
            principal_part = payment - interest
            balance = max(0, balance - principal_part)

        equity = value - balance
        rows.append({
            "year": year,
            "property_value": round(value, 2),
            "mortgage_balance": round(balance, 2),
            "equity": round(equity, 2),
            "ltv": round(balance / value * 100, 2) if value > 0 else 0.0,
        })

    return pd.DataFrame(rows)


def property_profit(
    current_value: float,
    purchase_price: float,
    total_interest: float,
) -> float:
    """Net profit on a property accounting for interest paid."""
    return round(current_value - purchase_price - total_interest, 2)
