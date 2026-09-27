"""SPEC §9 M4-M6: three representative members recomputed in live Excel formulas agree with Python within EUR 1."""
import pytest

from helpers import VALUATION, clean_members, make_basis
from pension import excel_build, ias19


@pytest.fixture(scope="module")
def workbook(tmp_path_factory):
    from pycel import ExcelCompiler
    path = tmp_path_factory.mktemp("xl") / "excel_checks.xlsx"
    excel_build.build(clean_members(), make_basis(), 0.0375, ias19.curve(VALUATION), path)
    return ExcelCompiler(filename=str(path))


@pytest.mark.parametrize("row,label", [(2, "Pensioner"), (3, "Deferred"), (4, "Active")])
def test_engine_matches_excel_within_one_euro(workbook, row, label):
    python_pv = workbook.evaluate(f"Check!C{row}")
    excel_pv = workbook.evaluate(f"Check!D{row}")
    print(f"{label}: Python {python_pv:,.2f}  Excel {excel_pv:,.2f}")
    assert abs(excel_pv - python_pv) < 1.0


@pytest.mark.parametrize("row,label", [(2, "Pensioner"), (3, "Deferred"), (4, "Active")])
def test_ias19_curve_pv_matches_excel_within_one_euro(workbook, row, label):
    python_pv = workbook.evaluate(f"Check!F{row}")
    excel_pv = workbook.evaluate(f"Check!G{row}")
    print(f"{label} (IAS 19 curve): Python {python_pv:,.2f}  Excel {excel_pv:,.2f}")
    assert abs(excel_pv - python_pv) < 1.0
