"""Shared pytest fixtures for Streamlit integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.financial_data import UserProfile

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def sample_profile() -> UserProfile:
    """Load the sample profile from data/sample_profile.json."""
    with open(DATA_DIR / "sample_profile.json") as f:
        return UserProfile.model_validate(json.load(f))


@pytest.fixture
def empty_profile() -> UserProfile:
    """A blank profile with no assets, debts, or goals."""
    return UserProfile()
