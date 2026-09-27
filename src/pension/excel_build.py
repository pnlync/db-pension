"""Build validation/excel_checks.xlsx: three representative members valued in live Excel formulas (SPEC §9 M4-M6).

Only inputs (blue) and the Python results on the Check sheet are typed in; every other number is a formula, so the
workbook is an independent re-implementation of the engine for one member of each status, on three bases:
IAS 19 (curve), Section 34 transfer values (non-pensioners) and the annuity cost proxy (pensioners).
"""
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from pension import cashflows, funding_standard, mva
from pension.curves import FlatRate
from pension.io import ROOT
from pension.mortality import MAX_AGE, extended_ilt15

OUT = ROOT / "validation" / "excel_checks.xlsx"
FIRST = 18            # row of t = 0 on member sheets; t = 1..100 below it
HORIZON = cashflows.HORIZON
LAST = FIRST + HORIZON
BLUE = Font(color="0000FF")
BOLD = Font(bold=True)
YELLOW = PatternFill("solid", fgColor="FFF2CC")
TABLE = ["t", "year", "age", "q", "survival", "avg survival", "pension index", "cash flow", "DF 1", "PV 1", "PV 2"]


def put(ws, cell, value, font=None):
    ws[cell] = value
    if font:
        ws[cell].font = font


# --- shared sheets -------------------------------------------------------------------------------

def build_ilt(wb):
    ws = wb.create_sheet("ILT")
    ws.append(["age", "q_M (ILT15, extended to 120)", "q_F"])
    table = extended_ilt15()
    for age in range(MAX_AGE + 1):
        ws.append([age, float(table["M"][age]), float(table["F"][age])])


def build_revaluation(wb, history):
    ws = wb.create_sheet("Revaluation")
    ws.append(["revaluation year", "official %"])
    for year, pct in history.items():
        ws.append([int(year), float(pct)])
    return int(history.index.min())


def build_curve(wb, name, discount_curve):
    """AAA annual spot at each payment time t - 0.5 (ECB monthly tenors, no interpolation) plus the spread;
    beyond 30 years the last one-year forward is held flat (SPEC §7.1)."""
    ws = wb.create_sheet(name)
    ws.append(["t", "payment time", "AAA spot (annual) at payment time", "discount factor (AAA + spread)"])
    tenors, spots = discount_curve.tenors, discount_curve.spots
    put(ws, "F1", "spread"); put(ws, "G1", discount_curve.spread, BLUE)
    put(ws, "F2", "AAA spot 29y"); put(ws, "G2", float(spots[np.isclose(tenors, 29)][0]), BLUE)
    put(ws, "F3", "AAA spot 30y"); put(ws, "G3", float(spots[np.isclose(tenors, 30)][0]), BLUE)
    put(ws, "F4", "DF 29y"); ws["G4"] = "=(1+G2+G1)^-29"
    put(ws, "F5", "DF 30y"); ws["G5"] = "=(1+G3+G1)^-30"
    put(ws, "F6", "forward 29-30y"); ws["G6"] = "=G4/G5-1"
    for t in range(1, HORIZON + 1):
        r, time = t + 1, t - 0.5
        ws.cell(r, 1, t)
        ws.cell(r, 2, time)
        if time <= 30:
            ws.cell(r, 3, float(spots[np.isclose(tenors, time)][0])).font = BLUE
            ws.cell(r, 4, f"=(1+C{r}+$G$1)^-B{r}")
        else:
            ws.cell(r, 4, f"=$G$5*(1+$G$6)^-(B{r}-30)")


def build_inputs(wb, sheet, basis, extra=()):
    ws = wb.create_sheet(sheet)
    pre, post = basis.mortality_pre, basis.mortality_post
    known_year = min(basis.known_increases) if basis.known_increases else 0
    loading = basis.annuity_loading or {"M": 0.0, "F": 0.0, "base_year": 2014}
    rows = [
        ("val_year", "Valuation year", basis.year),
        ("pi", "Inflation", basis.inflation),
        ("g", "Salary growth", basis.salary_growth),
        ("r", "Deferred revaluation (future years)", basis.revaluation),
        ("e", "Pension increase (future years)", basis.pension_increase),
        ("known_year", "Year of the known increase (0 = none)", known_year),
        ("known_inc", "Known increase that year", basis.known_increases.get(known_year, 0.0)),
        ("spc1", "SPC in year 1 (annual)", basis.spc_next_year),
        ("offset", "SPC offset multiple", basis.rules["spc_offset_multiple"]),
        ("accrual", "Accrual fraction (1/..)", basis.rules["accrual_fraction"]),
        ("max_service", "Maximum service", basis.rules["max_service_years"]),
        ("pre_M", "Mortality multiplier before 65, M", pre.multiplier["M"]),
        ("pre_F", "Mortality multiplier before 65, F", pre.multiplier["F"]),
        ("post_M", "Mortality multiplier from 65, M", post.multiplier["M"]),
        ("post_F", "Mortality multiplier from 65, F", post.multiplier["F"]),
        ("imp", "Mortality improvement", post.improvement),
        ("imp_base", "Improvement base year", post.base_year),
        ("w_on", "Withdrawal decrement on (1/0)", 1 if basis.withdrawal else 0),
        ("w35", "Withdrawal rate at 35", 0.04),
        ("wslope", "Withdrawal slope per year", 0.002),
        ("wzero", "Withdrawal zero from age", 55),
        ("load_M", "Annuity value loading a year, M", loading["M"]),
        ("load_F", "Annuity value loading a year, F", loading["F"]),
        ("load_base", "Loading base year", loading["base_year"]),
    ] + list(extra)
    ws.append(["key", "input", "value"])
    names = {}
    for i, (key, label, value) in enumerate(rows, start=2):
        ws.append([key, label, value])
        ws.cell(i, 3).font = BLUE
        names[key] = f"{sheet}!$C${i}"
    return names


# --- member sheets ---------------------------------------------------------------------------------

def q_formula(n, r):
    """q for the age at the start of year t: pre-retirement multiplier for t <= T, post after."""
    ilt = f"INDEX(ILT!$B$2:$C${MAX_AGE + 2},MIN(C{r},{MAX_AGE})+1,IF($B$4=\"M\",1,2))"
    mult = (f"IF(A{r}<=$B$6,IF($B$4=\"M\",{n['pre_M']},{n['pre_F']}),"
            f"IF($B$4=\"M\",{n['post_M']},{n['post_F']}))")
    return f"=IF(C{r}>={MAX_AGE},1,MIN(1,{mult}*{ilt}*(1-{n['imp']})^MAX(B{r}-{n['imp_base']},0)))"


def member_header(ws, title, member, extra):
    put(ws, "A1", title, BOLD)
    put(ws, "A3", "member_id"); put(ws, "B3", member.member_id, BLUE)
    put(ws, "A4", "sex"); put(ws, "B4", member.sex, BLUE)
    put(ws, "A5", "age x (nearest, at valuation)"); put(ws, "B5", int(member.age), BLUE)
    put(ws, "A6", "T (years to 65)"); put(ws, "B6", int(member["T"]), BLUE)
    for i, (label, value, font) in enumerate(extra, start=7):
        put(ws, f"A{i}", label)
        put(ws, f"B{i}", value, font)


def increase(n, r):
    return f"(1+IF(B{r}={n['known_year']},{n['known_inc']},{n['e']}))"


def loading(n):
    return f"(1+IF($B$4=\"M\",{n['load_M']},{n['load_F']}))^MAX({n['val_year']}+$B$6-{n['load_base']},0)"


def table_rows(ws, n, df1, df2, amount_cell, starts_at_retirement):
    """Columns A-K for t = 0..100. df1/df2: formulas (with {r}) for the discount factor of PV 1 / PV 2."""
    for j, name in enumerate(TABLE, start=1):
        ws.cell(FIRST - 1, j, name).font = BOLD
    for r in range(FIRST, LAST + 1):
        t, prev = r - FIRST, r - 1
        ws[f"A{r}"] = t
        if t == 0:
            ws[f"E{r}"] = 1
            ws[f"G{r}"] = 0 if starts_at_retirement else 1
            continue
        ws[f"B{r}"] = f"={n['val_year']}+A{r}"
        ws[f"C{r}"] = f"=$B$5+A{r}-1"
        ws[f"D{r}"] = q_formula(n, r)
        ws[f"E{r}"] = f"=E{prev}*(1-D{r})"
        ws[f"F{r}"] = f"=(E{prev}+E{r})/2"
        if starts_at_retirement:
            ws[f"G{r}"] = f"=IF(A{r}<$B$6+1,0,IF(A{r}=$B$6+1,1,G{prev}*{increase(n, r)}))"
        else:
            ws[f"G{r}"] = f"=G{prev}*{increase(n, r)}"
        ws[f"H{r}"] = f"={amount_cell}*G{r}*F{r}"
        ws[f"I{r}"] = "=" + df1.format(r=r)
        ws[f"J{r}"] = f"=H{r}*I{r}"
        ws[f"K{r}"] = f"=H{r}*" + df2.format(r=r) if df2 else None


def curve_df(sheet):
    return f"INDEX({sheet}!$D$2:$D${HORIZON + 1},A{{r}})"


def s34_df(n):
    return (f"(1+{n['d_pre']})^-MIN(A{{r}}-0.5,$B$6)*(1+{n['d_post']})^-MAX(A{{r}}-0.5-$B$6,0)")


def pensioner_sheet(wb, name, n, m, df1, df2):
    ws = wb.create_sheet(name)
    member_header(ws, f"{name}: P x increases x average survival, paid mid-year", m,
                  [("pension in payment (2025)", float(m.pension), BLUE)])
    table_rows(ws, n, df1, df2, "$B$7", starts_at_retirement=False)
    return ws


def deferred_sheet(wb, name, n, m, first_rev_year, val_year, df1, df2):
    ws = wb.create_sheet(name)
    left = m.date_left
    member_header(ws, f"{name}: pension at exit, official revaluation to the valuation year, then r a year to 65", m, [
        ("pension at exit", float(m.deferred_pension_at_exit), BLUE),
        ("exit year", left.year, BLUE),
        ("exit month", left.month, BLUE),
        ("exit day", left.day, BLUE),
        ("complete months to 31 Dec", "=12-B9+IF(B10=1,1,0)", None),
        ("revaluation factor to valuation year", None, None),
        ("pension at valuation date", "=B7*B12", None),
        ("pension at 65 x loading", f"=B13*(1+{n['r']})^B6*{loading(n)}", None),
    ])
    put(ws, "M16", "rev. year", BOLD); put(ws, "N16", "factor", BOLD)
    for k, year in enumerate(range(left.year, val_year + 1)):
        r = 17 + k
        ws[f"M{r}"] = year
        pct = f"INDEX(Revaluation!$B:$B,M{r}-{first_rev_year}+2)/100"
        ws[f"N{r}"] = f"=1+{pct}*$B$11/12" if k == 0 else f"=N{r - 1}*(1+{pct})"
        last = r
    ws["B12"] = f"=N{last}"
    table_rows(ws, n, df1, df2, "$B$14", starts_at_retirement=True)
    return ws


def leaver_today_sheet(wb, name, n, m, df1):
    ws = wb.create_sheet(name)
    member_header(ws, f"{name}: active treated as leaving at the valuation date (Funding Standard)", m, [
        ("service n (years)", float(m.service), BLUE),
        ("salary (2025)", float(m.salary), BLUE),
        ("pension if leaving today", f"=MIN(B7,{n['max_service']})/{n['accrual']}*MAX(B8-{n['offset']}*{n['spc1']},0)", None),
        ("pension at 65 x loading", f"=B9*(1+{n['r']})^B6*{loading(n)}", None),
    ])
    table_rows(ws, n, df1, None, "$B$10", starts_at_retirement=True)
    return ws


def active_sheet(wb, name, n, m, df1, df2):
    ws = wb.create_sheet(name)
    member_header(ws, f"{name}: withdraw (deferred pension) / die (nothing) / retire at 65; past service only (PUC)", m, [
        ("service n (years)", float(m.service), BLUE),
        ("salary (2025)", float(m.salary), BLUE),
        ("salary at 65", f"=B8*(1+{n['g']})^B6", None),
        ("SPC at 65", f"={n['spc1']}*(1+{n['pi']})^(B6-1)", None),
        ("retirement pension R", f"=MIN(B7,{n['max_service']})/{n['accrual']}*MAX(B9-{n['offset']}*B10,0)", None),
        ("K = leaver terms + in service at 65 x R / s(T)", None, None),
    ])
    table_rows(ws, n, df1, df2, "$B$12", starts_at_retirement=True)
    for j, name_ in enumerate(["q death", "q withdraw", "in service", "leavers", "salary", "SPC", "B at exit", "B65",
                               "leaver term"], start=13):
        ws.cell(FIRST - 1, j, name_).font = BOLD
    ws[f"O{FIRST}"] = 1
    for r in range(FIRST + 1, LAST + 1):
        ws[f"M{r}"] = f"=IF(A{r}<=$B$6,1-E{r}/E{r - 1},0)"
        ws[f"N{r}"] = (f"=IF(A{r}<=$B$6,{n['w_on']}*IF(C{r}<{n['wzero']},MAX(0,{n['w35']}-{n['wslope']}*(C{r}-35)),0),0)")
        ws[f"O{r}"] = f"=O{r - 1}*(1-M{r}-N{r})"
        ws[f"P{r}"] = f"=O{r - 1}*N{r}"
        ws[f"Q{r}"] = f"=$B$8*(1+{n['g']})^A{r}"
        ws[f"R{r}"] = f"={n['spc1']}*(1+{n['pi']})^(A{r}-1)"
        ws[f"S{r}"] = f"=MIN($B$7,{n['max_service']})/{n['accrual']}*MAX(Q{r}-{n['offset']}*R{r},0)"
        ws[f"T{r}"] = f"=S{r}*(1+{n['r']}*0.5)*(1+{n['r']})^($B$6-A{r})"
        ws[f"U{r}"] = f"=IF(A{r}<=$B$6,P{r}*(1-M{r}/2)*T{r}/E{r},0)"
    ws["B12"] = (f"=SUM(U{FIRST + 1}:U{LAST})+INDEX(O{FIRST}:O{LAST},$B$6+1)*B11/INDEX(E{FIRST}:E{LAST},$B$6+1)")
    return ws


def totals(ws, labels):
    """Put the PV totals in D3:E5."""
    cols = {"PV 1": "J", "PV 2": "K"}
    for i, (label, col) in enumerate(labels, start=3):
        ws[f"D{i}"] = label
        ws[f"E{i}"] = f"=SUM({cols[col]}{FIRST + 1}:{cols[col]}{LAST})"


def tv_block(ws, n):
    """Section 34: TV = PV (6% / 4.25%) x MVA_pre(T) x MVA_post(T)."""
    ws["D4"], ws["E4"] = "MVA pre", (f"=((1+{n['d_pre']})/(1+{n['d_post']}+MIN($B$6,{n['window']})/{n['t_div']}"
                                     f"*({n['d_pre']}-{n['d_post']})))^MIN($B$6,{n['window']})")
    ws["D5"], ws["E5"] = "MVA post", f"=IF($B$6<={n['window']},{n['mva_npa']}*({n['window']}-$B$6)/{n['window']}+$B$6/{n['window']},1)"
    ws["D6"], ws["E6"] = "Transfer value", "=E3*E4*E5"


# --- the workbook ----------------------------------------------------------------------------------------

def representative_members(members):
    """A male pensioner in his 70s, a deferred woman in her 50s, an active man in his 40s."""
    pick = {
        "Pensioner": members[(members.status == "P") & (members.sex == "M") & members.age.between(70, 75)],
        "Deferred": members[(members.status == "D") & (members.sex == "F") & members.age.between(50, 55)],
        "Active": members[(members.status == "A") & (members.sex == "M") & members.age.between(42, 47)],
    }
    return {k: v.iloc[0] for k, v in pick.items()}


def build(members, basis, flat_rate, discount_curve, path=OUT, valuation_date=None):
    valuation_date = valuation_date or basis.valuation_date
    wb = Workbook()
    wb.remove(wb.active)
    check = wb.create_sheet("Check")
    n = build_inputs(wb, "Inputs_IAS19", basis, [("flat", "Flat discount rate (engine check)", flat_rate)])
    s34_basis = funding_standard.s34_basis(valuation_date)
    s34 = mva.params()
    mva_npa = funding_standard.mva_npa_at(valuation_date)
    ns = build_inputs(wb, "Inputs_S34", s34_basis, [
        ("d_pre", "Discount rate before 65", s34["discount_pre_retirement"]),
        ("d_post", "Discount rate after 65", s34["discount_post_retirement"]),
        ("window", "MVA window (years)", s34["mva"]["window_years"]),
        ("t_div", "Pre-retirement MVA divisor", s34["mva"]["pre_retirement_T_divisor"]),
        ("mva_npa", "MVA at NPA, index-linked (Nov 2025)", mva_npa)])
    ann_basis = funding_standard.annuity_basis(valuation_date)
    na = build_inputs(wb, "Inputs_Annuity", ann_basis)
    build_ilt(wb)
    first_rev_year = build_revaluation(wb, basis.revaluation_history)
    build_curve(wb, "Curve_IAS19", discount_curve)
    ann_curve = funding_standard.annuity_curve(valuation_date)
    build_curve(wb, "Curve_Annuity", ann_curve)
    reps = representative_members(members)
    flat = f"(1+{n['flat']})^-(A{{r}}-0.5)"

    ws = pensioner_sheet(wb, "Pensioner", n, reps["Pensioner"], flat, curve_df("Curve_IAS19"))
    totals(ws, [("PV (flat rate)", "PV 1"), ("PV (IAS 19 curve)", "PV 2")])
    ws = deferred_sheet(wb, "Deferred", n, reps["Deferred"], first_rev_year, basis.year, flat, curve_df("Curve_IAS19"))
    totals(ws, [("PV (flat rate)", "PV 1"), ("PV (IAS 19 curve)", "PV 2")])
    ws = active_sheet(wb, "Active", n, reps["Active"], flat, curve_df("Curve_IAS19"))
    totals(ws, [("PV (flat rate)", "PV 1"), ("PV (IAS 19 curve)", "PV 2")])
    ws = pensioner_sheet(wb, "FS_Pensioner", na, reps["Pensioner"], curve_df("Curve_Annuity"), None)
    totals(ws, [("Annuity cost (AAA + insurer spread)", "PV 1")])
    ws = deferred_sheet(wb, "FS_Deferred", ns, reps["Deferred"], first_rev_year, basis.year, s34_df(ns), None)
    totals(ws, [("PV at 6% / 4.25%", "PV 1")])
    tv_block(ws, ns)
    ws = leaver_today_sheet(wb, "FS_Active", ns, reps["Active"], s34_df(ns))
    totals(ws, [("PV at 6% / 4.25%", "PV 1")])
    tv_block(ws, ns)

    # Python results for the same members
    python = {}
    for label, m in reps.items():
        one = members[members.member_id == m.member_id]
        cf = cashflows.project_cashflows(one, basis)
        python[label] = (float(cashflows.pv(cf, FlatRate(flat_rate))[0]), float(cashflows.pv(cf, discount_curve)[0]))
    fs_python = {
        "FS_Pensioner": float(funding_standard.annuity_costs(members[members.member_id == reps["Pensioner"].member_id],
                                                           ann_basis, ann_curve)[0][0]),
        "FS_Deferred": float(funding_standard.transfer_values(members[members.member_id == reps["Deferred"].member_id],
                                                            s34_basis, mva_npa)[0][0]),
        "FS_Active": float(funding_standard.transfer_values(members[members.member_id == reps["Active"].member_id],
                                                          s34_basis, mva_npa)[0][0]),
    }
    check.append(["sheet", "member_id", "measure", "Python", "Excel (formulas)", "difference"])
    rows = []
    for label in ("Pensioner", "Deferred", "Active"):
        rows.append((label, reps[label].member_id, "PV at flat rate", python[label][0], f"={label}!E3"))
        rows.append((label, reps[label].member_id, "IAS 19 PV (curve)", python[label][1], f"={label}!E4"))
    rows.append(("FS_Pensioner", reps["Pensioner"].member_id, "FS annuity cost", fs_python["FS_Pensioner"], "=FS_Pensioner!E3"))
    rows.append(("FS_Deferred", reps["Deferred"].member_id, "FS transfer value", fs_python["FS_Deferred"], "=FS_Deferred!E6"))
    rows.append(("FS_Active", reps["Active"].member_id, "FS transfer value", fs_python["FS_Active"], "=FS_Active!E6"))
    for i, row in enumerate(rows, start=2):
        check.append(list(row) + [f"=E{i}-D{i}"])
        check[f"D{i}"].fill = YELLOW
    path.parent.mkdir(exist_ok=True)
    wb.save(path)
    return {"path": path, "rows": len(rows), "members": {k: v.member_id for k, v in reps.items()}}
