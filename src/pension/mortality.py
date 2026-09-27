"""Mortality (SPEC §8, M3): ILT15 base table with multipliers and improvements."""
import numpy as np

from pension.io import read_market


def ilt15_qx():
    """ILT15 q(x) for ages 0-105 as {'M': array, 'F': array}, indexed by age."""
    t = read_market("ilt15")
    return {sex: t[t.sex == sex].sort_values("age").qx.to_numpy() for sex in ("M", "F")}


def q_year(base_qx, age, sex, year, multiplier, improvement, base_year):
    """q(x, y) = multiplier[sex] x q_base(x) x (1 - improvement)^max(y - base_year, 0), for one calendar year y.

    age: integer ages (array); sex: 'M'/'F' (array). Ages above the table's last age use the last age.
    """
    age = np.minimum(np.asarray(age, dtype=int), len(base_qx["M"]) - 1)
    sex = np.asarray(sex)
    q_base = np.where(sex == "M", base_qx["M"][age], base_qx["F"][age])
    mult = np.where(sex == "M", multiplier["M"], multiplier["F"])
    factor = (1 - improvement) ** max(year - base_year, 0)
    return np.minimum(mult * q_base * factor, 1.0)
