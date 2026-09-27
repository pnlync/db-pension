"""Asset model (SPEC §8.3): each bond class is one annual-coupon bond with the target duration, revalued on its
curve (AAA for sovereigns, AAA + spread for corporates, the real curve for inflation-linked); equities and cash
are held at market value.
"""
from dataclasses import dataclass

import numpy as np

from pension.curves import Curve
from pension.io import load_config, read_market

BOND_CLASSES = ("nominal_sovereigns", "long_sovereigns", "inflation_linked_sovereigns", "corporates")
NOMINAL_SOVEREIGN = ("nominal_sovereigns", "long_sovereigns")   # valued on the AAA curve


def config():
    return load_config("assets")


def market_inflation(valuation_date):
    t = read_market("mva_section34").set_index("date")
    row = t.loc[valuation_date.isoformat()]
    return (1 + row.oat_nominal_pct / 100) / (1 + row.oat_real_pct / 100) - 1


@dataclass(frozen=True)
class Market:
    """The curves assets are revalued on at one date. shift: parallel shift of nominal and real yields."""
    aaa: Curve
    inflation: float
    corporate_spread: float
    shift: float = 0.0

    @classmethod
    def at(cls, valuation_date, curve_date):
        return cls(Curve.ecb(curve_date), market_inflation(valuation_date), config()["corporate_spread"])

    def shifted(self, shift):
        return Market(self.aaa, self.inflation, self.corporate_spread, self.shift + shift)

    def discount(self, bond_class, t):
        t = np.asarray(t, dtype=float)
        if bond_class in NOMINAL_SOVEREIGN:
            return self.aaa.shifted(self.shift).discount(t)
        if bond_class == "corporates":
            return self.aaa.with_spread(self.corporate_spread).shifted(self.shift).discount(t)
        # real curve: (1 + nominal spot) / (1 + inflation) - 1, flat inflation (limitation)
        nominal = self.aaa.shifted(self.shift).discount(t)
        return nominal * (1 + self.inflation) ** t


@dataclass(frozen=True)
class Bond:
    coupon: float
    maturity: int

    def cashflows(self):
        t = np.arange(1, self.maturity + 1)
        cf = np.full(self.maturity, self.coupon)
        cf[-1] += 1.0
        return t, cf

    def price(self, market, bond_class):
        t, cf = self.cashflows()
        return float((cf * market.discount(bond_class, t)).sum())

    def duration(self, market, bond_class):
        """Modified duration from a 1 bp parallel shift."""
        p0 = self.price(market, bond_class)
        p1 = self.price(market.shifted(-0.0001), bond_class)
        return (p1 - p0) / p0 / 0.0001


def par_bond(market, bond_class, maturity):
    """Annual-coupon bond priced at par on the class curve."""
    df = market.discount(bond_class, np.arange(1, maturity + 1))
    return Bond((1 - df[-1]) / df.sum(), maturity)


def bond_with_duration(market, bond_class, target):
    """The par bond whose modified duration is closest to the target (integer maturities 1-50)."""
    bonds = [par_bond(market, bond_class, m) for m in range(1, 51)]
    return min(bonds, key=lambda b: abs(b.duration(market, bond_class) - target))


@dataclass
class Portfolio:
    """Holdings: units of each class's bond, plus equity and cash values."""
    bonds: dict        # class -> Bond
    units: dict        # class -> units (face)
    equities: float
    cash: float

    @classmethod
    def from_allocation(cls, total, allocation, market, durations):
        bonds, units = {}, {}
        for c in BOND_CLASSES:
            bonds[c] = bond_with_duration(market, c, durations[c])
            units[c] = allocation.get(c, 0.0) * total / bonds[c].price(market, c)
        return cls(bonds, units, allocation.get("equities", 0.0) * total, allocation.get("cash", 0.0) * total)

    def values(self, market, equity_factor=1.0):
        v = {c: self.units[c] * self.bonds[c].price(market, c) for c in BOND_CLASSES}
        v["equities"] = self.equities * equity_factor
        v["cash"] = self.cash
        return v

    def total(self, market, equity_factor=1.0):
        return sum(self.values(market, equity_factor).values())

    def qualifying(self, market):
        q = config()["qualifying_for_fsr"]
        return sum(v for k, v in self.values(market).items() if k in q)

    def pv01(self, market, classes=BOND_CLASSES):
        up = self.values(market.shifted(-0.0001))
        base = self.values(market)
        return sum(up[c] - base[c] for c in classes)


def durations():
    return config()["bond_durations"]


def closing_portfolio(total, market, allocation=None):
    return Portfolio.from_allocation(total, allocation or config()["allocation"], market, durations())
