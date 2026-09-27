"""M4 acceptance tests (SPEC §9 M4): benefit and cash-flow engine."""
import numpy as np
import pytest

from helpers import clean_members, make_basis
from pension import benefits, cashflows
from pension.curves import FlatRate
from pension.io import load_config
from pension.mortality import Mortality

NO_DEATHS = Mortality({"M": 0.0, "F": 0.0}, 0.0, 2014)


@pytest.fixture(scope="module")
def members():
    return clean_members()


def one(members, status, **conditions):
    m = members[members.status == status]
    for col, (low, high) in conditions.items():
        m = m[(m[col] >= low) & (m[col] <= high)]
    return m.head(1).reset_index(drop=True)


def test_zero_interest_zero_mortality_pv_equals_sum_of_payments(members):
    basis = make_basis(mortality_pre=NO_DEATHS, mortality_post=NO_DEATHS, withdrawal=None)
    cf = cashflows.project_cashflows(members, basis)
    assert cashflows.pv(cf, FlatRate(0.0)).sum() == pytest.approx(cf.sum(), rel=1e-12)


def test_pensioner_payments_without_mortality(members):
    """P x 1.022 in 2026 (known increase), then x (1 + e) each year."""
    basis = make_basis(mortality_pre=NO_DEATHS, mortality_post=NO_DEATHS)
    p = one(members, "P", age=(70, 75))
    cf = cashflows.project_cashflows(p, basis)[0]
    e = basis.pension_increase
    assert cf[0] == pytest.approx(p.pension[0] * 1.022)
    assert cf[1] == pytest.approx(p.pension[0] * 1.022 * (1 + e))
    assert cf[9] == pytest.approx(p.pension[0] * 1.022 * (1 + e) ** 9)


def test_pensioner_payment_uses_average_survival(members):
    basis = make_basis()
    p = one(members, "P", age=(80, 85))
    s = basis.mortality_post.survival(p.age.to_numpy(), p.sex.to_numpy(), 2026, 2)[0]
    cf = cashflows.project_cashflows(p, basis)[0]
    assert cf[1] == pytest.approx(p.pension[0] * 1.022 * (1 + basis.pension_increase) * (s[1] + s[2]) / 2)


def test_deferred_hand_calculation(members):
    """Pension at exit x official revaluation to 2025 x (1 + r)^T, paid from year T + 1."""
    basis = make_basis(mortality_pre=NO_DEATHS, mortality_post=NO_DEATHS)
    d = one(members, "D", T=(10, 20)).iloc[0]
    factor = benefits.revaluation_factor(d.date_left, 2025, basis.revaluation_history)
    b65 = d.deferred_pension_at_exit * factor * (1 + basis.revaluation) ** d["T"]
    cf = cashflows.project_cashflows(one(members, "D", T=(10, 20)), basis)[0]
    assert np.all(cf[: d["T"]] == 0)
    assert cf[d["T"]] == pytest.approx(b65)
    assert cf[d["T"] + 1] == pytest.approx(b65 * (1 + basis.pension_increase))


def test_active_retirement_only_hand_calculation(members):
    """Active aged 55+ (no withdrawal): n/60 x max(S(1+g)^T - 1.5 SPC(1+pi)^(T-1), 0), paid from T + 1."""
    basis = make_basis(mortality_pre=NO_DEATHS, mortality_post=NO_DEATHS)
    a = one(members, "A", age=(58, 62))
    row = a.iloc[0]
    T, g, pi = row["T"], basis.salary_growth, basis.inflation
    ps = max(row.salary * (1 + g) ** T - 1.5 * basis.spc_next_year * (1 + pi) ** (T - 1), 0)
    pension = min(row.service, 40) / 60 * ps
    cf = cashflows.project_cashflows(a, basis)[0]
    assert np.all(cf[:T] == 0)
    assert cf[T] == pytest.approx(pension)


def test_member_totals_equal_scheme_total(members):
    basis = make_basis()
    cf = cashflows.project_cashflows(members, basis)
    by_member = cashflows.pv(cf, FlatRate(0.035)).sum()
    scheme = cashflows.pv(cf.sum(axis=0, keepdims=True), FlatRate(0.035))[0]
    assert by_member == pytest.approx(scheme, rel=1e-12)


def test_zero_salary_growth_changes_only_actives(members):
    base = cashflows.project_cashflows(members, make_basis())
    flat = cashflows.project_cashflows(members, make_basis(salary_growth=0.0))
    changed = np.abs(base - flat).sum(axis=1) > 1e-9
    assert set(members.status[changed]) == {"A"}
    assert (flat.sum() < base.sum())


def test_cpi_5_percent_gives_revaluation_4_and_increases_3():
    rules = load_config("scheme_rules")
    assert benefits.scheme_rates(0.05, rules) == (0.04, 0.03)
    assert benefits.scheme_rates(-0.01, rules) == (-0.01, 0.0)
    assert benefits.scheme_rates(0.019, rules) == (0.019, 0.019)


def test_actives_as_leavers_have_no_salary_growth(members):
    """Leaver basis: the benefit does not depend on salary growth or withdrawal rates."""
    a = one(members, "A", age=(40, 50))
    lv = make_basis(actives_as_leavers=True)
    cf1 = cashflows.project_cashflows(a, lv)
    cf2 = cashflows.project_cashflows(a, lv.with_(salary_growth=0.10, withdrawal=None))
    assert np.allclose(cf1, cf2)


def test_service_increment_raises_actives_only(members):
    base = cashflows.project_cashflows(members, make_basis())
    plus = cashflows.project_cashflows(members, make_basis(service_increment=1.0))
    changed = np.abs(plus - base).sum(axis=1) > 1e-9
    assert set(members.status[changed]) == {"A"}
