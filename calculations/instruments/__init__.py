"""Domain objects encapsulating projection logic for financial instruments."""

from __future__ import annotations

from calculations.instruments.asset import AssetState
from calculations.instruments.debt import (
    StandardDebtState,
    StudentLoanState,
    create_debt_state,
)
from calculations.instruments.goal import (
    LoanGoalState,
    MortgageGoalState,
    SavingsGoalState,
    create_goal_state,
)
from calculations.instruments.helpers import mortgage_monthly_payment
from calculations.instruments.protocols import (
    ProjectableAsset,
    ProjectableDebt,
    ProjectableGoal,
)

# Backward-compatible alias used by projections.py
_mortgage_monthly_payment = mortgage_monthly_payment

__all__ = [
    "AssetState",
    "LoanGoalState",
    "MortgageGoalState",
    "ProjectableAsset",
    "ProjectableDebt",
    "ProjectableGoal",
    "SavingsGoalState",
    "StandardDebtState",
    "StudentLoanState",
    "create_debt_state",
    "create_goal_state",
    "mortgage_monthly_payment",
]
