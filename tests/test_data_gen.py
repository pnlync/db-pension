"""M1 acceptance tests (SPEC §6, §9 M1): synthetic opening data, 2025 movements, closing raw extract."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from pension import benefits, data_gen
from pension.io import load_config

CLOSING = pd.Timestamp("2025-12-31")
OPENING = pd.Timestamp("2024-12-31")


@pytest.fixture(scope="module")
def gen():
    return data_gen.generate(load_config("data_gen"))


def age_at(dob, when):
    return (when - pd.to_datetime(dob)).dt.days / 365.25


# --- reproducibility ----------------------------------------------------------

def test_reproducible_with_seed(gen):
    again = data_gen.generate(load_config("data_gen"))
    for name in ("opening", "movements", "closing_true", "closing_raw", "answer_key"):
        pd.testing.assert_frame_equal(gen[name], again[name])


def test_different_seed_gives_different_data(gen):
    cfg = load_config("data_gen")
    cfg["seed"] += 1
    other = data_gen.generate(cfg)
    assert not gen["opening"]["salary"].equals(other["opening"]["salary"])


# --- counts -----------------------------------------------------------------

def test_closing_counts_about_250_300_450(gen):
    counts = gen["closing_true"].status.value_counts()
    print("closing counts:", counts.to_dict())
    for status, target in (("A", 250), ("D", 300), ("P", 450)):
        assert abs(counts[status] - target) <= 10


def test_status_flows_reconcile(gen):
    """opening + in - out = closing, by status."""
    op = gen["opening"].status.value_counts()
    cl = gen["closing_true"].status.value_counts()
    mv = gen["movements"]
    exits = mv[mv.event.isin(["withdrawal", "retirement", "death"])]
    for s in "ADP":
        out = (exits.old_status == s).sum()
        into = (exits.new_status == s).sum()
        assert op[s] + into - out == cl[s]


def test_every_closing_member_traces_to_opening(gen):
    assert set(gen["closing_true"].member_id) <= set(gen["opening"].member_id)


# --- distributions (opening snapshot) ----------------------------------------

def test_active_distribution(gen):
    a = gen["opening"].query("status == 'A'")
    age = age_at(a.date_of_birth, OPENING)
    service = a.pensionable_service
    assert age.between(35, 65).all() and abs(age.mean() - 50) < 1.5
    assert (service <= age - 22 + 0.01).all()
    assert (pd.to_datetime(a.date_joined) <= pd.Timestamp("2012-12-31")).all()
    assert a.salary.between(40_000, 120_000).all()
    assert abs(a.salary.median() / 65_000 - 1) < 0.10


def test_deferred_distribution(gen):
    d = gen["opening"].query("status == 'D'")
    age = age_at(d.date_of_birth, OPENING)
    left = pd.to_datetime(d.date_left)
    assert age.between(35, 65).all()
    assert left.between(pd.Timestamp("2000-01-01"), OPENING).all()
    assert d.deferred_pension_at_exit.between(2_000, 20_000).all()
    assert (pd.to_datetime(d.date_joined) <= pd.Timestamp("2012-12-31")).all()
    assert d.salary.isna().all()


def test_pensioner_distribution(gen):
    p = gen["opening"].query("status == 'P'")
    age = age_at(p.date_of_birth, OPENING)
    assert age.between(65, 96).all() and 70 < age.mean() < 78
    assert p.pension_in_payment.between(8_000, 45_000).all()


def test_male_share_about_65_percent(gen):
    share = gen["opening"].groupby("status").sex.apply(lambda s: (s == "M").mean())
    assert share.between(0.58, 0.72).all()


# --- 2025 movements ------------------------------------------------------------

def test_salary_experience_a_little_above_assumption(gen):
    inc = gen["movements"].query("event == 'salary_increase'")
    rise = inc.new_value / inc.old_value - 1
    assert 0.030 < rise.mean() < 0.040


def test_actives_reaching_65_retire(gen):
    op = gen["opening"].set_index("member_id")
    retired = gen["movements"].query("event == 'retirement' and old_status == 'A'")
    for _, m in retired.iterrows():
        dob = pd.Timestamp(op.loc[m.member_id, "date_of_birth"])
        assert pd.Timestamp(m.event_date) == dob + pd.DateOffset(years=65)
    active_close = gen["closing_true"].query("status == 'A'")
    assert (age_at(active_close.date_of_birth, CLOSING) < 65).all()


def test_retirement_pension_follows_scheme_rules(gen):
    """Active retiring at 65: min(n, 40)/60 x max(salary - 1.5 x SPC, 0)."""
    cl = gen["closing_true"].set_index("member_id")
    retired = gen["movements"].query("event == 'retirement' and old_status == 'A'")
    spc = data_gen.spc_annual(load_config("statutory_ie"), date(2025, 1, 1))
    for mid in retired.member_id:
        m = cl.loc[mid]
        salary = gen["movements"].query("member_id == @mid and event == 'salary_increase'").new_value.iloc[0]
        expected = min(m.pensionable_service, 40) / 60 * max(salary - 1.5 * spc, 0)
        assert m.pension_in_payment == pytest.approx(round(expected, 2), abs=0.01)


def test_pensions_in_payment_increased_by_2024_cpi(gen):
    """1 January 2025 increase = 2024 CPI annual average (2.1%), floor 0, cap 3%."""
    op = gen["opening"].query("status == 'P'").set_index("member_id")
    cl = gen["closing_true"].set_index("member_id")
    both = op.index.intersection(cl.index)
    ratio = cl.loc[both, "pension_in_payment"] / op.loc[both, "pension_in_payment"]
    assert np.allclose(ratio, 1.021, atol=1e-4)


def test_statutory_revaluation_example():
    """Pensions Authority preservation notes para 155: leave 1 July 2001, EUR 10,000 -> 4% x 6/12 in 2001, then full years."""
    table = pd.Series({2001: 4.0, 2002: 4.0, 2003: 2.8, 2004: 2.2, 2005: 1.9, 2006: 2.6})
    factor = benefits.revaluation_factor(date(2001, 7, 1), 2006, table)
    assert round(10_000 * factor) == 11_652


def test_deaths_and_withdrawals_happen(gen):
    ev = gen["movements"].event.value_counts()
    assert ev.get("death", 0) >= 3 and ev.get("withdrawal", 0) >= 1 and ev.get("retirement", 0) >= 5


# --- injected errors -----------------------------------------------------------

def test_every_error_type_injected(gen):
    key = gen["answer_key"]
    expected = load_config("data_gen")["errors"]
    assert key.error_type.value_counts().to_dict() == expected
    assert 15 <= len(key) <= 25   # about 2% of 1,000


def test_raw_extract_is_truth_plus_errors(gen):
    raw, true, key = gen["closing_raw"], gen["closing_true"], gen["answer_key"]
    n_extra = key.error_type.isin(["duplicate_member_id", "untraceable_record"]).sum()
    assert len(raw) == len(true) + n_extra
    assert set(key.member_id) <= set(raw.member_id)
    untouched = raw[~raw.member_id.isin(key.member_id)].set_index("member_id")
    pd.testing.assert_frame_equal(untouched, true.set_index("member_id").loc[untouched.index])
