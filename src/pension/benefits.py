"""Scheme benefit rules (SPEC §5): accrued pension and the statutory revaluation of preserved benefits."""
from datetime import date


def accrued_pension(service, salary, spc, rules):
    """Pension = min(n, max years) / accrual x max(salary - offset x SPC, 0)  (SPEC §5)."""
    n = min(service, rules["max_service_years"])
    pensionable_salary = max(salary - rules["spc_offset_multiple"] * spc, 0.0)
    return n / rules["accrual_fraction"] * pensionable_salary


def complete_months_to_year_end(left):
    """Complete calendar months from the leaving date to 31 December (1 July -> 6; 15 July -> 5; 1 December -> 1)."""
    return 12 - left.month + (1 if left.day == 1 else 0)


def revaluation_factor(date_left, last_revaluation_year, pct_by_year):
    """Cumulative statutory revaluation of a preserved benefit (Pensions Act s33; Pensions Authority
    preservation notes paras 151-155).

    First revaluation year = year of leaving, pro rata by complete months to the year end.
    Later years: the full percentage, compounded. pct_by_year is in percent, indexed by year.
    """
    if last_revaluation_year < date_left.year:
        return 1.0
    factor = 1.0 + pct_by_year[date_left.year] / 100 * complete_months_to_year_end(date_left) / 12
    for year in range(date_left.year + 1, last_revaluation_year + 1):
        factor *= 1.0 + pct_by_year[year] / 100
    return factor


def last_revaluation_year(payment_date):
    """Last complete calendar year ending before the date benefits come into payment."""
    return payment_date.year - 1


def birthday(dob, age):
    """Date of the given birthday (29 February -> 28 February in non-leap years)."""
    try:
        return dob.replace(year=dob.year + age)
    except ValueError:
        return date(dob.year + age, 2, 28)


def scheme_rates(cpi, rules):
    """Deferred revaluation and pension increase implied by an assumed CPI (SPEC §5):
    revaluation = min(CPI, 4%) (can be negative); increases = min(max(CPI, 0%), 3%)."""
    reval = rules["revaluation"]
    revaluation = min(cpi, reval["cap"]) if reval["floor"] is None else min(max(cpi, reval["floor"]), reval["cap"])
    inc = rules["pension_increases"]
    increase = min(max(cpi, inc["floor"]), inc["cap"])
    return revaluation, increase
