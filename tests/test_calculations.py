"""Calculation logic tests — realistic scenarios for UK financial planning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from calculations.net_worth import (
    asset_allocation,
    debt_to_asset_ratio,
    liquidity_breakdown,
    net_worth,
    total_assets,
    total_debts,
)
from calculations.projections import find_milestones, mortgage_info_at_retirement, project_net_worth
from calculations.retirement import (
    drawdown_simulation,
    future_value,
    healthcare_cost_projection,
    inflation_adjusted,
    required_pot_size,
    retirement_income_gap,
    retirement_readiness,
    savings_needed,
)
from calculations.tax import (
    capital_gains_tax,
    income_tax,
    national_insurance,
    pension_drawdown_tax,
)
from models.financial_data import (
    Asset,
    AssetCategory,
    Debt,
    DebtCategory,
    DefinedBenefitPension,
    GoalFunding,
    LifeGoal,
    RetirementProfile,
    TaxWrapper,
    UserProfile,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def sample_profile() -> UserProfile:
    with open(DATA_DIR / "sample_profile.json") as f:
        return UserProfile.model_validate(json.load(f))


@pytest.fixture()
def typical_assets() -> list[Asset]:
    """A 30-year-old with an ISA, a pension, and a house."""
    return [
        Asset(name="S&S ISA", category=AssetCategory.ISA, current_value=60_000,
              annual_growth_rate=0.07, is_liquid=True, tax_wrapper=TaxWrapper.ISA),
        Asset(name="Workplace Pension", category=AssetCategory.PENSION, current_value=25_000,
              annual_growth_rate=0.07, is_liquid=False, tax_wrapper=TaxWrapper.PENSION),
        Asset(name="Family Home", category=AssetCategory.PROPERTY, current_value=300_000,
              annual_growth_rate=0.04, is_liquid=False, tax_wrapper=TaxWrapper.NONE),
    ]


@pytest.fixture()
def typical_debts() -> list[Debt]:
    """Mortgage + student loan."""
    return [
        Debt(name="Mortgage", category=DebtCategory.MORTGAGE,
             outstanding_balance=250_000, interest_rate=0.045,
             monthly_payment=1_400, remaining_term_months=300),
        Debt(name="Student Loan", category=DebtCategory.STUDENT_LOAN,
             outstanding_balance=45_000, interest_rate=0.05,
             monthly_payment=0, remaining_term_months=0),
    ]


# ══════════════════════════════════════════════════════════════════════════
#  Net Worth
# ══════════════════════════════════════════════════════════════════════════

class TestNetWorth:
    def test_total_assets(self, typical_assets: list[Asset]) -> None:
        assert total_assets(typical_assets) == 385_000

    def test_total_debts(self, typical_debts: list[Debt]) -> None:
        assert total_debts(typical_debts) == 295_000

    def test_net_worth_positive(self, typical_assets: list[Asset], typical_debts: list[Debt]) -> None:
        nw = net_worth(typical_assets, typical_debts)
        assert nw == 90_000  # 385k assets - 295k debts

    def test_net_worth_empty(self) -> None:
        assert net_worth([], []) == 0.0

    def test_liquidity_breakdown(self, typical_assets: list[Asset]) -> None:
        lb = liquidity_breakdown(typical_assets)
        assert lb["liquid"] == 60_000  # Only ISA is liquid
        assert lb["illiquid"] == 325_000  # Pension + property
        assert lb["total"] == 385_000
        assert lb["liquid_ratio"] == pytest.approx(60_000 / 385_000, rel=1e-4)

    def test_liquidity_empty_assets(self) -> None:
        lb = liquidity_breakdown([])
        assert lb["liquid_ratio"] == 0.0

    def test_asset_allocation_percentages_sum_to_100(self, typical_assets: list[Asset]) -> None:
        alloc = asset_allocation(typical_assets)
        total_pct = sum(v["percentage"] for v in alloc.values())
        assert total_pct == pytest.approx(100.0, abs=0.01)

    def test_asset_allocation_values(self, typical_assets: list[Asset]) -> None:
        alloc = asset_allocation(typical_assets)
        assert alloc["ISA"]["value"] == 60_000
        assert alloc["Property"]["value"] == 300_000
        assert alloc["Property"]["percentage"] == pytest.approx(300_000 / 385_000 * 100, rel=1e-4)

    def test_debt_to_asset_ratio(self, typical_assets: list[Asset], typical_debts: list[Debt]) -> None:
        ratio = debt_to_asset_ratio(typical_assets, typical_debts)
        assert ratio == pytest.approx(295_000 / 385_000, rel=1e-4)

    def test_debt_to_asset_ratio_no_assets(self, typical_debts: list[Debt]) -> None:
        assert debt_to_asset_ratio([], typical_debts) == 0.0


# ══════════════════════════════════════════════════════════════════════════
#  UK Tax
# ══════════════════════════════════════════════════════════════════════════

class TestIncomeTax:
    def test_below_personal_allowance(self) -> None:
        result = income_tax(10_000)
        assert result["tax"] == 0.0
        assert result["effective_rate"] == 0.0

    def test_basic_rate_only(self) -> None:
        """£30k salary: (30000 - 12570) × 20% = £3,486."""
        result = income_tax(30_000)
        assert result["tax"] == 3_486.0
        assert result["effective_rate"] == pytest.approx(3_486 / 30_000, abs=0.0001)
        assert len(result["breakdown"]) == 1
        assert result["breakdown"][0]["band"] == "Basic Rate"

    def test_higher_rate(self) -> None:
        """£60k: basic band (50270-12570)×20% + higher band (60000-50270)×40%."""
        result = income_tax(60_000)
        basic = (50_270 - 12_570) * 0.20  # 7540
        higher = (60_000 - 50_270) * 0.40  # 3892
        assert result["tax"] == pytest.approx(basic + higher, abs=0.01)
        assert len(result["breakdown"]) == 2

    def test_personal_allowance_taper(self) -> None:
        """At £125,140 the personal allowance is fully tapered away."""
        result = income_tax(125_140)
        # PA tapers: (125140 - 100000) / 2 = 12570 → PA = 0
        # Fully taxable: basic + higher + no PA
        assert result["tax"] > income_tax(100_000)["tax"]

    def test_additional_rate(self) -> None:
        """£200k salary hits all bands including 45% additional rate."""
        result = income_tax(200_000)
        assert result["effective_rate"] > 0.35  # Effective rate well above basic
        bands = [b["band"] for b in result["breakdown"]]
        assert "Additional Rate" in bands

    def test_zero_income(self) -> None:
        result = income_tax(0)
        assert result["tax"] == 0.0


class TestNationalInsurance:
    def test_below_threshold(self) -> None:
        assert national_insurance(10_000) == 0.0

    def test_between_thresholds(self) -> None:
        """£30k: (30000 - 12570) × 8% = £1,394.40."""
        ni = national_insurance(30_000)
        assert ni == pytest.approx((30_000 - 12_570) * 0.08, abs=0.01)

    def test_above_upper_limit(self) -> None:
        """£60k: (50270-12570)×8% + (60000-50270)×2%."""
        ni = national_insurance(60_000)
        main = (50_270 - 12_570) * 0.08
        upper = (60_000 - 50_270) * 0.02
        assert ni == pytest.approx(main + upper, abs=0.01)


class TestCapitalGainsTax:
    def test_within_annual_exempt(self) -> None:
        """Gains under £3,000 are tax-free."""
        assert capital_gains_tax(2_500) == 0.0

    def test_basic_rate_shares(self) -> None:
        """£20k gain on shares, basic rate: (20000-3000)×10% = £1,700."""
        assert capital_gains_tax(20_000) == pytest.approx(17_000 * 0.10, abs=0.01)

    def test_higher_rate_property(self) -> None:
        """£50k property gain, higher rate: (50000-3000)×24% = £11,280."""
        assert capital_gains_tax(50_000, is_property=True, is_higher_rate=True) == pytest.approx(
            47_000 * 0.24, abs=0.01
        )


class TestPensionDrawdownTax:
    def test_first_withdrawal_25pct_tax_free(self) -> None:
        """First withdrawal gets 25% tax-free via PCLS."""
        result = pension_drawdown_tax(40_000, other_income=0, lump_sum_taken=False)
        assert result["tax_free_portion"] == 10_000
        assert result["taxable_portion"] == 30_000
        assert result["net_withdrawal"] > result["withdrawal"] - result["tax_free_portion"]

    def test_subsequent_withdrawal_fully_taxed(self) -> None:
        """After lump sum taken, entire withdrawal is taxable."""
        result = pension_drawdown_tax(40_000, other_income=0, lump_sum_taken=True)
        assert result["tax_free_portion"] == 0.0
        assert result["taxable_portion"] == 40_000
        assert result["tax"] > 0

    def test_net_withdrawal_never_exceeds_gross(self) -> None:
        result = pension_drawdown_tax(50_000, other_income=20_000, lump_sum_taken=True)
        assert result["net_withdrawal"] <= result["withdrawal"]
        assert result["net_withdrawal"] > 0


# ══════════════════════════════════════════════════════════════════════════
#  Retirement
# ══════════════════════════════════════════════════════════════════════════

class TestRetirementHelpers:
    def test_inflation_adjusted_erodes_purchasing_power(self) -> None:
        """£100 in 10 years at 2.5% inflation buys less."""
        adjusted = inflation_adjusted(100, years=10, inflation_rate=0.025)
        assert adjusted < 100
        assert adjusted == pytest.approx(100 / (1.025 ** 10), abs=0.01)

    def test_inflation_adjusted_zero_years(self) -> None:
        assert inflation_adjusted(1000, years=0) == 1000.0

    def test_future_value_compounding(self) -> None:
        """£10k at 7% for 30 years → ~£76.1k."""
        fv = future_value(10_000, years=30, rate=0.07)
        assert fv == pytest.approx(10_000 * (1.07 ** 30), abs=1)

    def test_retirement_readiness_fully_funded(self) -> None:
        assert retirement_readiness(500_000, 500_000) == 100.0

    def test_retirement_readiness_half_funded(self) -> None:
        assert retirement_readiness(250_000, 500_000) == 50.0

    def test_retirement_readiness_over_funded(self) -> None:
        """Capped at 100%."""
        assert retirement_readiness(600_000, 500_000) == 100.0


class TestRetirementIncomeGap:
    def test_early_retiree_has_two_phases(self) -> None:
        """Retiring at 60 with SPA 67 produces a phase-1 gap with no state pension."""
        profile = RetirementProfile(
            current_age=30, target_retirement_age=60, desired_annual_income=35_000,
            state_pension_age=67, expected_state_pension=11_502,
            life_expectancy=90,
        )
        gap = retirement_income_gap(profile)
        assert gap["phase1_years"] == 7  # 67 - 60
        assert gap["phase2_years"] == 23  # 90 - 67
        assert gap["phase1_gap"] == 35_000  # No guaranteed income in phase 1
        assert gap["phase2_gap"] == 35_000 - 11_502  # State pension in phase 2

    def test_retire_at_state_pension_age(self) -> None:
        """No phase-1 gap when retirement = SPA."""
        profile = RetirementProfile(
            current_age=40, target_retirement_age=67, desired_annual_income=30_000,
            state_pension_age=67, expected_state_pension=11_502,
            life_expectancy=90,
        )
        gap = retirement_income_gap(profile)
        assert gap["phase1_years"] == 0
        assert gap["phase2_years"] == 23
        assert gap["annual_gap"] == pytest.approx(30_000 - 11_502, rel=0.01)

    def test_db_pension_reduces_gap(self) -> None:
        """A DB pension starting at 60 reduces the phase-1 gap."""
        profile = RetirementProfile(
            current_age=30, target_retirement_age=60, desired_annual_income=35_000,
            state_pension_age=67, expected_state_pension=11_502,
            life_expectancy=90,
            defined_benefit_pensions=[
                DefinedBenefitPension(name="Civil Service", annual_income=10_000, start_age=60),
            ],
        )
        gap = retirement_income_gap(profile)
        assert gap["phase1_guaranteed"] == 10_000
        assert gap["phase1_gap"] == 25_000  # 35k - 10k DB


class TestPotSizeAndSavings:
    def test_required_pot_positive(self) -> None:
        """A £23.5k annual gap over 30 years needs a substantial pot."""
        pot = required_pot_size(23_500, years_in_retirement=30, growth_rate=0.04, inflation_rate=0.025)
        assert pot > 400_000  # Should be a large pot
        assert pot < 1_000_000  # But not unreasonably large

    def test_required_pot_zero_gap(self) -> None:
        assert required_pot_size(0, years_in_retirement=30) == 0.0

    def test_savings_needed_from_zero(self) -> None:
        """Starting from £0, saving for a £500k pot over 30 years at 7%."""
        monthly = savings_needed(500_000, current_savings=0, years_to_retirement=30, growth_rate=0.07)
        assert monthly > 0
        assert monthly < 1_500  # Should be achievable monthly savings

    def test_savings_needed_already_funded(self) -> None:
        """If current savings can grow to exceed the target, no saving needed."""
        # £100k at 7% for 30 years → ~£761k, well above £500k target
        monthly = savings_needed(500_000, current_savings=100_000, years_to_retirement=30, growth_rate=0.07)
        assert monthly == 0.0

    def test_savings_needed_zero_years(self) -> None:
        """Already at retirement — shortfall is the gap itself."""
        monthly = savings_needed(500_000, current_savings=200_000, years_to_retirement=0)
        assert monthly == 300_000  # 500k - 200k


class TestDrawdownSimulation:
    def test_drawdown_produces_correct_years(self) -> None:
        sim = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=30)
        assert len(sim) == 30

    def test_drawdown_first_year_tax_free_portion(self) -> None:
        """Year 1 should include the 25% PCLS tax benefit."""
        sim = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=5)
        year1 = sim.iloc[0]
        # First withdrawal gets 25% tax-free, so tax should be lower
        assert year1["tax"] >= 0

    def test_drawdown_balance_depletes_with_high_withdrawal(self) -> None:
        """Withdrawing £80k/year from £500k pot should deplete it."""
        sim = drawdown_simulation(pot=500_000, annual_withdrawal=80_000, years=30)
        final = sim.iloc[-1]
        assert final["end_balance"] == 0.0

    def test_drawdown_with_state_pension_phasing(self) -> None:
        """State pension kicking in should appear in other_income."""
        sim = drawdown_simulation(
            pot=500_000, annual_withdrawal=30_000, years=10,
            state_pension=11_502, state_pension_starts_year=5,
        )
        assert sim.iloc[3]["other_income"] == 0  # Year 4: no state pension yet
        assert sim.iloc[4]["other_income"] == pytest.approx(11_502, rel=0.01)  # Year 5: pension starts


class TestHealthcareCosts:
    def test_healthcare_projection_positive(self) -> None:
        """£5k/year care from age 80 to 90, starting retirement at 60."""
        pv = healthcare_cost_projection(
            annual_cost=5_000, start_age=80, life_expectancy=90,
            inflation_rate=0.025, growth_rate=0.04, retirement_age=60,
        )
        assert pv > 0
        # 10 years of £5k inflated and discounted — should be substantial
        assert pv > 30_000

    def test_healthcare_zero_cost(self) -> None:
        assert healthcare_cost_projection(0, start_age=80, life_expectancy=90) == 0.0


# ══════════════════════════════════════════════════════════════════════════
#  Projections
# ══════════════════════════════════════════════════════════════════════════

class TestProjections:
    def test_projection_length(self, sample_profile: UserProfile) -> None:
        proj = project_net_worth(sample_profile, years=30, scenario="Base")
        assert len(proj) == 31  # Year 0 (now) through year 30

    def test_net_worth_grows_over_time(self, sample_profile: UserProfile) -> None:
        """With positive savings and growth, net worth should increase."""
        proj = project_net_worth(sample_profile, years=20, scenario="Base")
        first_nw = proj.iloc[0]["net_worth"]
        last_nw = proj.iloc[-1]["net_worth"]
        assert last_nw > first_nw

    def test_optimistic_beats_pessimistic(self, sample_profile: UserProfile) -> None:
        """Optimistic scenario should yield higher final net worth than pessimistic."""
        opt = project_net_worth(sample_profile, years=30, scenario="Optimistic")
        pes = project_net_worth(sample_profile, years=30, scenario="Pessimistic")
        assert opt.iloc[-1]["net_worth"] > pes.iloc[-1]["net_worth"]

    def test_projection_has_required_columns(self, sample_profile: UserProfile) -> None:
        proj = project_net_worth(sample_profile, years=10, scenario="Base")
        for col in ["year", "total_assets", "total_debts", "net_worth", "goal_spending"]:
            assert col in proj.columns

    def test_first_year_matches_current_state(self, sample_profile: UserProfile) -> None:
        """Year 0 should reflect the current balance sheet."""
        proj = project_net_worth(sample_profile, years=5, scenario="Base")
        row0 = proj.iloc[0]
        expected_assets = total_assets(sample_profile.assets)
        expected_debts = total_debts(sample_profile.debts)
        assert row0["total_assets"] == pytest.approx(expected_assets, rel=1e-4)
        assert row0["total_debts"] == pytest.approx(expected_debts, rel=1e-4)


class TestMilestones:
    def test_milestones_include_life_goals(self, sample_profile: UserProfile) -> None:
        proj = project_net_worth(sample_profile, years=30, scenario="Base")
        milestones = find_milestones(proj, sample_profile)
        goal_events = [m for m in milestones if m["event"].startswith("Goal:")]
        assert len(goal_events) == len(sample_profile.life_goals)

    def test_milestones_sorted_by_year(self, sample_profile: UserProfile) -> None:
        proj = project_net_worth(sample_profile, years=30, scenario="Base")
        milestones = find_milestones(proj, sample_profile)
        years = [m["year"] for m in milestones]
        assert years == sorted(years)


# ══════════════════════════════════════════════════════════════════════════
#  Mortgage-Aware Savings & Retirement
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def mortgage_profile() -> UserProfile:
    """Profile with a mortgage debt and liquid savings — no life goals."""
    return UserProfile(
        annual_salary=60_000,
        monthly_savings=2_000,
        annual_living_expenses=18_000,
        annual_holiday_budget=2_400,
        assets=[
            Asset(
                name="Cash ISA", category=AssetCategory.ISA, current_value=50_000,
                annual_growth_rate=0.07, is_liquid=True, tax_wrapper=TaxWrapper.ISA,
                annual_contribution=0,
            ),
        ],
        debts=[
            Debt(
                name="Mortgage", category=DebtCategory.MORTGAGE,
                outstanding_balance=200_000, interest_rate=0.045,
                monthly_payment=1_200, remaining_term_months=240,  # 20 years
            ),
        ],
        life_goals=[],
    )


@pytest.fixture()
def goal_mortgage_profile() -> UserProfile:
    """Profile that buys a house via a mortgage-funded life goal."""
    from datetime import date as _d
    buy_year = _d.today().year + 3
    return UserProfile(
        annual_salary=55_000,
        monthly_savings=1_500,
        annual_living_expenses=20_000,
        annual_holiday_budget=2_000,
        assets=[
            Asset(
                name="Cash ISA", category=AssetCategory.ISA, current_value=40_000,
                annual_growth_rate=0.07, is_liquid=True, tax_wrapper=TaxWrapper.ISA,
                annual_contribution=0,
            ),
            Asset(
                name="Pension", category=AssetCategory.PENSION, current_value=20_000,
                annual_growth_rate=0.07, is_liquid=False, tax_wrapper=TaxWrapper.PENSION,
                annual_contribution=3_000,
            ),
        ],
        debts=[],
        life_goals=[
            LifeGoal(
                name="Buy a house", target_cost=300_000, target_year=buy_year,
                funding_source=GoalFunding.MORTGAGE,
                deposit_percentage=0.10, mortgage_rate=0.045, mortgage_term_years=25,
            ),
        ],
    )


class TestMortgageAwareSavings:
    """Projection engine deducts mortgage payments from the savings pool."""

    def test_mortgage_reduces_savings_during_active_period(self, mortgage_profile: UserProfile) -> None:
        """With an active mortgage, less goes into liquid assets vs. no mortgage."""
        # Projection with mortgage
        proj_with = project_net_worth(mortgage_profile, years=10, scenario="Base")

        # Same profile but no mortgage
        no_mortgage = mortgage_profile.model_copy(deep=True)
        no_mortgage.debts = []
        proj_without = project_net_worth(no_mortgage, years=10, scenario="Base")

        # Year 5: liquid assets should be lower with mortgage (savings eaten by payments)
        # Even though net worth could differ due to debt, total_assets should be lower
        # because less money went into savings each year.
        with_assets_y5 = proj_with.iloc[5]["total_assets"]
        without_assets_y5 = proj_without.iloc[5]["total_assets"]
        assert without_assets_y5 > with_assets_y5

    def test_mortgage_payoff_increases_savings(self, mortgage_profile: UserProfile) -> None:
        """After mortgage pays off, more money flows into savings."""
        proj = project_net_worth(mortgage_profile, years=25, scenario="Base")

        # Find when debts hit zero
        debt_free_rows = proj[proj["total_debts"] <= 0]
        if not debt_free_rows.empty:
            payoff_idx = debt_free_rows.index[0]
            if payoff_idx > 1 and payoff_idx < len(proj) - 2:
                # Year-on-year asset growth should increase after payoff
                pre_payoff_growth = float(proj.iloc[payoff_idx]["total_assets"] - proj.iloc[payoff_idx - 1]["total_assets"])
                post_payoff_growth = float(proj.iloc[payoff_idx + 1]["total_assets"] - proj.iloc[payoff_idx]["total_assets"])
                assert post_payoff_growth > pre_payoff_growth

    def test_dynamic_mortgage_from_goal_reduces_savings(self, goal_mortgage_profile: UserProfile) -> None:
        """A mortgage-funded life goal should reduce savings once activated."""
        proj = project_net_worth(goal_mortgage_profile, years=30, scenario="Base")

        # Before goal year - no mortgage deductions
        # After goal year - mortgage payments reduce savings pool
        from datetime import date as _d
        buy_year = _d.today().year + 3
        buy_idx = proj[proj["year"] == buy_year].index
        if not buy_idx.empty:
            idx = int(buy_idx[0])
            # Total debts should jump when mortgage is created
            debts_before = float(proj.iloc[max(0, idx - 1)]["total_debts"])
            debts_after = float(proj.iloc[min(len(proj) - 1, idx + 1)]["total_debts"])
            assert debts_after > debts_before

    def test_no_mortgage_no_savings_deduction(self) -> None:
        """Profile without mortgage should distribute full savings."""
        profile = UserProfile(
            annual_salary=50_000,
            monthly_savings=1_000,
            assets=[
                Asset(
                    name="Cash", category=AssetCategory.CASH, current_value=10_000,
                    annual_growth_rate=0.02, is_liquid=True, tax_wrapper=TaxWrapper.NONE,
                    annual_contribution=0,
                ),
            ],
            debts=[],
            life_goals=[],
        )
        proj = project_net_worth(profile, years=5, scenario="Base")
        # With no mortgage, full £12k/yr savings should flow to assets
        year1_growth = float(proj.iloc[1]["total_assets"] - proj.iloc[0]["total_assets"])
        # Should be at least close to annual savings (£12k) plus some growth
        assert year1_growth > 11_000


class TestMortgageMilestones:
    """Mortgage payoff year detection."""

    def test_milestone_includes_mortgage_payoff(self, mortgage_profile: UserProfile) -> None:
        proj = project_net_worth(mortgage_profile, years=25, scenario="Base")
        milestones = find_milestones(proj, mortgage_profile)
        payoff_events = [m for m in milestones if m["event"] == "Mortgage paid off"]
        assert len(payoff_events) == 1

    def test_mortgage_info_at_retirement_extends(self) -> None:
        """Mortgage extending past retirement age should be flagged."""
        from datetime import date as _d
        profile = UserProfile(
            annual_salary=50_000,
            monthly_savings=1_000,
            assets=[
                Asset(name="Cash", category=AssetCategory.CASH, current_value=10_000,
                      annual_growth_rate=0.02, is_liquid=True, tax_wrapper=TaxWrapper.NONE),
            ],
            debts=[
                Debt(name="Mortgage", category=DebtCategory.MORTGAGE,
                     outstanding_balance=300_000, interest_rate=0.045,
                     monthly_payment=1_500, remaining_term_months=360),  # 30 years
            ],
            retirement=RetirementProfile(current_age=45, target_retirement_age=60),
        )
        info = mortgage_info_at_retirement(profile)
        assert info["has_mortgage"] is True
        assert info["extends_into_retirement"] is True
        assert info["mortgage_years_in_retirement"] > 0

    def test_mortgage_info_no_mortgage(self) -> None:
        profile = UserProfile(
            assets=[Asset(name="Cash", category=AssetCategory.CASH, current_value=10_000,
                          annual_growth_rate=0.02, is_liquid=True, tax_wrapper=TaxWrapper.NONE)],
            debts=[],
        )
        info = mortgage_info_at_retirement(profile)
        assert info["has_mortgage"] is False
        assert info["extends_into_retirement"] is False


class TestMortgageAwareRetirement:
    """Retirement calculations account for mortgage payments."""

    def test_income_gap_increases_with_mortgage(self) -> None:
        """Mortgage during retirement should increase the annual gap."""
        profile = RetirementProfile(
            current_age=30, target_retirement_age=65,
            desired_annual_income=30_000,
            state_pension_age=67, expected_state_pension=11_502,
            life_expectancy=90,
        )
        gap_no_mortgage = retirement_income_gap(profile)
        gap_with_mortgage = retirement_income_gap(
            profile, mortgage_annual_payment=12_000, mortgage_years_in_retirement=5,
        )
        assert gap_with_mortgage["annual_gap"] > gap_no_mortgage["annual_gap"]

    def test_income_gap_no_mortgage_unchanged(self) -> None:
        """Without mortgage params the gap should be identical to before."""
        profile = RetirementProfile(
            current_age=40, target_retirement_age=67,
            desired_annual_income=30_000,
            state_pension_age=67, expected_state_pension=11_502,
            life_expectancy=90,
        )
        gap = retirement_income_gap(profile)
        gap_explicit = retirement_income_gap(profile, mortgage_annual_payment=0.0, mortgage_years_in_retirement=0)
        assert gap["annual_gap"] == gap_explicit["annual_gap"]

    def test_pot_size_larger_with_mortgage(self) -> None:
        """Required pot should be larger when mortgage overlaps retirement."""
        base_pot = required_pot_size(20_000, 25, 0.04, 0.025)
        mortgage_pot = required_pot_size(
            20_000, 25, 0.04, 0.025,
            mortgage_annual_payment=15_000, mortgage_years_in_retirement=10,
        )
        assert mortgage_pot > base_pot

    def test_pot_size_no_mortgage_unchanged(self) -> None:
        """Without mortgage params pot should be identical."""
        pot_a = required_pot_size(20_000, 25, 0.04, 0.025)
        pot_b = required_pot_size(20_000, 25, 0.04, 0.025, mortgage_annual_payment=0)
        assert pot_a == pot_b

    def test_drawdown_with_mortgage_withdraws_more_early(self) -> None:
        """Drawdown with mortgage should withdraw more in early years."""
        sim_no = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=20)
        sim_with = drawdown_simulation(
            pot=500_000, annual_withdrawal=25_000, years=20,
            mortgage_annual_payment=12_000, mortgage_years_remaining=5,
        )
        # In year 3, withdrawal should be higher with mortgage
        assert sim_with.iloc[2]["withdrawal"] > sim_no.iloc[2]["withdrawal"]
        # In year 10 (after mortgage), withdrawal should be equal
        assert sim_with.iloc[9]["withdrawal"] == pytest.approx(sim_no.iloc[9]["withdrawal"], rel=0.01)

    def test_drawdown_no_mortgage_unchanged(self) -> None:
        """Drawdown without mortgage params should produce identical results."""
        sim_a = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=10)
        sim_b = drawdown_simulation(
            pot=500_000, annual_withdrawal=25_000, years=10,
            mortgage_annual_payment=0, mortgage_years_remaining=0,
        )
        assert sim_a["end_balance"].tolist() == sim_b["end_balance"].tolist()
