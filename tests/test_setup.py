"""M0 scaffold checks (SPEC §10): config files exist and parse."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ["scheme_rules", "assumptions_ias19", "statutory_ie",
           "assumptions_insurer", "assets", "scenarios"]


def test_config_files_parse():
    for name in CONFIGS:
        path = ROOT / "config" / f"{name}.yaml"
        assert path.exists(), path
        yaml.safe_load(path.read_text())


def test_scheme_rules_match_spec_5():
    rules = yaml.safe_load((ROOT / "config" / "scheme_rules.yaml").read_text())
    assert rules["accrual_fraction"] == 60
    assert rules["normal_retirement_age"] == 65
    assert rules["pension_increases"]["cap"] == 0.03


def test_register_header():
    header = (ROOT / "data" / "assumptions_register.csv").read_text().splitlines()[0]
    assert header == "name,value,basis,source,effective_date,retrieval_date,used_in"
