"""M2 acceptance tests (SPEC §9 M2): data checks find every injected error; membership reconciles."""
import pandas as pd
import pytest

from pension import data_checks
from pension.io import FIXTURES, MEMBERS

# answer-key error type -> rule that must flag it
EXPECTED_RULE = {
    "missing_date_of_birth": "completeness",
    "duplicate_member_id": "uniqueness",
    "birth_after_joining": "date_order",
    "service_exceeds_age_minus_18": "service_vs_age",
    "pensioner_zero_pension": "pension_positive",
    "deferred_with_salary": "deferred_no_salary",
    "salary_extra_zero": "salary_range",
    "active_with_retirement_date": "active_no_exit_date",
    "untraceable_record": "traceability",
}


@pytest.fixture(scope="module")
def result():
    return data_checks.run(
        pd.read_csv(MEMBERS / "members_2025_raw.csv", dtype=str),
        pd.read_csv(MEMBERS / "members_2024.csv", dtype=str),
        pd.read_csv(MEMBERS / "movements_2025.csv", dtype=str),
    )


@pytest.fixture(scope="module")
def key():
    return pd.read_csv(FIXTURES / "injected_errors.csv")


def test_every_injected_error_found(result, key):
    found = set(zip(result["issues"].member_id, result["issues"].rule))
    missed = [(m, e) for m, e in zip(key.member_id, key.error_type) if (m, EXPECTED_RULE[e]) not in found]
    print(f"injected {len(key)}, issues logged {len(result['issues'])}, missed {missed}")
    assert not missed


def test_no_false_positives(result, key):
    assert set(result["issues"].member_id) <= set(key.member_id)


def test_every_issue_has_an_action(result):
    assert result["issues"].action.str.len().gt(0).all()


def test_clean_data_equals_truth(result):
    truth = pd.read_csv(FIXTURES / "members_2025_true.csv", dtype=str).set_index("member_id").sort_index()
    clean = result["clean"].set_index("member_id").sort_index()
    pd.testing.assert_frame_equal(clean, truth)


def test_membership_reconciliation_differences_zero(result):
    rec = result["reconciliation"]
    assert (rec["difference"] == 0).all()
    assert rec.loc["total", "closing"] == len(result["clean"])


def test_reconciliation_matrix_matches_movements(result):
    mv = pd.read_csv(MEMBERS / "movements_2025.csv")
    exits = mv[mv.event.isin(["withdrawal", "retirement", "death"])]
    matrix = result["matrix"]
    for (old, new), n in exits.groupby(["old_status", "new_status"]).size().items():
        assert matrix.loc[old, new] == n
