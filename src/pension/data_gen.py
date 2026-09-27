"""M1 synthetic membership (SPEC §6): opening snapshot at 2024-12-31, simulated 2025 movements,
closing raw extract at 2025-12-31 with injected errors and a hidden answer key.

All member data and member experience are synthetic. Run: uv run python -m pension.data_gen
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from pension import benefits, mortality
from pension.io import FIXTURES, MEMBERS, cpi_annual_average, load_config, statutory_revaluation

COLUMNS = ["member_id", "status", "sex", "date_of_birth", "date_joined", "date_left", "date_retired",
           "salary", "pensionable_service", "deferred_pension_at_exit", "pension_in_payment"]
MOVEMENT_COLUMNS = ["member_id", "event", "event_date", "old_status", "new_status", "old_value", "new_value"]
DAYS_PER_YEAR = 365.25


def years_between(start, end):
    return (end - start).days / DAYS_PER_YEAR


def years_before(when, years):
    return when - timedelta(days=round(years * DAYS_PER_YEAR))


def years_after(when, years):
    return when + timedelta(days=round(years * DAYS_PER_YEAR))


def to_date(value):
    return date.fromisoformat(str(value))


def spc_annual(statutory, on_date):
    """State Pension (Contributory), annual, in force on the date (weekly rate x 52)."""
    spc = statutory["state_pension_contributory"]
    in_force = [r for r in spc["rates"] if to_date(r["effective_date"]) <= on_date]
    latest = max(in_force, key=lambda r: to_date(r["effective_date"]))
    return latest["weekly_eur"] * spc["weeks_per_year"]


def lognormal_clipped(rng, median, sigma, low, high, size):
    return np.clip(rng.lognormal(np.log(median), sigma, size), low, high)


def blank_member(member_id, status, sex, dob):
    return {"member_id": member_id, "status": status, "sex": sex, "date_of_birth": dob,
            "date_joined": None, "date_left": None, "date_retired": None, "salary": np.nan,
            "pensionable_service": np.nan, "deferred_pension_at_exit": np.nan, "pension_in_payment": np.nan}


# --- opening snapshot -------------------------------------------------------------

def make_actives(cfg, rng, opening):
    c = cfg["active"]
    n = c["count"]
    ages = np.clip(rng.normal(c["age_mean"], c["age_sd"], n), c["age_min"], c["age_max"])
    services = rng.uniform(c["service_min"], c["service_max"], n)
    salaries = lognormal_clipped(rng, c["salary_median"], c["salary_sigma"], c["salary_min"], c["salary_max"], n)
    sexes = np.where(rng.random(n) < cfg["male_share"], "M", "F")
    members = []
    for age, service, salary, sex in zip(ages, services, salaries, sexes):
        service = min(service, age - c["min_age_at_joining"])
        m = blank_member(None, "A", sex, years_before(opening, age))
        m["date_joined"] = years_before(opening, service)
        m["pensionable_service"] = round(years_between(m["date_joined"], opening), 4)
        m["salary"] = float(round(salary))
        members.append(m)
    return members


def make_deferreds(cfg, rng, opening):
    c = cfg["deferred"]
    closed = to_date(load_config("scheme_rules")["closed_to_new_entrants"])
    exit_from, exit_to = to_date(c["exit_from"]), to_date(c["exit_to"])
    members = []
    while len(members) < c["count"]:
        age = rng.uniform(c["age_min"], c["age_max"])
        dob = years_before(opening, age)
        earliest_exit = max(exit_from, years_after(dob, c["min_age_at_exit"]))
        left = earliest_exit + timedelta(days=int(rng.integers(0, (exit_to - earliest_exit).days + 1)))
        age_at_exit = years_between(dob, left)
        lowest = max(c["service_at_exit_min"], years_between(closed, left))   # joined by the closure date
        highest = age_at_exit - c["min_age_at_joining"]
        if lowest > highest:
            continue   # redraw: this exit date is impossible for a member of this age
        service = rng.uniform(lowest, highest)
        m = blank_member(None, "D", "M" if rng.random() < cfg["male_share"] else "F", dob)
        m["date_left"] = left
        m["date_joined"] = min(years_before(left, service), closed)
        m["pensionable_service"] = round(years_between(m["date_joined"], left), 4)
        m["deferred_pension_at_exit"] = round(float(lognormal_clipped(
            rng, c["pension_median"], c["pension_sigma"], c["pension_min"], c["pension_max"], 1)[0]), 2)
        members.append(m)
    return members


def make_pensioners(cfg, rng, opening):
    c = cfg["pensioner"]
    n = c["count"]
    ages = np.clip(c["age_min"] + rng.exponential(c["age_excess_mean"], n), c["age_min"], c["age_max"])
    services = rng.uniform(c["service_min"], c["service_max"], n)
    pensions = lognormal_clipped(rng, c["pension_median"], c["pension_sigma"], c["pension_min"], c["pension_max"], n)
    sexes = np.where(rng.random(n) < cfg["male_share"], "M", "F")
    nra = load_config("scheme_rules")["normal_retirement_age"]
    members = []
    for age, service, pension, sex in zip(ages, services, pensions, sexes):
        m = blank_member(None, "P", sex, years_before(opening, age))
        m["date_retired"] = min(benefits.birthday(m["date_of_birth"], nra), opening)
        m["date_joined"] = years_before(m["date_retired"], service)
        m["pensionable_service"] = round(years_between(m["date_joined"], m["date_retired"]), 4)
        m["pension_in_payment"] = round(float(pension), 2)
        members.append(m)
    return members


def make_opening(cfg, rng):
    opening = to_date(cfg["opening_date"])
    members = make_actives(cfg, rng, opening) + make_deferreds(cfg, rng, opening) + make_pensioners(cfg, rng, opening)
    order = rng.permutation(len(members))   # mix the statuses before numbering
    for number, i in enumerate(order, start=1):
        members[i]["member_id"] = f"M{number:04d}"
    return pd.DataFrame(members, columns=COLUMNS).sort_values("member_id").reset_index(drop=True)


# --- 2025 movements ---------------------------------------------------------------

def simulate_2025(opening_df, cfg, rng):
    """Apply one year of synthetic experience; returns (movements, closing snapshot).

    Salaries rise on 1 January; pensions in payment rise on 1 January by the 2024 CPI annual average
    (floor 0, cap 3%); withdrawals and deaths happen at mid-year; retirements on the 65th birthday.
    Decrement probabilities are the IAS 19 ones on the opening basis (SPEC §6.2).
    """
    rules, statutory, ias19 = load_config("scheme_rules"), load_config("statutory_ie"), load_config("assumptions_ias19")
    exp = cfg["experience_2025"]
    year_start, closing = date(2025, 1, 1), to_date(cfg["closing_date"])
    exit_date = to_date(exp["exit_date"])
    nra = rules["normal_retirement_age"]
    spc = spc_annual(statutory, year_start)
    increase = cpi_annual_average()[2024] / 100
    increase = min(max(increase, rules["pension_increases"]["floor"]), rules["pension_increases"]["cap"])
    revaluation = statutory_revaluation()
    base_qx = mortality.ilt15_qx()
    mort, wd = ias19["mortality"], ias19["withdrawal"]

    movements, closing_members = [], []

    def move(member_id, event, when, old_status, new_status, old_value=np.nan, new_value=np.nan):
        movements.append({"member_id": member_id, "event": event, "event_date": when, "old_status": old_status,
                          "new_status": new_status, "old_value": old_value, "new_value": new_value})

    for m in opening_df.to_dict("records"):
        m = dict(m)
        status, mid = m["status"], m["member_id"]
        age = int(years_between(m["date_of_birth"], year_start))            # age last birthday on 1 Jan 2025
        q_death = mortality.q_year(base_qx, [age], [m["sex"]], 2025, mort["multiplier"], mort["improvement"],
                                   mort["base_year"])[0]
        u = rng.random()
        salary_shock = rng.normal(exp["salary_increase_mean"], exp["salary_increase_sd"])
        birthday_nra = benefits.birthday(m["date_of_birth"], nra)
        reaches_nra = birthday_nra <= closing

        if status == "A":
            new_salary = float(round(m["salary"] * (1 + salary_shock)))
            move(mid, "salary_increase", year_start, "A", "A", m["salary"], new_salary)
            m["salary"] = new_salary
            q_withdraw = max(0.0, wd["rate_at_35"] - wd["slope_per_year"] * (age - 35)) if age < wd["zero_from_age"] else 0.0
            if reaches_nra:   # deaths before the birthday are ignored for these few members (limitation)
                service = round(years_between(m["date_joined"], birthday_nra), 4)
                pension = round(benefits.accrued_pension(service, new_salary, spc, rules), 2)
                move(mid, "retirement", birthday_nra, "A", "P", new_value=pension)
                m.update(status="P", date_retired=birthday_nra, salary=np.nan,
                         pensionable_service=service, pension_in_payment=pension)
            elif u < q_death:
                move(mid, "death", exit_date, "A", "died")
                continue
            elif u < q_death + q_withdraw:
                service = round(years_between(m["date_joined"], exit_date), 4)
                pension = round(benefits.accrued_pension(service, new_salary, spc, rules), 2)
                move(mid, "withdrawal", exit_date, "A", "D", new_value=pension)
                m.update(status="D", date_left=exit_date, salary=np.nan,
                         pensionable_service=service, deferred_pension_at_exit=pension)

        elif status == "D":
            if reaches_nra:
                factor = benefits.revaluation_factor(m["date_left"], benefits.last_revaluation_year(birthday_nra),
                                                     revaluation)
                pension = round(m["deferred_pension_at_exit"] * factor, 2)
                move(mid, "retirement", birthday_nra, "D", "P", m["deferred_pension_at_exit"], pension)
                m.update(status="P", date_retired=birthday_nra, deferred_pension_at_exit=np.nan,
                         pension_in_payment=pension)
            elif u < q_death:
                move(mid, "death", exit_date, "D", "died")
                continue

        else:   # pensioner
            new_pension = round(m["pension_in_payment"] * (1 + increase), 2)
            move(mid, "pension_increase", year_start, "P", "P", m["pension_in_payment"], new_pension)
            m["pension_in_payment"] = new_pension
            if u < q_death:
                move(mid, "death", exit_date, "P", "died")
                continue

        closing_members.append(m)

    movements = pd.DataFrame(movements, columns=MOVEMENT_COLUMNS)
    closing_df = pd.DataFrame(closing_members, columns=COLUMNS).reset_index(drop=True)
    return movements, closing_df


# --- injected errors ---------------------------------------------------------------

def inject_errors(closing_df, cfg, rng):
    """Closing raw extract = true closing data + errors (SPEC §6.2). Each affected member gets one error."""
    raw = closing_df.copy()
    key, extra_rows = [], []
    used = set()

    def pick(mask):
        candidates = [mid for mid in raw.loc[mask, "member_id"] if mid not in used]
        mid = candidates[int(rng.integers(len(candidates)))]
        used.add(mid)
        return mid, raw.index[raw.member_id == mid][0]

    def record(mid, error_type, field, true_value, injected_value):
        key.append({"member_id": mid, "error_type": error_type, "field": field,
                    "true_value": true_value, "injected_value": injected_value})

    counts = cfg["errors"]
    everyone = raw.member_id.notna()
    actives, deferreds, pensioners = raw.status == "A", raw.status == "D", raw.status == "P"

    for _ in range(counts["missing_date_of_birth"]):
        mid, i = pick(everyone)
        record(mid, "missing_date_of_birth", "date_of_birth", raw.at[i, "date_of_birth"], None)
        raw.at[i, "date_of_birth"] = None
    for _ in range(counts["duplicate_member_id"]):
        mid, i = pick(everyone)
        record(mid, "duplicate_member_id", "member_id", mid, mid)
        extra_rows.append(raw.loc[i].copy())
    for _ in range(counts["birth_after_joining"]):
        mid, i = pick(everyone)
        wrong = raw.at[i, "date_joined"] + timedelta(days=int(rng.integers(30, 3000)))
        record(mid, "birth_after_joining", "date_of_birth", raw.at[i, "date_of_birth"], wrong)
        raw.at[i, "date_of_birth"] = wrong
    for _ in range(counts["service_exceeds_age_minus_18"]):
        mid, i = pick(actives)
        age = years_between(raw.at[i, "date_of_birth"], to_date(cfg["closing_date"]))
        wrong = round(age - 18 + float(rng.uniform(2, 10)), 4)
        record(mid, "service_exceeds_age_minus_18", "pensionable_service", raw.at[i, "pensionable_service"], wrong)
        raw.at[i, "pensionable_service"] = wrong
    for _ in range(counts["pensioner_zero_pension"]):
        mid, i = pick(pensioners)
        record(mid, "pensioner_zero_pension", "pension_in_payment", raw.at[i, "pension_in_payment"], 0.0)
        raw.at[i, "pension_in_payment"] = 0.0
    for _ in range(counts["deferred_with_salary"]):
        mid, i = pick(deferreds)
        wrong = float(round(rng.uniform(40_000, 90_000)))
        record(mid, "deferred_with_salary", "salary", np.nan, wrong)
        raw.at[i, "salary"] = wrong
    for _ in range(counts["salary_extra_zero"]):
        mid, i = pick(actives & (raw.salary >= 55_000))   # x10 lands above the EUR 500k range limit
        record(mid, "salary_extra_zero", "salary", raw.at[i, "salary"], raw.at[i, "salary"] * 10)
        raw.at[i, "salary"] = raw.at[i, "salary"] * 10
    for _ in range(counts["active_with_retirement_date"]):
        mid, i = pick(actives)
        wrong = date(2025, 1, 1) + timedelta(days=int(rng.integers(0, 365)))
        record(mid, "active_with_retirement_date", "date_retired", None, wrong)
        raw.at[i, "date_retired"] = wrong
    next_number = int(raw.member_id.str[1:].astype(int).max()) + 1
    for k in range(counts["untraceable_record"]):
        _, i = pick(actives)   # a plausible active record under an ID that is not in the opening data
        row = raw.loc[i].copy()
        row["member_id"] = f"M{next_number + k:04d}"
        row["date_of_birth"] = row["date_of_birth"] - timedelta(days=int(rng.integers(200, 2000)))
        record(row["member_id"], "untraceable_record", "member_id", None, row["member_id"])
        extra_rows.append(row)

    raw = pd.concat([raw, pd.DataFrame(extra_rows)], ignore_index=True)
    raw = raw.sort_values("member_id", kind="stable").reset_index(drop=True)
    answer_key = pd.DataFrame(key, columns=["member_id", "error_type", "field", "true_value", "injected_value"])
    return raw, answer_key


# --- driver ------------------------------------------------------------------------

def generate(cfg):
    rng = np.random.default_rng(cfg["seed"])
    opening = make_opening(cfg, rng)
    movements, closing_true = simulate_2025(opening, cfg, rng)
    closing_raw, answer_key = inject_errors(closing_true, cfg, rng)
    return {"opening": opening, "movements": movements, "closing_true": closing_true,
            "closing_raw": closing_raw, "answer_key": answer_key}


def main():
    out = generate(load_config("data_gen"))
    MEMBERS.mkdir(parents=True, exist_ok=True)
    out["opening"].to_csv(MEMBERS / "members_2024.csv", index=False)
    out["movements"].to_csv(MEMBERS / "movements_2025.csv", index=False)
    out["closing_raw"].to_csv(MEMBERS / "members_2025_raw.csv", index=False)
    out["closing_true"].to_csv(FIXTURES / "members_2025_true.csv", index=False)
    out["answer_key"].to_csv(FIXTURES / "injected_errors.csv", index=False)
    print("opening:", out["opening"].status.value_counts().to_dict())
    print("closing (true):", out["closing_true"].status.value_counts().to_dict())
    print("movements:", out["movements"].event.value_counts().to_dict())
    print("raw records:", len(out["closing_raw"]), "injected errors:", len(out["answer_key"]))


if __name__ == "__main__":
    main()
