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
