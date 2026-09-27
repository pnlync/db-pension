"""M11 acceptance tests (SPEC §9 M11): pensioner buy-in price and day-one effects."""
import json

import numpy as np
import pytest

from helpers import VALUATION, clean_members
from pension import buyin, cashflows, funding_standard as fs, ias19
from pension.io import OUTPUTS


@pytest.fixture(scope="module")
def members():
    return clean_members()


@pytest.fixture(scope="module")
def priced(members):
    return buyin.price(members[members.status == "P"], VALUATION)


@pytest.fixture(scope="module")
def pro_rata(members, priced):
    total = json.loads((OUTPUTS / "aoc_2025.json").read_text())["asset_reconciliation"]["closing"]
    return buyin.day_one(members, VALUATION, total, priced, "pro_rata")


def test_premium_identity(priced):
    """Premium = TP - spread passed on + profit; TP = BEL + RM; no capital loading on top of the RM."""
    assert priced["tp"] == pytest.approx(priced["bel"] + priced["rm"])
    assert priced["premium"] == pytest.approx(priced["tp"] - priced["spread_passed_on"] + priced["profit"])
    assert priced["profit"] == pytest.approx(0.02 * priced["bel"])
    assert priced["rm"] > 0 and priced["spread_passed_on"] > 0


def test_waterfall_zero_residual(members, priced):
    steps = buyin.waterfall(members[members.status == "P"], VALUATION, priced)
    assert steps[0]["level"] + sum(s["effect"] for s in steps[1:]) == pytest.approx(priced["premium"], abs=1e-6)
    dbo_p = ias19.valuation(members, VALUATION)["by_member"][(members.status == "P").to_numpy()].sum()
    assert steps[0]["level"] == pytest.approx(dbo_p, rel=1e-12)


def test_oci_loss_identity_under_exact_match(pro_rata):
    """IAS 19: policy valued at the insured DBO, so OCI loss = premium - insured DBO exactly."""
    a = pro_rata["ias19"]
    assert a["after"]["oci_loss"] == pytest.approx(pro_rata["premium"] - pro_rata["insured_ias19_dbo"])
    assert a["before"]["assets"] - a["after"]["assets"] == pytest.approx(a["after"]["oci_loss"])


def test_fs_after_equals_before_minus_insured(members, pro_rata):
    before = fs.liabilities(members, VALUATION)
    after_np = before["non_pensioners"]
    assert pro_rata["fs"]["after"]["liabilities"] == pytest.approx(after_np + fs.wind_up_expenses(after_np))
    assert pro_rata["fs"]["insured_liability"] == pytest.approx(before["pensioners"])


def test_insured_pv01_equals_pensioner_pv01(members, pro_rata):
    r = ias19.valuation(members, VALUATION)
    pens = (members.status == "P").to_numpy()
    assert pro_rata["insured_pv01_ias19"] == pytest.approx(ias19.pv01(r["cf"][pens], r["curve"]))
    assert 0 < pro_rata["pv01_insured_share"]["ias19"] < pro_rata["pv01_insured_share"]["fs"] < 1


def test_premium_falls_with_spread_and_rises_with_margin(members):
    p = members[members.status == "P"]
    assert buyin.price(p, VALUATION, spread=0.0)["premium"] > buyin.price(p, VALUATION, spread=0.01)["premium"]
    assert buyin.price(p, VALUATION, margin=0.03)["premium"] > buyin.price(p, VALUATION, margin=0.01)["premium"]


def test_payment_method_changes_only_assets(members, priced):
    total = json.loads((OUTPUTS / "aoc_2025.json").read_text())["asset_reconciliation"]["closing"]
    sov = buyin.day_one(members, VALUATION, total, priced, "sell_sovereigns")
    eq = buyin.day_one(members, VALUATION, total, priced, "sell_equities")
    assert sov["fs"]["after"]["liabilities"] == eq["fs"]["after"]["liabilities"]
    assert sov["fs"]["after"]["qualifying"] < eq["fs"]["after"]["qualifying"]
    assert sov["fs"]["after"]["fsr"] > eq["fs"]["after"]["fsr"]
