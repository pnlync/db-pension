"""M9 risk (SPEC §9 M9, slimmed in v1.6): scenarios on both bases with assets revalued, PV01, hedge ratios,
tornado of IAS 19 deficit impacts."""
from dataclasses import replace

import numpy as np

from pension import assets, cashflows, funding_standard as fs, ias19
from pension.mortality import Mortality

SHIFT = 0.005


def base_state(members, valuation_date, total_assets, curve_date):
    market = assets.Market.at(valuation_date, curve_date)
    return {
        "members": members, "date": valuation_date, "market": market,
        "portfolio": assets.closing_portfolio(total_assets, market),
        "ias19_basis": ias19.basis(valuation_date), "ias19_curve": ias19.curve(valuation_date),
        "ann_basis": fs.annuity_basis(valuation_date), "ann_curve": fs.annuity_curve(valuation_date),
        "mva_npa": fs.mva_npa_at(valuation_date),
    }


def insurer_longevity_k(ann_basis, year):
    return ann_basis.mortality_post.longevity_k(sex="M", year=year, extra_years=1.0)


def evaluate(state, rate_shift=0.0, inflation_shift=0.0, salary_shift=0.0, longevity=False, equity_factor=1.0):
    """Liabilities, assets and funding levels on both bases for one scenario."""
    m, d = state["members"], state["date"]
    # IAS 19
    b = state["ias19_basis"]
    if inflation_shift:
        b = ias19.basis(d, inflation=b.inflation + inflation_shift)
    if salary_shift:
        b = b.with_(salary_growth=b.salary_growth + salary_shift)
    if longevity:
        k = b.mortality_post.longevity_k(year=d.year + 1)
        b = b.with_(mortality_pre=b.mortality_pre.with_k(k), mortality_post=b.mortality_post.with_k(k))
    curve = state["ias19_curve"].shifted(rate_shift)
    dbo = cashflows.pv(cashflows.project_cashflows(m, b), curve).sum()
    # Funding Standard: non-pensioners via MVA_post (j moves with rates), pensioners at annuity cost
    ann_b = state["ann_basis"]
    if inflation_shift:
        pi = round((ann_b.inflation + inflation_shift) * 100, 1) / 100
        ann_b = ann_b.with_(inflation=pi, pension_increase=fs.fixed_increase(pi, ann_b.rules["pension_increases"]["cap"]))
    if longevity:
        k = insurer_longevity_k(ann_b, d.year + 1)
        ann_b = ann_b.with_(mortality_pre=ann_b.mortality_pre.with_k(k), mortality_post=ann_b.mortality_post.with_k(k))
    mva_npa = fs.mva_npa_at(d, rate_shift) if rate_shift else state["mva_npa"]
    fsl = fs.liabilities_on(m, d, mva_npa, ann_b, state["ann_curve"].shifted(rate_shift))["total"]
    # assets: bonds on shifted curves (inflation shift moves the real curve), equities scaled
    market = state["market"].shifted(rate_shift)
    if inflation_shift:
        market = replace(market, inflation=market.inflation + inflation_shift)
    a = state["portfolio"].total(market, equity_factor)
    return {"ias19_dbo": dbo, "fs_liability": fsl, "assets": a,
            "ias19_deficit": dbo - a, "ias19_funding_level": a / dbo,
            "fs_surplus": a - fsl, "fs_funding_level": a / fsl}


SCENARIOS = {
    "base": {},
    "discount_minus_50bp": {"rate_shift": -SHIFT},
    "discount_plus_50bp": {"rate_shift": SHIFT},
    "inflation_plus_50bp": {"inflation_shift": SHIFT},
    "inflation_minus_50bp": {"inflation_shift": -SHIFT},
    "salary_plus_50bp": {"salary_shift": SHIFT},
    "salary_minus_50bp": {"salary_shift": -SHIFT},
    "life_expectancy_plus_1": {"longevity": True},
    "equities_minus_20pct": {"equity_factor": 0.8},
    "combined": {"rate_shift": -SHIFT, "longevity": True, "equity_factor": 0.8},
}


def scenarios(state):
    return {name: evaluate(state, **kw) for name, kw in SCENARIOS.items()}


def pv01s(state, fsr_result):
    """PV01 (EUR per 1 bp fall): IAS 19 by curve bump; FS = dL_FS(-0.5%) / 50; assets by bond class."""
    b, c = state["ias19_basis"], state["ias19_curve"]
    cf = cashflows.project_cashflows(state["members"], b)
    liab_ias19 = ias19.pv01(cf, c)
    liab_fs = fsr_result["d_liabilities"]["total"] / 50
    pf, mk = state["portfolio"], state["market"]
    by_class = {k: pf.pv01(mk, classes=(k,)) for k in assets.BOND_CLASSES}
    asset_total = sum(by_class.values())
    return {"ias19_liability": liab_ias19, "fs_liability": liab_fs, "assets_by_class": by_class, "assets": asset_total,
            "hedge_ratio_ias19": asset_total / liab_ias19, "hedge_ratio_fs": asset_total / liab_fs}
