"""Mortality (SPEC §8, M3): ILT15 base table, multipliers, improvements, cohort survival, life expectancy
and the longevity stress k.

q(x, y) = k x multiplier[sex] x q_ILT15(x) x (1 - improvement)^max(y - base_year, 0), capped at 1,
followed along the cohort diagonal: a member aged x in year y is x + 1 in year y + 1.
"""
from functools import lru_cache

import numpy as np
from scipy.optimize import brentq

from pension.io import read_market

MAX_AGE = 120
EXTRAPOLATION_FIT_YEARS = 10   # geometric growth of q fitted over ILT15 ages 95-105


def ilt15_qx():
    """ILT15 q(x) for ages 0-105 as {'M': array, 'F': array}, indexed by age."""
    t = read_market("ilt15")
    return {sex: t[t.sex == sex].sort_values("age").qx.to_numpy() for sex in ("M", "F")}


@lru_cache(maxsize=1)
def extended_ilt15():
    """ILT15 extended from 105 to 120: q grows geometrically at its 95-105 rate, capped at 1; q(120) = 1."""
    out = {}
    for sex, q in ilt15_qx().items():
        last = len(q) - 1
        growth = (q[last] / q[last - EXTRAPOLATION_FIT_YEARS]) ** (1 / EXTRAPOLATION_FIT_YEARS)
        extra = [min(q[last] * growth ** n, 1.0) for n in range(1, MAX_AGE - last + 1)]
        full = np.concatenate([q, extra])
        full[MAX_AGE] = 1.0
        out[sex] = full
    return out


def q_year(base_qx, age, sex, year, multiplier, improvement, base_year):
    """q(x, y) for one calendar year y (used for simulated 2025 experience).

    age: integer ages (array); sex: 'M'/'F' (array). Ages above the table's last age use the last age.
    """
    age = np.minimum(np.asarray(age, dtype=int), len(base_qx["M"]) - 1)
    sex = np.asarray(sex)
    q_base = np.where(sex == "M", base_qx["M"][age], base_qx["F"][age])
    mult = np.where(sex == "M", multiplier["M"], multiplier["F"])
    factor = (1 - improvement) ** max(year - base_year, 0)
    return np.minimum(mult * q_base * factor, 1.0)


class Mortality:
    """A mortality basis: multiplier by sex, annual improvement from base_year, optional stress factor k."""

    def __init__(self, multiplier, improvement, base_year, k=1.0):
        self.multiplier = {"M": multiplier["M"], "F": multiplier["F"]}
        self.improvement = improvement
        self.base_year = base_year
        self.k = k
        self.table = extended_ilt15()

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg["multiplier"], cfg["improvement"], cfg["base_year"])

    def with_k(self, k):
        return Mortality(self.multiplier, self.improvement, self.base_year, k)

    def q(self, age, sex, year):
        """q for arrays of integer age and sex in calendar year(s) year."""
        age = np.minimum(np.asarray(age, dtype=int), MAX_AGE)
        sex = np.asarray(sex)
        q_base = np.where(sex == "M", self.table["M"][age], self.table["F"][age])
        mult = np.where(sex == "M", self.multiplier["M"], self.multiplier["F"])
        factor = (1 - self.improvement) ** np.maximum(np.asarray(year) - self.base_year, 0)
        q = self.k * mult * q_base * factor
        return np.where(age >= MAX_AGE, 1.0, np.minimum(q, 1.0))

    def survival(self, age, sex, first_year, horizon):
        """t_p_x for t = 0..horizon, shape (members, horizon + 1).

        Members are aged `age` (integer) at the start of `first_year`; year t runs over calendar year first_year + t - 1.
        """
        age, sex = np.asarray(age), np.asarray(sex)
        p = np.ones((len(age), horizon + 1))
        for t in range(1, horizon + 1):
            q = self.q(age + t - 1, sex, first_year + t - 1)
            p[:, t] = p[:, t - 1] * (1 - q)
        return p

    def e65_at_age(self, sex, age_now, first_year, retirement_age=65):
        """Complete life expectancy at 65 for someone aged age_now at the start of first_year (cohort)."""
        year_at_65 = first_year + (retirement_age - age_now)
        p = self.survival(np.array([retirement_age]), np.array([sex]), year_at_65, MAX_AGE - retirement_age)[0]
        return p[1:].sum() + 0.5

    def e65_now(self, sex, first_year):
        return self.e65_at_age(sex, 65, first_year)

    def longevity_k(self, sex="M", year=2026, extra_years=1.0):
        """k such that k x q raises e65 (male aged 65 now) by exactly extra_years (root finding)."""
        target = self.e65_now(sex, year) + extra_years
        return brentq(lambda k: self.with_k(k).e65_now(sex, year) - target, 0.3, 1.0, xtol=1e-12)
