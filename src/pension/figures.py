"""The five figures (SPEC §11). Each states 'synthetic members' and the market-data date."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

COLOURS = {"A": "#4C72B0", "D": "#DD8452", "P": "#55A868"}
LABELS = {"A": "Actives", "D": "Deferreds", "P": "Pensioners"}


def footnote(fig, text):
    fig.text(0.01, 0.01, text, fontsize=8, color="#555555", ha="left", va="bottom")


def fig1_cashflows(cf, status, first_year, path, years=60, market_date="2025-12-31"):
    """Figure 1: expected benefit payments by status (IAS 19 basis), EUR m a year."""
    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = first_year + np.arange(years)
    bottom = np.zeros(years)
    for s in ("P", "D", "A"):
        values = cf[status == s].sum(axis=0)[:years] / 1e6
        ax.bar(x, values, bottom=bottom, color=COLOURS[s], label=LABELS[s], width=0.85)
        bottom += values
    ax.set_title("Figure 1. Expected benefit payments by member status (IAS 19 basis)")
    ax.set_ylabel("EUR m a year")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    footnote(fig, f"Synthetic members. IAS 19 assumptions and market data at {market_date}.")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def waterfall(ax, labels, start, effects, end_label, colours=("#C44E52", "#55A868")):
    """Bars: first level, then each effect floating from the running level, then the end level."""
    level = start
    ax.bar(0, start, color="#4C72B0")
    ax.text(0, start, f"{start:.1f}", ha="center", va="bottom", fontsize=8)
    for i, e in enumerate(effects, start=1):
        bottom = level if e >= 0 else level + e
        ax.bar(i, abs(e), bottom=bottom, color=colours[0] if e >= 0 else colours[1])
        ax.text(i, max(level, level + e), f"{e:+.1f}", ha="center", va="bottom", fontsize=8)
        level += e
    n = len(effects) + 1
    ax.bar(n, level, color="#4C72B0")
    ax.text(n, level, f"{level:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(range(n + 1), labels + [end_label], rotation=30, ha="right", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)


def fig2_bridge(steps, path, market_date="2025-12-31"):
    """Figure 2: IAS 19 DBO -> Funding Standard liability (EUR m), sequential full revaluations."""
    fig, ax = plt.subplots(figsize=(9, 5))
    short = ["IAS 19 DBO", "Leaver basis\n(actives)", "S34 mortality\n+ loading", "1.5% revaluation\n+ increases",
             "6% / 4.25%\nx MVA", "Annuity cost\n(pensioners)", "Wind-up\nexpenses"]
    effects = [s["effect"] / 1e6 for s in steps[1:]]
    waterfall(ax, short, steps[0]["effect"] / 1e6, effects, "Funding Standard\nliability")
    lo = min(s["level"] for s in steps) / 1e6
    ax.set_ylim(lo * 0.85, None)
    ax.set_ylabel("EUR m")
    ax.set_title("Figure 2. IAS 19 DBO to Funding Standard liability")
    footnote(fig, f"Synthetic members. Market data and MVA at {market_date} (MVA: 30 Nov 2025). "
                  "Bridge effects are sequential rather than unique standalone decompositions.")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig3_waterfall(w, path, market_date="2025-12-31"):
    """Figure 3: IAS 19 deficit 2024-12-31 -> 2025-12-31 (EUR m)."""
    fig, ax = plt.subplots(figsize=(9, 5))
    labels = ["Deficit\n31 Dec 2024", "Service cost\nless contributions", "Admin\nexpenses", "Net interest",
              "Assets below\ninterest income", "Member\nexperience", "Assumption changes\n(mainly discount rate)"]
    keys = ["service_cost_less_contributions", "admin_expenses", "net_interest", "asset_performance", "experience",
            "assumption_changes"]
    waterfall(ax, labels, w["opening_deficit"] / 1e6, [w[k] / 1e6 for k in keys], "Deficit\n31 Dec 2025")
    ax.axhline(0, color="#999999", lw=0.8)
    ax.set_ylabel("EUR m (deficit = DBO - assets)")
    ax.set_title("Figure 3. IAS 19 deficit: what moved in 2025")
    footnote(fig, f"Synthetic members and member experience. Market data 2024-12-30 and {market_date}; "
                  "equities MSCI World net EUR, cash €STR.")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_tornado(results, path, market_date="2025-12-31"):
    """Supporting figure: change in the IAS 19 deficit under each one-at-a-time scenario (EUR m)."""
    pairs = [("Discount rate -/+0.5%", "discount_minus_50bp", "discount_plus_50bp"),
             ("Inflation +/-0.5%", "inflation_plus_50bp", "inflation_minus_50bp"),
             ("Equities -20%", "equities_minus_20pct", None),
             ("Life expectancy +1 year", "life_expectancy_plus_1", None),
             ("Salary +/-0.5%", "salary_plus_50bp", "salary_minus_50bp")]
    base = results["base"]["ias19_deficit"]
    rows = []
    for label, bad, good in pairs:
        rows.append((label, (results[bad]["ias19_deficit"] - base) / 1e6,
                     (results[good]["ias19_deficit"] - base) / 1e6 if good else 0.0))
    rows.sort(key=lambda r: abs(r[1]) + abs(r[2]))
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, (label, bad, good) in enumerate(rows):
        ax.barh(i, bad, color="#C44E52")
        ax.barh(i, good, color="#55A868")
        ax.text(bad, i, f" {bad:+.1f}", va="center", ha="left" if bad >= 0 else "right", fontsize=8)
        if good:
            ax.text(good, i, f"{good:+.1f} ", va="center", ha="right" if good < 0 else "left", fontsize=8)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    lo, hi = min(r[2] for r in rows + [("", 0, 0)]), max(r[1] for r in rows)
    ax.set_xlim(lo * 1.35, hi * 1.2)
    ax.axvline(0, color="#555555", lw=0.8)
    ax.set_xlabel("Change in IAS 19 deficit, EUR m (assets revalued)")
    ax.set_title("Deficit sensitivity (IAS 19)")
    ax.spines[["top", "right"]].set_visible(False)
    footnote(fig, f"Synthetic members. Market data at {market_date}.")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig4_paths(paths, contributions, path, market_date="2025-12-31"):
    """Figure 4: assets / (FS + FSR) over the 3-year funding proposal under each option."""
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [2.2, 1]})
    styles = {"No action": ("#999999", "--"), "Contributions only": ("#4C72B0", "-"),
              "Switch only": ("#DD8452", "-"), "Switch + contributions": ("#55A868", "-")}
    for name, p in paths.items():
        colour, ls = styles[name]
        ax.plot([x["year"] for x in p], [x["cover"] * 100 for x in p], ls, color=colour, marker="o", label=name)
    ax.axhline(100, color="#C44E52", lw=0.8)
    ax.set_ylabel("Assets / (FS + FSR), %")
    ax.set_xticks([x["year"] for x in next(iter(paths.values()))])
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("FS + FSR cover")
    ax.spines[["top", "right"]].set_visible(False)
    names = list(contributions)
    ax2.bar(range(len(names)), [contributions[k] / 1e6 for k in names], color=[styles[k][0] for k in names])
    for i, k in enumerate(names):
        ax2.text(i, contributions[k] / 1e6, f"{contributions[k] / 1e6:.1f}", ha="center", va="bottom", fontsize=8)
    ax2.set_xticks(range(len(names)), [k.replace(" + ", "\n+ ").replace(" only", "\nonly") for k in names], fontsize=8)
    ax2.set_title("Deficit contributions, EUR m a year")
    ax2.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Figure 4. Restoring the funding standard reserve over 3 years")
    footnote(fig, f"Synthetic members. Yields held at {market_date}; expected returns in config/assets.yaml. "
                  "3 years is the base scenario; the statutory period follows the Pensions Act.")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig5_buyin(steps, compare, path, market_date="2025-12-31"):
    """Figure 5: premium build-up (left) and the three measures before / after on day one (right)."""
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1.6, 1]})
    short = ["Pensioner\nIAS 19 DBO", "EIOPA\nRFR + VA", "Fixed-rate\nincreases", "Insurer\nmortality", "Expenses",
             "Risk\nmargin", "Spread\npassed on", "Profit"]
    waterfall(ax, short[:-1] + [short[-1]], steps[0]["level"] / 1e6, [s["effect"] / 1e6 for s in steps[1:]],
              "Premium")
    ax.set_ylim(steps[0]["level"] / 1e6 * 0.85, None)
    ax.set_ylabel("EUR m")
    ax.set_title("Buy-in premium (Solvency II TP is the benchmark, not the price)", fontsize=10)
    labels = list(compare)
    measures = ["IAS 19 funding level", "FS funding level", "FS + FSR cover"]
    width = 0.8 / len(labels)
    colours = ["#999999", "#4C72B0", "#55A868"]
    for i, lab in enumerate(labels):
        vals = [compare[lab][mm] * 100 for mm in measures]
        xs = np.arange(len(measures)) + i * width
        ax2.bar(xs, vals, width, label=lab, color=colours[i % 3])
        for x, v in zip(xs, vals):
            ax2.text(x, v, f"{v:.0f}", ha="center", va="bottom", fontsize=7)
    ax2.axhline(100, color="#C44E52", lw=0.8)
    ax2.set_xticks(np.arange(len(measures)) + width * (len(labels) - 1) / 2, measures, fontsize=8)
    ax2.set_ylim(80, None)
    ax2.set_ylabel("%")
    ax2.legend(frameon=False, fontsize=7)
    ax2.set_title("Day one: before and after", fontsize=10)
    ax2.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Figure 5. Pensioner buy-in: price and day-one effects")
    footnote(fig, f"Synthetic members. EIOPA RFR + VA and ECB curves at {market_date}. IAS 19 effect assumes a "
                  "qualifying insurance policy that exactly matches the insured benefits. Illustrative price.")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)
