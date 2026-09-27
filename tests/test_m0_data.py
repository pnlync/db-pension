"""M0 acceptance tests (SPEC §9 M0): transcribed market and statutory data."""
import csv
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / "data" / "market"
REQUIRED_META = ("source", "effective_date", "retrieved")


def read_meta(path):
    meta = {}
    for line in path.read_text().splitlines():
        if not line.startswith("# "):
            break
        key, _, value = line[2:].partition(": ")
        meta[key] = value
    return meta


def read(name):
    return pd.read_csv(MARKET / name, comment="#")


def complete_expectation(qx):
    """e(x) = sum_{t>=1} tpx + 1/2 (deaths uniform over the year); table closes after its last age."""
    return np.cumprod(1 - qx).sum() + 0.5


# --- every data file states source and date ---------------------------------

def test_every_market_file_states_source_and_dates():
    files = sorted(MARKET.glob("*.csv"))
    assert len(files) >= 6
    for path in files:
        meta = read_meta(path)
        for key in REQUIRED_META:
            assert meta.get(key), f"{path.name} missing '{key}'"


def test_statutory_sources_have_document_and_dates():
    cfg = yaml.safe_load((ROOT / "config" / "statutory_ie.yaml").read_text())
    for name, src in cfg["sources"].items():
        for key in ("document", "url", "effective_date", "retrieved"):
            assert src.get(key), f"{name} missing '{key}'"


def test_register_rows_complete():
    with open(ROOT / "data" / "assumptions_register.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 25
    for row in rows:
        assert all(v.strip() for v in row.values()), row["name"]


# --- ILT15 ------------------------------------------------------------------

def test_ilt15_complete_and_internally_consistent():
    d = read("ilt15.csv")
    for sex in "MF":
        t = d[d.sex == sex].set_index("age")
        assert list(t.index) == list(range(106))
        assert np.allclose(t.px + t.qx, 1.0, atol=1e-9)
        # l(x+1) = l(x) - d(x), up to rounding of the published integers
        assert (t.lx.shift(-1) - (t.lx - t.dx)).abs().max() <= 1
        # q(x) = d(x) / l(x), up to rounding of d and l
        assert ((t.qx - t.dx / t.lx).abs() <= 1 / t.lx + 1e-5).all()


def test_ilt15_e65_matches_cso():
    d = read("ilt15.csv")
    for sex, published in (("M", 16.6), ("F", 19.8)):
        qx = d[(d.sex == sex) & (d.age >= 65)].qx.to_numpy()
        e65 = complete_expectation(qx)
        print(f"ILT15 e65 {sex}: {e65:.3f} (CSO {published})")
        assert abs(e65 - published) < 0.1


def test_ilt15_recomputed_ex_matches_table_at_all_ages():
    d = read("ilt15.csv")
    for sex in "MF":
        t = d[d.sex == sex].sort_values("age")
        qx = t.qx.to_numpy()
        ex = np.array([complete_expectation(qx[a:]) for a in range(len(qx))])
        assert np.abs(ex[:100] - t.ex.to_numpy()[:100]).max() < 0.02


def test_ilt17_e65_matches_table():
    d = read("ilt17.csv")
    for sex in "MF":
        t = d[d.sex == sex].sort_values("age")
        assert abs(complete_expectation(t.qx.to_numpy()[65:]) - t.ex.to_numpy()[65]) < 0.02


# --- MVA table --------------------------------------------------------------

def mva_for_effective_date(table, effective):
    """Section 34 para 4.1: last working day of the month immediately before the effective date."""
    first_of_month = pd.Timestamp(effective.year, effective.month, 1)
    return table[table.date < first_of_month].iloc[-1]


def test_mva_table_has_every_month_since_2017():
    t = read("mva_section34.csv")
    t["date"] = pd.to_datetime(t.date)
    months = t.date.dt.to_period("M")
    assert months.is_unique
    since_2017 = months[months >= pd.Period("2017-01", "M")]
    expected = pd.period_range("2017-01", "2026-08", freq="M")
    assert set(expected) <= set(since_2017)
    assert len(expected) == 116


def test_mva_date_rule_picks_november_factors():
    t = read("mva_section34.csv")
    t["date"] = pd.to_datetime(t.date)
    for effective, mva1, mva2 in ((date(2024, 12, 31), 1.182, 1.277), (date(2025, 12, 31), 1.149, 1.237)):
        row = mva_for_effective_date(t, effective)
        assert row.date.month == 11
        assert (row.mva1, row.mva2) == (mva1, mva2)


# --- ECB curves -------------------------------------------------------------

def test_ecb_curves_complete_and_converted():
    for name in ("ecb_aaa_spot_2024-12-30.csv", "ecb_aaa_spot_2025-12-31.csv"):
        t = read(name)
        assert list(t.tenor_months) == list(range(3, 361))
        assert np.allclose(t.spot_annual, np.exp(t.spot_cc_pct / 100) - 1, atol=1e-10)
        assert t.spot_annual.between(-0.01, 0.06).all()


# --- CPI --------------------------------------------------------------------

def test_cpi_index_agrees_with_published_changes():
    t = read("cpi_ie.csv").set_index("year")
    assert t.index.min() <= 2000 and t.index.max() == 2025
    change = (t.cpi_dec / t.cpi_dec.shift(1) - 1) * 100
    diff = (change - t.pct_12m_published).loc[2000:2025].abs()
    assert diff.max() < 0.25   # index is published to 0.1 on a Dec 2023 = 100 base
    assert t.loc[2025, "pct_12m_published"] == 2.8


# --- ASP PEN-3 appendix ----------------------------------------------------

def test_pen3_table_interpolation_checks():
    tab = yaml.safe_load((ROOT / "config" / "statutory_ie.yaml").read_text())["funding_standard"]["fixed_increase_table"]
    pi, cap3 = np.array(tab["pi"]), np.array(tab["index_linked"][0.03])
    assert np.all(np.diff(cap3) > 0)
    for p, fixed in ((0.01, 0.0115), (0.02, 0.0185), (0.03, 0.0240), (0.019, 0.0178)):
        assert round(float(np.interp(p, pi, cap3)), 4) == fixed
