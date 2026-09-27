"""Section 34 market value adjustments (Section 34 guidance v02, paras 4.1-5.1; SPEC §9 M6).

All constants come from config/statutory_ie.yaml (section34).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from pension.io import load_config, read_market


def params():
    return load_config("statutory_ie")["section34"]


def round_yield(y, step):
    """Round a yield (decimal) to the nearest step (0.25%), halves up."""
    q = Decimal(str(y)) / Decimal(str(step))
    return float(q.quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal(str(step)))


def annuity_certain(rate, n):
    """a_n at rate (payments in arrears) and v^n."""
    v = (1 + rate) ** -n
    return (1 - v) / rate if rate != 0 else float(n), v


def mva_npa_fixed(i_yield, p=None):
    """MVA1 at NPA: 0.0425 x a15 + v^15 at i, i = OAT 2032 nominal yield rounded to 0.25% (para 4.6)."""
    p = params() if p is None else p
    m = p["mva"]
    a, v = annuity_certain(round_yield(i_yield, m["yield_rounding"]), m["npa_annuity_term_years"])
    return m["fixed_coupon"] * a + v


def mva_npa_index_linked(j_yield, p=None):
    """MVA2 at NPA: (1.0425/1.015 - 1) x a15 + v^15 at j, j = OAT€i 2032 real yield rounded to 0.25% (para 4.6)."""
    p = params() if p is None else p
    m = p["mva"]
    coupon = (1 + p["discount_post_retirement"]) / (1 + p["price_inflation_post"]) - 1
    a, v = annuity_certain(round_yield(j_yield, m["yield_rounding"]), m["npa_annuity_term_years"])
    return coupon * a + v


def mva_pre(T, p=None):
    """[1.06 / (1.0425 + T/20 x (0.06 - 0.0425))]^T, T whole years to NPA capped at 10 (para 4.3)."""
    p = params() if p is None else p
    T = np.minimum(np.asarray(T, dtype=float), p["mva"]["window_years"])
    d_pre, d_post = p["discount_pre_retirement"], p["discount_post_retirement"]
    return ((1 + d_pre) / (1 + d_post + T / p["mva"]["pre_retirement_T_divisor"] * (d_pre - d_post))) ** T


def mva_post(T, mva_npa, p=None):
    """MVA_NPA x (10 - N)/10 + N/10 for N <= 10 complete years to NPA; 1 beyond (paras 4.4, 4.7)."""
    p = params() if p is None else p
    w = p["mva"]["window_years"]
    N = np.asarray(T, dtype=float)
    return np.where(N <= w, mva_npa * (w - N) / w + N / w, 1.0)


def table():
    t = read_market("mva_section34")
    t["date"] = pd.to_datetime(t.date).dt.date
    return t


def row_for_effective_date(effective):
    """Para 4.1: the MVA at the last working day of the month immediately before the effective date."""
    t = table()
    first = date(effective.year, effective.month, 1)
    return t[t.date < first].iloc[-1]


def golden_test(since=date(2017, 1, 1)):
    """Recompute MVA1 and MVA2 from the published OAT yields for every month since `since`."""
    t = table()
    t = t[t.date >= since].copy()
    t["mva1_model"] = [round(mva_npa_fixed(y / 100), 3) for y in t.oat_nominal_pct]
    t["mva2_model"] = [round(mva_npa_index_linked(y / 100), 3) for y in t.oat_real_pct]
    t["mva1_match"] = np.isclose(t.mva1_model, t.mva1, atol=1e-9)
    t["mva2_match"] = np.isclose(t.mva2_model, t.mva2, atol=1e-9)
    return t
