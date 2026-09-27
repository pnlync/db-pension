"""Build validation/excel_checks.xlsx: three representative members valued in live Excel formulas (SPEC §9 M4-M6).

Only inputs (blue) and the Python results on the Check sheet are typed in; every other number is a formula,
so the workbook is an independent re-implementation of the cash-flow engine for one member of each status.
Run: uv run python -m pension.excel_build
"""
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from pension import benefits, cashflows
from pension.io import ROOT
from pension.mortality import MAX_AGE, extended_ilt15

OUT = ROOT / "validation" / "excel_checks.xlsx"
FIRST = 17            # row of t = 0 on member sheets; t = 1..100 below it
HORIZON = cashflows.HORIZON
LAST = FIRST + HORIZON
BLUE = Font(color="0000FF")
BOLD = Font(bold=True)
YELLOW = PatternFill("solid", fgColor="FFF2CC")


def put(ws, cell, value, font=None):
    ws[cell] = value
    if font:
        ws[cell].font = font


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


def build_curve(wb, discount_curve):
    """ECB AAA annual spot at each payment time t - 0.5 (published monthly tenors), plus the AA spread;
    beyond 30 years the last one-year forward is held flat (SPEC §7.1)."""
    ws = wb.create_sheet("Curve")
    ws.append(["t", "payment time", "AAA spot (annual) at payment time", "discount factor (AAA + spread)"])
    put(ws, "F1", "AA spread"); put(ws, "G1", discount_curve.spread, BLUE)
    put(ws, "F2", "AAA spot 29y"); put(ws, "G2", float(discount_curve.spots[discount_curve.tenors == 29][0]), BLUE)
    put(ws, "F3", "AAA spot 30y"); put(ws, "G3", float(discount_curve.spots[discount_curve.tenors == 30][0]), BLUE)
    put(ws, "F4", "DF 29y"); ws["G4"] = "=(1+G2+G1)^-29"
    put(ws, "F5", "DF 30y"); ws["G5"] = "=(1+G3+G1)^-30"
    put(ws, "F6", "forward 29-30y"); ws["G6"] = "=G4/G5-1"
    for t in range(1, HORIZON + 1):
        r = t + 1
        time = t - 0.5
        ws.cell(r, 1, t)
        ws.cell(r, 2, time)
        if time <= 30:
            ws.cell(r, 3, float(discount_curve.spots[np.isclose(discount_curve.tenors, time)][0])).font = BLUE
            ws.cell(r, 4, f"=(1+C{r}+$G$1)^-B{r}")
        else:
            ws.cell(r, 4, f"=$G$5*(1+$G$6)^-(B{r}-30)")


def build_inputs(wb, basis, flat_rate):
    ws = wb.active
    ws.title = "Inputs"
    mort = basis.mortality_post
    rows = [
        ("val_year", "Valuation year", basis.year),
        ("pi", "Inflation", basis.inflation),
        ("g", "Salary growth", basis.salary_growth),
        ("r", "Deferred revaluation (future years)", basis.revaluation),
        ("e", "Pension increase (future years)", basis.pension_increase),
        ("known_year", "Year of the known increase", min(basis.known_increases)),
        ("known_inc", "Known increase that year", basis.known_increases[min(basis.known_increases)]),
        ("spc1", "SPC in year 1 (annual)", basis.spc_next_year),
        ("offset", "SPC offset multiple", basis.rules["spc_offset_multiple"]),
        ("accrual", "Accrual fraction (1/..)", basis.rules["accrual_fraction"]),
        ("max_service", "Maximum service", basis.rules["max_service_years"]),
        ("mult_M", "Mortality multiplier M", mort.multiplier["M"]),
        ("mult_F", "Mortality multiplier F", mort.multiplier["F"]),
        ("imp", "Mortality improvement", mort.improvement),
        ("imp_base", "Improvement base year", mort.base_year),
        ("w35", "Withdrawal rate at 35", 0.04),
        ("wslope", "Withdrawal slope per year", 0.002),
        ("wzero", "Withdrawal zero from age", 55),
        ("flat", "Flat discount rate (engine check)", flat_rate),
    ]
    ws.append(["key", "input", "value"])
    names = {}
    for i, (key, label, value) in enumerate(rows, start=2):
        ws.append([key, label, value])
        ws.cell(i, 3).font = BLUE
        names[key] = f"Inputs!$C${i}"
    return names


def q_formula(n, age_cell, year_cell, sex_cell):
    ilt = f"INDEX(ILT!$B$2:$C${MAX_AGE + 2},MIN({age_cell},{MAX_AGE})+1,IF({sex_cell}=\"M\",1,2))"
    mult = f"IF({sex_cell}=\"M\",{n['mult_M']},{n['mult_F']})"
    return (f"=IF({age_cell}>={MAX_AGE},1,MIN(1,{mult}*{ilt}*(1-{n['imp']})^MAX({year_cell}-{n['imp_base']},0)))")


def member_header(ws, title, member, extra):
    put(ws, "A1", title, BOLD)
    put(ws, "A3", "member_id"); put(ws, "B3", member.member_id, BLUE)
    put(ws, "A4", "sex"); put(ws, "B4", member.sex, BLUE)
    put(ws, "A5", "age x (nearest, at valuation)"); put(ws, "B5", int(member.age), BLUE)
    put(ws, "A6", "T (years to 65)"); put(ws, "B6", int(member["T"]), BLUE)
    for i, (label, value, font) in enumerate(extra, start=7):
        put(ws, f"A{i}", label)
        put(ws, f"B{i}", value, font)


def table_header(ws, columns):
    for j, name in enumerate(columns, start=1):
        ws.cell(FIRST - 1, j, name).font = BOLD


def common_columns(ws, n, r):
    """A t, B year, C age at start of year, D q, E survival, F average survival, I discount factor."""
    t, prev = r - FIRST, r - 1
    ws[f"A{r}"] = t
    if t == 0:
        ws[f"E{r}"] = 1
        return
    ws[f"B{r}"] = f"={n['val_year']}+A{r}"
    ws[f"C{r}"] = f"=$B$5+A{r}-1"
    ws[f"D{r}"] = q_formula(n, f"C{r}", f"B{r}", "$B$4")
    ws[f"E{r}"] = f"=E{prev}*(1-D{r})"
    ws[f"F{r}"] = f"=(E{prev}+E{r})/2"
    ws[f"I{r}"] = f"=(1+{n['flat']})^-(A{r}-0.5)"
    ws[f"J{r}"] = f"=H{r}*I{r}"
    ws[f"K{r}"] = f"=H{r}*INDEX(Curve!$D$2:$D${HORIZON + 1},A{r})"


def increase(n, r):
    return f"(1+IF(B{r}={n['known_year']},{n['known_inc']},{n['e']}))"


def build_pensioner(wb, n, m):
    ws = wb.create_sheet("Pensioner")
    member_header(ws, "Pensioner: P x increases x average survival, paid mid-year", m,
                  [("pension in payment (2025)", float(m.pension), BLUE)])
    table_header(ws, ["t", "year", "age", "q", "survival", "avg survival", "pension index", "cash flow", "DF", "PV", "PV curve"])
    for r in range(FIRST, LAST + 1):
        common_columns(ws, n, r)
        if r == FIRST:
            ws[f"G{r}"] = 1
            continue
        ws[f"G{r}"] = f"=G{r - 1}*{increase(n, r)}"
        ws[f"H{r}"] = f"=$B$7*G{r}*F{r}"
    ws["D3"], ws["E3"] = "PV (flat rate)", f"=SUM(J{FIRST + 1}:J{LAST})"
    ws["D4"], ws["E4"] = "PV (IAS 19 curve)", f"=SUM(K{FIRST + 1}:K{LAST})"
    return "Pensioner"


def build_deferred(wb, n, m, first_rev_year, val_year):
    ws = wb.create_sheet("Deferred")
    left = m.date_left
    member_header(ws, "Deferred: pension at exit, official revaluation to the valuation year, then r a year to 65", m, [
        ("pension at exit", float(m.deferred_pension_at_exit), BLUE),
        ("exit year", left.year, BLUE),
        ("exit month", left.month, BLUE),
        ("exit day", left.day, BLUE),
        ("complete months to 31 Dec", "=12-B9+IF(B10=1,1,0)", None),
        ("revaluation factor to valuation year", None, None),
        ("pension at valuation date", "=B7*B12", None),
        ("pension at 65 (B65)", f"=B13*(1+{n['r']})^B6", None),
    ])
    # revaluation block in columns L:M, one row per year from the exit year to the valuation year
    put(ws, "L16", "rev. year", BOLD); put(ws, "M16", "factor", BOLD)
    for k, year in enumerate(range(left.year, val_year + 1)):
        r = 17 + k
        ws[f"L{r}"] = year
        pct = f"INDEX(Revaluation!$B:$B,L{r}-{first_rev_year}+2)/100"
        ws[f"M{r}"] = f"=1+{pct}*$B$11/12" if k == 0 else f"=M{r - 1}*(1+{pct})"
        last = r
    ws["B12"] = f"=M{last}"
    table_header(ws, ["t", "year", "age", "q", "survival", "avg survival", "pension index", "cash flow", "DF", "PV", "PV curve"])
    for r in range(FIRST, LAST + 1):
        common_columns(ws, n, r)
        if r == FIRST:
            ws[f"G{r}"] = 0
            continue
        ws[f"G{r}"] = f"=IF(A{r}<$B$6+1,0,IF(A{r}=$B$6+1,1,G{r - 1}*{increase(n, r)}))"
        ws[f"H{r}"] = f"=$B$14*G{r}*F{r}"
    ws["D3"], ws["E3"] = "PV (flat rate)", f"=SUM(J{FIRST + 1}:J{LAST})"
    ws["D4"], ws["E4"] = "PV (IAS 19 curve)", f"=SUM(K{FIRST + 1}:K{LAST})"
    return "Deferred"


def build_active(wb, n, m):
    ws = wb.create_sheet("Active")
    member_header(ws, "Active: withdraw (deferred pension) / die (nothing) / retire at 65, past service only (PUC)", m, [
        ("service n (years)", float(m.service), BLUE),
        ("salary (2025)", float(m.salary), BLUE),
        ("salary at 65", f"=B8*(1+{n['g']})^B6", None),
        ("SPC at 65", f"={n['spc1']}*(1+{n['pi']})^(B6-1)", None),
        ("retirement pension R", f"=MIN(B7,{n['max_service']})/{n['accrual']}*MAX(B9-{n['offset']}*B10,0)", None),
        ("K = sum of leaver terms + in service at 65 x R / s(T)", None, None),
    ])
    table_header(ws, ["t", "year", "age", "q", "survival", "avg survival", "pension index", "cash flow", "DF", "PV",
                      "PV curve", "q death", "q withdraw", "in service", "leavers", "salary", "SPC", "B at exit",
                      "B65", "leaver term"])
    for r in range(FIRST, LAST + 1):
        common_columns(ws, n, r)
        t = r - FIRST
        if t == 0:
            ws[f"G{r}"] = 0
            ws[f"N{r}"] = 1
            continue
        ws[f"G{r}"] = f"=IF(A{r}<$B$6+1,0,IF(A{r}=$B$6+1,1,G{r - 1}*{increase(n, r)}))"
        ws[f"H{r}"] = f"=$B$12*G{r}*F{r}"
        ws[f"L{r}"] = f"=IF(A{r}<=$B$6,1-E{r}/E{r - 1},0)"
        ws[f"M{r}"] = (f"=IF(A{r}<=$B$6,IF(C{r}<{n['wzero']},MAX(0,{n['w35']}-{n['wslope']}*(C{r}-35)),0),0)")
        ws[f"N{r}"] = f"=N{r - 1}*(1-L{r}-M{r})"
        ws[f"O{r}"] = f"=N{r - 1}*M{r}"
        ws[f"P{r}"] = f"=$B$8*(1+{n['g']})^A{r}"
        ws[f"Q{r}"] = f"={n['spc1']}*(1+{n['pi']})^(A{r}-1)"
        ws[f"R{r}"] = f"=MIN($B$7,{n['max_service']})/{n['accrual']}*MAX(P{r}-{n['offset']}*Q{r},0)"
        ws[f"S{r}"] = f"=R{r}*(1+{n['r']}*0.5)*(1+{n['r']})^($B$6-A{r})"
        ws[f"T{r}"] = f"=IF(A{r}<=$B$6,O{r}*(1-L{r}/2)*S{r}/E{r},0)"
    ws["B12"] = (f"=SUM(T{FIRST + 1}:T{LAST})+INDEX(N{FIRST}:N{LAST},$B$6+1)*B11/INDEX(E{FIRST}:E{LAST},$B$6+1)")
    ws["D3"], ws["E3"] = "PV (flat rate)", f"=SUM(J{FIRST + 1}:J{LAST})"
    ws["D4"], ws["E4"] = "PV (IAS 19 curve)", f"=SUM(K{FIRST + 1}:K{LAST})"
    return "Active"


def representative_members(members):
    """One member of each status: a male pensioner in his 70s, a deferred in her 50s, an active in his 40s."""
    pick = {
        "Pensioner": members[(members.status == "P") & (members.sex == "M") & members.age.between(70, 75)],
        "Deferred": members[(members.status == "D") & (members.sex == "F") & members.age.between(50, 55)],
        "Active": members[(members.status == "A") & (members.sex == "M") & members.age.between(42, 47)],
    }
    return {k: v.iloc[0] for k, v in pick.items()}


def build(members, basis, flat_rate, discount_curve, path=OUT):
    wb = Workbook()
    n = build_inputs(wb, basis, flat_rate)
    build_curve(wb, discount_curve)
    build_ilt(wb)
    first_rev_year = build_revaluation(wb, basis.revaluation_history)
    reps = representative_members(members)
    cells = {
        "Pensioner": build_pensioner(wb, n, reps["Pensioner"]),
        "Deferred": build_deferred(wb, n, reps["Deferred"], first_rev_year, basis.year),
        "Active": build_active(wb, n, reps["Active"]),
    }
    ws = wb.create_sheet("Check", 1)
    ws.append(["member", "member_id", "Python PV (flat rate)", "Excel PV (flat rate)", "difference",
               "Python PV (IAS 19 curve)", "Excel PV (IAS 19 curve)", "difference"])
    for i, (label, sheet) in enumerate(cells.items(), start=2):
        m = reps[label]
        cf = cashflows.project_cashflows(members[members.member_id == m.member_id], basis)
        flat_pv = float(cashflows.pv(cf, cashflows_flat(flat_rate))[0])
        curve_pv = float(cashflows.pv(cf, discount_curve)[0])
        ws.append([label, m.member_id, flat_pv, f"={sheet}!E3", f"=D{i}-C{i}", curve_pv, f"={sheet}!E4", f"=G{i}-F{i}"])
        ws[f"C{i}"].fill = YELLOW
        ws[f"F{i}"].fill = YELLOW
    path.parent.mkdir(exist_ok=True)
    wb.save(path)
    return {"path": path, "members": {k: v.member_id for k, v in reps.items()}}


def cashflows_flat(rate):
    from pension.curves import FlatRate
    return FlatRate(rate)
