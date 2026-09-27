"""M6 acceptance tests (SPEC §9 M6): Section 34 MVA, transfer values, annuity cost, wind-up expenses, FSR."""
from pathlib import Path

import numpy as np
import pytest

from helpers import VALUATION, clean_members
from pension import assets, funding_standard as fs, mva
from pension.io import load_config


@pytest.fixture(scope="module")
def members():
    return clean_members()


@pytest.fixture(scope="module")
def result(members):
    from pension import ias19
    dbo = ias19.valuation(members, VALUATION)["dbo"]
    market = assets.Market.at(VALUATION, "2025-12-31")
    total = load_config("assets")["target_closing_ias19_funding_level"] * dbo
    return fs.fsr(members, VALUATION, assets.closing_portfolio(total, market), market)


def test_mva_golden_test_every_month_since_2017():
    t = mva.golden_test()
    assert len(t) >= 116
    assert t.mva1_match.all() and t.mva2_match.all()


def test_mva_date_rule_and_values_at_valuation_dates():
    from datetime import date
    assert mva.row_for_effective_date(date(2025, 12, 31)).mva2 == 1.237
    assert fs.mva_npa_at(date(2025, 12, 31)) == pytest.approx(1.237, abs=5e-4)
    assert fs.mva_npa_at(date(2024, 12, 31)) == pytest.approx(1.277, abs=5e-4)


def test_pre_retirement_mva_formula():
    assert mva.mva_pre(0) == 1.0
    assert mva.mva_pre(10) == pytest.approx((1.06 / (1.0425 + 0.5 * 0.0175)) ** 10)
    assert mva.mva_pre(25) == mva.mva_pre(10)


def test_appendix_table_points_and_interpolation():
    table = load_config("statutory_ie")["funding_standard"]["fixed_increase_table"]
    for cap, values in table["index_linked"].items():
        for pi, value in zip(table["pi"], values):
            assert fs.fixed_increase(pi, cap) == pytest.approx(value)
    assert fs.fixed_increase(0.019, 0.03) == pytest.approx(0.0178)


def test_tv_10_or_more_years_from_65_does_not_move_with_j(members):
    b = fs.s34_basis(VALUATION)
    far = members[(members.status != "P") & (members["T"] >= 10)]   # N = 10 gives MVA_post = 1
    near = members[(members.status != "P") & (members["T"] < 10)]
    tv_far_1, _ = fs.transfer_values(far, b, mva.mva_npa_index_linked(0.010))
    tv_far_2, _ = fs.transfer_values(far, b, mva.mva_npa_index_linked(0.005))
    assert np.allclose(tv_far_1, tv_far_2)
    tv_near_1, _ = fs.transfer_values(near, b, mva.mva_npa_index_linked(0.010))
    tv_near_2, _ = fs.transfer_values(near, b, mva.mva_npa_index_linked(0.005))
    assert (tv_near_2 > tv_near_1).all()   # lower real yield -> higher MVA -> higher TV


def test_liability_components_add_up(result):
    L = result["fs_liabilities"]
    assert L["total"] == pytest.approx(L["non_pensioners"] + L["pensioners"] + L["expenses"])
    assert L["expenses"] == pytest.approx(max(0.02 * (L["non_pensioners"] + L["pensioners"]), 10_000))
    assert sum(L["by_status"].values()) == pytest.approx(L["non_pensioners"] + L["pensioners"])


def test_fsr_formula(result):
    unmatched = max(result["fs_liabilities"]["total"] - result["qualifying_assets"], 0)
    assert result["proportion_part"] == pytest.approx(0.10 * unmatched)
    assert result["interest_part"] == pytest.approx(result["d_liabilities"]["total"] - result["d_qualifying_assets"])
    assert result["fsr"] == pytest.approx(result["proportion_part"] + result["interest_part"])


def test_design_target_meets_fs_not_fs_plus_fsr(result):
    """SPEC §12: at 2025-12-31 the scheme meets the Funding Standard but not FS + FSR."""
    print(f"FS level {result['fs_funding_level']:.1%}, FS + FSR cover {result['fs_plus_fsr_cover']:.1%}")
    assert result["fs_met"] and not result["fs_plus_fsr_met"]


def test_interest_test_non_pensioners_only_within_10_years(members):
    """Non-pensioner liabilities react to the 0.5% fall only through MVA_post (members within 10 years of 65)."""
    b = fs.s34_basis(VALUATION)
    np_members = members[members.status != "P"]
    base, _ = fs.transfer_values(np_members, b, fs.mva_npa_at(VALUATION))
    shocked, _ = fs.transfer_values(np_members, b, fs.mva_npa_at(VALUATION, -0.005))
    moved = ~np.isclose(base, shocked)
    assert (np_members["T"].to_numpy()[moved] <= 10).all()


def test_funding_standard_does_not_read_ias19_assumptions():
    source = Path(fs.__file__).read_text()
    for forbidden in ("assumptions_ias19", "import ias19", "from pension.ias19", "ias19."):
        assert forbidden not in source
