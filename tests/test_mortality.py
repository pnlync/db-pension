"""M3 acceptance tests (SPEC §9 M3): mortality basis, cohort survival, e65, longevity stress k."""
import numpy as np
import pytest

from pension import mortality
from pension.io import load_config

IAS19 = load_config("assumptions_ias19")["mortality"]


@pytest.fixture(scope="module")
def basis():
    return mortality.Mortality.from_config(IAS19)


def hand_e65(sex, first_year, multiplier, improvement, base_year):
    """Straightforward loop: complete e65 for someone reaching 65 at the start of first_year."""
    table = mortality.extended_ilt15()[sex]
    alive, total = 1.0, 0.0
    for s, age in enumerate(range(65, 121)):
        year = first_year + s
        q = 1.0 if age == 120 else min(multiplier * table[age] * (1 - improvement) ** max(year - base_year, 0), 1.0)
        alive *= 1 - q
        total += alive
    return total + 0.5


def test_extended_table_reaches_one_at_120():
    t = mortality.extended_ilt15()
    for sex in "MF":
        assert len(t[sex]) == 121 and t[sex][120] == 1.0
        assert np.all(np.diff(t[sex][60:]) >= 0)   # rises, then capped at 1 before 120
        assert np.allclose(t[sex][:106], mortality.ilt15_qx()[sex])


def test_period_ilt15_e65_unchanged_by_extension():
    flat = mortality.Mortality({"M": 1.0, "F": 1.0}, 0.0, 2014)
    assert flat.e65_now("M", 2026) == pytest.approx(16.59, abs=0.02)
    assert flat.e65_now("F", 2026) == pytest.approx(19.79, abs=0.02)


def test_e65_matches_hand_calculation(basis):
    for sex in "MF":
        expected = hand_e65(sex, 2026, IAS19["multiplier"][sex], IAS19["improvement"], IAS19["base_year"])
        assert basis.e65_now(sex, 2026) == pytest.approx(expected, abs=1e-10)


def test_e65_at_45_uses_the_cohort_diagonal(basis):
    """A 45-year-old reaches 65 twenty years later, with twenty more years of improvement."""
    expected = hand_e65("M", 2046, IAS19["multiplier"]["M"], IAS19["improvement"], IAS19["base_year"])
    assert basis.e65_at_age("M", 45, 2026) == pytest.approx(expected, abs=1e-10)
    assert basis.e65_at_age("M", 45, 2026) > basis.e65_now("M", 2026)


def test_survival_probabilities(basis):
    p = basis.survival(np.array([65, 80]), np.array(["M", "F"]), 2026, horizon=60)
    assert p.shape == (2, 61) and np.allclose(p[:, 0], 1.0)
    assert np.all(np.diff(p, axis=1) <= 0)
    q65 = basis.q(np.array([65]), np.array(["M"]), 2026)[0]
    assert p[0, 1] == pytest.approx(1 - q65)


def test_longevity_stress_k_adds_one_year(basis):
    k = basis.longevity_k(sex="M", year=2026, extra_years=1.0)
    stressed = basis.with_k(k)
    gain = stressed.e65_now("M", 2026) - basis.e65_now("M", 2026)
    print(f"k = {k:.4f}, e65 gain {gain:.4f}")
    assert 0 < k < 1
    assert gain == pytest.approx(1.0, abs=0.05)
