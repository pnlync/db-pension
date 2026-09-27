"""SPEC §9 M4-M6: three representative members recomputed in live Excel formulas agree with Python within EUR 1
(engine at a flat rate, IAS 19 on the curve, Section 34 transfer values and the annuity cost proxy)."""
import pytest

from helpers import VALUATION, clean_members
from pension import excel_build, ias19

ROWS = list(range(2, 11))


@pytest.fixture(scope="module")
def workbook(tmp_path_factory):
    from pycel import ExcelCompiler
    path = tmp_path_factory.mktemp("xl") / "excel_checks.xlsx"
    excel_build.build(clean_members(), ias19.basis(VALUATION), 0.0375, ias19.curve(VALUATION), path)
    return ExcelCompiler(filename=str(path))


@pytest.mark.parametrize("row", ROWS)
def test_python_matches_excel_within_one_euro(workbook, row):
    label = f"{workbook.evaluate(f'Check!A{row}')} / {workbook.evaluate(f'Check!C{row}')}"
    python_value = workbook.evaluate(f"Check!D{row}")
    excel_value = workbook.evaluate(f"Check!E{row}")
    print(f"{label}: Python {python_value:,.2f}  Excel {excel_value:,.2f}")
    assert abs(excel_value - python_value) < 1.0
