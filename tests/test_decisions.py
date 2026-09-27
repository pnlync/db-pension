"""M10 acceptance tests (SPEC §9 M10): funding projection, contribution solve, switch."""
import json

import pytest

from helpers import VALUATION, clean_members
from pension import assets, decisions as d, funding_standard as fs
from pension.io import OUTPUTS, load_config


@pytest.fixture(scope="module")
def setup():
    members = clean_members()
    total = json.loads((OUTPUTS / "aoc_2025.json").read_text())["asset_reconciliation"]["closing"]
    market = assets.Market.at(VALUATION, "2025-12-31")
    alloc = load_config("assets")["allocation"]
    alloc_sw = d.allocation_after_switch(alloc)
    return {"members": members, "total": total, "market": market, "alloc": alloc, "alloc_sw": alloc_sw,
            "dq": d.qualifying_sensitivity(total, alloc, market, 0.005),
            "dq_sw": d.qualifying_sensitivity(total, alloc_sw, market, 0.005),
            "proj": d.build_projection(members, 10)}


def test_year_zero_equals_m6(setup):
    s = setup
    y0 = d.run_projection(s["proj"], s["total"], s["alloc"], s["dq"], 0.0)[0]
    m6 = fs.fsr(s["members"], VALUATION, assets.closing_portfolio(s["total"], s["market"]), s["market"])
    assert y0["fs"] == pytest.approx(m6["fs_liabilities"]["total"], rel=1e-10)
    assert y0["fsr"] == pytest.approx(m6["fsr"], rel=1e-9)


def test_solved_contribution_hits_target_within_1k(setup):
    s = setup
    c = d.solve_contribution(s["proj"], s["total"], s["alloc"], s["dq"], 3)
    end = d.run_projection(s["proj"], s["total"], s["alloc"], s["dq"], c, 3)[3]
    print(f"C = {c / 1e6:.3f}m a year; year-3 gap {end['assets'] - end['required']:,.0f}")
    assert abs(end["assets"] - end["required"]) < 1_000


def test_contribution_falls_as_period_lengthens(setup):
    s = setup
    cs = [d.solve_contribution(s["proj"], s["total"], s["alloc"], s["dq"], y) for y in (3, 5, 10)]
    assert cs[0] > cs[1] > cs[2] > 0


def test_switch_changes_assets_and_fsr_only(setup):
    s = setup
    base = d.run_projection(s["proj"], s["total"], s["alloc"], s["dq"], 0.0)[0]
    sw = d.run_projection(s["proj"], s["total"], s["alloc_sw"], s["dq_sw"], 0.0)[0]
    assert sw["fs"] == base["fs"] and sw["assets"] == base["assets"]
    assert sw["fsr_proportion"] < base["fsr_proportion"] and sw["fsr_interest"] < base["fsr_interest"]
    assert d.expected_return(s["alloc_sw"]) < d.expected_return(s["alloc"])


def test_projected_membership_conserves_probability(setup):
    """Weights of each original member's records sum to its survival probability (leavers stay alive or die)."""
    members = setup["members"]
    b = d.projection_basis()
    recs = d.project_membership(members, 3, b, d.extended_history(b))
    total = recs.groupby("member_id").weight.sum()
    assert total.max() <= 1 + 1e-12 and total.min() > 0.5
