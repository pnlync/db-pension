"""The pipeline: every public number is written to outputs/ from here (SPEC §11).
Run: uv run python -m pension.pipeline
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from pension import aoc, assets, bridge, buyin, cashflows, decisions, risk, excel_build, figures, funding_standard, ias19, mva
from pension.io import MEMBERS, OUTPUTS, ROOT, load_config

CLOSING = date(2025, 12, 31)
OPENING = date(2024, 12, 31)


def members_at(valuation_date):
    name = "members_2025_clean.csv" if valuation_date == CLOSING else "members_2024.csv"
    return cashflows.prepare_members(pd.read_csv(MEMBERS / name, dtype=str), valuation_date)


def to_json(obj):
    if isinstance(obj, dict):
        return {str(k): to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    return obj


def write_json(name, data):
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / name).write_text(json.dumps(to_json(data), indent=2, allow_nan=False))


def life_expectancies(mortality, year):
    return {"male_65_now": mortality.e65_now("M", year), "female_65_now": mortality.e65_now("F", year),
            "male_65_in_20_years": mortality.e65_at_age("M", 45, year),
            "female_65_in_20_years": mortality.e65_at_age("F", 45, year)}


def closing_assets_placeholder(dbo):
    """Until M8 rolls the assets forward: design target funding level x DBO (SPEC §12)."""
    return load_config("assets")["target_closing_ias19_funding_level"] * dbo


def run_aoc():
    """M8: opening valuation, 2025 analysis of change, asset roll-forward (sets the closing assets)."""
    m0, m1 = members_at(OPENING), members_at(CLOSING)
    r = aoc.run(m0, m1, pd.read_csv(MEMBERS / "members_2024.csv"), pd.read_csv(MEMBERS / "movements_2025.csv"))
    liab, roll, acc, fsc = r["liabilities"], r["assets"], r["accounts"], r["fs"]
    r0 = liab["opening_result"]
    out = {
        "opening": {"date": OPENING.isoformat(), "dbo": r0["dbo"], "dbo_by_status": r0["dbo_by_status"],
                    "sedr": r0["sedr"], "duration": r0["duration"], "inflation": r0["basis"].inflation,
                    "assets": roll.opening, "fs_liability": fsc["fs_opening"], "fs_funding_level": fsc["fs_level_opening"]},
        "flows_2025": r["flows"],
        "dbo_reconciliation": liab["steps"] | {"closing": liab["closing"], "expected_closing": liab["expected_closing"]},
        "asset_reconciliation": {"opening": roll.opening, "interest_income": acc["interest_income"],
                                 "return_above_interest": acc["return_above_interest"],
                                 "employer_contributions": r["flows"]["employer_contributions"],
                                 "member_contributions": r["flows"]["member_contributions"],
                                 "benefits_paid": -r["flows"]["benefits"], "expenses": -r["flows"]["expenses"],
                                 "closing": roll.closing},
        "asset_returns_2025": roll.returns, "assets_by_class": {"opening": roll.opening_by_class,
                                                                "closing": roll.closing_by_class},
        "pl_2025": acc["pl"], "oci_2025": acc["oci"],
        "net_liability": {"opening": acc["opening_net_liability"], "closing": acc["closing_net_liability"]},
        "deficit_waterfall": acc["waterfall"],
        "fs_change": fsc,
        "checks": {
            "other_pct_of_dbo": liab["steps"]["other"] / liab["closing"],
            "asset_identity": roll.closing - (roll.opening + acc["interest_income"] + acc["return_above_interest"]
                                              + roll.net_flow),
            "net_liability_identity": acc["closing_net_liability"] - (acc["opening_net_liability"] + acc["pl"]["total"]
                                                                      + acc["oci"]["total"]
                                                                      - r["flows"]["employer_contributions"]),
        },
    }
    write_json("aoc_2025.json", out)
    figures.fig3_waterfall(acc["waterfall"], OUTPUTS / "fig3_deficit_waterfall.png")
    return out


def run_ias19(members=None, assets=None):
    members = members_at(CLOSING) if members is None else members
    r = ias19.valuation(members, CLOSING)
    sc = ias19.service_cost(members, CLOSING, r["basis"], r["curve"])
    sens = ias19.sensitivities(members, CLOSING, r)
    cfg_assets = load_config("assets")
    cfg = ias19.config()
    assets = closing_assets_placeholder(r["dbo"]) if assets is None else assets

    rate = r["sedr"]
    half = (1 + rate) ** 0.5 - 1
    employer_contrib = (cfg_assets["contributions"]["employer_normal_rate"] * sc["pensionable_payroll"]
                        + cfg_assets["contributions"]["employer_deficit_eur"])
    net_interest = rate * (r["dbo"] - assets) - half * employer_contrib   # contributions mid-year
    admin = cfg["admin_expenses"]["per_member_eur"] * len(members)
    b = r["basis"]
    out = {
        "valuation_date": CLOSING.isoformat(),
        "members": members.status.value_counts().to_dict(),
        "assumptions": {
            "sedr": rate, "aa_spread": cfg["discount"]["aa_spread"], "inflation": b.inflation,
            "salary_growth": b.salary_growth, "pension_increases": b.pension_increase,
            "deferred_revaluation": b.revaluation, "known_increase_2026": b.known_increases,
            "mortality": cfg["mortality"]["multiplier"] | {"improvement": cfg["mortality"]["improvement"]},
            "life_expectancy": life_expectancies(b.mortality_post, CLOSING.year + 1),
        },
        "dbo": r["dbo"], "dbo_by_status": r["dbo_by_status"],
        "pensioner_share": r["dbo_by_status"]["P"] / r["dbo"],
        "duration": r["duration"], "pv01": r["pv01"],
        "service_cost_2026": sc,
        "service_cost_pct_pensionable_payroll": sc["gross"] / sc["pensionable_payroll"],
        "assets": assets, "assets_source": "2025 roll-forward (M8), rebalanced to the strategic allocation at 2025-12-31",
        "net_liability": r["dbo"] - assets, "funding_level": assets / r["dbo"],
        "asset_ceiling": "not applicable: the scheme is in deficit, so IFRIC 14 does not restrict any asset",
        "pl_2026": {"employer_service_cost": sc["employer"], "net_interest": net_interest, "admin_expenses": admin,
                    "total": sc["employer"] + net_interest + admin},
        "expected_2026": {"benefits": float(r["cf_total"][0]), "employer_contributions": employer_contrib,
                          "member_contributions": sc["member_contributions"]},
        "maturity_profile_10y": [float(x) for x in r["cf_total"][:10]],
        "sensitivities": {"k_life_expectancy_plus_1": sens["k"],
                          "dbo": sens["dbo"],
                          "change_pct": {k: v / r["dbo"] - 1 for k, v in sens["dbo"].items()}},
        "asset_allocation": {k: w * assets for k, w in cfg_assets["allocation"].items()},
    }
    write_json("ias19_2025.json", out)
    figures.fig1_cashflows(r["cf"], members.status.to_numpy(), CLOSING.year + 1, OUTPUTS / "fig1_cashflows.png")
    return out, r


def closing_market():
    return assets.Market.at(CLOSING, "2025-12-31")


def run_funding_standard(members, total_assets):
    market = closing_market()
    portfolio = assets.closing_portfolio(total_assets, market)
    r = funding_standard.fsr(members, CLOSING, portfolio, market)
    L = r["fs_liabilities"]
    golden = mva.golden_test()
    golden.to_csv(OUTPUTS / "mva_golden_test.csv", index=False)
    b = funding_standard.annuity_basis(CLOSING)
    out = {
        "valuation_date": CLOSING.isoformat(),
        "liabilities": {"actives": L["by_status"]["A"], "deferreds": L["by_status"]["D"],
                        "pensioners": L["pensioners"], "non_pensioners": L["non_pensioners"],
                        "wind_up_expenses": L["expenses"], "total": L["total"]},
        "basis": {"mva_npa_index_linked": funding_standard.mva_npa_at(CLOSING),
                  "mva_row_date": str(mva.row_for_effective_date(CLOSING).date),
                  "annuity_pi": b.inflation, "annuity_fixed_increase": b.pension_increase,
                  "insurer_spread": funding_standard.insurer()["fs_annuity_proxy"]["insurer_spread"]},
        "assets": r["assets"], "qualifying_assets": r["qualifying_assets"],
        "asset_values": portfolio.values(market),
        "fs_funding_level": r["fs_funding_level"], "fs_met": r["fs_met"],
        "fsr": {"proportion_part": r["proportion_part"], "interest_part": r["interest_part"], "total": r["fsr"],
                "d_liabilities": r["d_liabilities"], "d_qualifying_assets": r["d_qualifying_assets"]},
        "fs_plus_fsr": r["fs_plus_fsr"], "fs_plus_fsr_cover": r["fs_plus_fsr_cover"],
        "fs_plus_fsr_met": r["fs_plus_fsr_met"], "shortfall_fs_plus_fsr": r["shortfall_fs_plus_fsr"],
        "mva_golden_test": {"months": len(golden), "mva1_matched": int(golden.mva1_match.sum()),
                            "mva2_matched": int(golden.mva2_match.sum())},
    }
    write_json("funding_standard_2025.json", out)
    return out, r


def run_risk(members, total_assets):
    state = risk.base_state(members, CLOSING, total_assets, "2025-12-31")
    results = risk.scenarios(state)
    f = funding_standard.fsr(members, CLOSING, state["portfolio"], state["market"])
    p = risk.pv01s(state, f)
    base, down = results["base"], results["discount_minus_50bp"]
    out = {"scenarios": results, "pv01": p,
           "funding_level_change_minus_50bp": {
               "ias19_pp": (down["ias19_funding_level"] - base["ias19_funding_level"]) * 100,
               "fs_pp": (down["fs_funding_level"] - base["fs_funding_level"]) * 100}}
    write_json("risk_2025.json", out)
    figures.fig_tornado(results, OUTPUTS / "fig_tornado.png")
    return out


def run_decisions(members, total_assets):
    """M10: funding projection, contribution solve (3 / 5 / 10 years), switch experiment, trustee table."""
    cfg = load_config("assets")
    rate_fall = load_config("statutory_ie")["fsr"]["interest_rate_fall"]
    market = closing_market()
    alloc = cfg["allocation"]
    alloc_sw = decisions.allocation_after_switch(alloc)
    dq = decisions.qualifying_sensitivity(total_assets, alloc, market, rate_fall)
    dq_sw = decisions.qualifying_sensitivity(total_assets, alloc_sw, market, rate_fall)
    proj = decisions.build_projection(members, 10)
    solved = {}
    for years in (3, 5, 10):
        solved[years] = {"contributions_only": decisions.solve_contribution(proj, total_assets, alloc, dq, years),
                         "switch_and_contributions": decisions.solve_contribution(proj, total_assets, alloc_sw, dq_sw, years)}
    c3, c3_sw = solved[3]["contributions_only"], solved[3]["switch_and_contributions"]

    def path(al, d, c):
        return decisions.run_projection(proj, total_assets, al, d, c, 3)[:4]

    paths = {"No action": path(alloc, dq, 0.0), "Contributions only": path(alloc, dq, c3),
             "Switch only": path(alloc_sw, dq_sw, 0.0), "Switch + contributions": path(alloc_sw, dq_sw, c3_sw)}

    # the switch at 2025-12-31: FSR, hedge ratios, -50 bp hit, expected return
    def snapshot(al):
        state = risk.base_state(members, CLOSING, total_assets, "2025-12-31")
        state["portfolio"] = assets.Portfolio.from_allocation(total_assets, al, market, assets.durations())
        f = funding_standard.fsr(members, CLOSING, state["portfolio"], market)
        p = risk.pv01s(state, f)
        base, down = risk.evaluate(state), risk.evaluate(state, rate_shift=-risk.SHIFT)
        return {"fsr_proportion": f["proportion_part"], "fsr_interest": f["interest_part"], "fsr": f["fsr"],
                "qualifying_assets": f["qualifying_assets"], "fs_plus_fsr_cover": f["fs_plus_fsr_cover"],
                "shortfall": f["shortfall_fs_plus_fsr"], "hedge_ratio_ias19": p["hedge_ratio_ias19"],
                "hedge_ratio_fs": p["hedge_ratio_fs"], "asset_pv01": p["assets"],
                "ias19_funding_change_minus_50bp_pp": (down["ias19_funding_level"] - base["ias19_funding_level"]) * 100,
                "fs_funding_change_minus_50bp_pp": (down["fs_funding_level"] - base["fs_funding_level"]) * 100,
                "expected_return": decisions.expected_return(al),
                "ias19_deficit": base["ias19_deficit"]}
    now, now_sw = snapshot(alloc), snapshot(alloc_sw)
    options = {
        "Contributions only": {"allocation": "current", "c": c3, "snapshot": now, "cover_year_3": paths["Contributions only"][3]["cover"]},
        "Switch only": {"allocation": "switch", "c": 0.0, "snapshot": now_sw, "cover_year_3": paths["Switch only"][3]["cover"]},
        "Switch + contributions": {"allocation": "switch", "c": c3_sw, "snapshot": now_sw,
                                   "cover_year_3": paths["Switch + contributions"][3]["cover"]},
    }
    table = [{"option": k, "deficit_contribution_a_year": v["c"], "contributions_over_3_years": 3 * v["c"],
              "fs_plus_fsr_cover_now": v["snapshot"]["fs_plus_fsr_cover"], "fs_plus_fsr_cover_year_3": v["cover_year_3"],
              "ias19_deficit_now": v["snapshot"]["ias19_deficit"],
              "hedge_ratio_ias19": v["snapshot"]["hedge_ratio_ias19"], "hedge_ratio_fs": v["snapshot"]["hedge_ratio_fs"],
              "ias19_funding_change_minus_50bp_pp": v["snapshot"]["ias19_funding_change_minus_50bp_pp"],
              "expected_return": v["snapshot"]["expected_return"]} for k, v in options.items()]
    out = {"note": "3 years is the base scenario; 5 and 10 years are strategic planning scenarios, not proposed "
                   "statutory recovery periods. C is the total deficit contribution a year (replacing the current "
                   "EUR 2.0m), paid mid-year; normal contributions continue.",
           "solved_contribution": solved, "fs_path_10y": [x.total for x in proj.fs],
           "switch": {"before": now, "after": now_sw,
                      "shortfall_reduction": 1 - now_sw["shortfall"] / now["shortfall"]},
           "paths_3y": paths, "trustee_table": table,
           "expected_return_cost_of_switch_eur": (now["expected_return"] - now_sw["expected_return"]) * total_assets}
    write_json("decisions_2025.json", out)
    figures.fig4_paths(paths, {k: v["c"] for k, v in options.items()}, OUTPUTS / "fig4_funding_paths.png")
    return out


def run_buyin(members, total_assets, fs_out):
    """M11: Solvency II benchmark, premium, waterfall, day-one effects on IAS 19, FS and FSR."""
    pensioners = members[members.status == "P"]
    priced = buyin.price(pensioners, CLOSING)
    steps = buyin.waterfall(pensioners, CLOSING, priced)
    cfg = buyin.config()["buyin"]
    grid = {f"s={s:.3f}": {f"m={m:.2f}": buyin.price(pensioners, CLOSING, s, m)["premium"]
                           for m in cfg["profit_margin"]} for s in cfg["spread_passed_on"]}
    effects = {meth: buyin.day_one(members, CLOSING, total_assets, priced, meth)
               for meth in ("pro_rata", "sell_sovereigns", "sell_equities")}
    proxy = fs_out["liabilities"]["pensioners"]
    fs_quote = fs_out["liabilities"]["non_pensioners"] + priced["premium"]
    fs_quote += funding_standard.wind_up_expenses(fs_quote)
    pro = effects["pro_rata"]
    out = {"price": priced, "premium_pct_of_ias19_dbo": priced["premium"] / pro["insured_ias19_dbo"],
           "tp_pct_of_ias19_dbo": priced["tp"] / pro["insured_ias19_dbo"], "waterfall": steps,
           "premium_grid": grid,
           "vs_fs_annuity_proxy": {"proxy": proxy, "premium": priced["premium"],
                                   "premium_over_proxy": priced["premium"] / proxy - 1,
                                   "fs_liability_if_quote_consistent": fs_quote,
                                   "fs_level_if_quote_consistent": total_assets / fs_quote},
           "day_one": effects,
           "note": "Two liability measures (IAS 19, Funding Standard) plus one transaction price. The IAS 19 OCI loss "
                   "assumes a qualifying insurance policy that exactly matches the insured benefits."}
    write_json("buyin_2025.json", out)
    compare = {"Before": {"IAS 19 funding level": pro["ias19"]["before"]["funding_level"],
                          "FS funding level": pro["fs"]["before"]["fs_level"],
                          "FS + FSR cover": pro["fs"]["before"]["cover"]},
               "After (pay pro rata)": {"IAS 19 funding level": pro["ias19"]["after"]["funding_level"],
                                        "FS funding level": pro["fs"]["after"]["fs_level"],
                                        "FS + FSR cover": pro["fs"]["after"]["cover"]},
               "After (sell equities)": {"IAS 19 funding level": effects["sell_equities"]["ias19"]["after"]["funding_level"],
                                         "FS funding level": effects["sell_equities"]["fs"]["after"]["fs_level"],
                                         "FS + FSR cover": effects["sell_equities"]["fs"]["after"]["cover"]}}
    figures.fig5_buyin(steps, compare, OUTPUTS / "fig5_buyin.png")
    return out


def run_bridge(members, fs_total, dbo):
    steps = bridge.run(members, CLOSING)
    out = {"steps": steps, "fs_minus_ias19": fs_total - dbo,
           "sum_of_effects": sum(s["effect"] for s in steps[1:]),
           "residual": steps[-1]["level"] - fs_total,
           "note": "Bridge effects are sequential rather than unique standalone decompositions."}
    write_json("bridge_2025.json", out)
    figures.fig2_bridge(steps, OUTPUTS / "fig2_bridge.png")
    return out


def run_cv_numbers():
    """outputs/cv_numbers.json: every number quoted in the CV, README and memo (SPEC §11, §9 M12)."""
    def load(name):
        path = OUTPUTS / name
        return json.loads(path.read_text()) if path.exists() else None
    ias, fs_, br = load("ias19_2025.json"), load("funding_standard_2025.json"), load("bridge_2025.json")
    steps = {s["key"]: s["effect"] for s in br["steps"]}
    non_pensioner_effect = sum(steps[k] for k in ("leaver_basis", "s34_mortality", "s34_increases", "s34_discount"))
    cv = {
        "members_opening": len(pd.read_csv(MEMBERS / "members_2024.csv")),
        "members_closing": sum(ias["members"].values()),
        "ias19_dbo_m": round(ias["dbo"] / 1e6, 1), "ias19_sedr_pct": round(ias["assumptions"]["sedr"] * 100, 2),
        "ias19_duration_years": round(ias["duration"], 1),
        "fs_liability_m": round(fs_["liabilities"]["total"] / 1e6, 1),
        "fs_minus_ias19_m": round(br["fs_minus_ias19"] / 1e6, 1),
        "bridge_non_pensioners_m": round(non_pensioner_effect / 1e6, 1),
        "bridge_pensioner_annuity_cost_m": round(steps["annuity_cost"] / 1e6, 1),
        "bridge_wind_up_m": round(steps["expenses"] / 1e6, 1),
        "fsr_m": round(fs_["fsr"]["total"] / 1e6, 1),
        "fs_funding_level_pct": round(fs_["fs_funding_level"] * 100, 1),
        "fs_plus_fsr_shortfall_m": round(fs_["shortfall_fs_plus_fsr"] / 1e6, 1),
        "mva_months_reproduced": fs_["mva_golden_test"]["months"],
        "excel_members_reconciled": 3,
    }
    a, rk, dec = load("aoc_2025.json"), load("risk_2025.json"), load("decisions_2025.json")
    if a:
        w = a["deficit_waterfall"]
        cv |= {"ias19_deficit_opening_m": round(w["opening_deficit"] / 1e6, 1),
               "ias19_deficit_closing_m": round(w["closing_deficit"] / 1e6, 1),
               "aoc_assumption_changes_m": round(w["assumption_changes"] / 1e6, 1),
               "aoc_curve_m": round(a["dbo_reconciliation"]["curve"] / 1e6, 1),
               "aoc_other_m": round(a["dbo_reconciliation"]["other"] / 1e6, 1),
               "fs_level_opening_pct": round(a["opening"]["fs_funding_level"] * 100, 1),
               "sedr_opening_pct": round(a["opening"]["sedr"] * 100, 2)}
    if rk:
        cv |= {"hedge_ratio_ias19_pct": round(rk["pv01"]["hedge_ratio_ias19"] * 100),
               "hedge_ratio_fs_pct": round(rk["pv01"]["hedge_ratio_fs"] * 100)}
    if dec:
        sw = dec["switch"]
        cv |= {"contribution_3y_m": round(dec["solved_contribution"]["3"]["contributions_only"] / 1e6, 1),
               "contribution_3y_with_switch_m": round(dec["solved_contribution"]["3"]["switch_and_contributions"] / 1e6, 1),
               "switch_weight_pct": round(load_config("assets")["switch"]["weight"] * 100),
               "switch_shortfall_reduction_pct": round(sw["shortfall_reduction"] * 100),
               "switch_hedge_ratio_ias19_pct": round(sw["after"]["hedge_ratio_ias19"] * 100),
               "switch_hedge_ratio_fs_pct": round(sw["after"]["hedge_ratio_fs"] * 100),
               "switch_expected_return_cost_m": round(dec["expected_return_cost_of_switch_eur"] / 1e6, 1)}
    bi = load("buyin_2025.json")
    if bi:
        pro, eq = bi["day_one"]["pro_rata"], bi["day_one"]["sell_equities"]
        cv |= {"buyin_premium_m": round(bi["price"]["premium"] / 1e6, 1),
               "buyin_premium_pct_ias19": round(bi["premium_pct_of_ias19_dbo"] * 100),
               "buyin_tp_pct_ias19": round(bi["tp_pct_of_ias19_dbo"] * 100),
               "buyin_oci_loss_m": round(pro["ias19"]["after"]["oci_loss"] / 1e6, 1),
               "buyin_ias19_level_before_pct": round(pro["ias19"]["before"]["funding_level"] * 100, 1),
               "buyin_ias19_level_after_pct": round(pro["ias19"]["after"]["funding_level"] * 100, 1),
               "buyin_fsr_before_m": round(pro["fs"]["before"]["fsr"] / 1e6, 1),
               "buyin_fsr_after_m": round(pro["fs"]["after"]["fsr"] / 1e6, 1),
               "buyin_pv01_insured_ias19_pct": round(pro["pv01_insured_share"]["ias19"] * 100),
               "buyin_pv01_insured_fs_pct": round(pro["pv01_insured_share"]["fs"] * 100),
               "buyin_premium_over_fs_proxy_pct": round(bi["vs_fs_annuity_proxy"]["premium_over_proxy"] * 100, 1),
               "buyin_shortfall_after_sell_equities_m": round(eq["fs"]["after"]["shortfall"] / 1e6, 1)}
    write_json("cv_numbers.json", cv)
    return cv


def run_excel(members, ias19_result):
    return excel_build.build(members, ias19_result["basis"], 0.0375, ias19_result["curve"])


def main():
    members = members_at(CLOSING)
    aoc_out = run_aoc()
    out, r = run_ias19(members, assets=aoc_out["asset_reconciliation"]["closing"])
    fs_out, _ = run_funding_standard(members, out["assets"])
    br = run_bridge(members, fs_out["liabilities"]["total"], out["dbo"])
    rk = run_risk(members, out["assets"])
    dec = run_decisions(members, out["assets"])
    bi = run_buyin(members, out["assets"], fs_out)
    run_excel(members, r)
    run_cv_numbers()
    from pension import disclosure
    disclosure.write(out, disclosure.aoc_tables(aoc_out))
    print(f"IAS 19 DBO {out['dbo'] / 1e6:.1f}m, SEDR {out['assumptions']['sedr']:.2%}, duration {out['duration']:.1f}")
    print(f"FS {fs_out['liabilities']['total'] / 1e6:.1f}m, FS level {fs_out['fs_funding_level']:.1%}, "
          f"FSR {fs_out['fsr']['total'] / 1e6:.1f}m, FS + FSR cover {fs_out['fs_plus_fsr_cover']:.1%}")
    print("bridge:", ", ".join(f"{s['effect'] / 1e6:+.1f}" for s in br["steps"][1:]), f"residual {br['residual']:.2f}")


if __name__ == "__main__":
    main()
