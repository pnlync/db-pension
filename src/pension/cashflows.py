"""M4 benefit and cash-flow engine (SPEC §4, §9 M4).

project_cashflows(members, basis) -> expected benefit payments by member and year; pv(...) discounts them.

Conventions (SPEC §4, notes/M4):
- Annual grid. Year t (t = 1, 2, ...) is calendar year valuation_year + t; payments at t - 0.5.
- Ages: age nearest birthday at the valuation date, x. Years to 65: T = 65 - x (at least 1 for actives).
- Salary in year t = S (1 + g)^t (S = salary in the valuation year); SPC in year t = SPC_1 (1 + pi)^(t - 1).
- Actives leave or die mid-year; leavers' first-year revaluation is 6/12 of that year's rate.
- Non-pensioners start their pension in year T + 1; pensions rise on 1 January from the year after they start.
- Payment in year t uses the average of survival to t - 1 and to t.
- Only service to the valuation date counts (PUC); service_increment = 1 gives the DBO with one more year.
"""
from dataclasses import dataclass, field, replace
from datetime import date

import numpy as np
import pandas as pd

from pension import benefits

HORIZON = 100   # years; everyone is dead by 120


@dataclass(frozen=True)
class Basis:
    """Everything that turns member data into expected cash flows. Discounting is separate (see pv)."""

    name: str
    valuation_date: date
    rules: dict                       # scheme_rules.yaml
    inflation: float                  # pi: SPC projection
    salary_growth: float              # g
    revaluation: float                # deferred revaluation after the valuation year (a year)
    pension_increase: float           # increases in payment after known years (a year)
    mortality_pre: object             # Mortality before 65
    mortality_post: object            # Mortality from 65 (and for pensioners)
    spc_next_year: float              # SPC in force in year 1 (annual)
    withdrawal: object = None         # callable(age array) -> q_w, or None
    known_increases: dict = field(default_factory=dict)   # {calendar year: increase already determined}
    revaluation_history: object = None                     # official % by revaluation year (pd.Series)
    actives_as_leavers: bool = False  # Funding Standard / bridge step 1: actives leave at the valuation date
    annuity_loading: dict = None      # {'M', 'F', 'base_year'}: Section 34 loading on post-65 values
    service_increment: float = 0.0    # extra years of service (1 for the service cost)

    def with_(self, **changes):
        return replace(self, **changes)

    @property
    def year(self):
        return self.valuation_date.year


def ias19_withdrawal(cfg):
    """q_w(age) = max(0, rate_at_35 - slope x (age - 35)) below zero_from_age, else 0 (SPEC §8.1)."""
    def q(age):
        age = np.asarray(age, dtype=float)
        rate = np.maximum(0.0, cfg["rate_at_35"] - cfg["slope_per_year"] * (age - 35))
        return np.where(age < cfg["zero_from_age"], rate, 0.0)
    return q


# --- member preparation ---------------------------------------------------------------

def prepare_members(df, valuation_date, nra=65):
    """Clean member data -> the fields the engine uses (one row per member)."""
    m = pd.DataFrame({"member_id": df.member_id, "status": df.status, "sex": df.sex})
    dob = pd.to_datetime(df.date_of_birth)
    exact_age = (pd.Timestamp(valuation_date) - dob).dt.days / 365.25
    m["age"] = np.floor(exact_age + 0.5).astype(int)                      # age nearest birthday
    years_to_nra = np.maximum(nra - m.age, 0)
    m["T"] = np.where(m.status == "A", np.maximum(years_to_nra, 1), years_to_nra)   # actives: at least 1 year
    m["service"] = pd.to_numeric(df.pensionable_service)
    m["salary"] = pd.to_numeric(df.salary)
    m["pension"] = pd.to_numeric(df.pension_in_payment)
    m["deferred_pension_at_exit"] = pd.to_numeric(df.deferred_pension_at_exit)
    m["date_left"] = pd.to_datetime(df.date_left).dt.date
    return m.reset_index(drop=True)


# --- building blocks ---------------------------------------------------------------------

def survival_split(basis, age, sex, T, horizon):
    """Survival from the valuation date, t = 0..horizon: pre-retirement mortality for years 1..T, then post."""
    pre = basis.mortality_pre.survival(age, sex, basis.year + 1, horizon)
    post = basis.mortality_post.survival(age, sex, basis.year + 1, horizon)
    s = np.ones((len(age), horizon + 1))
    for i in range(len(age)):
        Ti = min(T[i], horizon)
        s[i, : Ti + 1] = pre[i, : Ti + 1]
        if Ti < horizon:
            # after 65: continue from s[T] with post-retirement one-year survival ratios
            ratios = post[i, Ti + 1:] / np.where(post[i, Ti:-1] > 0, post[i, Ti:-1], 1.0)
            s[i, Ti + 1:] = pre[i, Ti] * np.cumprod(ratios)
    return s


def increase_rate(basis, calendar_year):
    return basis.known_increases.get(calendar_year, basis.pension_increase)


def pension_path_from(basis, first_payment_year, horizon):
    """Index of a pension that starts in year first_payment_year (level that year), rising on each later 1 January.

    Returns an array over t = 0..horizon (zero before the start)."""
    path = np.zeros(horizon + 1)
    level = 1.0
    for t in range(first_payment_year, horizon + 1):
        if t > first_payment_year:
            level *= 1 + increase_rate(basis, basis.year + t)
        path[t] = level
    return path


def pay_mid_year(amount_index, s, s_start):
    """Expected payments over t = 1..H: amount x average survival over the year, relative to survival at s_start."""
    avg = (s[:-1] + s[1:]) / 2
    return amount_index[1:] * avg / s_start


def loading_factor(basis, sex, T):
    if not basis.annuity_loading:
        return 1.0
    years = max(basis.year + T - basis.annuity_loading["base_year"], 0)
    return (1 + basis.annuity_loading[sex]) ** years


def pensionable_salary(basis, salary, spc):
    return max(salary - basis.rules["spc_offset_multiple"] * spc, 0.0)


def accrued(basis, service, salary, spc):
    return benefits.accrued_pension(service, salary, spc, basis.rules)


# --- projection by status ------------------------------------------------------------------

def project_pensioner(basis, m, s, H):
    path = np.zeros(H + 1)
    level = 1.0
    for t in range(1, H + 1):
        level *= 1 + increase_rate(basis, basis.year + t)   # 1 January increase each year
        path[t] = level
    return m.pension * pay_mid_year(path, s, 1.0)


def deferred_b65(basis, pension_at_valuation, T):
    """Revalue from the valuation date to 65: T full revaluation years at the assumed rate."""
    return pension_at_valuation * (1 + basis.revaluation) ** T


def project_deferred(basis, m, s, H):
    history = basis.revaluation_history
    factor = benefits.revaluation_factor(m.date_left, basis.year, history)
    b65 = deferred_b65(basis, m.deferred_pension_at_exit * factor, m.T)
    path = pension_path_from(basis, m.T + 1, H)
    return b65 * loading_factor(basis, m.sex, m.T) * pay_mid_year(path, s, 1.0)


def project_leaver_today(basis, m, s, H):
    """Active treated as leaving at the valuation date: deferred pension on current salary and service."""
    service = m.service + basis.service_increment
    b_now = accrued(basis, service, m.salary, basis.spc_next_year)
    b65 = deferred_b65(basis, b_now, m.T)
    path = pension_path_from(basis, m.T + 1, H)
    return b65 * loading_factor(basis, m.sex, m.T) * pay_mid_year(path, s, 1.0)


def project_active(basis, m, s, H):
    """Three outcomes each year until 65: withdraw (deferred pension), die (nothing), retire at 65."""
    T, g, pi, r = m.T, basis.salary_growth, basis.inflation, basis.revaluation
    service = m.service + basis.service_increment
    path = pension_path_from(basis, T + 1, H)
    load = loading_factor(basis, m.sex, T)
    cf = np.zeros(H)
    in_service = 1.0
    for t in range(1, T + 1):
        age_start = m.age + t - 1
        q_d = 1 - s[t] / s[t - 1]
        q_w = float(basis.withdrawal(age_start)) if basis.withdrawal else 0.0
        leavers = in_service * q_w
        in_service -= in_service * (q_d + q_w)
        if leavers > 0:
            salary_t = m.salary * (1 + g) ** t
            spc_t = basis.spc_next_year * (1 + pi) ** (t - 1)
            b_exit = accrued(basis, service, salary_t, spc_t)
            b65 = b_exit * (1 + r * 0.5) * (1 + r) ** (T - t)      # exit mid-year: 6/12 of year t's rate
            alive_end_year = leavers * (1 - q_d / 2)                   # survive the rest of the exit year
            cf += alive_end_year * b65 * load * pay_mid_year(path, s, s[t])
    salary_T = m.salary * (1 + g) ** T
    spc_T = basis.spc_next_year * (1 + pi) ** (T - 1)
    retirement_pension = accrued(basis, service, salary_T, spc_T)
    cf += in_service * retirement_pension * load * pay_mid_year(path, s, s[T])
    return cf


def project_cashflows(members, basis, horizon=HORIZON):
    """Expected benefit payments, shape (members, horizon); column t-1 is paid at t - 0.5."""
    age, sex = members.age.to_numpy(), members.sex.to_numpy()
    T = members["T"].to_numpy()
    s_all = survival_split(basis, age, sex, T, horizon)
    cf = np.zeros((len(members), horizon))
    for i, m in enumerate(members.itertuples(index=False)):
        s = s_all[i]
        if m.status == "P":
            cf[i] = project_pensioner(basis, m, s, horizon)
        elif m.status == "D":
            cf[i] = project_deferred(basis, m, s, horizon)
        elif basis.actives_as_leavers:
            cf[i] = project_leaver_today(basis, m, s, horizon)
        else:
            cf[i] = project_active(basis, m, s, horizon)
    return cf


# --- discounting ----------------------------------------------------------------------------

def payment_times(horizon=HORIZON):
    return np.arange(1, horizon + 1) - 0.5


def pv(cf, discount):
    """Present value by member. discount: object with .discount(times), or an array (horizon,) or (members, horizon)."""
    if hasattr(discount, "discount"):
        discount = discount.discount(payment_times(cf.shape[1]))
    return (cf * discount).sum(axis=1)


def split_discount_factors(T, pre_rate, post_rate, horizon=HORIZON):
    """Section 34 discounting per member: pre_rate to 65 (T years), post_rate after. Shape (members, horizon)."""
    times = payment_times(horizon)
    T = np.asarray(T, dtype=float)[:, None]
    before = (1 + pre_rate) ** -np.minimum(times, T)
    after = (1 + post_rate) ** -np.maximum(times - T, 0)
    return before * after
