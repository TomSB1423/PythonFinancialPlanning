# 💰 Financial Planning Playground

A personal net worth tracker and retirement planner built with Streamlit. Focused on big-picture financial planning — not day-to-day budgeting.

## Features

- **Net Worth Dashboard** — KPIs, asset allocation, liquidity analysis
- **Assets & Debts** — Track cash, pensions, ISAs, property, mortgages, loans
- **Life Goals** — Plan major milestones (house, cabin, children, sailing boat)
- **Retirement Planner** — Income gap analysis, drawdown simulation, tax modelling
- **Projections** — Year-by-year simulations with optimistic/base/pessimistic scenarios

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Data

All data lives in your browser session. Use the sidebar to **export/import JSON** files to save your plan. A sample profile is included for demo purposes.

## UK-Focused

Tax calculations use 2025/26 UK rates (income tax, CGT, pension relief). Currency is GBP (£).
