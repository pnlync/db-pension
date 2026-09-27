# SPEC: DB Pension Scheme Model

Version 1.6 (2026-09-27). Change log in §14.

A model of a synthetic Irish final-salary (defined benefit) pension scheme. It values the same member benefits under IAS 19 and under the Irish Funding Standard (with the funding standard reserve), explains the gap between the two, rolls the scheme forward through 2025 on actual market data, measures risk, sizes a funding proposal and prices a pensioner buy-in.

This file is the contract for the coding agent. The companion guide (Chinese, "DB Pension Project Guide") explains the concepts. If this file is unclear, contradicts itself or looks wrong, stop and ask. Do not guess.

Disclaimer to carry in the README and every report:

> All member data and member experience are synthetic. Market data are public and dated. Illustrative implementation based on published Pensions Authority and Society of Actuaries in Ireland guidance; not an actuarial certification or regulatory filing.

---

## 1. How we work

1. One module at a time, in the order of section 9 (M0, M1, ...). Do not start the next module until the user says "next".
2. Before coding a module, explain it in Chinese: the question it answers, inputs, outputs, key formulas, common mistakes. Wait for the user's OK.
3. Write the module's acceptance tests first. After implementing, report each test as PASS or FAIL with the numbers.
4. Show the key results as a small table or chart and say whether they look reasonable and why.
5. Put the module's teach-back questions, with model answers, in the module notes for the owner's self-study (owner's decision, 2026-09-27: do not ask them interactively).
6. Write `notes/M<n>_<name>.md` (Chinese): plain-language explanation, one-member worked example, key formulas, code map, validation results (expected vs actual), teach-back questions with answers, and 2-3 interview takeaways.
7. Commit once per module with the message `M<n>: <module name>`.

## 2. Business questions

1. What has the scheme promised, and what will it pay each year?
2. What are those promises worth under IAS 19 (company accounts) and under the Funding Standard (trustees, regulator)? Why do the two numbers differ?
3. Why did the position change during 2025?
4. How sensitive is it to rates, inflation, salaries, longevity and equities?
5. Should the sponsor pay more, or should the trustees change the investment strategy, to meet the funding standard reserve?
6. What would a pensioner buy-in cost, and what does it do to each measure on day one?

Framing for all reports: **two liability measures (IAS 19, Funding Standard) plus one transaction price (buy-in).** Never call the buy-in price a third liability.

## 3. Scope

In scope: members with a single retirement pension from age 65; withdrawal and death decrements for actives; statutory revaluation for deferreds; capped CPI increases in payment; IAS 19 PUC; Funding Standard and FSR; 2025 analysis of change; deterministic sensitivities; 3-year funding proposal; one unlevered investment switch; pensioner buy-in priced from a Solvency II benchmark.

Out of scope for the core (list them as limitations): spouse's and dependants' pensions, early and late retirement, commutation, death-in-service benefits, discretionary increases, swaps and leveraged LDI, Section 53B sovereign annuities, stochastic inflation for caps and floors, DC and auto-enrolment. Future work (not in this version): a stochastic journey plan (ESG, buy-out probability), partial buy-outs of deferreds, LPI option pricing.

## 4. Dates and conventions

| Item | Value |
|---|---|
| Main valuation date | 2025-12-31 |
| Opening date for the roll-forward | 2024-12-31 |
| Currency | EUR |
| Time step | annual; project to age 120 |
| Salary changes | 1 January each year |
| Exits (withdrawal, retirement, death) | mid-year |
| Pension payments | annual amount, paid at mid-year (t - 0.5) |
| Pension increases | 1 January, by the previous year's CPI annual average change, floor 0%, cap 3% |
| Deferred revaluation | statutory revaluation percentage (Pensions Act s33): min(CPI annual average change, 4%), can be negative; official percentages for past years |
| Survival for a payment in year t | average of survival to t - 1 and t |

All bases use the same timing conventions. Record the monthly-versus-annual approximation as a limitation.

Engine conventions (fixed in M4, see notes/M4): age nearest birthday at the valuation date; years to 65 T = 65 - x (at least 1 for actives); year t is calendar year valuation year + t, paid at t - 0.5; salary in year t = S (1 + g)^t with S the valuation-year salary; SPC in year t = SPC(year 1) (1 + pi)^(t - 1); non-pensioners' pensions start in year T + 1 and rise from the following 1 January; actives leave or die mid-year and a leaver's first-year revaluation is 6/12; facts known at the valuation date (the next 1 January pension increase, the statutory revaluation of the valuation year, the next year's SPC) are used on every basis.

## 5. Scheme rules (`config/scheme_rules.yaml`)

| Rule | Value |
|---|---|
| Name | clearly fictional, e.g. "Synthetic Scheme IE-1" (check CRO for a clash) |
| Type | private-sector final-salary DB, closed to new entrants at end-2012, actives still accruing |
| Accrual | 1/60 of final pensionable salary per year of service, maximum 40 years |
| Pensionable salary | max(salary - 1.5 x State Pension (Contributory), 0) |
| Normal retirement age | 65 |
| Member contributions | 5% of pensionable salary |
| Leaver benefit | accrued pension at exit (service x PS at exit / 60), revalued to 65 |
| Revaluation before retirement | statutory revaluation percentage: CPI annual average change, cap 4% a year, can be negative (no negatives before the 2015 revaluation year) |
| Increases in payment | CPI, floor 0%, cap 3% |
| Death | no benefit on death (v1) |

Retirement pension for an active member retiring at 65 (leavers: replace T with the time to exit):

```
B_ret = min(n, 40) / 60 x max( S (1+g)^T - 1.5 SPC (1+pi)^T , 0 )
```

n = completed service, S = current salary, g = salary growth, T = years to 65, SPC = current State Pension (Contributory), pi = inflation. SPC is projected with inflation.

## 6. Membership data

### 6.1 Fields

`member_id, status (A/D/P), sex (M/F), date_of_birth, date_joined, date_left, date_retired, salary, pensionable_service, deferred_pension_at_exit, pension_in_payment`

### 6.2 Generation (`src/pension/data_gen.py`, fixed seed)

Generate the opening snapshot at 2024-12-31, simulate 2025, produce the closing raw extract at 2025-12-31.

| Status | Closing count (approx.) | Distribution used in the prototype |
|---|---|---|
| Active | 250 | age N(50, 7) clipped 35-64; service U(12, 35) capped at age - 22 (closed at end-2012, so at least 12 years at 2024-12-31); salary lognormal(ln 65,000, 0.3) clipped EUR 40k-120k |
| Deferred | 300 | age U(35, 64); exit date 2000-2024; pension at exit lognormal(ln 6,000, 0.6) clipped EUR 2k-20k |
| Pensioner | 450 | age 65 + Exp(mean 9) clipped 65-95; pension lognormal(ln 18,000, 0.45) clipped EUR 8k-45k |

About 65% male in each group. Tune the generator so the design targets in section 12 hold.

2025 movements (store in `movements_2025.csv`): salary increases (mean a little above the IAS 19 assumption, with individual noise), pension increases (1 January 2025, 2024 CPI annual average), withdrawals, retirements at 65, deaths. Draw them with the IAS 19 decrement probabilities (opening basis) and the fixed seed. No new entrants. Generator settings live in `config/data_gen.yaml`. Simplification: the few actives and deferreds who reach 65 in 2025 are not exposed to death before their birthday.

Closing raw extract: opening + movements, then inject errors into about 2% of records, one or more of each type:

- missing date of birth
- duplicate member_id
- date of birth after date joined
- service greater than age - 18
- pensioner with zero pension
- deferred member with a salary
- salary with an extra zero (x10, above the EUR 500k range limit)
- status active with a retirement date
- a closing record that cannot be traced to an opening record and a movement

Keep a hidden answer key (`tests/fixtures/injected_errors.csv`) so M2 can prove it found every error.

## 7. Market and statutory data

### 7.1 Market data (`data/market/`, each file with source and download date in a header or sidecar)

| Data | Use | Source |
|---|---|---|
| ECB euro area AAA government spot curve, 2024-12-31 and 2025-12-31 | IAS 19 risk-free part; bond revaluation; annuity cost proxy | ECB Data Portal, YC dataset (series like `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y`; confirm keys and compounding convention in the ECB methodology note) |
| AA spread (constant) | IAS 19 curve = AAA + spread | calibrate to IAS 19 discount rates disclosed in 3-5 Irish companies' 2025 annual reports; compare at similar duration |
| EIOPA risk-free rate with VA, 2025-12-31 | buy-in BEL | EIOPA monthly RFR (already in the life project) |
| Section 34 MVA factors, monthly since January 2017 | FS non-pensioners; FSR; golden test | SAI MVA page |
| French OAT 2032 nominal and OAT€i 2032 real yields | implied inflation proxy (Fisher); MVA check | SAI MVA page (end-2024: 2.97% and 1.00%; end-2025: 3.09% and 1.20%) |
| CSO Irish Life Tables No. 15 (2005-2007), ages 0-105, M and F | base table for every basis | CSO ILT15 PDF (the only official format); the table stops at 105, the extension to 120 is set in M3 |
| CSO Irish Life Tables No. 17 (2015-2017) | comparison only | CSO |
| Statutory revaluation percentages 1996-2025 | historical deferred revaluation; 2025 experience | Occupational Pension Schemes (Revaluation) Regulations, one S.I. a year (Irish Statute Book) |
| Irish CPI annual average changes | pension increases in payment; 2025 experience | CSO CPM01 (annual average of the monthly index) |
| 2025 equity index total return in EUR; EUR short rate (€STR) for 2025 | asset roll-forward | public index provider; ECB |

Original downloads go in `data/market/raw/` (downloaded manually by the owner, not committed; see its README). Transcribed, cleaned files in `data/market/` are committed.

The ECB does not publish a curve on 31 December in every year (none for 2024-12-31). Use the last published business day on or before the valuation date (2024-12-30; 2025-12-31) and record it as the curve date. ECB spot rates are continuously compounded, in percent: convert to annual effective rates before use.

Beyond 30 years hold the last forward rate flat. Implied inflation: `pi = (1 + y_nominal) / (1 + y_real) - 1` (about 1.95% at end-2024, 1.87% at end-2025). It is a 7-year proxy for the HICP ex-tobacco swap curve that ASP PEN-3 refers to; state this.

### 7.2 Statutory parameters (`config/statutory_ie.yaml`)

Every value below lives in this file with its source document, paragraph and effective date. None of these numbers may appear in code.

| Parameter | Value | Source |
|---|---|---|
| Pre-retirement discount rate | 6.00% | Section 34 guidance v02 |
| Post-retirement discount rate | 4.25% | Section 34 guidance v02 |
| Revaluation and increases for CPI-linked benefits with cap >= 1.5% | 1.50% | Section 34 guidance v02 |
| Pre-retirement mortality | 73% (M) / 77% (F) of ILT15 | Section 34 guidance v02 |
| Post-retirement mortality | 58% (M) / 62% (F) of ILT15 | Section 34 guidance v02 |
| Annuity value loading | 0.36% (M) / 0.30% (F) a year, compound, from 2014 to the year of reaching NPA | Section 34 guidance v02 |
| MVA formulas and the date rule | see M6 | Section 34 guidance v02, para 4.1 |
| CPI-linked increases (floor 0, cap 3%) converted to fixed | full appendix table (checks: PI 1.0% -> 1.15%, 2.0% -> 1.85%, 3.0% -> 2.40%; PI 1.9% -> 1.78% by linear interpolation) | ASP PEN-3 v4.1 appendix; transcribe the whole table |
| Wind-up expenses | max(2% of liabilities, EUR 10,000) | ASP PEN-3 v4.1 para 2.4(c): the typical allowance; the actuary may use a best estimate instead |
| FSR proportion | 10% of FS liabilities not covered by qualifying assets | Pensions Authority; FSR Regulations |
| FSR interest-rate stress | net effect of a 0.5% fall in interest rates | Pensions Authority FSR FAQ; ASP PEN-3 |
| Qualifying assets | EU sovereign bonds, sovereign annuities, cash and deposits (not swaps) | Pensions Authority FSR FAQ |
| State Pension (Contributory) | 2026: EUR 299.30 a week = EUR 15,563.60 a year (2025-12-31 valuation); 2025: EUR 289.30 a week = EUR 15,043.60 a year (2024-12-31 valuation) | Department of Social Protection, Rates of Payment (SW19) 2025 and 2026 |

## 8. Assumption sets (three files that never read each other)

| File | Nature | Who chooses |
|---|---|---|
| `assumptions_ias19.yaml` | best estimate | company and actuary; calibrated and justified |
| `statutory_ie.yaml` | prescribed | the law and guidance; not a choice |
| `assumptions_insurer.yaml` | market view: FS annuity cost proxy and buy-in pricing | insurer-style assumptions, illustrative |

They share only the member data and the ILT15 base table. `funding_standard.py` must not import anything from the IAS 19 assumptions, and vice versa. Every assumption also gets a row in `data/assumptions_register.csv`: name, value, basis, source, effective_date (when the value or rule applies), retrieval_date (when it was downloaded or read), used_in.

### 8.1 IAS 19 (`assumptions_ias19.yaml`)

| Assumption | Starting value |
|---|---|
| Discount | ECB AAA spot + constant AA spread, per-year discounting; report the single equivalent discount rate (SEDR) |
| Inflation | market implied (Fisher proxy), about 1.9% |
| Salary growth | inflation + 1.0% |
| Pension increases | min(max(CPI, 0), 3%) |
| Deferred revaluation | min(CPI, 4%) |
| Mortality | 58% (M) / 62% (F) of ILT15, improvements 1.0% a year from 2014, cohort basis; calibrate multiplier and improvement together to life expectancies disclosed in Irish annual reports |
| Withdrawal | max(0, 4% - 0.2% x (age - 35)) below 55, zero from 55 |
| Admin expenses | per member per year, through P&L |

Mortality form: `q(x, y) = mult x q_ILT15(x) x (1 - imp)^max(y - 2014, 0)`, followed along the cohort diagonal from the valuation year. Prototype check: e65 = 23.1 (male aged 65 now), 25.0 (male aged 45 now, at 65).

Calibrated in M5 (config/assumptions_ias19.yaml): AA spread 1.00% (2025 disclosed IAS 19 discount rates of Kerry 4.30%, Glanbia 4.15%, AIB 4.21% less the ECB AAA spot at their durations: mean 102 bp); mortality 66% (M) / 75% (F) of ILT15 with 0.9% a year improvements (Kerry and Glanbia disclosed e65: male 22 now / 23.4-24 in 20 years; female 24-24.5 / 25.9-26). Admin expenses EUR 300 per member a year.

### 8.2 Insurer (`assumptions_insurer.yaml`)

| Assumption | Starting value |
|---|---|
| Annuity cost proxy discount (FS pensioners) | ECB AAA spot + insurer spread (state the value and rationale) |
| Buy-in BEL discount | EIOPA RFR + VA |
| Spread passed on to the scheme, s | 0 / 50 / 100 bp (sensitivity) |
| Mortality | 62% (M) / 70% (F) of ILT15, improvements 1.2% a year from 2014 (about 90% of the calibrated IAS 19 qx in 2026; set independently). v1.0 had 52% / 56% with 1.5%, relative to the prototype IAS 19 basis |
| Expenses | EUR per policy per year, increasing with inflation |
| RM | life-project Solvency II engine, 2027 rules; shocks: longevity (permanent 20% fall in qx) and expense |
| Profit margin m | 1-3% of BEL (sensitivity) |

### 8.3 Assets (`config/assets.yaml`)

Opening allocation: global equities 40%; euro nominal sovereigns 30% (duration ~10); euro inflation-linked sovereigns 15% (real duration ~10); euro corporates 10% (duration ~6); cash 5%. Sovereigns and cash (50%) are qualifying assets. Model each bond class as a coupon bond (or small ladder) with the target duration, revalued on the relevant curve (AAA for sovereigns, AAA + spread for corporates, real curve for inflation-linked). Expected returns for projections (M10) go here with their rationale.

## 9. Modules

Each module lists purpose, inputs, method, outputs, acceptance tests and teach-back questions. Gates: v1 after M7, v2 after M10, v3 after M12.

### M0 Setup

- Repo, `pyproject.toml`, config files, `assumptions_register.csv`.
- Transcribe ILT15 and ILT17 (M and F), the SAI MVA table (Jan 2017 to the latest month), the ASP PEN-3 appendix table; download ECB curves, CPI, State Pension amounts.
- Tests: every data file states source and date; ILT15 complete life expectancy at 65 matches CSO (16.6 M, 19.8 F) within 0.1 year.
- Teach-back: which basis uses each data file, and why?

### M1 Data generation

- Opening snapshot, 2025 movements, closing raw extract with injected errors (section 6).
- Tests: reproducible with the seed; closing counts about 250 / 300 / 450; distributions as specified.
- Teach-back: why generate an opening snapshot and movements instead of a single file?

### M2 Data checks and membership reconciliation

- Rules: completeness, uniqueness, date logic (birth < join < exit or retirement <= valuation date), ranges (age 18-110, salary EUR 10k-500k, pension > 0), status consistency (actives have no exit date, deferreds no salary, pensioners a pension), traceability to opening data.
- Write every issue to `outputs/data_issues.csv` (member_id, rule, action). Never fix silently.
- Membership reconciliation: opening status x closing status (A, D, P, died); opening + in - out = closing by status.
- Tests: every injected error found (answer key); reconciliation differences are zero.
- Teach-back: how is each error type handled, and why keep a record?

### M3 Mortality

- Base tables, multipliers, improvements, cohort survival, complete life expectancy, calibration helper, and the longevity stress: find k such that `k x q` raises e65 by exactly 1.0 year (root finding).
- Tests: e65 matches a hand calculation; k gives +1.0 year within 0.05.
- Teach-back: why is population mortality not pensioner mortality?

### M4 Benefit and cash-flow engine

- A `Basis` object carries discount, inflation, salary growth, mortality, withdrawal, revaluation and increase rules and timing. `project_cashflows(members, basis)` returns expected cash flows by member and year; `pv(cashflows, curve)` discounts.
- Pensioner: P x increases x survival.
- Deferred: revalue the pension at exit to the valuation date with the official statutory revaluation percentages (first year pro rata by complete months after exit, per the Pensions Authority preservation notes para 155), then to 65 with the assumption, then pay as a pensioner.
- Active: three outcomes each year until 65: withdraw (deferred pension n/60 x PS at exit, revalued to 65), die (nothing), retire at 65 (n/60 x PS at 65). Only completed service n counts (PUC).
- Figure 1: expected payments stacked by status over about 60 years.
- Tests: three representative members (one per status) reproduced in `validation/excel_checks.xlsx` within EUR 1; zero interest and zero mortality gives PV = sum of payments; member totals = scheme total; zero salary growth changes only actives; CPI 5% gives revaluation 4% and increases 3%.
- Teach-back: for a 45-year-old with 20 years' service, why use salary at 65 but multiply by only 20 years?

### M5 IAS 19

- Curve = ECB AAA spot + AA spread; DBO by status; SEDR; duration and PV01 (parallel -1 bp); service cost (DBO increase from one extra year of service, net of member contributions); 2026 P&L forecast (service cost + SEDR x net liability with mid-year timing + admin); sensitivities (discount, inflation, salary +/-0.5%; life expectancy +1 year via k).
- Disclosure note tables 1, 5, 6, 7 now; 2-4 come from M8:
  1. Principal actuarial assumptions (incl. life expectancy at 65)
  2. Reconciliation of the DBO
  3. Reconciliation of plan assets
  4. Amounts recognised in P&L and OCI
  5. Asset allocation
  6. Sensitivity analysis
  7. Duration, maturity profile (next 10 years), expected 2026 contributions and cost
- Net position: DBO - assets; the scheme is in deficit, so the asset ceiling (IFRIC 14) does not bite; say so in one line.
- Tests: Excel within EUR 1 for the three members; duration check within 1%; SEDR flat PV equals curve PV; directions (rates up -> DBO down, inflation up -> DBO up, salary affects actives only).
- Teach-back: why AA corporate bonds and not risk-free rates or expected asset returns? Why is service cost about a quarter of pensionable payroll?

### M6 Funding Standard and FSR

Non-pensioners, Section 34 standard transfer value per member:

1. Benefit if leaving today: actives min(n, 40)/60 x current PS; deferreds pension revalued to today.
2. Revalue to 65 at 1.5% a year.
3. Discount to today at 6.00% with pre-retirement survival (73% / 77% ILT15, no improvements).
4. Annuity value at 65: 4.25% discount, 1.5% increases, 58% / 62% ILT15; multiply by the loading (1.0036 or 1.0030) ^ (year of reaching 65 - 2014).
5. Multiply by MVA_pre(T) x MVA_post(T), using the factor at the last working day of the month before the effective date (2025-12-31 -> end-November 2025: MVA1 1.149, MVA2 1.237; 2024-12-31 -> end-November 2024: 1.182, 1.277). Index-linked benefits use MVA2.

Follow the guidance for payment frequency and timing; if the model simplifies, list it as a limitation.

```
TV = B65 x pre-retirement survival x 1.06^(-T) x a65(4.25%, 1.5%) x loading x MVA_pre(T) x MVA_post(T)

MVA_pre(T)  = [ 1.06 / (1.0425 + min(T,10)/20 x 0.0175) ] ^ min(T,10)
MVA_post(T) = MVA_NPA x (10 - T)/10 + T/10   if T <= 10;   1 if T > 10
MVA_NPA (index-linked, MVA2) = (1.0425/1.015 - 1) x a_15|j + v_j^15,  j = OAT€i 2032 yield rounded to the nearest 0.25%
MVA_NPA (fixed, MVA1)        = 0.0425 x a_15|i + v_i^15,              i = OAT 2032 nominal yield rounded to the nearest 0.25%
```

Pensioners: annuity purchase cost proxy (insurer file): discount ECB AAA spot + insurer spread, insurer mortality, CPI-linked increases converted to a fixed rate with the ASP PEN-3 appendix table (PI = implied inflation rounded to 0.1%).

Wind-up expenses: max(2% x (non-pensioner + pensioner liabilities), EUR 10,000). FS assets = market value.

FSR:

```
FSR = 10% x max(L_FS - A_qual, 0) + [ dL_FS - dA_qual ] for a 0.5% fall in rates
```

- dL_FS: pensioner annuity cost with the discount curve 0.5% lower; non-pensioners only through MVA_post recomputed with j 0.5% lower (6% and 4.25% unchanged); expenses recomputed.
- dA_qual: qualifying bonds revalued 0.5% lower; cash unchanged. No derivatives in the project.
- The interest component can be negative. Pass if assets >= FS liabilities + FSR.

- Outputs: FS liabilities by status, FSR components, FS and FS + FSR funding levels and shortfalls, MVA golden-test report.
- Tests: MVA golden test reproduces every published MVA1 and MVA2 since January 2017 (116 months to August 2026; include later months if published) to 3 decimals; appendix-table interpolation returns table values at table points; Excel within EUR 1 for the three members; TV of a member more than 10 years from 65 does not change when j changes.
- Teach-back: why are actives treated as leaving today? Why is the FSR not 10% of liabilities?

### M7 Basis bridge (Figure 2)

Sequential full revaluations from IAS 19 DBO to FS liability, in this fixed order:

| Step | Change | Members |
|---|---|---|
| 0 | IAS 19 DBO | all |
| 1 | leaver basis: no salary growth, no withdrawal | actives |
| 2 | Section 34 mortality and annuity loading | non-pensioners |
| 3 | revaluation and increases at 1.5% | non-pensioners |
| 4 | 6% / 4.25% discount x MVA | non-pensioners |
| 5 | annuity purchase cost | pensioners |
| 6 | wind-up expenses | all |
| = | FS liability | |

State: "Bridge effects are sequential rather than unique standalone decompositions."

- Tests: steps sum exactly to FS - IAS 19 (zero residual).
- Teach-back: direction and reason for each step.

**Gate v1**: M0-M7 tests pass; update CV to v1.

### M8 Assets and 2025 analysis of change (Figure 3)

- Before M8 (not a module, no commit): an end-to-end sketch on real data of the asset roll-forward, the AoC, the M10 contribution solve and the M11 buy-in, to confirm that the design setting (meets FS, not FS + FSR) and the later options still make sense. Adjust design targets once, here, if needed.
- Market inputs to confirm with the owner before coding: 2025 EUR total return of global equities (MSCI World net EUR, found 6.77%) and the 2025 average €STR; sources recorded in the register.
- Opening valuation at 2024-12-31 on the opening basis (IAS 19 and FS).
- Liability AoC (IAS 19), each step a full revaluation, fixed order: opening DBO; + service cost; + interest cost (opening SEDR x opening DBO, less half a year's interest on actual benefits); - actual benefits paid; = expected closing DBO; curve roll-down (value at 2025-12-31 of the opening projection's remaining expected cash flows, opening basis and opening curve, compared with the SEDR roll-forward using expected benefits); experience, in this order: membership movements (closing data valued with expected 2025 salaries and inflation-linked items; includes actual less expected benefits paid), salaries (actual 2025 salaries), inflation-linked items (1 January 2026 increase, 2025 statutory revaluation and 2026 SPC, actual vs assumed); demographic assumption changes (none unless the basis changed); financial assumption changes (curve, then inflation); = closing DBO, which must equal an independent valuation of the 2025-12-31 data on the closing basis. (v1.6: membership first, because salary and inflation experience can only be measured on the closing data.)
- Asset AoC: opening + interest income (SEDR) + return above interest + employer contributions + member contributions - benefits - expenses = closing. Equities: 2025 EUR total return; bonds: revalued on the same curves as the liabilities plus coupons; cash: €STR. Employer contributions 2025 are an input (normal + fixed deficit contribution).
- P&L = service cost + net interest + admin. OCI = experience, demographic and financial remeasurements + return on assets above interest income.
- Deficit waterfall: opening deficit -> service cost less contributions -> net interest -> asset out/under-performance -> experience -> assumption changes -> closing deficit.
- Simplified FS change: MVA change, annuity cost (curve) change, asset return, contributions less new accrual, member experience.
- Calibrate opening assets (root finding) so that closing assets are about 99% of closing DBO (v1.5; 97% in v1.0) and the scheme meets FS but not FS + FSR.
- Fill disclosure tables 2-4.
- Tests: other < 0.1% of DBO; closing DBO equals independent revaluation; asset identity zero; net liability identity (closing = opening + P&L cost + OCI loss - employer contributions) zero.
- Teach-back: the three largest drivers of the 2025 change; why service cost goes to P&L but salary experience to OCI.

### M9 Risk (slimmed in v1.6: only what M10 and the memo use)

- Scenarios, each revaluing liabilities and assets on both bases and reporting liability, assets, deficit and funding level: discount +/-50 bp; inflation +/-50 bp; salary +/-50 bp; life expectancy +1 year (k); equities -20%; combined (-50 bp, +1 year, equities -20%).
- PV01: IAS 19 liability (curve -1 bp); FS liability = dL_FS(-0.5%) / 50; assets by bond class.
- Hedge ratio = asset PV01 / liability PV01 on each basis; funding-level change for -50 bp on each basis. No inflation hedge ratio.
- Tornado chart of IAS 19 deficit impacts.
- Tests: duration check; k check; FS unchanged under salary scenarios; equity scenario changes no cash flow.
- Teach-back: why is the FS hedge ratio about twice the IAS 19 one for the same portfolio?

### M10 Decisions (Figure 4)

- Deterministic projection: assets grow at expected returns (assets.yaml), plus normal contributions and deficit contribution C, less benefits and expenses; membership ages with expected decrements; FS liabilities and FSR recalculated each year with yields held constant.
- Solve the smallest C such that assets at year 3 >= FS + FSR (brentq). Base scenario 3 years; 5 and 10 years as management scenarios labelled "strategic planning scenarios, not proposed statutory recovery periods". The statutory period follows the Pensions Act; state this as a limitation.
- Switch experiment: same opening assets, move 20% from equities to long euro sovereigns (duration ~15). Report FSR components, shortfall, both hedge ratios, -50 bp funding-level change and expected return.
- Trustee comparison table: contributions only / switch only / both; columns FS + FSR funding level, IAS 19 deficit, hedge ratios, expected return, contributions over 3 years.
- Tests: C substituted back hits the target within EUR 1k; year-0 FS and FSR equal M6; C falls as the period lengthens; the switch changes assets and FSR only.
- Teach-back: what do contributions and the switch each solve, and at what cost?

**Gate v2**: M8-M10 tests pass; update CV to v2.

### M11 Pensioner buy-in (Figure 5)

- BEL (Solvency II): insurer mortality, EIOPA RFR + VA, benefit and expense cash flows; CPI-linked increases approximated by the appendix fixed rate (limitation).
- RM: computed in this project with the cost-of-capital method (Solvency II 2027 review parameters in assumptions_insurer.yaml): SCR for longevity (permanent 20% fall in qx) and expense (+10% level, +1% inflation), aggregated with the life-module correlation; future SCRs projected in proportion to the run-off of the BEL; interest-rate risk excluded as hedgeable. The life project's engine is the reference for the parameters, not a code dependency (v1.6). EIOPA RFR + VA at 2025-12-31 is copied from ../assurance/data/raw/.
- Solvency II technical provisions TP = BEL + RM are the **benchmark**, not the price.
- Premium = TP - spread passed on (difference between BEL at RFR + VA and at RFR + VA + s) + profit (m x BEL). Do not add a separate capital loading on top of RM.
- Premium waterfall: pensioner IAS 19 DBO -> discount (AA to RFR + VA) -> insurer mortality -> expenses -> RM (= SII benchmark) -> spread passed on -> profit -> premium.
- Compare with the M6 annuity cost proxy and record the difference.
- Day-one effects, for three ways of paying (pro rata, selling sovereigns, selling equities): IAS 19 (assuming the policy is a qualifying insurance policy that exactly matches the insured benefits, it is valued at the DBO of those benefits and OCI loss = premium - insured DBO; state this condition wherever the loss is reported; funding level); FS (purchased annuities offset liabilities, ASP PEN-3 para 2.7; FS level, FSR, FS + FSR cover); buy-out funding level (unchanged on day one); share of liability PV01 insured.
- Tests: OCI loss identity exact (under the exact-match assumption); waterfall has zero residual; FS liability after = before minus the insured liability (expenses adjusted); insured PV01 = pensioner liability PV01.
- Teach-back: why does the FS position improve while IAS 19 books a loss?

### M12 Packaging

- `reports/trustee_memo.md` (2-3 pages, English): purpose and headline numbers; why the two liability measures differ; what moved in 2025; options with numbers (contributions, switch, buy-in); recommendation framed as a comparison within the synthetic scenario; risks and limitations.
- `reports/disclosure_note.md` complete.
- README: business question, the two liability measures and the buy-in price, five figures, disclaimer, how to run. The buy-in OCI loss is always quoted "under the qualifying exact-match assumption".
- GitHub Pages page under `docs/` (required): one static page generated by the pipeline from `outputs/` (no hand-typed numbers): the business questions, headline numbers (two liability measures and the buy-in price), the five figures, the trustee options table, what was validated (MVA golden test, Excel, zero-residual bridge and AoC, data checks), limitations and the disclaimer; links to the disclosure note, the memo and the repository. Works without JavaScript; figures copied to `docs/`.
- `outputs/cv_numbers.json`: every number used in the CV, README and memo, generated by the pipeline.
- Tests: every number in README, memo, web page and CV found in `outputs/`; synthetic labels on every figure with member data; the page's links resolve.

**Gate v3**: M11-M12 tests pass; update CV to the final version.

## 10. Repository

```
db-pension-model/
  README.md
  SPEC.md
  pyproject.toml
  config/      scheme_rules.yaml, assumptions_ias19.yaml, statutory_ie.yaml,
               assumptions_insurer.yaml, assets.yaml, scenarios.yaml
  data/        market/ (raw/ not committed), members/, assumptions_register.csv
  src/pension/ data_gen.py, data_checks.py, mortality.py, benefits.py, cashflows.py,
               ias19.py, funding_standard.py, mva.py, bridge.py, assets.py, aoc.py,
               risk.py, decisions.py, buyin.py, pipeline.py, figures.py, disclosure.py, site.py
  tests/       one test file per module, fixtures/
  validation/  excel_checks.xlsx
  outputs/     tables, figures, data_issues.csv, cv_numbers.json
  reports/     disclosure_note.md, trustee_memo.md
  docs/        GitHub Pages
  notes/       per-module notes in Chinese (M<n>_*.md)
```

## 11. Output and labelling rules

- Figures: 1 cash flows by status; 2 IAS 19 to FS bridge; 3 2025 deficit waterfall; 4 funding paths under the three options; 5 buy-in before and after. Each states "synthetic members" and the market-data date.
- Every public number comes from a file in `outputs/` written by the pipeline. No hand-typed numbers in the README, memo, web page or CV.
- CV bullets are written after the results, from `outputs/cv_numbers.json`, and their wording follows the results: the planning guides' bullets are templates, not claims (for example the bridge is a small net gap made of large offsetting steps, not one gap in one direction).
- Units: EUR m to one decimal in tables; percentages to one decimal.

## 12. Design targets and prototype magnitudes (sanity checks only)

Design targets (tune the generator and opening assets to meet them):

- IAS 19 DBO about EUR 200m (180-220m); pensioners 55-60% of DBO; duration 15-18 years.
- At 2025-12-31 the scheme meets the Funding Standard but not FS + FSR. With 2025 market data the FS liability is 98% of the IAS 19 DBO (prototype 95%), so closing assets are set at 99% of the DBO (v1.5).

Prototype (illustrative flat rates, Gompertz stand-in for ILT15). These are sanity checks for orders of magnitude only: never tune to them and never quote them. Real-data results so far are in `outputs/` and the module notes:

| Item | Prototype |
|---|---|
| IAS 19 DBO | EUR 206.9m (A 53.3, D 30.5, P 123.1); duration 16.8; PV01 about EUR 349k/bp |
| Service cost 2026 | about EUR 2.9m, 27% of pensionable payroll |
| FS liability | EUR 196.1m (95% of IAS 19); non-pensioners 63% of IAS 19, pensioners 113% |
| Bridge (EUR m) | -6.4, -4.7, -6.8, -13.2, +16.4, +3.8 |
| At assets = 97% of DBO | FS level 102%; FSR 13.9m (10% part 9.6, interest part 4.4); FS + FSR shortfall 9.3m |
| Switch 20% equities to long sovereigns | shortfall 2.3m (-76%); hedge ratio IAS 19 29% -> 47%, FS 58% -> 91%; -50 bp funding hit -5.3pp -> -3.9pp |
| Buy-in | premium 116% of pensioner IAS 19 DBO; OCI loss 19.2m; IAS 19 level 97.0% -> 87.7%; FS + FSR cover 96% -> 106%; 36% of liability PV01 insured |

If a real-data result moves the other way, explain which assumption caused it; do not force the prototype numbers.

## 13. Limitations to state

Synthetic data and experience; simplified benefits (no spouses, early retirement, commutation, death benefits); AAA + spread instead of a true AA curve; OAT 2032 inflation proxy instead of the HICP swap curve; annual mid-year timing; annuity cost proxy and insurer loadings are illustrative; deterministic inflation understates the value of the 3% cap and 0% floor; funding proposal period per the Pensions Act not modelled; no derivatives, so their treatment in the FSR interest test is not tested; the FS liability for non-pensioners (transfer values) is not the cost of a guaranteed deferred-annuity buy-out.

## 14. Change log

All dated 2026-09-27.

- 1.6 (from 1.5): scope of M8-M12 re-planned after gate v1 (end-to-end sketch before M8; AoC experience order; M9 slimmed; buy-in risk margin computed in this project; GitHub Pages page specified; M13 dropped to future work); modelling conventions written down (§4); prototype magnitudes are sanity checks only and CV wording follows the results (§11, §12).
- 1.5 (from 1.4): insurer mortality 62% / 70% ILT15 with 1.2% improvements (about 90% of the calibrated IAS 19 qx, §8.2); asset design target 99% of IAS 19 DBO instead of 97% (§12), because at 2025 market levels the FS liability is 98% of the DBO; bond classes as single par bonds (§8.3).
- 1.4 (from 1.3): M4 engine conventions (age nearest birthday, annual grid, known increases; notes/M4); M5 calibration results: AA spread 1.00%, IAS 19 mortality 66% / 75% ILT15 with 0.9% improvements, from Kerry, Glanbia and AIB 2025 annual reports (§8.1); ILT15 extended to 120 (M3).
- 1.3 (from 1.2): active service at the opening date U(12, 35), since the scheme closed at end-2012; generator settings in `config/data_gen.yaml`; 'salary with an extra zero' is x10 (§6.2).
- 1.2 (from 1.1): teach-back questions go into the module notes instead of being asked (§1); State Pension source, ILT15 range, wind-up wording settled in M0 (§7); deferred revaluation uses the official statutory percentages and 'CPI' means the annual average change (§4, §5, §7.1); one limitation added (§13).
- 1.1 (from 1.0): register date columns (§8), module notes (§1, §10), buy-in accounting condition (M11, M12), ECB curve date rule (§7.1), raw downloads folder (§7.1, §10).
