---
description: "Use when writing or modifying Python code, Streamlit pages, UI components, calculations, Pydantic models, or charts in this financial planning app. Covers coding style, icon conventions, and project structure."
applyTo: "**/*.py"
---

# Coding Standards

## No Emojis -- Use Unicode Symbols Instead

Replace emojis with minimal Unicode symbols throughout the codebase.

| Context            | Avoid                               | Prefer                                                        |
| ------------------ | ----------------------------------- | ------------------------------------------------------------- |
| Page titles        | `st.title("📊 Dashboard")`          | `st.title("Dashboard")`                                       |
| Buttons            | `st.button("🗑️ Delete")`            | `st.button("✕ Delete")`                                       |
| Success messages   | `st.success("✅ Pension lasts...")` | `st.success("Pension lasts...")`                              |
| Warnings           | `st.warning("⚠️ Depleted...")`      | `st.warning("Depleted...")` — Streamlit already shows an icon |
| Info boxes         | `st.info("💰 Salary...")`           | `st.info("Salary...")`                                        |
| Sidebar headers    | `"💾 Save / Load"`                  | `"Save / Load"`                                               |
| Download/upload    | `"📥 Export"` / `"📤 Import"`       | `"Export" / "Import"` or `"↓ Export" / "↑ Import"`            |
| Section separators | Emoji-laden headers                 | `# ── Section Name ──` (box-drawing chars)                    |

Allowed Unicode symbols: `→`, `←`, `↑`, `↓`, `✓`, `✕`, `·`, `—`, `─`, `═`, `▸`, `▾`.

Streamlit's `st.success`, `st.warning`, `st.error`, and `st.info` already render their own icons — do not prepend extra symbols.

When refactoring existing files, remove emojis and apply the same rules.

## Python Style

- Use `from __future__ import annotations` at the top of every module.
- Type-hint all function parameters and return types.
- Use Pydantic `BaseModel` with `Field(description=..., ge=..., le=...)` for data validation.
- Naming: `snake_case` for functions/variables, `PascalCase` for classes, `ALL_CAPS` for constants.
- Enums inherit from `(str, Enum)` for serialization compatibility.
- Keep imports explicit — no wildcard imports (`from x import *`).

## Comments

- One-line module docstring at the top of every file.
- Function docstrings only where logic is non-obvious — skip for trivial getters/helpers.
- Use box-drawing section separators to group related code:
  ```python
  # ── Section Name ──────────────────────────────────────────────────────
  ```
- Inline comments only for genuinely surprising logic. Prefer clarity through types and names.

## Streamlit Page Structure

Follow this order in every page file:

1. `st.set_page_config(...)` — no emoji in `page_icon`, use a simple string or omit.
2. Session state initialisation guard.
3. Page title (plain text or with a Unicode symbol).
4. KPI metrics row with `st.columns()`.
5. `st.divider()` between major sections.
6. Charts and detail sections.

## Charts and Formatting

- Use the Material Design colour palette defined in `components/charts.py`.
- Format currency with `format_gbp()` — values in GBP with `k`/`M` suffixes.
- Render with `st.plotly_chart(fig, use_container_width=True)`.

## Project Structure

- `calculations/` — Pure functions; no Streamlit imports.
- `components/` — Reusable UI builders (forms, charts).
- `models/` — Pydantic data models and assumptions constants.
- `pages/` — Streamlit pages; keep business logic in `calculations/`.
- `data/` — JSON defaults and sample profiles.

Do not mix UI logic into calculation modules or vice versa.
