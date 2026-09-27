"""Discount curves (SPEC §7.1): ECB AAA spot curve (annual effective) plus a constant spread; flat forward beyond 30y."""
import numpy as np

from pension.io import read_market


class Curve:
    """Spot curve on annual-effective rates. discount(t) for any t >= 0 (years).

    Between published tenors: linear interpolation of the spot rate. Beyond the last tenor: the last one-year
    forward rate is held flat (SPEC §7.1).
    """

    def __init__(self, tenors, spots, spread=0.0, shift=0.0, label=""):
        self.tenors = np.asarray(tenors, dtype=float)
        self.spots = np.asarray(spots, dtype=float)
        self.spread = spread
        self.shift = shift
        self.label = label

    @classmethod
    def ecb(cls, curve_date, spread=0.0):
        t = read_market(f"ecb_aaa_spot_{curve_date}")
        return cls(t.tenor_years, t.spot_annual, spread=spread, label=f"ECB AAA {curve_date}")

    def with_spread(self, spread):
        return Curve(self.tenors, self.spots, spread, self.shift, self.label)

    def shifted(self, shift):
        """Parallel shift of the whole curve (e.g. -0.0001 for PV01)."""
        return Curve(self.tenors, self.spots, self.spread, self.shift + shift, self.label)

    def spot(self, t):
        t = np.asarray(t, dtype=float)
        return np.interp(t, self.tenors, self.spots) + self.spread + self.shift

    def discount(self, t):
        t = np.asarray(t, dtype=float)
        last = self.tenors[-1]
        inside = (1 + self.spot(np.minimum(t, last))) ** -np.minimum(t, last)
        df_last = (1 + self.spot(last)) ** -last
        df_before = (1 + self.spot(last - 1)) ** -(last - 1)
        forward = df_before / df_last - 1
        beyond = df_last * (1 + forward) ** -(t - last)
        return np.where(t <= last, inside, beyond)


class FlatRate:
    """A single annual-effective rate (used for the SEDR and simple checks)."""

    def __init__(self, rate):
        self.rate = rate

    def discount(self, t):
        return (1 + self.rate) ** -np.asarray(t, dtype=float)
