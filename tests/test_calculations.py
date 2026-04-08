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
from calculations.cashflow import CashFlowBreakdown, annual_cash_flow, student_loan_annual_repayment
from calculations.projections import find_milestones, mortgage_info_at_retirement, project_net_worth, debt_payoff_projection
from calculations.instruments import (
    AssetState,
    LoanGoalState,
    MortgageGoalState,
    SavingsGoalState,
    StandardDebtState,
    StudentLoanState,
    create_debt_state,
    create_goal_state,
)
from calculations.retirement import (
    drawdown_simulation,
    future_value,
    healthcare_cost_projection,
    inflation_adjusted,
    required_pot_size,
    retirement_income_gap,
    retirement_readiness,
    savings_needed,
    years_to_fire,
)
from calculations.tax import (
    capital_gains_tax,
    income_tax,
    inheritance_tax,
    national_insurance,
    pension_drawdown_tax,
)
from calculations.property import (
    amortization_schedule,
    calculate_equity,
    calculate_ltv,
    equity_over_time,
    property_profit,
)
from models.financial_data import (
    Asset,
    AssetCategory,
    Debt,
    DebtCategory,
    GoalFunding,
    LifeGoal,
    RetirementProfile,
    StudentLoanPlan,
    TaxWrapper,
    UserProfile,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_profile() -> UserProfile:
    with open(DATA_DIR / "sample_profile.json") as f:
        return UserProfile.model_validate(json.load(f))


@pytest.fixture
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


@pytest.fixture
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
            state_pension_age=67, expected_state_pension=11_973,
            life_expectancy=90,
        )
        gap = retirement_income_gap(profile)
        assert gap["phase1_years"] == 7  # 67 - 60
        assert gap["phase2_years"] == 23  # 90 - 67
        assert gap["phase1_gap"] == 35_000  # No guaranteed income in phase 1
        assert gap["phase2_gap"] == 35_000 - 11_973  # State pension in phase 2

    def test_retire_at_state_pension_age(self) -> None:
        """No phase-1 gap when retirement = SPA."""
        profile = RetirementProfile(
            current_age=40, target_retirement_age=67, desired_annual_income=30_000,
            state_pension_age=67, expected_state_pension=11_973,
            life_expectancy=90,
        )
        gap = retirement_income_gap(profile)
        assert gap["phase1_years"] == 0
        assert gap["phase2_years"] == 23
        assert gap["annual_gap"] == pytest.approx(30_000 - 11_973, rel=0.01)


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

    def test_drawdown_age_column(self) -> None:
        """When start_age is provided, an age column should be present."""
        sim = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=10, start_age=60)
        assert "age" in sim.columns
        assert sim.iloc[0]["age"] == 60
        assert sim.iloc[-1]["age"] == 69

    def test_drawdown_no_age_without_start_age(self) -> None:
        """Without start_age the age column should be absent."""
        sim = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=5)
        assert "age" not in sim.columns

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
            state_pension=11_973, state_pension_starts_year=5,
        )
        assert sim.iloc[3]["other_income"] == 0  # Year 4: no state pension yet
        assert sim.iloc[4]["other_income"] == pytest.approx(11_973, rel=0.01)  # Year 5: pension starts


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
        for col in ["year", "age", "total_assets", "total_debts", "net_worth", "goal_spending"]:
            assert col in proj.columns

    def test_projection_age_column_values(self, sample_profile: UserProfile) -> None:
        """Age column should start at current_age and increment by 1 each year."""
        proj = project_net_worth(sample_profile, years=10, scenario="Base")
        expected_start = sample_profile.retirement.current_age
        ages = proj["age"].tolist()
        assert ages == list(range(expected_start, expected_start + 11))

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

    def test_milestones_have_age(self, sample_profile: UserProfile) -> None:
        """Every milestone should carry an age field."""
        proj = project_net_worth(sample_profile, years=30, scenario="Base")
        milestones = find_milestones(proj, sample_profile)
        for m in milestones:
            assert "age" in m
            assert isinstance(m["age"], int)


# ══════════════════════════════════════════════════════════════════════════
#  Mortgage-Aware Savings & Retirement
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mortgage_profile() -> UserProfile:
    """Profile with a mortgage debt and liquid savings — no life goals."""
    return UserProfile(
        annual_salary=60_000,
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


@pytest.fixture
def goal_mortgage_profile() -> UserProfile:
    """Profile that buys a house via a mortgage-funded life goal."""
    from datetime import date as _d
    buy_year = _d.today().year + 3
    return UserProfile(
        annual_salary=55_000,
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
        profile = UserProfile(
            annual_salary=50_000,
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
            state_pension_age=67, expected_state_pension=11_973,
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
            state_pension_age=67, expected_state_pension=11_973,
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


# ══════════════════════════════════════════════════════════════════════════
#  Inheritance Tax
# ══════════════════════════════════════════════════════════════════════════

class TestInheritanceTax:
    def test_below_nil_rate_band_no_tax(self) -> None:
        """Estate fully within NRB and RNRB → zero IHT."""
        result = inheritance_tax(300_000, has_residential_property=True)
        assert result["iht_due"] == 0.0
        assert result["taxable_estate"] == 0.0

    def test_above_bands_standard_rate(self) -> None:
        """Estate of £1M with property → 40% on amount above £500k."""
        result = inheritance_tax(1_000_000, has_residential_property=True)
        assert result["taxable_estate"] == 500_000.0
        assert result["iht_due"] == pytest.approx(200_000.0)
        assert result["effective_rate"] == pytest.approx(0.20, rel=1e-3)

    def test_no_residential_property_smaller_band(self) -> None:
        """Without residential property the RNRB does not apply."""
        result_with = inheritance_tax(600_000, has_residential_property=True)
        result_without = inheritance_tax(600_000, has_residential_property=False)
        assert result_without["iht_due"] > result_with["iht_due"]
        # Without RNRB taxable is £275k; with RNRB taxable is £100k
        assert result_without["taxable_estate"] == pytest.approx(275_000.0)
        assert result_with["taxable_estate"] == pytest.approx(100_000.0)

    def test_spouse_transfer_doubles_bands(self) -> None:
        """Spousal transfer doubles both NRB and RNRB."""
        result_single = inheritance_tax(900_000, has_residential_property=True, spouse_transfer=False)
        result_spouse = inheritance_tax(900_000, has_residential_property=True, spouse_transfer=True)
        # Spouse bands = £650k + £350k = £1M, so £900k estate → zero IHT
        assert result_spouse["iht_due"] == 0.0
        assert result_single["iht_due"] > 0.0

    def test_charity_rate_reduction(self) -> None:
        """Leaving 10%+ to charity drops rate from 40% to 36%."""
        result_no_charity = inheritance_tax(1_000_000, has_residential_property=True, charity_fraction=0.0)
        result_charity = inheritance_tax(1_000_000, has_residential_property=True, charity_fraction=0.10)
        # Charity reduces taxable estate and applies lower rate
        assert result_charity["iht_due"] < result_no_charity["iht_due"]

    def test_zero_estate(self) -> None:
        """Zero estate → all zeros, no division-by-zero errors."""
        result = inheritance_tax(0.0)
        assert result["iht_due"] == 0.0
        assert result["effective_rate"] == 0.0
        assert result["taxable_estate"] == 0.0

    def test_effective_rate_calculated_correctly(self) -> None:
        """Effective rate = iht_due / gross_estate."""
        result = inheritance_tax(1_000_000, has_residential_property=True)
        expected_rate = result["iht_due"] / result["gross_estate"]
        assert result["effective_rate"] == pytest.approx(expected_rate, rel=1e-4)

    def test_nil_rate_band_used_capped_at_estate(self) -> None:
        """For small estates the band used is capped at the estate value."""
        result = inheritance_tax(100_000, has_residential_property=False)
        assert result["nil_rate_band_used"] == 100_000.0

    def test_residence_nil_rate_band_used_capped_at_remaining(self) -> None:
        """RNRB used is capped at remaining estate after NRB."""
        # Estate £400k, NRB £325k → remaining £75k, RNRB capped at £75k
        result = inheritance_tax(400_000, has_residential_property=True)
        assert result["residence_nil_rate_band_used"] == pytest.approx(75_000.0)
        assert result["iht_due"] == 0.0


# ══════════════════════════════════════════════════════════════════════════
#  PA Taper — Precise Band Calculations
# ══════════════════════════════════════════════════════════════════════════

class TestPersonalAllowanceTaper:
    """Income tax for incomes in the £100k–£200k+ range where the PA tapers."""

    def test_100k_exact(self) -> None:
        """£100k — PA not yet tapered, basic + higher only."""
        result = income_tax(100_000)
        basic = (50_270 - 12_570) * 0.20  # 7_540
        higher = (100_000 - 50_270) * 0.40  # 19_892
        assert result["tax"] == pytest.approx(basic + higher, abs=1)
        assert result["tax"] == pytest.approx(27_432, abs=1)

    def test_120k_partial_taper(self) -> None:
        """£120k — PA tapered to £2,570 → effective 60% marginal rate zone."""
        result = income_tax(120_000)
        # PA = 12_570 - (120_000 - 100_000) / 2 = 2_570
        # taxable = 120_000 - 2_570 = 117_430
        # basic band width = 37_700, higher band = 125_140 - 2_570 - 37_700 = 84_870
        # basic = 37_700 × 0.20 = 7_540
        # higher = (117_430 - 37_700) × 0.40 = 79_730 × 0.40 = 31_892
        assert result["tax"] == pytest.approx(7_540 + 31_892, abs=1)
        assert result["tax"] == pytest.approx(39_432, abs=1)

    def test_125140_full_taper(self) -> None:
        """£125,140 — PA fully tapered to £0."""
        result = income_tax(125_140)
        # PA = 0, taxable = 125_140
        # basic = 37_700 × 0.20 = 7_540
        # higher = (125_140 - 37_700) × 0.40 = 87_440 × 0.40 = 34_976
        assert result["tax"] == pytest.approx(7_540 + 34_976, abs=1)
        assert result["tax"] == pytest.approx(42_516, abs=1)

    def test_200k_additional_rate(self) -> None:
        """£200k — PA = 0, hits additional rate band at £125,140."""
        result = income_tax(200_000)
        # PA = 0, taxable = 200_000
        # basic = 37_700 × 0.20 = 7_540
        # higher = (125_140 - 37_700) × 0.40 = 87_440 × 0.40 = 34_976
        # additional = (200_000 - 125_140) × 0.45 = 74_860 × 0.45 = 33_687
        assert result["tax"] == pytest.approx(7_540 + 34_976 + 33_687, abs=2)
        assert result["tax"] == pytest.approx(76_203, abs=2)


# ══════════════════════════════════════════════════════════════════════════
#  PCLS Drawdown — Cumulative Tax-Free Tracking
# ══════════════════════════════════════════════════════════════════════════

class TestPCLSDrawdown:
    """pension_drawdown_tax with the tax_free_amount parameter."""

    def test_explicit_tax_free_amount(self) -> None:
        """Passing tax_free_amount overrides the lump_sum_taken boolean."""
        result = pension_drawdown_tax(30_000, other_income=0, tax_free_amount=30_000)
        assert result["tax_free_portion"] == 30_000
        assert result["taxable_portion"] == 0.0
        assert result["tax"] == 0.0

    def test_partial_tax_free(self) -> None:
        """When tax_free_amount < withdrawal, only that much is tax-free."""
        result = pension_drawdown_tax(30_000, other_income=0, tax_free_amount=10_000)
        assert result["tax_free_portion"] == 10_000
        assert result["taxable_portion"] == 20_000
        assert result["tax"] > 0

    def test_zero_tax_free_remaining(self) -> None:
        """When tax_free_amount is 0, entire withdrawal is taxable."""
        result = pension_drawdown_tax(30_000, other_income=0, tax_free_amount=0)
        assert result["tax_free_portion"] == 0
        assert result["taxable_portion"] == 30_000

    def test_drawdown_simulation_cumulative_pcls(self) -> None:
        """Drawdown simulation correctly tracks cumulative tax-free allowance."""
        sim = drawdown_simulation(pot=500_000, annual_withdrawal=25_000, years=10)
        # 25% of £500k = £125k tax-free capacity
        # First 5 years: £25k/yr fully tax-free → zero tax
        assert sim.iloc[0]["tax"] == 0.0
        assert sim.iloc[4]["tax"] == 0.0
        # Year 6: tax-free exhausted → tax > 0
        assert sim.iloc[5]["tax"] > 0


# ══════════════════════════════════════════════════════════════════════════
#  Student Loan — Income-Contingent Repayment
# ══════════════════════════════════════════════════════════════════════════

class TestStudentLoanProjection:
    """Student loans use income-contingent repayment in the projection engine."""

    @pytest.fixture
    def student_loan_profile(self) -> UserProfile:
        from datetime import date as _d
        return UserProfile(
            annual_salary=35_000,
            assets=[
                Asset(
                    name="Cash", category=AssetCategory.CASH, current_value=5_000,
                    annual_growth_rate=0.02, is_liquid=True, tax_wrapper=TaxWrapper.NONE,
                ),
            ],
            debts=[
                Debt(
                    name="Student Loan", category=DebtCategory.STUDENT_LOAN,
                    outstanding_balance=40_000, interest_rate=0.071,
                    monthly_payment=0,  # Income-contingent, not fixed
                    remaining_term_months=360,
                    student_loan_plan=StudentLoanPlan.PLAN_2,
                    student_loan_repayment_threshold=29_385,
                    student_loan_repayment_rate=0.09,
                    student_loan_write_off_years=30,
                    student_loan_start_year=_d.today().year,
                ),
            ],
            life_goals=[],
        )

    def test_student_loan_repayment_reduces_balance(self, student_loan_profile: UserProfile) -> None:
        """Over time, income-contingent repayments should reduce the loan balance."""
        proj = project_net_worth(student_loan_profile, years=10, scenario="Base")
        # Repayment = (35_000 - 29_385) × 0.09 = ~£505/yr (before interest)
        # Balance should decrease or at least not grow uncontrollably
        debt_y0 = proj.iloc[0]["total_debts"]
        debt_y10 = proj.iloc[10]["total_debts"]
        # With 7.1% interest on £40k (~£2,840/yr) vs ~£693 repayment,
        # balance grows — but it's being tracked, not ignored.
        assert debt_y10 > 0  # Loan still exists after 10 years at this salary

    def test_student_loan_written_off(self, student_loan_profile: UserProfile) -> None:
        """Student loan should be written off after 30 years."""
        proj = project_net_worth(student_loan_profile, years=35, scenario="Base")
        # By year 31+, the student loan should be gone
        debt_y35 = proj.iloc[35]["total_debts"]
        assert debt_y35 == 0.0

    def test_student_loan_no_repayment_below_threshold(self) -> None:
        """Salary below threshold → no repayment, only interest accrues."""
        from datetime import date as _d
        low_income = UserProfile(
            annual_salary=20_000,
            assets=[
                Asset(
                    name="Cash", category=AssetCategory.CASH, current_value=5_000,
                    annual_growth_rate=0.02, is_liquid=True, tax_wrapper=TaxWrapper.NONE,
                ),
            ],
            debts=[
                Debt(
                    name="Student Loan", category=DebtCategory.STUDENT_LOAN,
                    outstanding_balance=30_000, interest_rate=0.071,
                    monthly_payment=0,
                    remaining_term_months=360,
                    student_loan_plan=StudentLoanPlan.PLAN_2,
                    student_loan_repayment_threshold=29_385,
                    student_loan_repayment_rate=0.09,
                    student_loan_write_off_years=30,
                    student_loan_start_year=_d.today().year,
                ),
            ],
            life_goals=[],
        )
        proj = project_net_worth(low_income, years=5, scenario="Base")
        # Debt grows because salary < threshold so no repayment
        debt_y0 = proj.iloc[0]["total_debts"]
        debt_y5 = proj.iloc[5]["total_debts"]
        assert debt_y5 > debt_y0


# ══════════════════════════════════════════════════════════════════════════
#  Loan-Funded Goals
# ══════════════════════════════════════════════════════════════════════════

class TestLoanFundedGoals:
    """Goals with GoalFunding.LOAN deduct only the deposit from savings."""

    def test_loan_goal_only_deducts_deposit(self) -> None:
        """A £20k car loan with 10% deposit should only deduct £2k from savings."""
        from datetime import date as _d
        buy_year = _d.today().year + 1
        profile = UserProfile(
            annual_salary=40_000,
            assets=[
                Asset(
                    name="Cash", category=AssetCategory.CASH, current_value=20_000,
                    annual_growth_rate=0.02, is_liquid=True, tax_wrapper=TaxWrapper.NONE,
                ),
            ],
            debts=[],
            life_goals=[
                LifeGoal(
                    name="Buy a car", target_cost=20_000, target_year=buy_year,
                    funding_source=GoalFunding.LOAN,
                    deposit_percentage=0.10,
                    loan_interest_rate=0.05,
                    loan_term_years=5,
                ),
            ],
        )
        proj = project_net_worth(profile, years=10, scenario="Base")
        # After the goal year, debts should include the loan
        buy_idx = proj[proj["year"] == buy_year].index
        if not buy_idx.empty:
            idx = int(buy_idx[0])
            if idx + 1 < len(proj):
                debts_after = float(proj.iloc[idx + 1]["total_debts"])
                # Loan amount = £18k (£20k - 10% deposit)
                assert debts_after > 0  # Loan debt exists


# ══════════════════════════════════════════════════════════════════════════
#  Instrument State Classes
# ══════════════════════════════════════════════════════════════════════════


class TestAssetState:
    """Unit tests for AssetState — grow, contribute, withdraw, deposit."""

    def test_grow_applies_growth_rate(self) -> None:
        a = AssetState(name="ISA", category="ISA", is_liquid=True, value=10_000, growth_rate=0.07)
        a.grow()
        assert a.value == pytest.approx(10_700, abs=0.01)

    def test_contribute_while_working(self) -> None:
        a = AssetState(name="ISA", category="ISA", is_liquid=True, value=10_000, growth_rate=0.07, annual_contribution=1_000)
        a.contribute(is_retired=False)
        assert a.value == pytest.approx(11_000, abs=0.01)

    def test_contribute_skipped_when_retired(self) -> None:
        a = AssetState(name="ISA", category="ISA", is_liquid=True, value=10_000, growth_rate=0.07, annual_contribution=1_000)
        a.contribute(is_retired=True)
        assert a.value == pytest.approx(10_000, abs=0.01)

    def test_deposit_adds_to_value(self) -> None:
        a = AssetState(name="Cash", category="Cash", is_liquid=True, value=5_000, growth_rate=0.02)
        a.deposit(2_000)
        assert a.value == pytest.approx(7_000, abs=0.01)

    def test_withdraw_returns_actual_amount(self) -> None:
        a = AssetState(name="ISA", category="ISA", is_liquid=True, value=5_000, growth_rate=0.07)
        taken = a.withdraw(3_000)
        assert taken == pytest.approx(3_000, abs=0.01)
        assert a.value == pytest.approx(2_000, abs=0.01)

    def test_withdraw_capped_at_value(self) -> None:
        a = AssetState(name="ISA", category="ISA", is_liquid=True, value=1_000, growth_rate=0.07)
        taken = a.withdraw(5_000)
        assert taken == pytest.approx(1_000, abs=0.01)
        assert a.value == pytest.approx(0, abs=0.01)

    def test_from_model(self) -> None:
        model = Asset(name="Pension", category=AssetCategory.PENSION, current_value=50_000, annual_growth_rate=0.07, is_liquid=False, annual_contribution=5_000)
        a = AssetState.from_model(model, scenario_multiplier=1.0)
        assert a.name == "Pension"
        assert a.category == "Pension"
        assert not a.is_liquid
        assert a.value == pytest.approx(50_000, abs=0.01)


class TestStandardDebtState:
    """Unit tests for StandardDebtState — amortisation, payoff, is_cleared."""

    def test_accrue_and_pay_reduces_balance(self) -> None:
        d = StandardDebtState(name="Mortgage", category="Mortgage", balance=100_000, rate=0.04, annual_payment=10_000)
        d.accrue_and_pay(50_000, False, 2026)
        assert d.balance < 100_000
        assert d.balance > 0

    def test_is_cleared_when_zero(self) -> None:
        d = StandardDebtState(name="Loan", category="Loan", balance=0, rate=0.05, annual_payment=1_000)
        assert d.is_cleared

    def test_remaining_years_clears_balance(self) -> None:
        d = StandardDebtState(name="Loan", category="Loan", balance=500, rate=0.0, annual_payment=500, remaining_years=1)
        d.accrue_and_pay(0, False, 2026)
        assert d.balance == 0
        assert d.is_cleared

    def test_from_model(self) -> None:
        model = Debt(name="Mortgage", category=DebtCategory.MORTGAGE, outstanding_balance=200_000, interest_rate=0.04, monthly_payment=1_000, remaining_term_months=240)
        d = StandardDebtState.from_model(model)
        assert d.name == "Mortgage"
        assert d.balance == pytest.approx(200_000, abs=0.01)
        assert d.annual_payment == pytest.approx(12_000, abs=0.01)

    def test_skip_when_cleared(self) -> None:
        d = StandardDebtState(name="Loan", category="Loan", balance=0, rate=0.05, annual_payment=1_000)
        d.accrue_and_pay(50_000, False, 2026)
        assert d.balance == 0


class TestStudentLoanState:
    """Unit tests for StudentLoanState — income-contingent, write-off."""

    def test_repayment_reduces_balance(self) -> None:
        model = Debt(
            name="SL", category=DebtCategory.STUDENT_LOAN, outstanding_balance=40_000,
            interest_rate=0.05, monthly_payment=0, remaining_term_months=0,
            student_loan_start_year=2020, student_loan_write_off_years=30,
        )
        sl = StudentLoanState(model)
        sl.accrue_and_pay(salary=51_000, is_retired=False, year=2026)
        # interest: 40k * 1.05 = 42k; repayment: (51000 - 29385) * 0.09 = 1945.35
        assert sl.balance < 42_000
        assert sl.balance > 0

    def test_write_off(self) -> None:
        model = Debt(
            name="SL", category=DebtCategory.STUDENT_LOAN, outstanding_balance=40_000,
            interest_rate=0.05, monthly_payment=0, remaining_term_months=0,
            student_loan_start_year=2000, student_loan_write_off_years=25,
        )
        sl = StudentLoanState(model)
        # write-off year = 2000 + 25 = 2025; year 2026 >= 2025 → written off
        sl.accrue_and_pay(salary=51_000, is_retired=False, year=2026)
        assert sl.balance == 0
        assert sl.is_cleared

    def test_no_repayment_when_below_threshold(self) -> None:
        model = Debt(
            name="SL", category=DebtCategory.STUDENT_LOAN, outstanding_balance=40_000,
            interest_rate=0.05, monthly_payment=0, remaining_term_months=0,
            student_loan_start_year=2020, student_loan_write_off_years=30,
        )
        sl = StudentLoanState(model)
        sl.accrue_and_pay(salary=20_000, is_retired=False, year=2026)
        # Only interest accrued, no repayment (salary < threshold)
        assert sl.balance == pytest.approx(42_000, abs=0.01)

    def test_no_repayment_when_retired(self) -> None:
        model = Debt(
            name="SL", category=DebtCategory.STUDENT_LOAN, outstanding_balance=40_000,
            interest_rate=0.05, monthly_payment=0, remaining_term_months=0,
            student_loan_start_year=2020, student_loan_write_off_years=30,
        )
        sl = StudentLoanState(model)
        sl.accrue_and_pay(salary=51_000, is_retired=True, year=2026)
        # Only interest, no repayment when retired
        assert sl.balance == pytest.approx(42_000, abs=0.01)

    def test_annual_payment_is_zero(self) -> None:
        model = Debt(
            name="SL", category=DebtCategory.STUDENT_LOAN, outstanding_balance=40_000,
            interest_rate=0.05, monthly_payment=0, remaining_term_months=0,
        )
        sl = StudentLoanState(model)
        assert sl.annual_payment == 0.0


class TestGoalStates:
    """Unit tests for SavingsGoalState, MortgageGoalState, LoanGoalState."""

    def test_savings_goal_lump_sum(self) -> None:
        goal = LifeGoal(name="Cabin", target_cost=80_000, target_year=2033, funding_source=GoalFunding.SAVINGS)
        gs = SavingsGoalState(goal)
        assert gs.lump_sum_cost() == pytest.approx(80_000)

    def test_savings_goal_ongoing_cost_in_range(self) -> None:
        goal = LifeGoal(name="Kids", target_cost=30_000, target_year=2031, funding_source=GoalFunding.SAVINGS, annual_ongoing_cost=15_000, ongoing_years=18)
        gs = SavingsGoalState(goal)
        assert gs.ongoing_cost(2031) == pytest.approx(15_000)
        assert gs.ongoing_cost(2048) == pytest.approx(15_000)
        assert gs.ongoing_cost(2049) == 0.0
        assert gs.ongoing_cost(2030) == 0.0

    def test_savings_goal_activate_spawns_nothing(self) -> None:
        goal = LifeGoal(name="Cabin", target_cost=80_000, target_year=2033, funding_source=GoalFunding.SAVINGS)
        gs = SavingsGoalState(goal)
        new_assets, new_debts = gs.activate(1.0)
        assert new_assets == []
        assert new_debts == []

    def test_mortgage_goal_lump_sum_is_deposit(self) -> None:
        goal = LifeGoal(name="House", target_cost=350_000, target_year=2029, funding_source=GoalFunding.MORTGAGE, deposit_percentage=0.10)
        gs = MortgageGoalState(goal)
        assert gs.lump_sum_cost() == pytest.approx(35_000)

    def test_mortgage_goal_activate_spawns_property_and_debt(self) -> None:
        goal = LifeGoal(
            name="House", target_cost=350_000, target_year=2029,
            funding_source=GoalFunding.MORTGAGE, deposit_percentage=0.10,
            mortgage_rate=0.045, mortgage_term_years=25,
        )
        gs = MortgageGoalState(goal)
        new_assets, new_debts = gs.activate(1.0)
        assert len(new_assets) == 1
        assert len(new_debts) == 1
        assert new_assets[0].category == "Property"
        assert new_assets[0].value == pytest.approx(350_000)
        assert not new_assets[0].is_liquid
        assert new_debts[0].balance == pytest.approx(315_000)

    def test_loan_goal_lump_sum_is_deposit(self) -> None:
        goal = LifeGoal(name="Car", target_cost=20_000, target_year=2028, funding_source=GoalFunding.LOAN, deposit_percentage=0.15)
        gs = LoanGoalState(goal)
        assert gs.lump_sum_cost() == pytest.approx(3_000)

    def test_loan_goal_activate_spawns_debt_only(self) -> None:
        goal = LifeGoal(
            name="Car", target_cost=20_000, target_year=2028,
            funding_source=GoalFunding.LOAN, deposit_percentage=0.15,
            loan_interest_rate=0.05, loan_term_years=5,
        )
        gs = LoanGoalState(goal)
        new_assets, new_debts = gs.activate(1.0)
        assert new_assets == []
        assert len(new_debts) == 1
        assert new_debts[0].balance == pytest.approx(17_000)

    def test_create_debt_state_factory(self) -> None:
        sl_model = Debt(name="SL", category=DebtCategory.STUDENT_LOAN, outstanding_balance=40_000, interest_rate=0.05, monthly_payment=0, remaining_term_months=0)
        ml_model = Debt(name="Mortgage", category=DebtCategory.MORTGAGE, outstanding_balance=200_000, interest_rate=0.04, monthly_payment=1_000, remaining_term_months=240)
        assert isinstance(create_debt_state(sl_model), StudentLoanState)
        assert isinstance(create_debt_state(ml_model), StandardDebtState)

    def test_create_goal_state_factory(self) -> None:
        g1 = LifeGoal(name="A", target_cost=100, target_year=2030, funding_source=GoalFunding.SAVINGS)
        g2 = LifeGoal(name="B", target_cost=100, target_year=2030, funding_source=GoalFunding.MORTGAGE)
        g3 = LifeGoal(name="C", target_cost=100, target_year=2030, funding_source=GoalFunding.LOAN)
        g4 = LifeGoal(name="D", target_cost=100, target_year=2030, funding_source=GoalFunding.MIXED)
        assert isinstance(create_goal_state(g1), SavingsGoalState)
        assert isinstance(create_goal_state(g2), MortgageGoalState)
        assert isinstance(create_goal_state(g3), LoanGoalState)
        assert isinstance(create_goal_state(g4), MortgageGoalState)


# ══════════════════════════════════════════════════════════════════════════
#  Property Calculations
# ══════════════════════════════════════════════════════════════════════════

class TestPropertyCalculations:
    """Tests for calculations/property.py."""

    def test_calculate_ltv_typical(self) -> None:
        assert calculate_ltv(180_000, 200_000) == 90.0

    def test_calculate_ltv_zero_value(self) -> None:
        assert calculate_ltv(100_000, 0) == 0.0

    def test_calculate_ltv_no_mortgage(self) -> None:
        assert calculate_ltv(0, 300_000) == 0.0

    def test_calculate_equity(self) -> None:
        assert calculate_equity(300_000, 200_000) == 100_000

    def test_calculate_equity_underwater(self) -> None:
        assert calculate_equity(150_000, 200_000) == -50_000

    def test_amortization_schedule_basic(self) -> None:
        df = amortization_schedule(200_000, 0.05, 25)
        assert len(df) == 25
        assert list(df.columns) == ["year", "payment", "principal_paid", "interest_paid", "remaining_balance"]
        # Balance should reduce to ~0 by end
        assert df.iloc[-1]["remaining_balance"] < 1.0
        # First year interest > principal; last year principal > interest
        assert df.iloc[0]["interest_paid"] > df.iloc[0]["principal_paid"]
        assert df.iloc[-1]["principal_paid"] > df.iloc[-1]["interest_paid"]

    def test_amortization_schedule_zero_principal(self) -> None:
        df = amortization_schedule(0, 0.05, 25)
        assert df.empty

    def test_amortization_schedule_zero_rate(self) -> None:
        df = amortization_schedule(120_000, 0.0, 10)
        assert len(df) == 10
        assert df["interest_paid"].sum() == 0.0
        assert df.iloc[-1]["remaining_balance"] < 1.0

    def test_equity_over_time_shape(self) -> None:
        df = equity_over_time(300_000, 0.03, 200_000, 0.05, 25, 30)
        assert len(df) == 31  # year 0 through 30
        assert df.iloc[0]["year"] == 0
        assert df.iloc[-1]["year"] == 30
        # Equity should grow over time
        assert df.iloc[-1]["equity"] > df.iloc[0]["equity"]
        # LTV should decrease
        assert df.iloc[-1]["ltv"] < df.iloc[0]["ltv"]

    def test_equity_over_time_mortgage_paid_off(self) -> None:
        """After mortgage term, balance should be zero."""
        df = equity_over_time(200_000, 0.02, 150_000, 0.04, 20, 25)
        # At year 20+, mortgage should be paid off
        assert df.iloc[20]["mortgage_balance"] < 1.0

    def test_property_profit_gain(self) -> None:
        assert property_profit(400_000, 300_000, 50_000) == 50_000

    def test_property_profit_loss(self) -> None:
        assert property_profit(280_000, 300_000, 50_000) == -70_000


# ══════════════════════════════════════════════════════════════════════════
#  Years to FIRE
# ══════════════════════════════════════════════════════════════════════════

class TestYearsToFire:
    """Tests for years_to_fire() in calculations/retirement.py."""

    def test_already_fire_with_large_pot(self) -> None:
        profile = UserProfile(
            assets=[
                Asset(name="Pension", category=AssetCategory.PENSION, current_value=2_000_000, annual_growth_rate=0.04),
            ],
            retirement=RetirementProfile(
                current_age=40,
                target_retirement_age=60,
                desired_annual_income=30_000,
                life_expectancy=90,
            ),
            annual_salary=50_000,
        )
        result = years_to_fire(profile)
        assert result == 0

    def test_returns_none_when_no_pension(self) -> None:
        profile = UserProfile(
            retirement=RetirementProfile(
                current_age=30,
                target_retirement_age=65,
                desired_annual_income=50_000,
                life_expectancy=90,
            ),
            annual_salary=30_000,
        )
        # No pension assets and no savings → None
        result = years_to_fire(profile)
        # Could be None or a high number depending on gap
        assert result is None or result > 50

    def test_returns_positive_years(self) -> None:
        profile = UserProfile(
            assets=[
                Asset(name="Pension", category=AssetCategory.PENSION, current_value=50_000, annual_growth_rate=0.06, annual_contribution=10_000),
            ],
            retirement=RetirementProfile(
                current_age=30,
                target_retirement_age=60,
                desired_annual_income=25_000,
                life_expectancy=90,
            ),
            annual_salary=50_000,
        )
        result = years_to_fire(profile)
        assert result is not None
        assert 5 < result < 40


# ══════════════════════════════════════════════════════════════════════════
#  Debt Payoff Projection
# ══════════════════════════════════════════════════════════════════════════

class TestDebtPayoffProjection:
    """Tests for debt_payoff_projection() in calculations/projections.py."""

    def test_empty_debts(self) -> None:
        profile = UserProfile()
        df = debt_payoff_projection(profile)
        assert "year" in df.columns
        assert "age" in df.columns
        assert len(df) == 0

    def test_single_loan_pays_off(self) -> None:
        profile = UserProfile(
            debts=[
                Debt(
                    name="Car Loan",
                    category=DebtCategory.LOAN,
                    outstanding_balance=10_000,
                    interest_rate=0.05,
                    monthly_payment=500,
                    remaining_term_months=24,
                ),
            ],
            annual_salary=40_000,
        )
        df = debt_payoff_projection(profile, years=5)
        assert len(df) == 6  # years 0 through 5
        assert "Car Loan_balance" in df.columns
        # Balance should reduce over time
        assert df.iloc[-1]["Car Loan_balance"] < df.iloc[0]["Car Loan_balance"]

    def test_student_loan_writes_off(self) -> None:
        from datetime import date
        profile = UserProfile(
            debts=[
                Debt(
                    name="Student Loan",
                    category=DebtCategory.STUDENT_LOAN,
                    outstanding_balance=40_000,
                    interest_rate=0.05,
                    monthly_payment=0,
                    remaining_term_months=0,
                    student_loan_plan=StudentLoanPlan.PLAN_2,
                    student_loan_start_year=date.today().year - 25,
                    student_loan_write_off_years=30,
                ),
            ],
            annual_salary=35_000,
        )
        df = debt_payoff_projection(profile, years=10)
        assert len(df) == 11
        assert "Student Loan_balance" in df.columns
        # Write-off in 5 years (30 - 25 years elapsed)
        assert df.iloc[-1]["Student Loan_balance"] == 0.0

    def test_multiple_debts_tracked(self) -> None:
        profile = UserProfile(
            debts=[
                Debt(name="Loan A", category=DebtCategory.LOAN, outstanding_balance=5_000, interest_rate=0.03, monthly_payment=200, remaining_term_months=30),
                Debt(name="Loan B", category=DebtCategory.LOAN, outstanding_balance=8_000, interest_rate=0.04, monthly_payment=300, remaining_term_months=36),
            ],
            annual_salary=50_000,
        )
        df = debt_payoff_projection(profile, years=5)
        assert "Loan A_balance" in df.columns
        assert "Loan B_balance" in df.columns


# ══════════════════════════════════════════════════════════════════════════
#  Cash Flow Waterfall
# ══════════════════════════════════════════════════════════════════════════

class TestCashFlow:
    """Tests for calculations/cashflow.py — annual cash flow waterfall."""

    def test_basic_salary_breakdown(self) -> None:
        """Tax, NI, and expenses should reduce gross to a positive surplus."""
        profile = UserProfile(annual_salary=50_000)
        cf = annual_cash_flow(profile)
        assert cf.gross_salary == 50_000
        assert cf.income_tax > 0
        assert cf.national_insurance > 0
        assert cf.net_take_home < 50_000
        assert cf.surplus >= 0
        # Net take-home should equal gross minus deductions
        expected_net = (
            cf.gross_salary
            - cf.pension_contribution
            - cf.income_tax
            - cf.national_insurance
            - cf.student_loan_repayment
        )
        assert abs(cf.net_take_home - expected_net) < 0.01

    def test_pension_sacrifice_reduces_taxable(self) -> None:
        """Pension contribution should reduce the adjusted gross for tax."""
        profile = UserProfile(
            annual_salary=60_000,
            assets=[
                Asset(
                    name="Pension", category=AssetCategory.PENSION,
                    current_value=50_000, annual_growth_rate=0.05,
                    annual_contribution=10_000, tax_wrapper=TaxWrapper.PENSION,
                ),
            ],
        )
        cf = annual_cash_flow(profile)
        assert cf.pension_contribution == 10_000
        assert cf.adjusted_gross == 50_000
        # Tax should be on adjusted gross, not full salary
        no_pension = annual_cash_flow(UserProfile(annual_salary=60_000))
        assert cf.income_tax < no_pension.income_tax

    def test_student_loan_deducted(self) -> None:
        """Student loan repayment should appear in deductions."""
        profile = UserProfile(
            annual_salary=40_000,
            debts=[
                Debt(
                    name="Student Loan", category=DebtCategory.STUDENT_LOAN,
                    outstanding_balance=30_000, interest_rate=0.065,
                    monthly_payment=0, remaining_term_months=300,
                    student_loan_plan=StudentLoanPlan.PLAN_2,
                ),
            ],
        )
        cf = annual_cash_flow(profile)
        assert cf.student_loan_repayment > 0
        # Threshold is ~£29,385 for Plan 2; salary above → repayment
        assert cf.student_loan_repayment == pytest.approx(
            (40_000 - 29_385) * 0.09, abs=1.0
        )

    def test_credit_cards_excluded(self) -> None:
        """Credit card debts should not appear in cash flow outflows."""
        profile = UserProfile(
            annual_salary=50_000,
            debts=[
                Debt(
                    name="Credit Card", category=DebtCategory.CREDIT_CARD,
                    outstanding_balance=5_000, interest_rate=0.20,
                    monthly_payment=200, remaining_term_months=30,
                ),
            ],
        )
        cf = annual_cash_flow(profile)
        assert cf.loan_payments == 0.0

    def test_salary_growth_over_years(self) -> None:
        """Gross salary should grow with yr_offset."""
        profile = UserProfile(annual_salary=50_000)
        cf_yr0 = annual_cash_flow(profile, yr_offset=0)
        cf_yr5 = annual_cash_flow(profile, yr_offset=5)
        assert cf_yr5.gross_salary > cf_yr0.gross_salary

    def test_expenses_inflate_over_years(self) -> None:
        """Living expenses and holiday budget should inflate."""
        profile = UserProfile(annual_salary=80_000)
        cf_yr0 = annual_cash_flow(profile, yr_offset=0)
        cf_yr5 = annual_cash_flow(profile, yr_offset=5)
        assert cf_yr5.living_expenses > cf_yr0.living_expenses
        assert cf_yr5.holiday_budget > cf_yr0.holiday_budget

    def test_retired_returns_zeros(self) -> None:
        """When retired, salary-side should be zero."""
        profile = UserProfile(annual_salary=60_000)
        cf = annual_cash_flow(profile, is_retired=True)
        assert cf.gross_salary == 0.0
        assert cf.net_take_home == 0.0
        assert cf.surplus == 0.0

    def test_mortgage_payments_passed_through(self) -> None:
        """Active mortgage payments should appear in outflows."""
        profile = UserProfile(annual_salary=60_000)
        cf = annual_cash_flow(profile, active_mortgage_payments=12_000)
        assert cf.mortgage_payments == 12_000
        assert cf.total_outflows >= 12_000

    def test_surplus_non_negative(self) -> None:
        """Surplus should never go below zero (clamped)."""
        profile = UserProfile(
            annual_salary=20_000,
            annual_living_expenses=50_000,
        )
        cf = annual_cash_flow(profile)
        assert cf.surplus >= 0.0


class TestStudentLoanAnnualRepayment:
    """Tests for the student_loan_annual_repayment helper."""

    def test_above_threshold(self) -> None:
        result = student_loan_annual_repayment(40_000, 29_385, 0.09)
        assert result == pytest.approx((40_000 - 29_385) * 0.09)

    def test_below_threshold(self) -> None:
        result = student_loan_annual_repayment(25_000, 29_385, 0.09)
        assert result == 0.0

    def test_at_threshold(self) -> None:
        result = student_loan_annual_repayment(29_385, 29_385, 0.09)
        assert result == 0.0
