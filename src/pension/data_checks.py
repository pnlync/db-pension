"""M2 data checks and membership reconciliation (SPEC §9 M2).

Every issue is written to outputs/data_issues.csv with the rule broken and the action taken: nothing is
fixed silently. Corrections use only last year's reconciled data and the administrator's movement report.
Run: uv run python -m pension.data_checks
"""
from datetime import date

import pandas as pd

from pension.io import MEMBERS, OUTPUTS

VALUATION_DATE = date(2025, 12, 31)
REQUIRED = {
    "all": ["member_id", "status", "sex", "date_of_birth", "date_joined", "pensionable_service"],
    "A": ["salary"],
    "D": ["date_left", "deferred_pension_at_exit"],
    "P": ["date_retired", "pension_in_payment"],
}
LIMITS = {"age": (18, 110), "salary": (10_000, 500_000)}   # SPEC §9 M2
ISSUE_COLUMNS = ["member_id", "rule", "field", "detail", "action"]


def to_date(value):
    return None if pd.isna(value) else date.fromisoformat(value)


def to_float(value):
    return float("nan") if pd.isna(value) else float(value)


def years(start, end):
    return (end - start).days / 365.25


class IssueLog:
    def __init__(self):
        self.rows = []

    def add(self, member_id, rule, field, detail, action):
        self.rows.append(dict(member_id=member_id, rule=rule, field=field, detail=detail, action=action))

    def frame(self):
        return pd.DataFrame(self.rows, columns=ISSUE_COLUMNS)


def latest_movement_value(movements, member_id, events):
    rows = movements[(movements.member_id == member_id) & movements.event.isin(events)]
    return None if rows.empty else rows.new_value.iloc[-1]


# --- pass 1: identity and dates (needed before any age-based rule) -----------------

def check_identity_and_dates(raw, opening, log):
    df = raw.copy()
    opening_ids = set(opening.member_id)
    dob_opening = opening.set_index("member_id").date_of_birth

    dup_ids = df.member_id[df.member_id.duplicated()].unique()
    for mid in dup_ids:
        rows = df[df.member_id == mid]
        identical = len(rows.drop_duplicates()) == 1
        action = "exact duplicate row removed" if identical else "records differ: query administrator"
        log.add(mid, "uniqueness", "member_id", f"{len(rows)} records", action)
    df = df.drop_duplicates()

    for mid in df.member_id[~df.member_id.isin(opening_ids)]:
        log.add(mid, "traceability", "member_id", "not in 2024-12-31 data and no movement",
                "excluded from the valuation; query administrator")
    df = df[df.member_id.isin(opening_ids)].copy()

    for i, row in df.iterrows():
        for field in REQUIRED["all"] + REQUIRED.get(row.status, []):
            if pd.isna(row[field]):
                if field == "date_of_birth":
                    df.at[i, field] = dob_opening[row.member_id]
                    action = f"restored from 2024-12-31 data ({dob_opening[row.member_id]})"
                else:
                    action = "query administrator"
                log.add(row.member_id, "completeness", field, "missing", action)

        dob, joined = to_date(df.at[i, "date_of_birth"]), to_date(row.date_joined)
        exit_date = to_date(row.date_left) or to_date(row.date_retired)
        dates = [d for d in (dob, joined, exit_date) if d is not None]
        in_order = dates == sorted(dates) and len(set(dates)) == len(dates) and dates[-1] <= VALUATION_DATE
        if not in_order:
            opening_dob = to_date(dob_opening[row.member_id])
            if opening_dob != dob and opening_dob < joined:
                df.at[i, "date_of_birth"] = dob_opening[row.member_id]
                action = f"date of birth restored from 2024-12-31 data ({dob_opening[row.member_id]})"
            else:
                action = "query administrator"
            log.add(row.member_id, "date_order", "date_of_birth",
                    f"birth {dob}, joined {joined}, exit {exit_date}", action)
    return df


# --- pass 2: ranges and status consistency --------------------------------------------

def check_values(df, movements, log):
    df = df.copy()
    for i, row in df.iterrows():
        mid, status = row.member_id, row.status
        dob, joined = to_date(row.date_of_birth), to_date(row.date_joined)
        age = years(dob, VALUATION_DATE)
        if not LIMITS["age"][0] <= age <= LIMITS["age"][1]:
            log.add(mid, "age_range", "date_of_birth", f"age {age:.1f}", "query administrator")

        end = {"A": VALUATION_DATE, "D": to_date(row.date_left), "P": to_date(row.date_retired)}[status]
        service = to_float(row.pensionable_service)
        if service > years(dob, end) - 18:
            if status == "A":
                fixed = round(years(joined, VALUATION_DATE), 4)
                df.at[i, "pensionable_service"] = repr(fixed)
                action = f"recomputed from date joined to the valuation date ({fixed})"
            else:
                action = "query administrator"
            log.add(mid, "service_vs_age", "pensionable_service", f"service {service} > age {years(dob, end):.1f} - 18", action)

        if status == "A":
            salary = to_float(row.salary)
            if not LIMITS["salary"][0] <= salary <= LIMITS["salary"][1]:
                reported = latest_movement_value(movements, mid, ["salary_increase"])
                df.at[i, "salary"] = reported
                log.add(mid, "salary_range", "salary", f"salary {salary:,.0f}",
                        f"replaced by the 1 January 2025 salary in the movement report ({reported})")
            if pd.notna(row.date_left) or pd.notna(row.date_retired):
                exits = movements[(movements.member_id == mid) & movements.event.isin(["withdrawal", "retirement"])]
                if exits.empty:
                    df.at[i, "date_left"], df.at[i, "date_retired"] = None, None
                    action = "no exit in the movement report: exit date removed"
                else:
                    action = "movement report shows an exit: query administrator about the status"
                log.add(mid, "active_no_exit_date", "date_left/date_retired",
                        f"left {row.date_left}, retired {row.date_retired}", action)

        if status == "D" and pd.notna(row.salary):
            df.at[i, "salary"] = None
            log.add(mid, "deferred_no_salary", "salary", f"salary {row.salary}", "salary removed (not used for deferreds)")

        pension_field = {"D": "deferred_pension_at_exit", "P": "pension_in_payment"}.get(status)
        if pension_field and not to_float(row[pension_field]) > 0:
            reported = None
            if status == "P":
                reported = latest_movement_value(movements, mid, ["pension_increase", "retirement"])
            df.at[i, pension_field] = reported
            action = (f"replaced by the 2025 amount in the movement report ({reported})" if reported
                      else "query administrator")
            log.add(mid, "pension_positive", pension_field, f"{pension_field} {row[pension_field]}", action)
    return df


# --- membership reconciliation ---------------------------------------------------------

def reconcile(opening, clean, movements):
    """Opening status x closing status (A, D, P, died); opening + in - out = closing by status."""
    closing_status = clean.set_index("member_id").status
    died = set(movements.member_id[movements.event == "death"])
    rows = []
    for mid, status in zip(opening.member_id, opening.status):
        if mid in closing_status.index:
            rows.append((status, closing_status[mid]))
        elif mid in died:
            rows.append((status, "died"))
        else:
            rows.append((status, "unexplained"))
    moves = pd.DataFrame(rows, columns=["opening", "closing"])
    matrix = pd.crosstab(moves.opening, moves.closing).reindex(
        index=["A", "D", "P"], columns=["A", "D", "P", "died", "unexplained"], fill_value=0)

    table = pd.DataFrame(index=["A", "D", "P"])
    table["opening"] = matrix.sum(axis=1)
    table["in"] = [matrix.loc[[o for o in "ADP" if o != s], s].sum() for s in "ADP"]
    table["out"] = [matrix.loc[s].drop(s).sum() for s in "ADP"]
    table["expected_closing"] = table.opening + table["in"] - table.out
    table["closing"] = clean.status.value_counts().reindex(["A", "D", "P"], fill_value=0)
    table["difference"] = table.closing - table.expected_closing
    # whole scheme: transfers between statuses cancel; only deaths (and anything unexplained) leave
    out_total = matrix["died"].sum() + matrix["unexplained"].sum()
    opening_total, closing_total = table.opening.sum(), table.closing.sum()
    table.loc["total"] = [opening_total, 0, out_total, opening_total - out_total, closing_total,
                          closing_total - (opening_total - out_total)]
    return matrix, table


def run(raw, opening, movements):
    """raw, opening, movements read with dtype=str. Returns issues, clean data, matrix, reconciliation."""
    log = IssueLog()
    df = check_identity_and_dates(raw, opening, log)
    clean = check_values(df, movements, log)

    recheck = IssueLog()
    check_values(check_identity_and_dates(clean, opening, recheck), movements, recheck)
    assert not recheck.rows, f"issues remain after cleaning: {recheck.rows}"

    clean = clean.sort_values("member_id").reset_index(drop=True)
    matrix, table = reconcile(opening, clean, movements)
    return {"issues": log.frame(), "clean": clean, "matrix": matrix, "reconciliation": table}


def main():
    raw = pd.read_csv(MEMBERS / "members_2025_raw.csv", dtype=str)
    opening = pd.read_csv(MEMBERS / "members_2024.csv", dtype=str)
    movements = pd.read_csv(MEMBERS / "movements_2025.csv", dtype=str)
    out = run(raw, opening, movements)
    OUTPUTS.mkdir(exist_ok=True)
    out["clean"].to_csv(MEMBERS / "members_2025_clean.csv", index=False)
    out["issues"].to_csv(OUTPUTS / "data_issues.csv", index=False)
    out["matrix"].to_csv(OUTPUTS / "membership_movement_matrix.csv")
    out["reconciliation"].to_csv(OUTPUTS / "membership_reconciliation.csv", index_label="status")
    print(out["issues"].groupby("rule").size().to_string())
    print(out["matrix"].to_string())
    print(out["reconciliation"].to_string())


if __name__ == "__main__":
    main()
