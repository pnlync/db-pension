"""M11 pensioner buy-in (SPEC §9 M11).

Solvency II technical provisions (TP = BEL + RM) are the insurer's regulatory benchmark, not the price:
premium = TP - spread passed on + profit. Two liability measures (IAS 19, Funding Standard) plus one
transaction price; the buy-in price is never a third liability.
"""
import numpy as np

from pension import assets, cashflows, funding_standard as fs, ias19
from pension.curves import Curve
from pension.io import load_config, read_market


def config():
    return load_config("assumptions_insurer")


def eiopa_curve(with_va=True, spread=0.0):
    t = read_market(config()["solvency2"]["curve_file"])
    return Curve(t.maturity, t.spot_with_va if with_va else t.spot_no_va, spread=spread,
                 label="EIOPA RFR" + (" + VA" if with_va else ""))


def insurer_basis(valuation_date):
    """Annuitant mortality and the PEN-3 fixed-rate substitute for CPI-linked increases (limitation)."""
    return fs.annuity_basis(valuation_date)


def expense_cashflows(pensioners, b, per_policy, expense_inflation):
    """EUR per policy a year, rising with inflation from year 2, times average survival, paid mid-year."""
    unit = pensioners.assign(pension=1.0)
    cf = cashflows.project_cashflows(unit, b.with_(known_increases={}, pension_increase=expense_inflation))
    return per_policy / (1 + expense_inflation) * cf


def bel_parts(pensioners, b, curve, per_policy, expense_inflation):
    benefit_cf = cashflows.project_cashflows(pensioners, b)
    expense_cf = expense_cashflows(pensioners, b, per_policy, expense_inflation)
    return benefit_cf, expense_cf, cashflows.pv(benefit_cf, curve).sum(), cashflows.pv(expense_cf, curve).sum()


def runoff(total_cf, curve):
    """Value at the start of each future year j of the cash flows still to come (j = 0, 1, ...)."""
    H = len(total_cf)
    times = cashflows.payment_times(H)
    df = curve.discount(times)
    out = np.zeros(H)
    for j in range(H):
        out[j] = (total_cf[j:] * df[j:]).sum() / curve.discount(j)
    return out


def risk_margin(pensioners, valuation_date):
    """Cost-of-capital RM: SCR(longevity, expense) at t = 0, projected in proportion to the BEL run-off."""
    cfg, s2 = config()["buyin"], config()["solvency2"]
    b = insurer_basis(valuation_date)
    curve = eiopa_curve(with_va=True)
    per_policy, infl = cfg["expense_per_policy_eur"], b.inflation
    bcf, ecf, bel_b, bel_e = bel_parts(pensioners, b, curve, per_policy, infl)
    bel = bel_b + bel_e

    mort = b.mortality_post.with_k(1 - cfg["longevity_shock"])
    lb = b.with_(mortality_pre=mort, mortality_post=mort)
    _, _, lb_b, lb_e = bel_parts(pensioners, lb, curve, per_policy, infl)
    scr_longevity = lb_b + lb_e - bel
    shock = cfg["expense_shock"]
    _, _, _, ex_e = bel_parts(pensioners, b, curve, per_policy * (1 + shock["level"]), infl + shock["inflation_add"])
    scr_expense = ex_e - bel_e
    rho = s2["life_correlation_longevity_expense"]
    scr0 = np.sqrt(scr_longevity ** 2 + scr_expense ** 2 + 2 * rho * scr_longevity * scr_expense)

    run = runoff((bcf + ecf).sum(axis=0), curve)
    scr = scr0 * run / run[0]
    j = np.arange(len(scr))
    weight = np.maximum(s2["time_weight_decay"] ** j, s2["time_weight_floor"])
    df_rm = eiopa_curve(with_va=False).discount(j + 1)
    rm = s2["cost_of_capital"] * float((weight * scr * df_rm).sum())
    return {"bel": bel, "bel_benefits": bel_b, "bel_expenses": bel_e, "scr_longevity": scr_longevity,
            "scr_expense": scr_expense, "scr": scr0, "rm": rm, "tp": bel + rm}


def price(pensioners, valuation_date, spread=None, margin=None):
    """Premium = TP - spread passed on + profit (x BEL); no separate capital loading on top of the RM."""
    cfg = config()["buyin"]
    s = cfg["spread_passed_on_base"] if spread is None else spread
    m = cfg["profit_margin_base"] if margin is None else margin
    b = insurer_basis(valuation_date)
    sii = risk_margin(pensioners, valuation_date)
    _, _, bel_s_b, bel_s_e = bel_parts(pensioners, b, eiopa_curve(True, spread=s), cfg["expense_per_policy_eur"],
                                       b.inflation)
    spread_passed_on = sii["bel"] - (bel_s_b + bel_s_e)
    profit = m * sii["bel"]
    return sii | {"spread": s, "margin": m, "spread_passed_on": spread_passed_on, "profit": profit,
                  "premium": sii["tp"] - spread_passed_on + profit}


def waterfall(pensioners, valuation_date, priced):
    """Pensioner IAS 19 DBO -> premium by sequential steps (zero residual)."""
    b_ias, c_ias = ias19.basis(valuation_date), ias19.curve(valuation_date)
    b_ins = insurer_basis(valuation_date)
    rfr = eiopa_curve(True)

    def pv(b, c):
        return cashflows.pv(cashflows.project_cashflows(pensioners, b), c).sum()

    levels = [("Pensioner IAS 19 DBO", pv(b_ias, c_ias))]
    levels.append(("Discount: AA curve -> EIOPA RFR + VA", pv(b_ias, rfr)))
    increases = b_ias.with_(pension_increase=b_ins.pension_increase)
    levels.append(("Increases: CPI assumption -> PEN-3 fixed rate", pv(increases, rfr)))
    levels.append(("Insurer mortality", pv(b_ins, rfr)))
    levels.append(("Expenses", priced["bel"]))
    levels.append(("Risk margin (= Solvency II TP)", priced["tp"]))
    levels.append(("Spread passed on", priced["tp"] - priced["spread_passed_on"]))
    levels.append(("Profit", priced["premium"]))
    steps = [{"step": i, "label": lab, "level": v, "effect": v if i == 0 else v - levels[i - 1][1]}
             for i, (lab, v) in enumerate(levels)]
    return steps


# --- day-one effects ----------------------------------------------------------------------------------------

def assets_after_payment(values, premium, method):
    """Class values after paying the premium: named classes sold first, the remainder pro rata."""
    v = dict(values)
    first = {"pro_rata": [], "sell_sovereigns": ["nominal_sovereigns", "long_sovereigns", "inflation_linked_sovereigns"],
             "sell_equities": ["equities"]}[method]
    left = premium
    for k in first:
        take = min(v.get(k, 0.0), left)
        v[k] -= take
        left -= take
    total = sum(v.values())
    return {k: x * (1 - left / total) for k, x in v.items()}


def day_one(members, valuation_date, total_assets, priced, method):
    market = assets.Market.at(valuation_date, "2025-12-31")
    pf = assets.closing_portfolio(total_assets, market)
    values_after = assets_after_payment(pf.values(market), priced["premium"], method)
    remaining = sum(values_after.values())
    weights = {k: v / remaining for k, v in values_after.items()}
    pf_after = assets.Portfolio.from_allocation(remaining, weights, market, assets.durations())

    pens = members.status == "P"
    r = ias19.valuation(members, valuation_date)
    status = members.status.to_numpy()
    dbo_p = r["by_member"][status == "P"].sum()
    cf = r["cf"]
    pv01_total = ias19.pv01(cf, r["curve"])
    pv01_p = ias19.pv01(cf[status == "P"], r["curve"])
    # IAS 19: policy valued at the DBO of the insured benefits (qualifying policy, exact match)
    plan_assets_after = remaining + dbo_p
    ias19_before = {"assets": total_assets, "funding_level": total_assets / r["dbo"],
                    "hedge_ratio": pf.pv01(market) / pv01_total}
    ias19_after = {"assets": plan_assets_after, "funding_level": plan_assets_after / r["dbo"],
                   "oci_loss": priced["premium"] - dbo_p, "hedge_ratio": (pf_after.pv01(market) + pv01_p) / pv01_total}
    # Funding Standard: purchased annuities reduce the liabilities (PEN-3 para 2.7); expenses on the remainder
    before = fs.fsr(members, valuation_date, pf, market)
    after = fs.fsr(members[~pens], valuation_date, pf_after, market)
    d_fs_p = before["d_liabilities"]["pensioners"]
    return {
        "method": method, "premium": priced["premium"], "insured_ias19_dbo": dbo_p,
        "assets_sold": total_assets - remaining, "assets_after_by_class": values_after,
        "ias19": {"before": ias19_before, "after": ias19_after},
        "fs": {"before": {"liabilities": before["fs_liabilities"]["total"], "fs_level": before["fs_funding_level"],
                          "fsr": before["fsr"], "cover": before["fs_plus_fsr_cover"],
                          "shortfall": before["shortfall_fs_plus_fsr"], "qualifying": before["qualifying_assets"]},
               "after": {"liabilities": after["fs_liabilities"]["total"], "fs_level": after["fs_funding_level"],
                         "fsr": after["fsr"], "cover": after["fs_plus_fsr_cover"],
                         "shortfall": after["shortfall_fs_plus_fsr"], "qualifying": after["qualifying_assets"],
                         "fsr_proportion": after["proportion_part"], "fsr_interest": after["interest_part"]},
               "insured_liability": before["fs_liabilities"]["pensioners"]},
        "pv01_insured_share": {"ias19": pv01_p / pv01_total, "fs": d_fs_p / before["d_liabilities"]["total"]},
        "insured_pv01_ias19": pv01_p,
        "buy_out_funding_level": "unchanged on day one: the policy is valued at its price",
    }
