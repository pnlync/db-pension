"""Paths and readers for config/*.yaml and the sourced data files in data/market/."""
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
MARKET = ROOT / "data" / "market"
MEMBERS = ROOT / "data" / "members"
OUTPUTS = ROOT / "outputs"
FIXTURES = ROOT / "tests" / "fixtures"


def load_config(name):
    """config/<name>.yaml as a dict."""
    return yaml.safe_load((CONFIG / f"{name}.yaml").read_text())


def read_market(name):
    """data/market/<name>.csv; the '# key: value' header lines (source, dates) are skipped."""
    return pd.read_csv(MARKET / f"{name}.csv", comment="#")


def statutory_revaluation():
    """Official revaluation percentage (in %) by revaluation year, Pensions Act s33."""
    t = read_market("revaluation_ie")
    return t.set_index("revaluation_year")["pct"]


def cpi_annual_average():
    """CPI annual average change (in %) by calendar year: the scheme's 'CPI' for pension increases."""
    t = read_market("cpi_ie")
    return t.set_index("year")["pct_annual_avg"]
