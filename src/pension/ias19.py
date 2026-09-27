"""M5 IAS 19 valuation (SPEC §9 M5): curve, DBO by status, SEDR, duration and PV01, service cost,
2026 P&L forecast, sensitivities and disclosure tables 1, 5, 6, 7.

Reads only assumptions_ias19.yaml, scheme rules, market data and the State Pension (never the Section 34 basis).
"""
from datetime import date

import numpy as np
from scipy.optimize import brentq

from pension import benefits, cashflows
from pension.curves import Curve, FlatRate
from pension.io import cpi_annual_average, load_config, read_market, statutory_revaluation
from pension.mortality import Mortality

PV01_SHIFT = -0.0001
SENSITIVITY_SHIFT = 0.005


def config():
    return load_config("assumptions_ias19")


def market_inflation(valuation_date):
    """Fisher on the OAT 2032 pair at the valuation date: (1 + nominal) / (1 + real) - 1."""
    t = read_market("mva_section34").set_index("date")
    row = t.loc[valuation_date.isoformat()]
    return (1 + row.oat_nominal_pct / 100) / (1 + row.oat_real_pct / 100) - 1


def curve(valuation_date, spread=None):
    cfg = config()["discount"]
    curve_date = cfg["curve_dates"][valuation_date]
    s = cfg["aa_spread"] if spread is None else spread
    return Curve.ecb(curve_date.isoformat() if hasattr(curve_date, "isoformat") else curve_date, spread=s)


def spc_for_year(year):
    from pension.data_gen import spc_annual
    return spc_annual(load_config("statutory_ie"), date(year, 1, 1))


def known_increase(valuation_date, rules):
    """The 1 January increase after the valuation date is already fixed by that year's CPI (floor 0, cap 3%)."""
    cpi = cpi_annual_average()[valuation_date.year] / 100
    inc = rules["pension_increases"]
    return {valuation_date.year + 1: min(max(cpi, inc["floor"]), inc["cap"])}


def basis(valuation_date, inflation=None, salary_margin=None, mortality=None, **changes):
    """IAS 19 basis at a valuation date (2024-12-31 or 2025-12-31)."""
    cfg, rules = config(), load_config("scheme_rules")
    pi = market_inflation(valuation_date) if inflation is None else inflation
    margin = cfg["salary_growth"]["margin_over_inflation"] if salary_margin is None else salary_margin
    mort = Mortality.from_config(cfg["mortality"]) if mortality is None else mortality
    revaluation, increase = benefits.scheme_rates(pi, rules)
    b = cashflows.Basis(
        name=f"IAS 19 {valuation_date}", valuation_date=valuation_date, rules=rules, inflation=pi,
        salary_growth=pi + margin, revaluation=revaluation, pension_increase=increase,
        mortality_pre=mort, mortality_post=mort, spc_next_year=spc_for_year(valuation_date.year + 1),
        withdrawal=cashflows.ias19_withdrawal(cfg["withdrawal"]),
        known_increases=known_increase(valuation_date, rules), revaluation_history=statutory_revaluation())
    return b.with_(**changes)


# --- measures -------------------------------------------------------------------------------

def dbo_by_member(members, b, discount):
    return cashflows.pv(cashflows.project_cashflows(members, b), discount)


def sedr(cf_total, discount_curve):
    """Single equivalent discount rate: the flat rate giving the same PV as the curve."""
    target = cashflows.pv(cf_total[None, :], discount_curve)[0]
    return brentq(lambda r: cashflows.pv(cf_total[None, :], FlatRate(r))[0] - target, -0.02, 0.2, xtol=1e-12)


def pv01(cf, discount_curve):
    """Increase in PV for a 1 bp fall in the whole curve."""
    return cashflows.pv(cf, discount_curve.shifted(PV01_SHIFT)).sum() - cashflows.pv(cf, discount_curve).sum()


def pensionable_payroll(members, b, year_index=1):
    a = members[members.status == "A"]
    salary = a.salary * (1 + b.salary_growth) ** year_index
    spc = b.spc_next_year * (1 + b.inflation) ** (year_index - 1)
    return np.maximum(salary - b.rules["spc_offset_multiple"] * spc, 0).sum(), salary.sum()


def valuation(members, valuation_date, b=None, discount=None):
    """Core IAS 19 results at a date."""
    b = basis(valuation_date) if b is None else b
    discount = curve(valuation_date) if discount is None else discount
    cf = cashflows.project_cashflows(members, b)
    by_member = cashflows.pv(cf, discount)
    dbo = by_member.sum()
    p01 = pv01(cf, discount)
    total_cf = cf.sum(axis=0)
    rate = sedr(total_cf, discount)
    status = members.status.to_numpy()
    return {
        "basis": b, "curve": discount, "cf": cf, "by_member": by_member,
        "dbo": dbo, "dbo_by_status": {s: by_member[status == s].sum() for s in "ADP"},
        "sedr": rate, "pv01": p01, "duration": p01 / (dbo * 1e-4),
        "cf_total": total_cf,
    }


def service_cost(members, valuation_date, b=None, discount=None):
    """Next year's current service cost = DBO with one more year of service - DBO (actives), gross and net
    of member contributions (5% of the year's pensionable salary)."""
    b = basis(valuation_date) if b is None else b
    discount = curve(valuation_date) if discount is None else discount
    actives = members[members.status == "A"]
    base = cashflows.pv(cashflows.project_cashflows(actives, b), discount).sum()
    plus = cashflows.pv(cashflows.project_cashflows(actives, b.with_(service_increment=1.0)), discount).sum()
    gross = plus - base
    payroll, salaries = pensionable_payroll(members, b)
    member_contributions = load_config("scheme_rules")["member_contribution_rate"] * payroll
    return {"gross": gross, "member_contributions": member_contributions, "employer": gross - member_contributions,
            "pensionable_payroll": payroll, "salary_roll": salaries}


def sensitivities(members, valuation_date, base_result):
    """DBO under one-at-a-time changes (SPEC §9 M5)."""
    b0, c0 = base_result["basis"], base_result["curve"]
    pi0 = b0.inflation
    mort = b0.mortality_post
    k = mort.longevity_k(sex="M", year=valuation_date.year + 1, extra_years=1.0)

    def dbo(b=b0, c=c0):
        return cashflows.pv(cashflows.project_cashflows(members, b), c).sum()

    def with_inflation(pi):
        return basis(valuation_date, inflation=pi, mortality=mort)

    out = {
        "discount_minus_0.5": dbo(c=c0.shifted(-SENSITIVITY_SHIFT)),
        "discount_plus_0.5": dbo(c=c0.shifted(SENSITIVITY_SHIFT)),
        "inflation_plus_0.5": dbo(b=with_inflation(pi0 + SENSITIVITY_SHIFT)),
        "inflation_minus_0.5": dbo(b=with_inflation(pi0 - SENSITIVITY_SHIFT)),
        "salary_plus_0.5": dbo(b=b0.with_(salary_growth=b0.salary_growth + SENSITIVITY_SHIFT)),
        "salary_minus_0.5": dbo(b=b0.with_(salary_growth=b0.salary_growth - SENSITIVITY_SHIFT)),
        "life_expectancy_plus_1": dbo(b=b0.with_(mortality_pre=mort.with_k(k), mortality_post=mort.with_k(k))),
    }
    return {"k": k, "dbo": out}
