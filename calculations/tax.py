"""UK tax calculations (2025/26 tax year, simplified)."""

from __future__ import annotations

from typing import TypedDict

from models.assumptions import (
    CGT_ANNUAL_EXEMPT,
    CGT_BASIC_RATE,
    CGT_BASIC_RATE_PROPERTY,
    CGT_HIGHER_RATE,
    CGT_HIGHER_RATE_PROPERTY,
    IHT_CHARITY_RATE,
    IHT_NIL_RATE_BAND,
    IHT_RATE,
    IHT_RESIDENCE_NIL_RATE_BAND,
    NI_PRIMARY_THRESHOLD,
    NI_RATE_MAIN,
    NI_RATE_UPPER,
    NI_UPPER_EARNINGS_LIMIT,
    PENSION_TAX_FREE_LUMP_SUM_RATE,
    PERSONAL_ALLOWANCE,
    PERSONAL_ALLOWANCE_TAPER_THRESHOLD,
    TAX_BANDS,
)


class TaxBreakdown(TypedDict):
    band: str
    taxable: float
    rate: float
    tax: float


class IncomeTaxResult(TypedDict):
    tax: float
    effective_rate: float
    breakdown: list[TaxBreakdown]


class PensionDrawdownTaxResult(TypedDict):
    withdrawal: float
    tax_free_portion: float
    taxable_portion: float
    tax: float
    net_withdrawal: float


def _adjusted_personal_allowance(gross_income: float) -> float:
    """Personal allowance tapers by £1 for every £2 over £100k."""
    if gross_income <= PERSONAL_ALLOWANCE_TAPER_THRESHOLD:
        return PERSONAL_ALLOWANCE
    reduction = (gross_income - PERSONAL_ALLOWANCE_TAPER_THRESHOLD) / 2
    return max(0, PERSONAL_ALLOWANCE - reduction)


def income_tax(gross_income: float) -> IncomeTaxResult:
    """Calculate UK income tax on gross income. Returns tax, effective_rate, breakdown."""
    if gross_income <= 0:
        return {"tax": 0.0, "effective_rate": 0.0, "breakdown": []}

    pa = _adjusted_personal_allowance(gross_income)
    taxable = max(0, gross_income - pa)
    total_tax = 0.0
    breakdown: list[TaxBreakdown] = []
    remaining = taxable

    # Skip the PA band, start taxing from basic rate upward
    prev_upper = 0.0
    for upper, rate, name in TAX_BANDS:
        if rate == 0:
            prev_upper = upper
            continue
        band_width = upper - prev_upper
        taxable_in_band = min(remaining, band_width)
        if taxable_in_band <= 0:
            break
        tax_in_band = taxable_in_band * rate
        total_tax += tax_in_band
        breakdown.append({"band": name, "taxable": taxable_in_band, "rate": rate, "tax": tax_in_band})
        remaining -= taxable_in_band
        prev_upper = upper

    return {
        "tax": round(total_tax, 2),
        "effective_rate": round(total_tax / gross_income, 4) if gross_income > 0 else 0,
        "breakdown": breakdown,
    }


def national_insurance(gross_salary: float) -> float:
    """Employee Class 1 NI contributions."""
    if gross_salary <= NI_PRIMARY_THRESHOLD:
        return 0.0
    ni = min(gross_salary, NI_UPPER_EARNINGS_LIMIT) - NI_PRIMARY_THRESHOLD
    ni_tax = ni * NI_RATE_MAIN
    if gross_salary > NI_UPPER_EARNINGS_LIMIT:
        ni_tax += (gross_salary - NI_UPPER_EARNINGS_LIMIT) * NI_RATE_UPPER
    return round(ni_tax, 2)


def capital_gains_tax(gain: float, is_property: bool = False, is_higher_rate: bool = False) -> float:
    """CGT on a gain after the annual exempt amount."""
    taxable = max(0, gain - CGT_ANNUAL_EXEMPT)
    if taxable == 0:
        return 0.0
    if is_property:
        rate = CGT_HIGHER_RATE_PROPERTY if is_higher_rate else CGT_BASIC_RATE_PROPERTY
    else:
        rate = CGT_HIGHER_RATE if is_higher_rate else CGT_BASIC_RATE
    return round(taxable * rate, 2)


class IHTResult(TypedDict):
    gross_estate: float
    nil_rate_band_used: float
    residence_nil_rate_band_used: float
    taxable_estate: float
    iht_due: float
    effective_rate: float


def inheritance_tax(
    estate_value: float,
    has_residential_property: bool = True,
    spouse_transfer: bool = False,
    charity_fraction: float = 0.0,
) -> IHTResult:
    """Estimate IHT on a UK estate.

    - *estate_value*: total estate (assets minus debts)
    - *has_residential_property*: eligible for RNRB (left to direct descendants)
    - *spouse_transfer*: if inheriting from spouse, doubles the nil-rate bands
    - *charity_fraction*: fraction of estate left to charity (0.10+ = 36% rate)

    Returns gross estate, bands used, taxable estate, IHT due, and effective rate.
    """
    band_multiplier = 2 if spouse_transfer else 1
    nrb = IHT_NIL_RATE_BAND * band_multiplier
    rnrb = IHT_RESIDENCE_NIL_RATE_BAND * band_multiplier if has_residential_property else 0.0

    total_band = nrb + rnrb
    taxable = max(0.0, estate_value - total_band)

    charity_amount = estate_value * max(0.0, min(1.0, charity_fraction))
    taxable = max(0.0, taxable - charity_amount)
    rate = IHT_CHARITY_RATE if charity_fraction >= 0.10 else IHT_RATE
    iht = taxable * rate

    return {
        "gross_estate": round(estate_value, 2),
        "nil_rate_band_used": round(min(estate_value, nrb), 2),
        "residence_nil_rate_band_used": round(min(max(0.0, estate_value - nrb), rnrb), 2),
        "taxable_estate": round(taxable, 2),
        "iht_due": round(iht, 2),
        "effective_rate": round(iht / estate_value, 4) if estate_value > 0 else 0.0,
    }


def pension_drawdown_tax(
    withdrawal: float,
    other_income: float = 0.0,
    lump_sum_taken: bool = False,
) -> PensionDrawdownTaxResult:
    """Tax on pension drawdown.

    If *lump_sum_taken* is False (first withdrawal / PCLS year), 25% is
    tax-free.  Once the lump sum has been taken, the entire withdrawal
    is taxable as income.
    """
    tax_free = 0.0 if lump_sum_taken else withdrawal * PENSION_TAX_FREE_LUMP_SUM_RATE
    taxable_withdrawal = withdrawal - tax_free
    total_income = other_income + taxable_withdrawal
    # Tax on total income minus tax on other income alone
    tax_on_total = income_tax(total_income)["tax"]
    tax_on_other = income_tax(other_income)["tax"]
    tax_on_drawdown = tax_on_total - tax_on_other
    return {
        "withdrawal": withdrawal,
        "tax_free_portion": round(tax_free, 2),
        "taxable_portion": round(taxable_withdrawal, 2),
        "tax": round(max(0, tax_on_drawdown), 2),
        "net_withdrawal": round(withdrawal - max(0, tax_on_drawdown), 2),
    }
