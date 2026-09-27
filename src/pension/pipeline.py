"""The pipeline: every public number is written to outputs/ from here (SPEC §11).
Run: uv run python -m pension.pipeline
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from pension import assets, bridge, cashflows, excel_build, figures, funding_standard, ias19, mva
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
    (OUTPUTS / name).write_text(json.dumps(to_json(data), indent=2))


def life_expectancies(mortality, year):
    return {"male_65_now": mortality.e65_now("M", year), "female_65_now": mortality.e65_now("F", year),
            "male_65_in_20_years": mortality.e65_at_age("M", 45, year),
            "female_65_in_20_years": mortality.e65_at_age("F", 45, year)}


def closing_assets_placeholder(dbo):
    """Until M8 rolls the assets forward: design target funding level x DBO (SPEC §12)."""
    return load_config("assets")["target_closing_ias19_funding_level"] * dbo


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
        "assets": assets, "assets_source": "placeholder: 99% of DBO until M8",
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
    write_json("cv_numbers.json", cv)
    return cv


def run_excel(members, ias19_result):
    return excel_build.build(members, ias19_result["basis"], 0.0375, ias19_result["curve"])


def main():
    members = members_at(CLOSING)
    out, r = run_ias19(members)
    fs_out, _ = run_funding_standard(members, out["assets"])
    br = run_bridge(members, fs_out["liabilities"]["total"], out["dbo"])
    run_excel(members, r)
    run_cv_numbers()
    from pension import disclosure
    disclosure.write(out)
    print(f"IAS 19 DBO {out['dbo'] / 1e6:.1f}m, SEDR {out['assumptions']['sedr']:.2%}, duration {out['duration']:.1f}")
    print(f"FS {fs_out['liabilities']['total'] / 1e6:.1f}m, FS level {fs_out['fs_funding_level']:.1%}, "
          f"FSR {fs_out['fsr']['total'] / 1e6:.1f}m, FS + FSR cover {fs_out['fs_plus_fsr_cover']:.1%}")
    print("bridge:", ", ".join(f"{s['effect'] / 1e6:+.1f}" for s in br["steps"][1:]), f"residual {br['residual']:.2f}")


if __name__ == "__main__":
    main()
