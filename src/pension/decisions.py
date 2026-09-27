"""M10 decisions (SPEC §9 M10): deterministic funding projection, the deficit contribution that restores
FS + FSR, and the equity-to-long-sovereign switch.

Projection: yields held at 2025-12-31 levels; members age with the IAS 19 best-estimate decrements and
inflation; actives keep accruing; each year every expected record (weighted by its probability) is revalued
on the Funding Standard basis, and the FSR is recalculated.
"""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from pension import assets, benefits, cashflows, funding_standard as fs, ias19
from pension.io import load_config, statutory_revaluation

V1 = date(2025, 12, 31)
EXIT_MONTH_DAY = (7, 1)       # projected withdrawals at mid-year


def projection_basis():
    """Best-estimate demographics and inflation for projecting the membership (IAS 19 closing basis)."""
    return ias19.basis(V1)


def extended_history(b):
    """Official revaluation to 2025, then the assumed rate (in %) for later years."""
    h = statutory_revaluation().copy()
    for year in range(V1.year + 1, V1.year + 101):
        h[year] = b.revaluation * 100
    return h


def increase_index(b, n):
    """Pension increase index from the valuation year to year n (1 January increases 2026..2025+n)."""
    level = 1.0
    for t in range(1, n + 1):
        level *= 1 + cashflows.increase_rate(b, V1.year + t)
    return level


def record(member_id, status, sex, age, T, service=np.nan, salary=np.nan, pension=np.nan, b_exit=np.nan,
           left=None, weight=1.0):
    return {"member_id": member_id, "status": status, "sex": sex, "age": age, "T": T, "service": service,
            "salary": salary, "pension": pension, "deferred_pension_at_exit": b_exit, "date_left": left,
            "weight": weight}


def project_membership(members, n, b, history):
    """Expected membership at the end of year n as weighted records (engine columns + weight)."""
    H = cashflows.HORIZON
    s_all = cashflows.survival_split(b, members.age.to_numpy(), members.sex.to_numpy(), members["T"].to_numpy(), H)
    rows = []
    rules = b.rules
    for i, m in enumerate(members.itertuples(index=False)):
        s = s_all[i]
        age_n = m.age + n
        if m.status == "P":
            rows.append(record(m.member_id, "P", m.sex, age_n, 0, pension=m.pension * increase_index(b, n), weight=s[n]))
        elif m.status == "D":
            T0 = m.T
            if n <= T0:
                rows.append(record(m.member_id, "D", m.sex, age_n, T0 - n, b_exit=m.deferred_pension_at_exit,
                                   left=m.date_left, weight=s[n]))
            else:
                b65 = m.deferred_pension_at_exit * benefits.revaluation_factor(m.date_left, V1.year + T0, history)
                level = b65 * increase_index_from(b, T0 + 1, n)
                rows.append(record(m.member_id, "P", m.sex, age_n, 0, pension=level, weight=s[n]))
        else:
            rows += project_active(m, s, n, b, rules, history)
    return pd.DataFrame(rows)


def increase_index_from(b, first_year, n):
    """Pension that started (level 1) in year first_year, after increases up to year n."""
    level = 1.0
    for t in range(first_year + 1, n + 1):
        level *= 1 + cashflows.increase_rate(b, V1.year + t)
    return level


def salary_in(m, t, b):
    return m.salary * (1 + b.salary_growth) ** t


def spc_in(t, b):
    return b.spc_next_year * (1 + b.inflation) ** (t - 1)


def project_active(m, s, n, b, rules, history):
    """In service at n (with future accrual), leavers in years 1..n as deferreds, retirement at T0."""
    T0 = m.T
    rows = []
    in_service = 1.0
    for k in range(1, min(n, T0) + 1):
        q_d = 1 - s[k] / s[k - 1]
        q_w = float(b.withdrawal(m.age + k - 1)) if b.withdrawal else 0.0
        leavers = in_service * q_w
        in_service -= in_service * (q_d + q_w)
        if leavers > 0:
            service = m.service + k - 0.5
            b_exit = benefits.accrued_pension(service, salary_in(m, k, b), spc_in(k, b), rules)
            left = date(V1.year + k, *EXIT_MONTH_DAY)
            weight = leavers * (1 - q_d / 2) * s[n] / s[k]
            if n <= T0:
                rows.append(record(m.member_id, "D", m.sex, m.age + n, T0 - n, b_exit=b_exit, left=left, weight=weight))
            else:
                b65 = b_exit * benefits.revaluation_factor(left, V1.year + T0, history)
                rows.append(record(m.member_id, "P", m.sex, m.age + n, 0,
                                   pension=b65 * increase_index_from(b, T0 + 1, n), weight=weight))
    if n < T0:
        rows.append(record(m.member_id, "A", m.sex, m.age + n, T0 - n, service=m.service + n,
                           salary=salary_in(m, n, b), weight=in_service))
    else:
        pension = benefits.accrued_pension(m.service + T0, salary_in(m, T0, b), spc_in(T0, b), rules)
        if n > T0:
            pension *= increase_index_from(b, T0 + 1, n)
            rows.append(record(m.member_id, "P", m.sex, m.age + n, 0, pension=pension, weight=in_service * s[n] / s[T0]))
        else:
            rows.append(record(m.member_id, "P", m.sex, m.age + n, 0, pension=pension, weight=in_service))
    return rows


# --- Funding Standard at a future date, yields unchanged ---------------------------------------------

@dataclass
class FSAt:
    total: float
    shocked_total: float
    records: int


def fs_bases_at(n, b, history):
    d = date(V1.year + n, 12, 31)
    s34 = fs.s34_basis(V1) if n == 0 else fs.s34_basis(V1).with_(
        valuation_date=d, spc_next_year=b.spc_next_year * (1 + b.inflation) ** n, revaluation_history=history)
    ann = fs.annuity_basis(V1) if n == 0 else fs.annuity_basis(V1).with_(
        valuation_date=d, known_increases={}, revaluation_history=history)
    return s34, ann


def fs_at(records, n, b, history, rate_fall):
    """Weighted FS liability of the projected records, and the same with rates 0.5% lower (FSR test)."""
    s34, ann = fs_bases_at(n, b, history)
    pens = (records.status == "P").to_numpy()
    w = records.weight.to_numpy()
    totals = []
    for shift in (0.0, -rate_fall):
        tv, _ = fs.transfer_values(records[~pens], s34, fs.mva_npa_at(V1, shift))
        an, _ = fs.annuity_costs(records[pens], ann, fs.annuity_curve(V1).shifted(shift))
        base = (tv * w[~pens]).sum() + (an * w[pens]).sum()
        totals.append(base + fs.wind_up_expenses(base))
    return FSAt(totals[0], totals[1], len(records))


# --- the projection -----------------------------------------------------------------------------------------

def expected_return(allocation):
    r = load_config("assets")["expected_returns"]
    return sum(w * r[k] for k, w in allocation.items())


def qualifying_share(allocation):
    q = load_config("assets")["qualifying_for_fsr"]
    return sum(w for k, w in allocation.items() if k in q)


def allocation_after_switch(allocation):
    sw = load_config("assets")["switch"]
    new = dict(allocation)
    new[sw["from"]] -= sw["weight"]
    new[sw["to"]] = new.get(sw["to"], 0.0) + sw["weight"]
    return new


@dataclass
class Projection:
    years: int
    fs: list              # FSAt for n = 0..years
    benefits: list        # expected benefits in year n = 1..years (index n-1)
    normal_contributions: list
    expenses: float


def build_projection(members, years):
    """Membership-driven pieces of the projection (independent of the asset strategy and of C)."""
    b = projection_basis()
    history = extended_history(b)
    rate_fall = load_config("statutory_ie")["fsr"]["interest_rate_fall"]
    fs_list = [fs_at(project_membership(members, n, b, history), n, b, history, rate_fall) for n in range(years + 1)]
    cf = cashflows.project_cashflows(members, b.with_(service_increment=0.0))
    cfg = load_config("assets")["contributions"]
    rules = b.rules
    normal = []
    for n in range(1, years + 1):
        recs = project_membership(members, n - 1, b, history)
        act = recs[recs.status == "A"]
        ps = np.maximum(act.salary * (1 + b.salary_growth) - rules["spc_offset_multiple"] * spc_in(n, b), 0)
        normal.append(float((act.weight * ps).sum() * (cfg["employer_normal_rate"] + rules["member_contribution_rate"])))
    expenses = ias19.config()["admin_expenses"]["per_member_eur"] * len(members)
    return Projection(years, fs_list, [float(x) for x in cf.sum(axis=0)[:years]], normal, expenses)


def fsr_parts(fs_now, assets_total, allocation, dq_per_euro):
    p = load_config("statutory_ie")["fsr"]
    a_qual = qualifying_share(allocation) * assets_total
    proportion = p["proportion"] * max(fs_now.total - a_qual, 0.0)
    d_liab = fs_now.shocked_total - fs_now.total
    interest = d_liab - dq_per_euro * assets_total
    return proportion, interest


def run_projection(proj, opening_assets, allocation, dq_per_euro, deficit_contribution, contribution_years=None):
    """Assets and FS + FSR each year for a deficit contribution C a year (paid mid-year)."""
    contribution_years = proj.years if contribution_years is None else contribution_years
    R = expected_return(allocation)
    a = opening_assets
    path = []
    for n in range(proj.years + 1):
        if n > 0:
            c = deficit_contribution if n <= contribution_years else 0.0
            flow = proj.normal_contributions[n - 1] + c - proj.benefits[n - 1] - proj.expenses
            a = a * (1 + R) + flow * (1 + R) ** 0.5
        prop, inter = fsr_parts(proj.fs[n], a, allocation, dq_per_euro)
        req = proj.fs[n].total + prop + inter
        path.append({"year": V1.year + n, "assets": a, "fs": proj.fs[n].total, "fsr_proportion": prop,
                     "fsr_interest": inter, "fsr": prop + inter, "required": req, "cover": a / req,
                     "fs_level": a / proj.fs[n].total})
    return path


def solve_contribution(proj, opening_assets, allocation, dq_per_euro, years):
    """Smallest level C (EUR a year for `years` years) with assets >= FS + FSR at the end of year `years`."""
    def gap(c):
        p = run_projection(proj, opening_assets, allocation, dq_per_euro, c, years)[years]
        return p["assets"] - p["required"]
    if gap(0.0) >= 0:
        return 0.0
    return brentq(gap, 0.0, 50e6, xtol=1.0)


def qualifying_sensitivity(total_assets, allocation, market, rate_fall):
    """dA_qual for a 0.5% fall in yields, per euro of assets (constant allocation, yields unchanged)."""
    pf = assets.Portfolio.from_allocation(total_assets, allocation, market, assets.durations())
    return (pf.qualifying(market.shifted(-rate_fall)) - pf.qualifying(market)) / total_assets
