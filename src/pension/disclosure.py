"""reports/disclosure_note.md: IAS 19 disclosure note generated from outputs/ (SPEC §9 M5, M8, M12).

Tables 1, 5, 6, 7 come from the 2025-12-31 valuation; tables 2-4 from the 2025 analysis of change (M8).
"""
from pension.io import ROOT

DISCLAIMER = ("All member data and member experience are synthetic. Market data are public and dated. Illustrative "
              "implementation based on published Pensions Authority and Society of Actuaries in Ireland guidance; "
              "not an actuarial certification or regulatory filing.")


def m(x):
    return f"{x / 1e6:,.1f}"


def pct(x):
    return f"{x * 100:.1f}%"


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def table_1(o):
    a = o["assumptions"]
    le = a["life_expectancy"]
    return table(["Assumption", "31 December 2025"], [
        ["Discount rate (single equivalent)", f"{a['sedr'] * 100:.2f}%"],
        ["Inflation (CPI)", f"{a['inflation'] * 100:.2f}%"],
        ["Salary increases", f"{a['salary_growth'] * 100:.2f}%"],
        ["Pension increases (CPI, floor 0%, cap 3%)", f"{a['pension_increases'] * 100:.2f}%"],
        ["Deferred revaluation (CPI, cap 4%)", f"{a['deferred_revaluation'] * 100:.2f}%"],
        ["Life expectancy at 65, male aged 65 now", f"{le['male_65_now']:.1f} years"],
        ["Life expectancy at 65, female aged 65 now", f"{le['female_65_now']:.1f} years"],
        ["Life expectancy at 65, male aged 45 now", f"{le['male_65_in_20_years']:.1f} years"],
        ["Life expectancy at 65, female aged 45 now", f"{le['female_65_in_20_years']:.1f} years"],
    ])


def table_5(o):
    names = {"equities": "Global equities", "nominal_sovereigns": "Euro nominal sovereign bonds",
             "inflation_linked_sovereigns": "Euro inflation-linked sovereign bonds",
             "corporates": "Euro corporate bonds", "cash": "Cash"}
    total = sum(o["asset_allocation"].values())
    rows = [[names[k], m(v), pct(v / total)] for k, v in o["asset_allocation"].items()]
    rows.append(["Total", m(total), "100.0%"])
    return table(["Asset class", "EUR m", "%"], rows)


def table_6(o):
    s = o["sensitivities"]["change_pct"]
    d = o["sensitivities"]["dbo"]
    rows = [
        ["Discount rate -0.5%", m(d["discount_minus_0.5"] - o["dbo"]), pct(s["discount_minus_0.5"])],
        ["Discount rate +0.5%", m(d["discount_plus_0.5"] - o["dbo"]), pct(s["discount_plus_0.5"])],
        ["Inflation +0.5%", m(d["inflation_plus_0.5"] - o["dbo"]), pct(s["inflation_plus_0.5"])],
        ["Inflation -0.5%", m(d["inflation_minus_0.5"] - o["dbo"]), pct(s["inflation_minus_0.5"])],
        ["Salary increases +0.5%", m(d["salary_plus_0.5"] - o["dbo"]), pct(s["salary_plus_0.5"])],
        ["Salary increases -0.5%", m(d["salary_minus_0.5"] - o["dbo"]), pct(s["salary_minus_0.5"])],
        ["Life expectancy +1 year", m(d["life_expectancy_plus_1"] - o["dbo"]), pct(s["life_expectancy_plus_1"])],
    ]
    return table(["Change in assumption", "Change in DBO (EUR m)", "%"], rows)


def table_7(o):
    e, p = o["expected_2026"], o["pl_2026"]
    rows = [["Weighted average duration of the DBO", f"{o['duration']:.1f} years"]]
    rows += [[f"Expected benefit payments {2026 + i}", m(v)] for i, v in enumerate(o["maturity_profile_10y"])]
    rows += [
        ["Expected employer contributions 2026", m(e["employer_contributions"])],
        ["Expected member contributions 2026", m(e["member_contributions"])],
        ["Expected employer service cost 2026", m(p["employer_service_cost"])],
        ["Expected net interest 2026", m(p["net_interest"])],
        ["Expected administration expenses 2026", m(p["admin_expenses"])],
        ["Expected P&L charge 2026", m(p["total"])],
    ]
    return table(["Item", "EUR m unless stated"], rows)


def aoc_tables(a):
    """Disclosure tables 2-4 from outputs/aoc_2025.json content (M8)."""
    L, A, pl, oci = a["dbo_reconciliation"], a["asset_reconciliation"], a["pl_2025"], a["oci_2025"]
    t2 = table(["Defined benefit obligation", "EUR m"], [
        ["At 1 January 2025", m(L["opening"])],
        ["Current service cost", m(L["service_cost"])],
        ["Interest cost", m(L["interest_cost"])],
        ["Benefits paid", m(L["benefits_paid"])],
        ["Remeasurement: experience (membership, salaries, inflation-linked)",
         m(L["membership"] + L["salaries"] + L["inflation_linked"])],
        ["Remeasurement: demographic assumptions", m(L["demographic"])],
        ["Remeasurement: financial assumptions (incl. curve roll-down)",
         m(L["roll_down"] + L["curve"] + L["inflation_assumption"] + L["other"])],
        ["At 31 December 2025", m(L["closing"])],
    ])
    t3 = table(["Plan assets", "EUR m"], [
        ["At 1 January 2025", m(A["opening"])],
        ["Interest income", m(A["interest_income"])],
        ["Return on plan assets excluding interest income", m(A["return_above_interest"])],
        ["Employer contributions", m(A["employer_contributions"])],
        ["Member contributions", m(A["member_contributions"])],
        ["Benefits paid", m(A["benefits_paid"])],
        ["Administration expenses", m(A["expenses"])],
        ["At 31 December 2025", m(A["closing"])],
    ])
    t4 = table(["Amounts recognised in 2025", "EUR m"], [
        ["Current service cost (net of member contributions)", m(pl["service_cost_net"])],
        ["Net interest on the net defined benefit liability", m(pl["net_interest"])],
        ["Administration expenses", m(pl["admin_expenses"])],
        ["Charge to profit or loss", m(pl["total"])],
        ["Remeasurement: experience", m(oci["experience"])],
        ["Remeasurement: demographic assumptions", m(oci["demographic"])],
        ["Remeasurement: financial assumptions", m(oci["financial"])],
        ["Return on plan assets excluding interest income", m(oci["return_on_assets_above_interest"])],
        ["Total recognised in other comprehensive income (negative = gain)", m(oci["total"])],
    ])
    return ["## 2. Reconciliation of the defined benefit obligation", t2,
            "## 3. Reconciliation of plan assets", t3,
            "## 4. Amounts recognised in profit or loss and other comprehensive income", t4]


def write(o, aoc=None):
    by = o["dbo_by_status"]
    parts = [
        "# IAS 19 disclosure note: Synthetic Scheme IE-1, 31 December 2025",
        f"> {DISCLAIMER}",
        "Amounts in EUR m unless stated. Generated by `python -m pension.pipeline` from `outputs/`.",
        "## Defined benefit obligation",
        table(["", "EUR m"], [["Actives", m(by["A"])], ["Deferreds", m(by["D"])], ["Pensioners", m(by["P"])],
                              ["Total DBO", m(o["dbo"])], ["Fair value of plan assets", m(o["assets"])],
                              ["Net defined benefit liability", m(o["net_liability"])]]),
        f"The scheme is in deficit, so the asset ceiling (IFRIC 14) does not restrict the amount recognised. "
        f"Assets: {o['assets_source']}.",
        "## 1. Principal actuarial assumptions",
        "The discount rate is based on the ECB euro area AAA government spot curve plus a constant AA spread "
        f"of {o['assumptions']['aa_spread'] * 100:.2f}% (an illustrative HQCB-consistent curve), applied year by year.",
        table_1(o),
    ]
    if aoc:
        parts += aoc
    else:
        parts += ["## 2-4. Reconciliations and amounts recognised", "Produced by the 2025 analysis of change (M8)."]
    parts += ["## 5. Asset allocation", table_5(o),
              "## 6. Sensitivity analysis", "One assumption changed at a time; life expectancy +1 year via a "
              f"uniform mortality multiplier k = {o['sensitivities']['k_life_expectancy_plus_1']:.3f}.", table_6(o),
              "## 7. Duration, maturity profile and 2026 expectations", table_7(o)]
    path = ROOT / "reports" / "disclosure_note.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n\n".join(parts) + "\n")
    return path
