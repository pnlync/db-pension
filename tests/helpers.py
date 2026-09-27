"""Shared test fixtures: a basis on the closing (2025-12-31) IAS 19 starting assumptions."""
from datetime import date

import pandas as pd

from pension import benefits, cashflows
from pension.io import MEMBERS, load_config, statutory_revaluation
from pension.mortality import Mortality

VALUATION = date(2025, 12, 31)


def make_basis(inflation=0.0187, **changes):
    rules = load_config("scheme_rules")
    ias19 = load_config("assumptions_ias19")
    mort = Mortality.from_config(ias19["mortality"])
    revaluation, increase = benefits.scheme_rates(inflation, rules)
    basis = cashflows.Basis(
        name="test", valuation_date=VALUATION, rules=rules, inflation=inflation,
        salary_growth=inflation + ias19["salary_growth"]["margin_over_inflation"],
        revaluation=revaluation, pension_increase=increase, mortality_pre=mort, mortality_post=mort,
        spc_next_year=299.30 * 52, withdrawal=cashflows.ias19_withdrawal(ias19["withdrawal"]),
        known_increases={2026: 0.022}, revaluation_history=statutory_revaluation())
    return basis.with_(**changes)


def clean_members():
    df = pd.read_csv(MEMBERS / "members_2025_clean.csv", dtype=str)
    return cashflows.prepare_members(df, VALUATION)
