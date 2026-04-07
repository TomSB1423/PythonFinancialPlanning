"""Reusable Streamlit form helpers."""

from __future__ import annotations

from datetime import date

import streamlit as st

from models.financial_data import (
    Asset,
    AssetCategory,
    Debt,
    DebtCategory,
    GoalFunding,
    LifeGoal,
    StudentLoanPlan,
    TaxWrapper,
)
from components.multi_step_form import FormStep, MultiStepForm


def asset_form(key_prefix: str = "new_asset", defaults: Asset | None = None) -> Asset | None:
    """Render an asset input form using multi-step pattern. Returns Asset on submit, None otherwise."""
    d = defaults or Asset(name="", current_value=0)

    def step1_basic_info() -> dict:
        """Step 1: Asset name, category, current value."""
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Asset Name", value=d.name, key=f"{key_prefix}_name")
            st.caption("e.g., ISA, Pension Pot, Buy-to-Let Property")

        with col2:
            category_idx = [c.value for c in AssetCategory].index(d.category.value)
            category = st.selectbox(
                "Category",
                [c.value for c in AssetCategory],
                index=category_idx,
                key=f"{key_prefix}_category",
            )

        current_value = st.number_input(
            "Current Value (£)",
            min_value=0.0,
            value=float(d.current_value),
            step=1000.0,
            key=f"{key_prefix}_current_value",
        )

        return {
            "name": name,
            "category": category,
            "current_value": current_value,
        }

    def step2_growth_contribution() -> dict:
        """Step 2: Growth rate and annual contributions."""
        growth = st.number_input(
            "Annual Growth Rate (%)",
            min_value=0.0,
            max_value=30.0,
            value=d.annual_growth_rate * 100,
            step=0.5,
            key=f"{key_prefix}_growth",
        )
        st.caption("Long-term average annual return (0–30%)")

        # Validation feedback for growth rate
        if growth == 0:
            st.warning("⚠ Zero growth rate — asset value won't increase. Reconsider if realistic.")

        contribution = st.number_input(
            "Annual Contribution (£)",
            min_value=0.0,
            value=float(d.annual_contribution),
            step=100.0,
            key=f"{key_prefix}_contribution",
        )
        st.caption("Amount added to this asset each year")

        # Validation feedback for contribution
        if contribution == 0 and growth == 0:
            st.error("Asset has no growth and no contributions — value is static.")

        return {
            "annual_growth_rate": growth / 100,
            "annual_contribution": contribution,
        }

    def step3_advanced() -> dict:
        """Step 3: Liquidity and tax wrapper."""
        col1, col2 = st.columns(2)

        with col1:
            is_liquid = st.checkbox(
                "Liquid (easy to access within 1–2 weeks)",
                value=d.is_liquid,
                key=f"{key_prefix}_liquid",
            )

        with col2:
            wrapper_idx = [w.value for w in TaxWrapper].index(d.tax_wrapper.value)
            wrapper = st.selectbox(
                "Tax Wrapper",
                [w.value for w in TaxWrapper],
                index=wrapper_idx,
                key=f"{key_prefix}_wrapper",
            )

        st.caption("Liquid assets used for emergency reserve calculations.")

        return {
            "is_liquid": is_liquid,
            "tax_wrapper": wrapper,
        }

    # Combine step 1 and 2 field dicts for Asset creation
    def on_submit(fields: dict) -> dict:
        """Merge all step fields into Asset model."""
        return {
            "name": fields["name"],
            "category": AssetCategory(fields["category"]),
            "current_value": fields["current_value"],
            "annual_growth_rate": fields["annual_growth_rate"],
            "annual_contribution": fields["annual_contribution"],
            "is_liquid": fields["is_liquid"],
            "tax_wrapper": TaxWrapper(fields["tax_wrapper"]),
        }

    form = MultiStepForm(
        form_key=key_prefix,
        title="Add Asset" if not defaults else "Edit Asset",
        steps=[
            FormStep("Basic Info", step1_basic_info, "Give your asset a name and enter its current value."),
            FormStep("Growth & Contribution", step2_growth_contribution, "Set expected annual return and contributions."),
            FormStep("Advanced", step3_advanced, "Mark if liquid and choose tax wrapper."),
        ],
    )

    result = form.render()
    if result is not None:
        asset_data = on_submit(result)
        return Asset(**asset_data)
    return None


def debt_form(key_prefix: str = "new_debt", defaults: Debt | None = None) -> Debt | None:
    """Render a debt input form using multi-step pattern. Returns Debt on submit, None otherwise."""
    d = defaults or Debt(name="", outstanding_balance=0, monthly_payment=0, remaining_term_months=0)

    # Store category in session state to check for student loan in later steps
    category_key = f"{key_prefix}_category_tmp"

    def step1_basic_debt_info() -> dict:
        """Step 1: Debt name, category, balance, interest rate."""
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Debt Name", value=d.name, key=f"{key_prefix}_name")
            st.caption("e.g., Mortgage, Car Loan, Credit Card")

            category_idx = [c.value for c in DebtCategory].index(d.category.value)
            category = st.selectbox(
                "Category",
                [c.value for c in DebtCategory],
                index=category_idx,
                key=f"{key_prefix}_category",
            )
            # Store category for later condition check
            st.session_state[category_key] = category

        with col2:
            balance = st.number_input(
                "Outstanding Balance (£)",
                min_value=0.0,
                value=float(d.outstanding_balance),
                step=1000.0,
                key=f"{key_prefix}_balance",
            )

            rate = st.number_input(
                "Interest Rate (%)",
                min_value=0.0,
                max_value=50.0,
                value=d.interest_rate * 100,
                step=0.1,
                key=f"{key_prefix}_rate",
            )

        return {
            "name": name,
            "category": category,
            "outstanding_balance": balance,
            "interest_rate": rate / 100,
        }

    def step2_repayment_terms() -> dict:
        """Step 2: Monthly payment and term (or student loan repayment fields)."""
        is_student_loan = st.session_state.get(category_key) == DebtCategory.STUDENT_LOAN.value

        if not is_student_loan:
            col1, col2 = st.columns(2)
            with col1:
                payment = st.number_input(
                    "Monthly Payment (£)",
                    min_value=0.0,
                    value=float(d.monthly_payment),
                    step=50.0,
                    key=f"{key_prefix}_payment",
                )

            with col2:
                term = st.number_input(
                    "Remaining Term (months)",
                    min_value=0,
                    value=d.remaining_term_months,
                    step=12,
                    key=f"{key_prefix}_term",
                )

            # Validation feedback
            if payment > 0 and term == 0:
                st.error("❌ Monthly payment set but term is 0 months. Debt would never be paid off.")
            elif payment == 0 and term > 0:
                st.warning("⚠ No monthly payment but term is set. Debt won't decrease.")
            elif payment > 0 and d.outstanding_balance > 0:
                months_to_payoff = d.outstanding_balance / payment if payment > 0 else float("inf")
                if months_to_payoff > term:
                    st.warning(
                        f"⚠ Payment £{payment}/month would take {months_to_payoff:.0f} months "
                        f"to clear debt, longer than term of {term} months."
                    )

            return {
                "monthly_payment": payment,
                "remaining_term_months": term,
                "student_loan_plan": None,
                "student_loan_repayment_threshold": None,
                "student_loan_repayment_rate": None,
                "student_loan_write_off_years": None,
                "student_loan_start_year": None,
            }

        else:
            # Student Loan conditional fields
            st.info("Plan 2 repayments are calculated as a percentage of projected salary above the threshold.")

            s_col1, s_col2 = st.columns(2)
            with s_col1:
                student_plan = StudentLoanPlan(
                    st.selectbox(
                        "Student Loan Plan",
                        options=[StudentLoanPlan.PLAN_2.value],
                        index=0,
                        key=f"{key_prefix}_sl_plan",
                    )
                )
                student_threshold = st.number_input(
                    "Repayment Threshold (£ / year)",
                    min_value=0.0,
                    value=float(d.student_loan_repayment_threshold or 27_295.0),
                    step=100.0,
                    key=f"{key_prefix}_sl_threshold",
                )

            with s_col2:
                student_rate = st.number_input(
                    "Repayment Rate (% of income above threshold)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float((d.student_loan_repayment_rate or 0.09) * 100),
                    step=0.5,
                    key=f"{key_prefix}_sl_rate",
                )
                student_write_off_years = st.number_input(
                    "Write-off Horizon (years)",
                    min_value=1,
                    max_value=60,
                    value=int(d.student_loan_write_off_years or 30),
                    step=1,
                    key=f"{key_prefix}_sl_writeoff",
                )

            student_start_year = st.number_input(
                "Repayment Start Year",
                min_value=1900,
                max_value=2200,
                value=int(d.student_loan_start_year or date.today().year),
                step=1,
                key=f"{key_prefix}_sl_start",
            )

            # Validation feedback for student loan
            if student_write_off_years < 20:
                st.warning("⚠ Write-off period less than 20 years is unusual for Plan 2 loans.")

            return {
                "monthly_payment": 0.0,
                "remaining_term_months": 0,
                "student_loan_plan": student_plan,
                "student_loan_repayment_threshold": student_threshold,
                "student_loan_repayment_rate": student_rate / 100,
                "student_loan_write_off_years": student_write_off_years,
                "student_loan_start_year": student_start_year,
            }

    def on_submit(fields: dict) -> dict:
        """Finalize debt fields."""
        return {
            "name": fields["name"],
            "category": DebtCategory(fields["category"]),
            "outstanding_balance": fields["outstanding_balance"],
            "interest_rate": fields["interest_rate"],
            "monthly_payment": fields["monthly_payment"],
            "remaining_term_months": fields["remaining_term_months"],
            "student_loan_plan": fields["student_loan_plan"],
            "student_loan_repayment_threshold": fields["student_loan_repayment_threshold"],
            "student_loan_repayment_rate": fields["student_loan_repayment_rate"],
            "student_loan_write_off_years": fields["student_loan_write_off_years"],
            "student_loan_start_year": fields["student_loan_start_year"],
        }

    form = MultiStepForm(
        form_key=key_prefix,
        title="Add Debt" if not defaults else "Edit Debt",
        steps=[
            FormStep("Basic Info", step1_basic_debt_info, "Enter debt name, category, balance, and interest rate."),
            FormStep("Repayment Terms", step2_repayment_terms, "Set repayment schedule or student loan details."),
        ],
    )

    result = form.render()
    if result is not None:
        debt_data = on_submit(result)
        return Debt(**debt_data)
    return None


def goal_form(key_prefix: str = "new_goal", defaults: LifeGoal | None = None) -> LifeGoal | None:
    """Render a life goal input form using multi-step pattern. Returns LifeGoal on submit, None otherwise."""
    d = defaults or LifeGoal(name="", target_cost=0, target_year=2030)

    # Store funding source in session state for later condition checks
    funding_key = f"{key_prefix}_funding_tmp"

    def step1_goal_details() -> dict:
        """Step 1: Goal name, cost, target year."""
        name = st.text_input("Goal Name", value=d.name, key=f"{key_prefix}_name")
        st.caption("e.g., House Purchase, Wedding, Car, Holiday")

        cost = st.number_input(
            "Target Cost (£)",
            min_value=0.0,
            value=float(d.target_cost),
            step=5000.0,
            key=f"{key_prefix}_cost",
        )

        year = st.number_input(
            "Target Year",
            min_value=2024,
            max_value=2080,
            value=d.target_year,
            key=f"{key_prefix}_year",
        )

        return {
            "name": name,
            "target_cost": cost,
            "target_year": int(year),
        }

    def step2_funding_priority() -> dict:
        """Step 2: Funding source and priority."""
        col1, col2 = st.columns(2)

        with col1:
            funding_idx = [f.value for f in GoalFunding].index(d.funding_source.value)
            funding = st.selectbox(
                "Funding Source",
                [f.value for f in GoalFunding],
                index=funding_idx,
                key=f"{key_prefix}_funding",
            )
            # Store for step 3 conditionals
            st.session_state[funding_key] = funding

        with col2:
            priority = st.slider(
                "Priority (1=highest, 5=lowest)",
                1,
                5,
                d.priority,
                key=f"{key_prefix}_priority",
            )

        st.caption("Priority affects which goals are funded first in projections.")

        notes = st.text_area(
            "Notes (optional)",
            value=d.notes,
            height=100,
            key=f"{key_prefix}_notes",
        )

        return {
            "funding_source": funding,
            "priority": priority,
            "notes": notes,
        }

    def step3_additional_details() -> dict:
        """Step 3: Recurring costs and conditional funding details."""
        results = {}

        # Recurring cost section
        st.markdown("#### Ongoing Costs (Optional)")
        col1, col2 = st.columns(2)
        with col1:
            ongoing = st.number_input(
                "Annual Ongoing Cost (£)",
                min_value=0.0,
                value=float(d.annual_ongoing_cost),
                step=1000.0,
                key=f"{key_prefix}_ongoing",
            )
        with col2:
            ongoing_years = st.number_input(
                "Ongoing Duration (years)",
                min_value=0,
                value=d.ongoing_years,
                step=1,
                key=f"{key_prefix}_ongoing_years",
            )
        st.caption("For recurring expenses like education or annual subscriptions. Leave at 0 if one-time cost.")

        results["annual_ongoing_cost"] = ongoing
        results["ongoing_years"] = int(ongoing_years)

        # Conditional funding details
        funding = st.session_state.get(funding_key, d.funding_source.value)

        if funding in ("Mortgage", "Mixed"):
            st.divider()
            st.markdown("#### Mortgage Details")
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                deposit_pct = st.number_input(
                    "Deposit (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=d.deposit_percentage * 100,
                    step=5.0,
                    key=f"{key_prefix}_deposit",
                )
            with m_col2:
                mortgage_rate = st.number_input(
                    "Mortgage Rate (%)",
                    min_value=0.0,
                    max_value=15.0,
                    value=d.mortgage_rate * 100,
                    step=0.25,
                    key=f"{key_prefix}_mort_rate",
                )
            with m_col3:
                mortgage_term = st.number_input(
                    "Mortgage Term (years)",
                    min_value=1,
                    max_value=40,
                    value=d.mortgage_term_years,
                    step=5,
                    key=f"{key_prefix}_mort_term",
                )
            results["deposit_percentage"] = deposit_pct / 100
            results["mortgage_rate"] = mortgage_rate / 100
            results["mortgage_term_years"] = int(mortgage_term)
        else:
            results["deposit_percentage"] = d.deposit_percentage
            results["mortgage_rate"] = d.mortgage_rate
            results["mortgage_term_years"] = d.mortgage_term_years

        if funding == "Loan":
            st.divider()
            st.markdown("#### Loan Details")
            l_col1, l_col2, l_col3 = st.columns(3)
            with l_col1:
                deposit_pct = st.number_input(
                    "Upfront Payment (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=d.deposit_percentage * 100,
                    step=5.0,
                    key=f"{key_prefix}_loan_deposit",
                )
            with l_col2:
                loan_rate = st.number_input(
                    "Loan Rate (%)",
                    min_value=0.0,
                    max_value=15.0,
                    value=d.loan_interest_rate * 100,
                    step=0.25,
                    key=f"{key_prefix}_loan_rate",
                )
            with l_col3:
                loan_term = st.number_input(
                    "Loan Term (years)",
                    min_value=1,
                    max_value=20,
                    value=d.loan_term_years,
                    step=1,
                    key=f"{key_prefix}_loan_term",
                )
            results["deposit_percentage"] = deposit_pct / 100
            results["loan_interest_rate"] = loan_rate / 100
            results["loan_term_years"] = int(loan_term)
        else:
            results["loan_interest_rate"] = d.loan_interest_rate
            results["loan_term_years"] = d.loan_term_years

        return results

    def on_submit(fields: dict) -> dict:
        """Finalize goal fields."""
        return {
            "name": fields["name"],
            "target_cost": fields["target_cost"],
            "target_year": fields["target_year"],
            "funding_source": GoalFunding(fields["funding_source"]),
            "priority": fields["priority"],
            "notes": fields["notes"],
            "annual_ongoing_cost": fields["annual_ongoing_cost"],
            "ongoing_years": fields["ongoing_years"],
            "deposit_percentage": fields["deposit_percentage"],
            "mortgage_rate": fields["mortgage_rate"],
            "mortgage_term_years": fields["mortgage_term_years"],
            "loan_interest_rate": fields["loan_interest_rate"],
            "loan_term_years": fields["loan_term_years"],
        }

    form = MultiStepForm(
        form_key=key_prefix,
        title="Add Goal" if not defaults else "Edit Goal",
        steps=[
            FormStep("Goal Details", step1_goal_details, "Enter goal name, target cost, and target year."),
            FormStep("Funding & Priority", step2_funding_priority, "Choose funding source and priority level."),
            FormStep("Additional Details", step3_additional_details, "Enter ongoing costs and financing details."),
        ],
    )

    result = form.render()
    if result is not None:
        goal_data = on_submit(result)
        return LifeGoal(**goal_data)
    return None
