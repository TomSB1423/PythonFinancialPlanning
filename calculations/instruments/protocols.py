"""Protocol definitions for projectable financial instruments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from calculations.instruments.asset import AssetState
    from calculations.instruments.debt import StandardDebtState


# ── Protocols ───────────────────────────────────────────────────────────────


class ProjectableAsset(Protocol):
    name: str
    category: str
    is_liquid: bool

    @property
    def value(self) -> float: ...

    def grow(self) -> None: ...

    def contribute(self, is_retired: bool) -> None: ...

    def deposit(self, amount: float) -> None: ...

    def withdraw(self, amount: float) -> float: ...


class ProjectableDebt(Protocol):
    name: str
    category: str

    @property
    def balance(self) -> float: ...

    @property
    def annual_payment(self) -> float: ...

    @property
    def is_cleared(self) -> bool: ...

    def accrue_and_pay(self, salary: float, is_retired: bool, year: int) -> None: ...


class ProjectableGoal(Protocol):
    name: str
    target_year: int

    def lump_sum_cost(self) -> float: ...

    def ongoing_cost(self, year: int) -> float: ...

    def activate(self, scenario_multiplier: float) -> tuple[list[AssetState], list[StandardDebtState]]: ...
