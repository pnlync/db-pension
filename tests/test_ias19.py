"""M5 acceptance tests (SPEC §9 M5, §12): IAS 19 valuation."""
from pathlib import Path

import numpy as np
import pytest

from helpers import VALUATION, clean_members
from pension import cashflows, ias19
from pension.curves import FlatRate
from pension.mortality import Mortality


@pytest.fixture(scope="module")
def members():
    return clean_members()


@pytest.fixture(scope="module")
def result(members):
    return ias19.valuation(members, VALUATION)


def test_design_targets(result):
    """SPEC §12: DBO EUR 180-220m, pensioners 55-60% of DBO, duration 15-18 years."""
    share = result["dbo_by_status"]["P"] / result["dbo"]
    print(f"DBO {result['dbo'] / 1e6:.1f}m, pensioners {share:.1%}, duration {result['duration']:.1f}")
    assert 180e6 <= result["dbo"] <= 220e6
    assert 0.55 <= share <= 0.60
    assert 15 <= result["duration"] <= 18


def test_sedr_flat_pv_equals_curve_pv(result):
    flat = cashflows.pv(result["cf_total"][None, :], FlatRate(result["sedr"]))[0]
    assert flat == pytest.approx(result["dbo"], rel=1e-9)


def test_duration_check_within_one_percent(result):
    """Bump duration (PV01 / DBO / 1bp) vs analytic effective duration sum((t-1/2) CF v / (1 + s)) / PV."""
    times = cashflows.payment_times()
    curve = result["curve"]
    v = curve.discount(times)
    spot = curve.spot(np.minimum(times, curve.tenors[-1]))
    analytic = (times * result["cf_total"] * v / (1 + spot)).sum() / result["dbo"]
    assert result["duration"] == pytest.approx(analytic, rel=0.01)


def test_rates_up_dbo_down(members, result):
    up = cashflows.pv(result["cf"], result["curve"].shifted(0.005)).sum()
    assert up < result["dbo"]


def test_inflation_up_dbo_up(members, result):
    b = ias19.basis(VALUATION, inflation=result["basis"].inflation + 0.005)
    assert ias19.dbo_by_member(members, b, result["curve"]).sum() > result["dbo"]


def test_salary_affects_actives_only(members, result):
    b = result["basis"].with_(salary_growth=result["basis"].salary_growth + 0.005)
    higher = ias19.dbo_by_member(members, b, result["curve"])
    changed = np.abs(higher - result["by_member"]) > 1e-6
    assert set(members.status[changed]) == {"A"}


def test_life_expectancy_plus_one_year(members, result):
    mort = result["basis"].mortality_post
    k = mort.longevity_k(year=2026)
    assert mort.with_k(k).e65_now("M", 2026) - mort.e65_now("M", 2026) == pytest.approx(1.0, abs=0.05)
    b = result["basis"].with_(mortality_pre=mort.with_k(k), mortality_post=mort.with_k(k))
    assert ias19.dbo_by_member(members, b, result["curve"]).sum() > result["dbo"]


def test_service_cost_net_of_member_contributions(members):
    sc = ias19.service_cost(members, VALUATION)
    assert sc["gross"] > 0
    assert sc["employer"] == pytest.approx(sc["gross"] - 0.05 * sc["pensionable_payroll"])
    assert 0.15 < sc["gross"] / sc["pensionable_payroll"] < 0.35


def test_aa_spread_calibration_reproduces_config():
    """Recompute the spread from the disclosed rates: mean(rate_i - AAA spot at duration_i) at 2025-12-31."""
    cfg = ias19.config()
    aaa = ias19.curve(VALUATION, spread=0.0)
    spreads = [d["discount_rate"][2025] - float(aaa.spot(d["duration_years"][2025])) for d in cfg["disclosures_2025"]]
    assert abs(np.mean(spreads) - cfg["discount"]["aa_spread"]) < 0.0005


def test_mortality_calibration_matches_disclosures():
    """Calibrated basis gives male 22.0 / 23.7 and female 24.25 within 0.15 years."""
    m = Mortality.from_config(ias19.config()["mortality"])
    assert m.e65_now("M", 2026) == pytest.approx(22.0, abs=0.15)
    assert m.e65_at_age("M", 45, 2026) == pytest.approx(23.7, abs=0.15)
    assert m.e65_now("F", 2026) == pytest.approx(24.25, abs=0.15)


def test_ias19_does_not_read_the_statutory_basis():
    """SPEC §8: the IAS 19 module never reads the Section 34 / Funding Standard / FSR sections or the insurer basis.
    (It may read market data, e.g. the OAT 2032 yields in mva_section34.csv, and the State Pension amount.)"""
    source = (Path(ias19.__file__)).read_text()
    for forbidden in ('["section34"]', '["funding_standard"]', '["fsr"]', "assumptions_insurer", "import funding_standard"):
        assert forbidden not in source
