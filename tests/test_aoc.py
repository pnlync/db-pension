"""M8 acceptance tests (SPEC §9 M8): assets and the 2025 analysis of change."""
import pandas as pd
import pytest

from pension import aoc, ias19, pipeline
from pension.io import MEMBERS, load_config


@pytest.fixture(scope="module")
def result():
    m0, m1 = pipeline.members_at(aoc.V0), pipeline.members_at(aoc.V1)
    return aoc.run(m0, m1, pd.read_csv(MEMBERS / "members_2024.csv"), pd.read_csv(MEMBERS / "movements_2025.csv"))


def test_closing_dbo_equals_independent_revaluation(result):
    L = result["liabilities"]
    steps = L["steps"]
    chained = sum(v for k, v in steps.items())
    assert chained == pytest.approx(L["closing"], abs=1e-3)
    independent = ias19.valuation(pipeline.members_at(aoc.V1), aoc.V1)["dbo"]
    assert L["closing"] == pytest.approx(independent, abs=1e-6)


def test_other_below_0_1_percent_of_dbo(result):
    L = result["liabilities"]
    print(f"other {L['steps']['other']:.2f}, roll-down {L['steps']['roll_down'] / 1e6:.3f}m")
    assert abs(L["steps"]["other"]) < 0.001 * L["closing"]


def test_roll_down_and_experience_are_small(result):
    s, dbo = result["liabilities"]["steps"], result["liabilities"]["closing"]
    for key in ("roll_down", "membership", "salaries", "inflation_linked"):
        assert abs(s[key]) < 0.01 * dbo


def test_directions(result):
    s = result["liabilities"]["steps"]
    assert s["curve"] < 0              # yields rose in 2025
    assert s["salaries"] > 0           # 2025 pay rises above the 2.95% assumption
    assert s["demographic"] == 0       # mortality basis unchanged


def test_asset_identity_zero(result):
    roll, acc = result["assets"], result["accounts"]
    rebuilt = roll.opening + acc["interest_income"] + acc["return_above_interest"] + roll.net_flow
    assert rebuilt == pytest.approx(roll.closing, abs=1e-6)
    assert sum(roll.closing_by_class.values()) == pytest.approx(roll.closing, abs=1e-6)


def test_net_liability_identity_zero(result):
    acc, flows = result["accounts"], result["flows"]
    rebuilt = (acc["opening_net_liability"] + acc["pl"]["total"] + acc["oci"]["total"]
               - flows["employer_contributions"])
    assert rebuilt == pytest.approx(acc["closing_net_liability"], abs=1e-4)


def test_deficit_waterfall_closes(result):
    w = result["accounts"]["waterfall"]
    moves = sum(v for k, v in w.items() if k not in ("opening_deficit", "closing_deficit"))
    assert w["opening_deficit"] + moves == pytest.approx(w["closing_deficit"], abs=1e-4)


def test_opening_assets_hit_the_design_target(result):
    target = load_config("assets")["target_closing_ias19_funding_level"] * result["liabilities"]["closing"]
    assert result["assets"].closing == pytest.approx(target, abs=1.0)


def test_fs_change_closes(result):
    f = result["fs"]
    moves_l = sum(f["liabilities"].values())
    moves_a = sum(f["assets"].values())
    assert f["fs_opening"] + moves_l == pytest.approx(f["fs_closing"], abs=1e-4)
    assert f["surplus_opening"] + moves_a - moves_l == pytest.approx(f["surplus_closing"], abs=1e-4)
    assert f["fs_level_opening"] < 1 <= f["fs_level_closing"]


def test_cash_return_compounds_estr():
    estr = pd.DataFrame({"TIME_PERIOD": ["2025-01-02", "2025-12-31"], "OBS_VALUE": [3.6, 0.0]})
    # 3.6% for 363 days (2 Jan to 31 Dec), 0% for the last day
    assert aoc.cash_return_2025(estr) == pytest.approx(0.036 * 363 / 360)
