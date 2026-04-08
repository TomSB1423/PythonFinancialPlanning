"""Shared helpers for instrument calculations."""

from __future__ import annotations

import numpy_financial as npf


def mortgage_monthly_payment(principal: float, annual_rate: float, term_years: int) -> float:
    """Calculate monthly mortgage repayment using numpy-financial."""
    if principal <= 0 or term_years <= 0:
        return 0.0
    if annual_rate <= 0:
        return principal / (term_years * 12)
    return float(-npf.pmt(annual_rate / 12, term_years * 12, principal))
