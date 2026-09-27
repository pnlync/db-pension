"""M8 assets and 2025 analysis of change (SPEC §9 M8).

Liabilities: a chain of full IAS 19 revaluations from the 2024-12-31 DBO to the 2025-12-31 DBO.
Assets: 2025 roll-forward (equities: MSCI World net EUR; bonds: revalued on the same curves plus coupons;
cash: €STR), with the opening asset value solved so that closing assets meet the design target.
"""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from pension import assets, cashflows, funding_standard as fs, ias19
from pension.io import load_config, read_market, statutory_revaluation

V0, V1 = date(2024, 12, 31), date(2025, 12, 31)
CURVE_DATES = {V0: "2024-12-30", V1: "2025-12-31"}


def market_returns_2025():
    """Equity and cash returns for 2025, from config/assets.yaml (sources in the register)."""
    return load_config("assets")["returns_2025"]


# --- actual 2025 flows (synthetic experience) -------------------------------------------------------

def year_fraction(start, end):
    return max((end - start).days, 0) / 365


def actual_flows_2025(opening, movements, rules, spc_2025):
    """Benefits paid, contributions and expenses in 2025, all treated as paid mid-year."""
    mv = movements.copy()
    mv["event_date"] = pd.to_datetime(mv.event_date).dt.date
    died = set(mv.member_id[mv.event == "death"])
    exit_dates = {r.member_id: r.event_date for r in mv[mv.event.isin(["withdrawal", "retirement", "death"])].itertuples()}

    benefits = 0.0
    for r in mv[mv.event == "pension_increase"].itertuples():          # opening pensioners, 2025 amount
        benefits += float(r.new_value) * (0.5 if r.member_id in died else 1.0)
    for r in mv[mv.event == "retirement"].itertuples():                 # new pensioners from their birthday
        benefits += float(r.new_value) * year_fraction(r.event_date, V1)

    salaries = mv[mv.event == "salary_increase"].set_index("member_id").new_value.astype(float)
    ps_years = 0.0
    for mid, salary in salaries.items():
        fraction = year_fraction(date(2025, 1, 1), exit_dates[mid]) if mid in exit_dates else 1.0
        ps_years += max(salary - rules["spc_offset_multiple"] * spc_2025, 0.0) * fraction
    cfg = load_config("assets")["contributions"]
    member = rules["member_contribution_rate"] * ps_years
    employer = cfg["employer_normal_rate"] * ps_years + cfg["employer_deficit_eur"]
    expenses = ias19.config()["admin_expenses"]["per_member_eur"] * len(opening)
    return {"benefits": benefits, "employer_contributions": employer, "member_contributions": member,
            "expenses": expenses, "pensionable_salary_years": ps_years}


# --- assets ---------------------------------------------------------------------------------------------

def cash_return_2025(estr):
    """€STR compounded daily (ACT/360) over 2025; estr: DataFrame with TIME_PERIOD, OBS_VALUE (%)."""
    days = pd.to_datetime(estr.TIME_PERIOD)
    next_day = list(days[1:]) + [pd.Timestamp("2026-01-01")]
    accrual = [(n - d).days for d, n in zip(days, next_day)]
    return float(np.prod(1 + estr.OBS_VALUE.to_numpy() / 100 * np.array(accrual) / 360) - 1)


@dataclass
class AssetRoll:
    opening: float
    opening_by_class: dict
    closing_by_class: dict
    returns: dict
    net_flow: float
    closing: float


def roll_assets(opening_total, flows, cash_return, equity_return):
    """Opening portfolio at the strategic allocation, revalued to 2025-12-31; net cash flow mid-year in cash."""
    mk0, mk1 = assets.Market.at(V0, CURVE_DATES[V0]), assets.Market.at(V1, CURVE_DATES[V1])
    pf = assets.closing_portfolio(opening_total, mk0)
    opening = pf.values(mk0)
    closing, returns = {}, {}
    for c in assets.BOND_CLASSES:
        bond = pf.bonds[c]
        aged = assets.Bond(bond.coupon, bond.maturity - 1)
        closing[c] = pf.units[c] * (aged.price(mk1, c) + bond.coupon)      # coupon received at the year end
        returns[c] = (aged.price(mk1, c) + bond.coupon) / bond.price(mk0, c) - 1   # per unit (defined if not held)
    closing["equities"] = opening["equities"] * (1 + equity_return)
    returns["equities"] = equity_return
    net_flow = flows["employer_contributions"] + flows["member_contributions"] - flows["benefits"] - flows["expenses"]
    closing["cash"] = opening["cash"] * (1 + cash_return) + net_flow * (1 + cash_return) ** 0.5
    returns["cash"] = cash_return
    return AssetRoll(opening_total, opening, closing, returns, net_flow, sum(closing.values()))


def solve_opening_assets(target_closing, flows, cash_return, equity_return):
    """Closing assets are linear in opening assets: solve exactly."""
    a = roll_assets(1.0, flows, cash_return, equity_return).closing
    b = roll_assets(2.0, flows, cash_return, equity_return).closing
    slope = b - a
    return 1.0 + (target_closing - a) / slope


# --- liabilities: IAS 19 analysis of change ---------------------------------------------------------------

def expected_basis_at_v1(b0):
    """IAS 19 basis at 2025-12-31 with opening assumptions and the 2025 inflation-linked items as expected."""
    b = ias19.basis(V1, inflation=b0.inflation)
    history = statutory_revaluation().copy()
    history[2025] = b0.revaluation * 100
    return b.with_(known_increases={2026: b0.pension_increase}, revaluation_history=history,
                   spc_next_year=b0.spc_next_year * (1 + b0.inflation))


def with_expected_salaries(m1, m0, g0):
    m = m1.copy()
    s0 = m0.set_index("member_id").salary
    actives = m.status == "A"
    m.loc[actives, "salary"] = (s0[m.member_id[actives]].to_numpy() * (1 + g0)).round()
    return m


def liability_aoc(m0, m1, flows):
    b0, c0 = ias19.basis(V0), ias19.curve(V0)
    b1, c1 = ias19.basis(V1), ias19.curve(V1)
    r0 = ias19.valuation(m0, V0, b0, c0)
    rate = r0["sedr"]
    half = (1 + rate) ** 0.5 - 1
    sc = ias19.service_cost(m0, V0, b0, c0)["gross"]
    benefits = flows["benefits"]

    def pv(m, b, c):
        return cashflows.pv(cashflows.project_cashflows(m, b), c).sum()

    # expected position a year on: the opening projection with one more year of service, remaining years
    cf_plus = cashflows.project_cashflows(m0, b0.with_(service_increment=1.0))
    expected_benefits = cf_plus[:, 0].sum()
    times = cashflows.payment_times(cf_plus.shape[1] - 1)
    e2 = (cf_plus[:, 1:].sum(axis=0) * c0.discount(times)).sum()

    L = {}
    L["opening"] = r0["dbo"]
    L["service_cost"] = sc
    L["interest_cost"] = rate * r0["dbo"] - half * benefits
    L["benefits_paid"] = -benefits
    expected_close = L["opening"] + sc + L["interest_cost"] - benefits
    L["roll_down"] = e2 - (r0["dbo"] + sc + rate * r0["dbo"] - (1 + half) * expected_benefits)
    level = expected_close + L["roll_down"]

    b_exp = expected_basis_at_v1(b0)
    b_act_open = ias19.basis(V1, inflation=b0.inflation)
    levels = {
        "membership": pv(with_expected_salaries(m1, m0, b0.salary_growth), b_exp, c0),
        "salaries": pv(m1, b_exp, c0),
        "inflation_linked": pv(m1, b_act_open, c0),
    }
    levels["demographic"] = levels["inflation_linked"]            # mortality basis unchanged in 2025
    levels["curve"] = pv(m1, b_act_open, c1)
    levels["inflation_assumption"] = pv(m1, b1, c1)
    for key, value in levels.items():
        L[key] = value - level
        level = value
    closing_independent = ias19.valuation(m1, V1, b1, c1)["dbo"]
    L["other"] = closing_independent - level
    return {"steps": L, "expected_closing": expected_close, "closing": closing_independent, "sedr_opening": rate,
            "expected_benefits": expected_benefits, "opening_result": r0}


# --- IAS 19 P&L, OCI and reconciliations ---------------------------------------------------------------------

def ias19_accounts(liab, roll, flows):
    L = liab["steps"]
    rate = liab["sedr_opening"]
    half = (1 + rate) ** 0.5 - 1
    interest_income = rate * roll.opening + half * roll.net_flow
    return_above = roll.closing - roll.opening - roll.net_flow - interest_income
    remeasurement = sum(L[k] for k in ("roll_down", "membership", "salaries", "inflation_linked", "demographic",
                                       "curve", "inflation_assumption", "other"))
    service_net = L["service_cost"] - flows["member_contributions"]
    net_interest = L["interest_cost"] - interest_income
    pl = {"service_cost_net": service_net, "net_interest": net_interest, "admin_expenses": flows["expenses"]}
    pl["total"] = sum(pl.values())
    oci = {"experience": L["membership"] + L["salaries"] + L["inflation_linked"],
           "demographic": L["demographic"],
           "financial": L["roll_down"] + L["curve"] + L["inflation_assumption"] + L["other"],
           "return_on_assets_above_interest": -return_above}
    oci["total"] = sum(oci.values())
    opening_nl = liab["steps"]["opening"] - roll.opening
    closing_nl = liab["closing"] - roll.closing
    waterfall = {
        "opening_deficit": opening_nl,
        "service_cost_less_contributions": L["service_cost"] - flows["member_contributions"]
                                          - flows["employer_contributions"],
        "admin_expenses": flows["expenses"],
        "net_interest": net_interest,
        "asset_performance": -return_above,
        "experience": oci["experience"],
        "assumption_changes": oci["demographic"] + oci["financial"],
    }
    waterfall["closing_deficit"] = closing_nl
    return {"interest_income": interest_income, "return_above_interest": return_above, "remeasurement": remeasurement,
            "pl": pl, "oci": oci, "opening_net_liability": opening_nl, "closing_net_liability": closing_nl,
            "waterfall": waterfall}


# --- Funding Standard: simplified change --------------------------------------------------------------------------

def fs_liabilities_with(members, valuation_date, mva_npa, annuity_increase, annuity_curve):
    pens = (members.status == "P").to_numpy()
    tv, _ = fs.transfer_values(members[~pens], fs.s34_basis(valuation_date), mva_npa)
    ann_b = fs.annuity_basis(valuation_date).with_(pension_increase=annuity_increase)
    ann, _ = fs.annuity_costs(members[pens], ann_b, annuity_curve)
    base = tv.sum() + ann.sum()
    return base + fs.wind_up_expenses(base)


def fs_change(m0, m1, roll, flows):
    fs0 = fs.liabilities(m0, V0)["total"]
    fs1 = fs.liabilities(m1, V1)["total"]
    open_increase = fs.annuity_basis(V0).pension_increase
    close_increase = fs.annuity_basis(V1).pension_increase
    la = fs_liabilities_with(m1, V1, fs.mva_npa_at(V0), open_increase, fs.annuity_curve(V0))
    lb = fs_liabilities_with(m1, V1, fs.mva_npa_at(V1), open_increase, fs.annuity_curve(V0))
    lc = fs_liabilities_with(m1, V1, fs.mva_npa_at(V1), close_increase, fs.annuity_curve(V1))
    liab = {"roll_forward_accrual_and_experience": la - fs0, "mva_change": lb - la,
            "annuity_cost_change": lc - lb, "other": fs1 - lc}
    asset_items = {"contributions": flows["employer_contributions"] + flows["member_contributions"],
                   "benefits_and_expenses": -(flows["benefits"] + flows["expenses"]),
                   "asset_return": roll.closing - roll.opening - roll.net_flow}
    surplus0, surplus1 = roll.opening - fs0, roll.closing - fs1
    return {"fs_opening": fs0, "fs_closing": fs1, "liabilities": liab, "assets": asset_items,
            "surplus_opening": surplus0, "surplus_closing": surplus1,
            "fs_level_opening": roll.opening / fs0, "fs_level_closing": roll.closing / fs1}


# --- driver ---------------------------------------------------------------------------------------------------------

def run(m0, m1, opening_df, movements, estr=None):
    rules = load_config("scheme_rules")
    flows = actual_flows_2025(opening_df, movements, rules, ias19.spc_for_year(2025))
    liab = liability_aoc(m0, m1, flows)
    ret = market_returns_2025()
    cash = cash_return_2025(read_market("estr_2025") if estr is None else estr)
    target = load_config("assets")["target_closing_ias19_funding_level"] * liab["closing"]
    a0 = solve_opening_assets(target, flows, cash, ret["equities"])
    roll = roll_assets(a0, flows, cash, ret["equities"])
    accounts = ias19_accounts(liab, roll, flows)
    fsc = fs_change(m0, m1, roll, flows)
    return {"flows": flows, "liabilities": liab, "assets": roll, "accounts": accounts, "fs": fsc}
