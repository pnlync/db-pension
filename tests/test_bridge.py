"""M7 acceptance tests (SPEC §9 M7): IAS 19 -> FS bridge by sequential full revaluations, zero residual."""
import pytest

from helpers import VALUATION, clean_members
from pension import bridge, funding_standard as fs, ias19


@pytest.fixture(scope="module")
def members():
    return clean_members()


@pytest.fixture(scope="module")
def steps(members):
    return bridge.run(members, VALUATION)


def test_starts_at_ias19_dbo(members, steps):
    assert steps[0]["level"] == pytest.approx(ias19.valuation(members, VALUATION)["dbo"], rel=1e-12)


def test_steps_sum_exactly_to_fs_minus_ias19(members, steps):
    fs_total = fs.liabilities(members, VALUATION)["total"]
    total_effect = sum(s["effect"] for s in steps[1:])
    assert total_effect == pytest.approx(fs_total - steps[0]["level"], abs=1e-6)
    assert steps[-1]["level"] == pytest.approx(fs_total, abs=1e-6)


def test_fixed_order_and_directions(steps):
    assert [s["key"] for s in steps] == [k for k, _, _ in bridge.STEPS]
    effects = {s["key"]: s["effect"] for s in steps}
    assert effects["leaver_basis"] < 0      # today's salary instead of salary at exit
    assert effects["s34_increases"] < 0     # 1.5% instead of ~1.9%
    assert effects["annuity_cost"] > 0      # insurer price above IAS 19 value
    assert effects["expenses"] > 0
