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
