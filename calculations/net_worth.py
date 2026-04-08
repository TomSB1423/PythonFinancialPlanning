"""Net worth, liquidity, and asset allocation calculations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.financial_data import Asset, Debt


# ── Totals ─────────────────────────────────────────────────────────────


def total_assets(assets: list[Asset]) -> float:
    return sum(a.current_value for a in assets)


def total_debts(debts: list[Debt]) -> float:
    return sum(d.outstanding_balance for d in debts)


def net_worth(assets: list[Asset], debts: list[Debt]) -> float:
    return total_assets(assets) - total_debts(debts)


# ── Breakdown ──────────────────────────────────────────────────────────


def liquidity_breakdown(assets: list[Asset]) -> dict[str, float]:
    liquid = sum(a.current_value for a in assets if a.is_liquid)
    illiquid = sum(a.current_value for a in assets if not a.is_liquid)
    total = liquid + illiquid
    return {
        "liquid": liquid,
        "illiquid": illiquid,
        "total": total,
        "liquid_ratio": liquid / total if total > 0 else 0.0,
    }


def asset_allocation(assets: list[Asset]) -> dict[str, dict[str, float]]:
    """Return {category: {value, percentage}} for each asset category."""
    total = total_assets(assets)
    by_category: dict[str, float] = {}
    for a in assets:
        cat = a.category.value
        by_category[cat] = by_category.get(cat, 0) + a.current_value

    return {
        cat: {"value": val, "percentage": val / total * 100 if total > 0 else 0}
        for cat, val in by_category.items()
    }


# ── Ratios ─────────────────────────────────────────────────────────────


def debt_to_asset_ratio(assets: list[Asset], debts: list[Debt]) -> float:
    ta = total_assets(assets)
    if ta == 0:
        return 0.0
    return total_debts(debts) / ta
