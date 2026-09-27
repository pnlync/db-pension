"""M12 packaging (SPEC §9 M12): README.md, reports/trustee_memo.md and the GitHub Pages page docs/index.html,
all generated from outputs/ (no hand-typed numbers)."""
import json
import shutil
from html import escape

from pension.disclosure import DISCLAIMER
from pension.io import OUTPUTS, ROOT

REPO = "https://github.com/pnlync/db-pension"
FIGURES = ["fig1_cashflows.png", "fig2_bridge.png", "fig3_deficit_waterfall.png", "fig4_funding_paths.png",
           "fig5_buyin.png", "fig_tornado.png"]


def load():
    names = {"ias": "ias19_2025", "fs": "funding_standard_2025", "br": "bridge_2025", "aoc": "aoc_2025",
             "risk": "risk_2025", "dec": "decisions_2025", "bi": "buyin_2025", "cv": "cv_numbers"}
    return {k: json.loads((OUTPUTS / f"{v}.json").read_text()) for k, v in names.items()}


def m(x):
    return f"{x / 1e6:,.1f}"


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def facts(o):
    """Every number the documents quote, formatted once, from outputs/."""
    ias, fs, br, aoc, rk, dec, bi, cv = (o[k] for k in ("ias", "fs", "br", "aoc", "risk", "dec", "bi", "cv"))
    steps = {s["key"]: s["effect"] for s in br["steps"]}
    pro, eq = bi["day_one"]["pro_rata"], bi["day_one"]["sell_equities"]
    w = aoc["deficit_waterfall"]
    table = {r["option"]: r for r in dec["trustee_table"]}
    f = {
        "members_opening": f"{cv['members_opening']:,}", "members_closing": f"{cv['members_closing']:,}",
        "dbo": m(ias["dbo"]), "dbo_a": m(ias["dbo_by_status"]["A"]), "dbo_d": m(ias["dbo_by_status"]["D"]),
        "dbo_p": m(ias["dbo_by_status"]["P"]), "sedr": pct(ias["assumptions"]["sedr"], 2),
        "duration": f"{ias['duration']:.1f}", "pensioner_share": pct(ias["pensioner_share"], 0),
        "sc": m(ias["service_cost_2026"]["gross"]), "sc_pct": pct(ias["service_cost_pct_pensionable_payroll"], 0),
        "assets": m(ias["assets"]), "ias_deficit": m(ias["net_liability"]), "ias_level": pct(ias["funding_level"]),
        "fs": m(fs["liabilities"]["total"]), "fs_np": m(fs["liabilities"]["non_pensioners"]),
        "fs_p": m(fs["liabilities"]["pensioners"]), "fs_exp": m(fs["liabilities"]["wind_up_expenses"]),
        "fs_level": pct(fs["fs_funding_level"]), "fsr": m(fs["fsr"]["total"]),
        "fsr_prop": m(fs["fsr"]["proportion_part"]), "fsr_int": m(fs["fsr"]["interest_part"]),
        "cover": pct(fs["fs_plus_fsr_cover"]), "shortfall": m(fs["shortfall_fs_plus_fsr"]),
        "mva_months": f"{fs['mva_golden_test']['months']}",
        "gap": m(-br["fs_minus_ias19"]), "br_np": m(-cv["bridge_non_pensioners_m"] * 1e6),
        "br_leaver": m(-steps["leaver_basis"]), "br_incr": m(-steps["s34_increases"]),
        "br_disc": m(-steps["s34_discount"]), "br_ann": m(steps["annuity_cost"]), "br_exp": m(steps["expenses"]),
        "dbo_open": m(aoc["opening"]["dbo"]), "sedr_open": pct(aoc["opening"]["sedr"], 2),
        "def_open": m(w["opening_deficit"]), "def_close": m(w["closing_deficit"]),
        "curve": m(-aoc["dbo_reconciliation"]["curve"]), "assump": m(-w["assumption_changes"]),
        "asset_perf": m(w["asset_performance"]), "pl": m(aoc["pl_2025"]["total"]), "oci": m(-aoc["oci_2025"]["total"]),
        "fs_level_open": pct(aoc["opening"]["fs_funding_level"]),
        "hr_ias": pct(rk["pv01"]["hedge_ratio_ias19"], 0), "hr_fs": pct(rk["pv01"]["hedge_ratio_fs"], 0),
        "hit_ias": f"{-rk['funding_level_change_minus_50bp']['ias19_pp']:.1f}",
        "hit_fs": f"{-rk['funding_level_change_minus_50bp']['fs_pp']:.1f}",
        "c3": m(dec["solved_contribution"]["3"]["contributions_only"]),
        "c3_sw": m(dec["solved_contribution"]["3"]["switch_and_contributions"]),
        "c10": m(dec["solved_contribution"]["10"]["contributions_only"]),
        "c10_sw": m(dec["solved_contribution"]["10"]["switch_and_contributions"]),
        "sw_cut": pct(dec["switch"]["shortfall_reduction"], 0), "sw_short": m(dec["switch"]["after"]["shortfall"]),
        "sw_hr_ias": pct(dec["switch"]["after"]["hedge_ratio_ias19"], 0),
        "sw_hr_fs": pct(dec["switch"]["after"]["hedge_ratio_fs"], 0),
        "sw_hit": f"{-dec['switch']['after']['ias19_funding_change_minus_50bp_pp']:.1f}",
        "sw_cost": m(dec["expected_return_cost_of_switch_eur"]),
        "sw_cover_now": pct(table["Switch only"]["fs_plus_fsr_cover_now"]),
        "sw_cover_3": pct(table["Switch only"]["fs_plus_fsr_cover_year_3"]),
        "c_cover_3": pct(table["Contributions only"]["fs_plus_fsr_cover_year_3"], 0),
        "both_cover_3": pct(table["Switch + contributions"]["fs_plus_fsr_cover_year_3"], 0),
        "prem": m(bi["price"]["premium"]), "prem_pct": pct(bi["premium_pct_of_ias19_dbo"], 0),
        "tp_pct": pct(bi["tp_pct_of_ias19_dbo"], 0), "rm": m(bi["price"]["rm"]),
        "oci_bi": m(pro["ias19"]["after"]["oci_loss"]), "bi_ias_after": pct(pro["ias19"]["after"]["funding_level"]),
        "bi_fs_after": pct(pro["fs"]["after"]["fs_level"]), "bi_fsr_after": m(pro["fs"]["after"]["fsr"]),
        "bi_cover_after": pct(pro["fs"]["after"]["cover"]), "bi_cover_eq": pct(eq["fs"]["after"]["cover"]),
        "bi_short_eq": m(eq["fs"]["after"]["shortfall"]),
        "bi_pv01_ias": pct(pro["pv01_insured_share"]["ias19"], 0), "bi_pv01_fs": pct(pro["pv01_insured_share"]["fs"], 0),
        "bi_over_proxy": pct(bi["vs_fs_annuity_proxy"]["premium_over_proxy"], 0),
        "bi_fs_quote": pct(bi["vs_fs_annuity_proxy"]["fs_level_if_quote_consistent"]),
    }
    return f


# --- trustee memo ------------------------------------------------------------------------------------------------

def memo(f):
    return f"""# Synthetic Scheme IE-1: funding position and options

To: the trustees (illustrative). Valuation date: 31 December 2025. Amounts in EUR m.

> {DISCLAIMER}

## 1. Purpose and headline numbers

This note sets out where the scheme stands on the two liability measures that matter to you and to the sponsor, what changed in 2025, and three ways of restoring the funding standard reserve (FSR).

| | 31 December 2025 |
|---|---|
| Assets | {f['assets']} |
| IAS 19 defined benefit obligation (company accounts) | {f['dbo']} |
| Funding Standard liability (statutory wind-up test) | {f['fs']} |
| Funding Standard funding level | {f['fs_level']} (met) |
| Funding standard reserve (FSR) | {f['fsr']} |
| Assets / (Funding Standard + FSR) | {f['cover']} (not met; shortfall {f['shortfall']}) |

The scheme meets the Funding Standard but not the Funding Standard plus the FSR, so a funding proposal is needed.

## 2. Why the two liability measures differ

Both measures value the same {f['members_closing']} members' benefits but answer different questions. IAS 19 is a going-concern, best-estimate measure: salaries are projected to retirement and cash flows are discounted at AA corporate bond yields (single equivalent rate {f['sedr']}). The Funding Standard asks whether the scheme could meet accrued benefits if it wound up today: active members are treated as leaving now, non-pensioners are valued as statutory transfer values (6% before 65 and 4.25% after, with the market value adjustment) and pensioners at the cost of buying annuities.

The Funding Standard liability is {f['gap']} below the IAS 19 DBO, but that small net gap hides large offsetting steps: the statutory basis takes {f['br_np']} off the non-pensioners (today's salary instead of salary at exit: {f['br_leaver']}; 1.5% increases: {f['br_incr']}; statutory discounting: {f['br_disc']}), while annuity pricing adds {f['br_ann']} for pensioners and wind-up expenses add {f['br_exp']}. Meeting the Funding Standard therefore does not mean the scheme is secure on an accounting or buy-out view.

## 3. What happened in 2025

Euro yields rose during 2025 and the IAS 19 discount rate moved from {f['sedr_open']} to {f['sedr']}. The DBO fell from {f['dbo_open']} to {f['dbo']}, and the IAS 19 deficit from {f['def_open']} to {f['def_close']}. The change in the discount curve alone reduced the DBO by {f['curve']}; the same rise in yields cut the value of the bond portfolio, so assets returned {f['asset_perf']} less than the IAS 19 interest credit. The 2025 charge to profit or loss was {f['pl']} and the other comprehensive income gain {f['oci']}. On the statutory basis the funding level improved from {f['fs_level_open']} to {f['fs_level']}. Member experience was close to the assumptions (synthetic data).

## 4. Main risks

The same portfolio hedges {f['hr_ias']} of the interest-rate sensitivity of the IAS 19 liability but {f['hr_fs']} of the Funding Standard liability, because statutory transfer values move with rates only within ten years of retirement. A 0.5% fall in yields would lower the IAS 19 funding level by {f['hit_ias']} percentage points and the Funding Standard level by {f['hit_fs']}. Inflation, a 20% fall in equities and a one-year rise in life expectancy are the other material risks (see the tornado chart).

## 5. Options

| Option | Deficit contributions a year | FS + FSR cover now | Cover after 3 years | IAS 19 / FS hedge ratio |
|---|---|---|---|---|
| Contributions only | {f['c3']} | {f['cover']} | {f['c_cover_3']} | {f['hr_ias']} / {f['hr_fs']} |
| Move 20% from equities to long euro sovereigns only | 0 | {f['sw_cover_now']} | {f['sw_cover_3']} | {f['sw_hr_ias']} / {f['sw_hr_fs']} |
| Switch and contributions | {f['c3_sw']} | {f['sw_cover_now']} | {f['both_cover_3']} | {f['sw_hr_ias']} / {f['sw_hr_fs']} |

- **Contributions** close the gap without changing risk. Three years is the base case; a ten-year plan would need {f['c10']} a year (a strategic planning scenario, not a proposed statutory recovery period).
- **The switch** cuts the FSR shortfall by {f['sw_cut']} to {f['sw_short']}, because sovereign bonds count against both parts of the reserve, and reduces the IAS 19 hit from a 0.5% fall in yields to {f['sw_hit']} points. It gives up about {f['sw_cost']} a year of expected return, so on its own the cover drifts down again, and over ten years it costs more than it saves ({f['c10_sw']} a year against {f['c10']}).
- **A pensioner buy-in** at the illustrative price of {f['prem']} ({f['prem_pct']} of the pensioners' IAS 19 value; Solvency II technical provisions {f['tp_pct']}) would remove the pensioners' longevity risk and {f['bi_pv01_fs']} of the Funding Standard rate sensitivity, and cut the FSR to {f['bi_fsr_after']}. But the price is {f['bi_over_proxy']} above the annuity cost used in the Funding Standard, so the Funding Standard level would fall to {f['bi_fs_after']}; the company would book an IAS 19 loss of {f['oci_bi']} in other comprehensive income (assuming a qualifying policy that exactly matches the insured benefits) and its funding level would fall to {f['bi_ias_after']}. Paying by selling equities rather than sovereign bonds keeps the qualifying assets and leaves a shortfall of {f['bi_short_eq']}.

## 6. Recommendation (within this synthetic scenario)

Adopt the switch together with deficit contributions of {f['c3_sw']} a year, which restores the funding standard plus reserve within three years at the lowest cash cost, and review the investment strategy again before committing to it for longer, because the lost equity return outweighs the lower reserve over a ten-year horizon. Do not proceed with a pensioner buy-in on the illustrative terms: seek insurer quotations, calibrate the Funding Standard annuity basis to them, and fund any transaction from equities.

## 7. Limitations

Member data and experience are synthetic and the benefits are simplified (no spouses' pensions, early retirement or commutation). The IAS 19 curve is ECB AAA plus a calibrated spread; inflation is proxied by French 2032 government bonds rather than the euro inflation swap curve; timing is annual; inflation is deterministic, which understates the value of the 3% cap and 0% floor. The annuity cost, insurer loadings and buy-in price are illustrative. The statutory recovery period follows the Pensions Act and is not modelled. The Funding Standard liability for non-pensioners is not the cost of a guaranteed deferred-annuity buy-out.
"""


# --- README ------------------------------------------------------------------------------------------------------

def readme(f):
    return f"""# DB Pension Scheme Model

A member-level model of a synthetic Irish final-salary scheme. It values the same benefits under **IAS 19** and under the **Irish Funding Standard** (with the funding standard reserve), explains the gap between them, rolls the scheme through 2025 on actual market data, measures risk, sizes a funding proposal and prices a pensioner buy-in: **two liability measures plus one transaction price**.

> {DISCLAIMER}

Project page: [pnlync.github.io/db-pension](https://pnlync.github.io/db-pension/) · Trustee memo: [`reports/trustee_memo.md`](reports/trustee_memo.md) · IAS 19 disclosure note: [`reports/disclosure_note.md`](reports/disclosure_note.md) · Build spec: [`SPEC.md`](SPEC.md)

## Business questions and answers (31 December 2025, EUR m)

| Question | Answer |
|---|---|
| What are the promises worth? | IAS 19 DBO {f['dbo']} (actives {f['dbo_a']}, deferreds {f['dbo_d']}, pensioners {f['dbo_p']}); Funding Standard liability {f['fs']} |
| Why do the two differ? | Net gap {f['gap']}: the statutory basis takes {f['br_np']} off non-pensioners; annuity pricing adds {f['br_ann']} and wind-up costs {f['br_exp']} |
| What moved in 2025? | Yields rose: IAS 19 deficit {f['def_open']} to {f['def_close']}; Funding Standard level {f['fs_level_open']} to {f['fs_level']} |
| How risky is it? | Hedge ratio {f['hr_ias']} on IAS 19 but {f['hr_fs']} on the Funding Standard |
| Contributions or investment? | FS + FSR shortfall {f['shortfall']}: {f['c3']} a year for 3 years, or {f['c3_sw']} with a 20% equity-to-sovereign switch |
| What would a pensioner buy-in cost? | {f['prem']}, {f['prem_pct']} of the pensioners' IAS 19 value; IAS 19 loss {f['oci_bi']} under the qualifying exact-match assumption |

## Figures

![Figure 1](outputs/fig1_cashflows.png)
![Figure 2](outputs/fig2_bridge.png)
![Figure 3](outputs/fig3_deficit_waterfall.png)
![Figure 4](outputs/fig4_funding_paths.png)
![Figure 5](outputs/fig5_buyin.png)

## What is validated

- Section 34 market value adjustments reproduced for all {f['mva_months']} published months since January 2017.
- Three representative members recomputed in live Excel formulas ([`validation/excel_checks.xlsx`](validation/excel_checks.xlsx)) on the IAS 19, transfer-value and annuity bases, to the cent.
- IAS 19 to Funding Standard bridge and the 2025 analysis of change close with zero residual; asset and net-liability identities hold.
- Injected data errors all found; membership reconciliation differences zero.
- Assumptions calibrated to Irish 2025 annual reports; every assumption in [`data/assumptions_register.csv`](data/assumptions_register.csv).

## How to run

```bash
uv sync
uv run python -m pension.data_gen      # synthetic members (fixed seed)
uv run python -m pension.data_checks   # data checks and reconciliation
uv run python -m pension.pipeline      # all valuations, outputs/, reports/, docs/
uv run pytest
```

## Repository

```
config/      scheme rules, IAS 19, statutory (Section 34, ASP PEN-3, FSR), insurer and asset assumptions
data/        market data with sources (raw downloads not committed), synthetic members, assumptions register
src/pension/ engine, IAS 19, Funding Standard, bridge, analysis of change, risk, decisions, buy-in, pipeline
tests/       acceptance tests per module
validation/  Excel recomputation of three members
outputs/     every number and figure quoted anywhere
reports/     disclosure note, trustee memo
docs/        project page (GitHub Pages)
notes/       module notes (Chinese)
```
"""


# --- web page ------------------------------------------------------------------------------------------------------

def page(f):
    e = escape
    finding = lambda num, label, text: (f'<div class="finding"><div class="num">{e(num)}</div>'
                                        f'<div class="label">{e(label)}</div><p>{text}</p></div>')
    fig = lambda name, caption: (f'<figure><img src="./figures/{name}" alt="{e(caption)}" loading="lazy">'
                                 f'<figcaption>{e(caption)}</figcaption></figure>')
    findings = "".join([
        finding(f"€{f['dbo']}m vs €{f['fs']}m", "Two liability measures",
                f"IAS 19 DBO and Funding Standard liability for the same {f['members_closing']} members. The €{f['gap']}m net gap hides −€{f['br_np']}m on non-pensioners and +€{f['br_ann']}m annuity pricing for pensioners."),
        finding(f"€{f['def_open']}m → €{f['def_close']}m", "IAS 19 deficit in 2025",
                f"Yields rose ({f['sedr_open']} → {f['sedr']} discount rate): the curve alone took €{f['curve']}m off the DBO; the Funding Standard level rose from {f['fs_level_open']} to {f['fs_level']}."),
        finding(f"{f['hr_ias']} vs {f['hr_fs']}", "Same assets, two hedge ratios",
                "Statutory transfer values barely move with rates, so the portfolio hedges twice as much Funding Standard risk as IAS 19 risk."),
        finding(f"€{f['c3']}m a year", "Restoring FS + FSR in 3 years",
                f"Or €{f['c3_sw']}m with a 20% equity-to-long-sovereign switch, which cuts the FSR shortfall by {f['sw_cut']} but gives up about €{f['sw_cost']}m a year of expected return."),
        finding(f"{f['prem_pct']}", "Buy-in price vs IAS 19 value",
                f"Premium €{f['prem']}m (Solvency II TP {f['tp_pct']}); IAS 19 loss €{f['oci_bi']}m under the exact-match assumption; FSR falls to €{f['bi_fsr_after']}m."),
        finding(f"{f['mva_months']} months", "Statutory MVA reproduced",
                "Every published Section 34 market value adjustment since 2017; three members reconcile to Excel to the cent; bridges and the analysis of change close with zero residual."),
    ])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DB Pension Scheme Model</title>
  <meta name="description" content="IAS 19, the Irish Funding Standard and reserve, a 2025 analysis of change, risk, a funding proposal and a pensioner buy-in for a synthetic Irish final-salary scheme.">
  <link rel="icon" type="image/svg+xml" href="./assets/favicon.svg">
  <link rel="stylesheet" href="./styles/site.css">
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="#top"><span class="brand-dot"></span>DB Pension <span class="long">Scheme Model</span></a>
    <nav class="topnav" aria-label="Sections">
      <a href="#measures">Two measures</a>
      <a href="#change">2025</a>
      <a href="#risk">Risk</a>
      <a href="#decisions">Decisions</a>
      <a href="#buyin">Buy-in</a>
      <a href="#validation">Validation</a>
      <a href="#limitations">Limitations</a>
    </nav>
  </div>
</header>
<main id="top">
  <section class="hero" aria-labelledby="title">
    <p class="eyebrow">Pensions actuarial project · Python, Excel</p>
    <h1 id="title">DB Pension Scheme Model</h1>
    <p class="question">What has an Irish final-salary scheme promised, what is it worth to the company and to the trustees, why did that change in 2025, and should the sponsor pay more, the trustees de-risk, or the pensioners be insured?</p>
    <p class="lede">One member-level engine values the same benefits under IAS&nbsp;19 and under the Irish Funding Standard with its reserve, rolls the scheme through 2025 on actual market data, measures risk, sizes a three-year funding proposal and prices a pensioner buy-in: two liability measures plus one transaction price.</p>
    <div class="links">
      <a class="btn primary" href="{REPO}/blob/main/reports/trustee_memo.md">Trustee memo</a>
      <a class="btn" href="{REPO}/blob/main/reports/disclosure_note.md">IAS 19 disclosure note</a>
      <a class="btn" href="./assets/excel_checks.xlsx">Excel recomputation</a>
      <a class="btn" href="{REPO}">GitHub repository</a>
      <a class="btn" href="https://pnlync.github.io/actuarial/">Portfolio homepage</a>
    </div>
    <p class="honesty"><strong>Synthetic members, real market and statutory data.</strong> {e(DISCLAIMER)}</p>
  </section>

  <section id="overview"><h2>What the model found</h2>
    <p class="section-q">Six results at 31 December 2025, each written by the pipeline to <code>outputs/</code>.</p>
    <div class="findings">{findings}</div>
  </section>

  <section id="measures"><h2>Two liability measures</h2>
    <p class="section-q">Same members, different purpose, different number.</p>
    <p>IAS&nbsp;19 is a going-concern, best-estimate measure: projected unit credit, salaries projected to exit, AA-consistent discounting (single equivalent rate {f['sedr']}, duration {f['duration']} years). The Funding Standard asks whether the scheme could meet accrued benefits on a wind-up today: actives leave now, non-pensioners are valued as Section&nbsp;34 transfer values with the market value adjustment, pensioners at annuity cost, plus wind-up expenses.</p>
    {fig('fig1_cashflows.png', 'Figure 1. Expected benefit payments by member status (IAS 19 basis).')}
    {fig('fig2_bridge.png', 'Figure 2. IAS 19 DBO to Funding Standard liability, six sequential full revaluations, zero residual.')}
  </section>

  <section id="change"><h2>What moved in 2025</h2>
    <p class="section-q">Every euro of the change in the deficit has a cause.</p>
    <p>Opening DBO €{f['dbo_open']}m at 31 December 2024; closing €{f['dbo']}m, equal to an independent revaluation. Assets were revalued on the same curves, with equities at the MSCI World net EUR return and cash at €STR. P&amp;L charge €{f['pl']}m; OCI gain €{f['oci']}m.</p>
    {fig('fig3_deficit_waterfall.png', 'Figure 3. IAS 19 deficit, 31 December 2024 to 31 December 2025.')}
  </section>

  <section id="risk"><h2>Risk</h2>
    <p class="section-q">Which basis is the hedge ratio measured on?</p>
    <p>Asset PV01 against liability PV01: {f['hr_ias']} on IAS&nbsp;19, {f['hr_fs']} on the Funding Standard. A 0.5% fall in yields costs {f['hit_ias']} points of IAS&nbsp;19 funding level but only {f['hit_fs']} on the statutory basis.</p>
    {fig('fig_tornado.png', 'IAS 19 deficit sensitivity with assets revalued.')}
  </section>

  <section id="decisions"><h2>Contributions or investment?</h2>
    <p class="section-q">What does each option solve, and at what cost?</p>
    <p>The scheme meets the Funding Standard ({f['fs_level']}) but not the Funding Standard plus the €{f['fsr']}m reserve ({f['cover']}). Projecting members, the statutory liability and the reserve year by year, deficit contributions of €{f['c3']}m a year restore it in three years; moving 20% from equities to long euro sovereigns cuts the shortfall by {f['sw_cut']} and the contribution to €{f['c3_sw']}m, at a cost of about €{f['sw_cost']}m a year of expected return.</p>
    {fig('fig4_funding_paths.png', 'Figure 4. Assets over Funding Standard plus reserve under each option.')}
  </section>

  <section id="buyin"><h2>Pensioner buy-in</h2>
    <p class="section-q">What does insuring the pensioners cost, and what does it do on day one?</p>
    <p>The insurer's Solvency&nbsp;II technical provisions (EIOPA risk-free rate with volatility adjustment, annuitant mortality, expenses and a cost-of-capital risk margin of €{f['rm']}m) are the benchmark, not the price: premium = technical provisions − investment spread passed on + profit = €{f['prem']}m. Under IAS&nbsp;19 the policy is worth the insured DBO, so the company books €{f['oci_bi']}m in OCI (qualifying exact-match policy assumed); under the Funding Standard the annuities offset the liability and the reserve falls to €{f['bi_fsr_after']}m. The price is {f['bi_over_proxy']} above the Funding Standard annuity proxy, a finding the memo acts on.</p>
    {fig('fig5_buyin.png', 'Figure 5. Buy-in premium build-up and day-one effects.')}
  </section>

  <section id="validation"><h2>Validation</h2>
    <ul class="tight">
      <li>All {f['mva_months']} published Section 34 MVA factors since January 2017 reproduced to three decimals.</li>
      <li>Three members recomputed in live Excel formulas on three bases, agreeing to the cent.</li>
      <li>Bridge and analysis of change close with zero residual; asset and net-liability identities hold.</li>
      <li>Injected data errors all found; membership reconciliation differences zero.</li>
      <li>Discount spread and mortality calibrated to three Irish 2025 annual reports.</li>
    </ul>
  </section>

  <section id="limitations"><h2>Limitations</h2>
    <p>Synthetic members and experience; simplified benefits; AAA plus spread instead of an AA curve; French 2032 bonds as the inflation proxy; annual timing; deterministic inflation; illustrative annuity cost and buy-in price; statutory recovery period not modelled.</p>
  </section>
</main>
<footer>{e(DISCLAIMER)} Generated by <code>python -m pension.pipeline</code>.</footer>
</body>
</html>
"""


def write_all():
    o = load()
    f = facts(o)
    (ROOT / "reports" / "trustee_memo.md").write_text(memo(f))
    (ROOT / "README.md").write_text(readme(f))
    docs = ROOT / "docs"
    (docs / "figures").mkdir(parents=True, exist_ok=True)
    for name in FIGURES:
        shutil.copy(OUTPUTS / name, docs / "figures" / name)
    shutil.copy(ROOT / "validation" / "excel_checks.xlsx", docs / "assets" / "excel_checks.xlsx")
    (docs / "index.html").write_text(page(f))
    return f
