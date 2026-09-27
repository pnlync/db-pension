"""M6 Funding Standard and Funding Standard Reserve (SPEC §9 M6).

Non-pensioners: Section 34 standard transfer values (actives treated as leaving at the effective date).
Pensioners: annuity purchase cost proxy (insurer basis). Plus wind-up expenses. FSR = 10% x unmatched liabilities
+ net effect of a 0.5% fall in interest rates.

Reads statutory_ie.yaml, assumptions_insurer.yaml, scheme rules and market data; never the IAS 19 assumptions (SPEC §8).
"""
import numpy as np

from pension import benefits, cashflows, mva
from pension.curves import Curve
from pension.io import cpi_annual_average, load_config, read_market, statutory_revaluation
from pension.mortality import Mortality


def statutory():
    return load_config("statutory_ie")


def insurer():
    return load_config("assumptions_insurer")


def market_inflation(valuation_date):
    """OAT 2032 Fisher proxy for PI (ASP PEN-3 asks for the HICP swap curve; SPEC §7.1)."""
    t = read_market("mva_section34").set_index("date")
    row = t.loc[valuation_date.isoformat()]
    return (1 + row.oat_nominal_pct / 100) / (1 + row.oat_real_pct / 100) - 1


def spc_for_year(year):
    from datetime import date

    from pension.data_gen import spc_annual
    return spc_annual(statutory(), date(year, 1, 1))


def known_increase(valuation_date, rules):
    cpi = cpi_annual_average()[valuation_date.year] / 100
    inc = rules["pension_increases"]
    return {valuation_date.year + 1: min(max(cpi, inc["floor"]), inc["cap"])}


# --- Section 34 transfer values (non-pensioners) -----------------------------------------------

def s34_assumed_rate(cap, s34):
    """Table 2: CPI-linked with an annual cap: cap >= 1.5% -> 1.5%, otherwise the cap."""
    rule = s34["capped_increase_rule"]
    return rule["assumed_increase"] if cap >= rule["cap_threshold"] else cap


def s34_basis(valuation_date):
    s34, rules = statutory()["section34"], load_config("scheme_rules")
    loading = dict(s34["annuity_value_loading"])
    return cashflows.Basis(
        name=f"Section 34 {valuation_date}", valuation_date=valuation_date, rules=rules,
        inflation=s34["price_inflation_pre"], salary_growth=0.0,
        revaluation=s34_assumed_rate(rules["revaluation"]["cap"], s34),
        pension_increase=s34_assumed_rate(rules["pension_increases"]["cap"], s34),
        mortality_pre=Mortality(s34["mortality_pre_retirement"], 0.0, loading["base_year"]),
        mortality_post=Mortality(s34["mortality_post_retirement"], 0.0, loading["base_year"]),
        spc_next_year=spc_for_year(valuation_date.year + 1), withdrawal=None,
        known_increases={}, revaluation_history=statutory_revaluation(),
        actives_as_leavers=True, annuity_loading=loading)


def mva_npa_at(valuation_date, real_yield_shift=0.0):
    """Index-linked MVA at NPA (MVA2) from the OAT€i yield at the para 4.1 date; shift for the FSR test."""
    row = mva.row_for_effective_date(valuation_date)
    return mva.mva_npa_index_linked(row.oat_real_pct / 100 + real_yield_shift)


def transfer_values(members, b, mva_npa):
    """TV = PV at 6% to 65 and 4.25% after, x MVA_pre(T) x MVA_post(T) (SPEC §9 M6)."""
    s34 = statutory()["section34"]
    cf = cashflows.project_cashflows(members, b)
    T = members["T"].to_numpy()
    df = cashflows.split_discount_factors(T, s34["discount_pre_retirement"], s34["discount_post_retirement"])
    unadjusted = cashflows.pv(cf, df)
    return unadjusted * mva.mva_pre(T) * mva.mva_post(T, mva_npa), cf


# --- pensioners: annuity purchase cost proxy -------------------------------------------------------

def fixed_increase(pi, cap, table=None):
    """ASP PEN-3 appendix: fixed rate substituted for CPI-linked increases (floor 0%) by linear interpolation."""
    table = statutory()["funding_standard"]["fixed_increase_table"] if table is None else table
    caps = sorted(table["index_linked"])
    by_cap = [np.interp(pi, table["pi"], table["index_linked"][c]) for c in caps]
    return round(float(np.interp(cap, caps, by_cap)), 4)


def annuity_basis(valuation_date):
    ins, rules = insurer(), load_config("scheme_rules")
    decimals = statutory()["funding_standard"]["fixed_increase_table"]["pi_rounding_decimals"]
    pi = round(market_inflation(valuation_date) * 100, decimals) / 100
    increase = fixed_increase(pi, rules["pension_increases"]["cap"])
    mort = Mortality.from_config(ins["mortality"])
    return cashflows.Basis(
        name=f"Annuity cost proxy {valuation_date}", valuation_date=valuation_date, rules=rules,
        inflation=pi, salary_growth=0.0, revaluation=0.0, pension_increase=increase,
        mortality_pre=mort, mortality_post=mort, spc_next_year=spc_for_year(valuation_date.year + 1),
        known_increases=known_increase(valuation_date, rules), revaluation_history=statutory_revaluation())


def annuity_curve(valuation_date):
    ins = insurer()["fs_annuity_proxy"]
    curve_date = ins["curve_dates"][valuation_date]
    return Curve.ecb(curve_date.isoformat() if hasattr(curve_date, "isoformat") else curve_date,
                     spread=ins["insurer_spread"])


def annuity_costs(members, b, curve):
    cf = cashflows.project_cashflows(members, b)
    return cashflows.pv(cf, curve), cf


# --- the Funding Standard and the FSR ----------------------------------------------------------------

def wind_up_expenses(liabilities):
    w = statutory()["funding_standard"]["wind_up_expenses"]
    return max(w["rate"] * liabilities, w["minimum_eur"])


def liabilities_on(members, valuation_date, mva_npa, ann_basis, ann_curve, s34=None):
    """FS liability total with explicit parameters (used by the analysis of change, scenarios and projections)."""
    pens = (members.status == "P").to_numpy()
    tv, _ = transfer_values(members[~pens], s34 or s34_basis(valuation_date), mva_npa)
    ann, _ = annuity_costs(members[pens], ann_basis, ann_curve)
    base = tv.sum() + ann.sum()
    return {"non_pensioners": tv.sum(), "pensioners": ann.sum(), "expenses": wind_up_expenses(base),
            "total": base + wind_up_expenses(base)}


def liabilities(members, valuation_date, rate_shift=0.0):
    """FS liabilities by component; rate_shift < 0 applies the FSR interest-rate test (PEN-3 para 3.2):
    pensioner annuity cost on the lower curve; non-pensioners only through MVA_post (j lower);
    Section 34 discount rates unchanged."""
    pens = (members.status == "P").to_numpy()
    non = ~pens
    tv, _ = transfer_values(members[non], s34_basis(valuation_date), mva_npa_at(valuation_date, rate_shift))
    ann, _ = annuity_costs(members[pens], annuity_basis(valuation_date), annuity_curve(valuation_date).shifted(rate_shift))
    np_total, p_total = tv.sum(), ann.sum()
    status = members.status.to_numpy()
    by_status = {"A": tv[status[non] == "A"].sum(), "D": tv[status[non] == "D"].sum(), "P": p_total}
    expenses = wind_up_expenses(np_total + p_total)
    return {"by_status": by_status, "non_pensioners": np_total, "pensioners": p_total, "expenses": expenses,
            "total": np_total + p_total + expenses, "tv_by_member": tv, "annuity_by_member": ann}


def fsr(members, valuation_date, portfolio, market):
    """Funding standard reserve (SPEC §9 M6)."""
    p = statutory()["fsr"]
    base = liabilities(members, valuation_date)
    shocked = liabilities(members, valuation_date, rate_shift=-p["interest_rate_fall"])
    assets_total = portfolio.total(market)
    a_qual = portfolio.qualifying(market)
    d_a_qual = portfolio.qualifying(market.shifted(-p["interest_rate_fall"])) - a_qual
    d_liab = shocked["total"] - base["total"]
    proportion_part = p["proportion"] * max(base["total"] - a_qual, 0.0)
    interest_part = d_liab - d_a_qual
    reserve = proportion_part + interest_part
    return {
        "fs_liabilities": base, "assets": assets_total, "qualifying_assets": a_qual,
        "fs_funding_level": assets_total / base["total"], "fs_met": assets_total >= base["total"],
        "proportion_part": proportion_part,
        "interest_part": interest_part,
        "d_liabilities": {"total": d_liab, "pensioners": shocked["pensioners"] - base["pensioners"],
                          "non_pensioners": shocked["non_pensioners"] - base["non_pensioners"],
                          "expenses": shocked["expenses"] - base["expenses"]},
        "d_qualifying_assets": d_a_qual,
        "fsr": reserve, "fs_plus_fsr": base["total"] + reserve,
        "fs_plus_fsr_cover": assets_total / (base["total"] + reserve),
        "fs_plus_fsr_met": assets_total >= base["total"] + reserve,
        "shortfall_fs_plus_fsr": max(base["total"] + reserve - assets_total, 0.0),
    }
