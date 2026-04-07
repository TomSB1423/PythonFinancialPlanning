"""Multi-step form builder for progressive form disclosure and improved UX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import streamlit as st


@dataclass
class FormStep:
    """Represents one step in a multi-step form."""

    title: str
    """Step title (e.g., 'Basic Info', 'Growth Settings')."""

    render_fn: Callable[[], dict[str, Any]]
    """Function to render form fields. Returns dict of field values."""

    help_text: str | None = None
    """Optional step description/help text."""

    condition_fn: Callable[[], bool] | None = None
    """Optional function to determine if step is shown. If returns False, step is skipped."""


class MultiStepForm:
    """
    Reusable multi-step form builder with progress tracking and step navigation.

    Example:
        def step1_render() -> dict:
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Asset Name")
            with col2:
                value = st.number_input("Value (£)", min_value=0.0)
            return {"name": name, "value": value}

        def step2_condition() -> bool:
            # Optionally skip a step based on prior inputs
            return st.session_state.skip_advanced is False

        form = MultiStepForm(
            form_key="asset_form",
            title="Add New Asset",
            steps=[
                FormStep("Basic Info", step1_render, "Enter asset name and current value"),
                FormStep("Growth Settings", step2_render, condition_fn=step2_condition),
            ]
        )
        all_fields = form.render()
        if all_fields is not None:  # Form submitted
            asset = Asset(**all_fields)
    """

    def __init__(
        self,
        form_key: str,
        title: str,
        steps: list[FormStep],
    ) -> None:
        """
        Initialize multi-step form.

        Args:
            form_key: Unique key for form state tracking in session_state
            title: Form title
            steps: List of FormStep objects
        """
        self.form_key = form_key
        self.title = title
        self.steps = steps
        self._get_visible_steps()  # Cache visible steps on init

    def _get_visible_steps(self) -> list[FormStep]:
        """Return only steps that pass their condition_fn (or have no condition)."""
        return [s for s in self.steps if s.condition_fn is None or s.condition_fn()]

    def render(self) -> dict[str, Any] | None:
        """
        Render the multi-step form. Returns combined field dict on submit, None otherwise.

        Returns:
            Dict of all fields from all steps if submitted; None if cancelled or in progress.
        """
        # Initialize step tracking in session state
        step_key = f"{self.form_key}_step"
        if step_key not in st.session_state:
            st.session_state[step_key] = 0

        visible_steps = self._get_visible_steps()
        current_step_idx = st.session_state[step_key]

        # Clamp current step to available range
        if current_step_idx >= len(visible_steps):
            current_step_idx = len(visible_steps) - 1
            st.session_state[step_key] = current_step_idx

        current_step = visible_steps[current_step_idx]
        is_final_step = current_step_idx == len(visible_steps) - 1

        # ── Render form title and progress ────
        st.subheader(self.title)
        progress_text = f"Step {current_step_idx + 1} of {len(visible_steps)}"
        st.caption(progress_text)

        # Progress bar
        st.progress(
            (current_step_idx + 1) / len(visible_steps),
            text=progress_text,
        )

        # ── Render current step ────
        if current_step.help_text:
            st.info(current_step.help_text)

        st.markdown(f"### {current_step.title}")

        # Call step's render function to collect fields
        step_fields = current_step.render_fn()

        # ── Render step navigation and form submission ────
        col_back, col_forward, col_cancel = st.columns([1, 1, 1])

        with col_back:
            if current_step_idx > 0:
                if st.button("← Back", key=f"{self.form_key}_back"):
                    st.session_state[step_key] -= 1
                    st.rerun()
            else:
                st.button("← Back", disabled=True, key=f"{self.form_key}_back_disabled")

        with col_cancel:
            if st.button("✕ Cancel", key=f"{self.form_key}_cancel"):
                # Reset step counter and return None
                st.session_state[step_key] = 0
                st.rerun()

        with col_forward:
            if is_final_step:
                if st.button("✓ Submit", type="primary", key=f"{self.form_key}_submit"):
                    # Reconstruct all fields from all steps on final submit
                    all_fields = {}
                    for i, step in enumerate(visible_steps):
                        # Call each step's render function again to get its fields
                        # This is necessary because Streamlit re-runs the entire script
                        fields = step.render_fn()
                        all_fields.update(fields)
                    st.session_state[step_key] = 0
                    return all_fields
            else:
                if st.button("Next →", type="primary", key=f"{self.form_key}_next"):
                    st.session_state[step_key] += 1
                    st.rerun()

        return None
