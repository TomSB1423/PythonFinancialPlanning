"""Mutable projection state for a single asset."""

from __future__ import annotations

from models.assumptions import GROWTH_RATES
from models.financial_data import Asset


# ── AssetState ─────────────────────────────────────────────────────────


class AssetState:
    """Mutable projection state for a single asset."""

    __slots__ = ("name", "category", "is_liquid", "_value", "_growth_rate", "_annual_contribution")

    def __init__(
        self,
        *,
        name: str,
        category: str,
        is_liquid: bool,
        value: float,
        growth_rate: float,
        annual_contribution: float = 0.0,
    ) -> None:
        self.name = name
        self.category = category
        self.is_liquid = is_liquid
        self._value = value
        self._growth_rate = growth_rate
        self._annual_contribution = annual_contribution

    @classmethod
    def from_model(cls, model: Asset, scenario_multiplier: float = 1.0) -> AssetState:
        return cls(
            name=model.name,
            category=model.category.value,
            is_liquid=model.is_liquid,
            value=model.current_value,
            growth_rate=GROWTH_RATES.get(model.category.value, 0.04) * scenario_multiplier,
            annual_contribution=model.annual_contribution,
        )

    @property
    def value(self) -> float:
        return self._value

    def grow(self) -> None:
        self._value *= 1 + self._growth_rate

    def contribute(self, is_retired: bool) -> None:
        if not is_retired:
            self._value += self._annual_contribution

    def deposit(self, amount: float) -> None:
        self._value += amount

    def withdraw(self, amount: float) -> float:
        actual = min(amount, self._value)
        self._value -= actual
        return actual
