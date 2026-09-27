"""M9 acceptance tests (SPEC §9 M9): scenarios, PV01 and hedge ratios on both bases."""
import json

import numpy as np
import pytest

from helpers import VALUATION, clean_members
from pension import cashflows, funding_standard as fs, ias19, risk
from pension.io import OUTPUTS


@pytest.fixture(scope="module")
def state():
    total = json.loads((OUTPUTS / "aoc_2025.json").read_text())["asset_reconciliation"]["closing"]
    return risk.base_state(clean_members(), VALUATION, total, "2025-12-31")


@pytest.fixture(scope="module")
def results(state):
    return risk.scenarios(state)


def test_base_matches_the_valuations(state, results):
    base = results["base"]
    assert base["ias19_dbo"] == pytest.approx(ias19.valuation(state["members"], VALUATION)["dbo"], rel=1e-12)
    assert base["fs_liability"] == pytest.approx(fs.liabilities(state["members"], VALUATION)["total"], rel=1e-12)


def test_fs_unchanged_under_salary_scenarios(results):
    for name in ("salary_plus_50bp", "salary_minus_50bp"):
        assert results[name]["fs_liability"] == pytest.approx(results["base"]["fs_liability"])
        assert results[name]["assets"] == pytest.approx(results["base"]["assets"])


def test_equity_scenario_changes_no_cash_flow(results):
    eq, base = results["equities_minus_20pct"], results["base"]
    assert eq["ias19_dbo"] == base["ias19_dbo"] and eq["fs_liability"] == base["fs_liability"]
    assert eq["assets"] < base["assets"]


def test_directions(results):
    base = results["base"]
    assert results["discount_minus_50bp"]["ias19_dbo"] > base["ias19_dbo"] > results["discount_plus_50bp"]["ias19_dbo"]
    assert results["inflation_plus_50bp"]["ias19_dbo"] > base["ias19_dbo"]
    assert results["life_expectancy_plus_1"]["fs_liability"] > base["fs_liability"]
    assert results["combined"]["ias19_deficit"] > max(results[k]["ias19_deficit"] for k in results if k != "combined")


def test_pv01_duration_check(state):
    """PV01 / (DBO x 1bp) equals the analytic effective duration within 1%."""
    b, c = state["ias19_basis"], state["ias19_curve"]
    cf = cashflows.project_cashflows(state["members"], b)
    total = cf.sum(axis=0)
    times = cashflows.payment_times()
    dbo = cashflows.pv(total[None, :], c)[0]
    analytic = (times * total * c.discount(times) / (1 + c.spot(np.minimum(times, 30)))).sum() / dbo
    assert ias19.pv01(cf, c) / (dbo * 1e-4) == pytest.approx(analytic, rel=0.01)


def test_hedge_ratios(state):
    f = fs.fsr(state["members"], VALUATION, state["portfolio"], state["market"])
    p = risk.pv01s(state, f)
    print(f"hedge ratio IAS 19 {p['hedge_ratio_ias19']:.1%}, FS {p['hedge_ratio_fs']:.1%}")
    assert 0 < p["hedge_ratio_ias19"] < p["hedge_ratio_fs"] < 1
    assert p["assets"] == pytest.approx(sum(p["assets_by_class"].values()))


def test_longevity_k_for_each_basis(state):
    b = state["ias19_basis"]
    k = b.mortality_post.longevity_k(year=2026)
    assert b.mortality_post.with_k(k).e65_now("M", 2026) - b.mortality_post.e65_now("M", 2026) == pytest.approx(1.0, abs=0.05)
    ki = risk.insurer_longevity_k(state["ann_basis"], 2026)
    m = state["ann_basis"].mortality_post
    assert m.with_k(ki).e65_now("M", 2026) - m.e65_now("M", 2026) == pytest.approx(1.0, abs=0.05)
