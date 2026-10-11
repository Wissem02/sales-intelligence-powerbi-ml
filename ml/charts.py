"""Charts for the README, built from ml/results.json and powerbi/data/fact_forecast.csv."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "images"; IMG.mkdir(exist_ok=True)
BLUE, ORANGE, LIGHT, INK, MUTED = "#2a78d6", "#eb6834", "#9fc3ee", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#bbb", "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.labelcolor": MUTED})
r = json.loads((ROOT / "ml" / "results.json").read_text())

# Segments: share of customers vs share of revenue
seg = pd.DataFrame(r["segments"]).set_index("Segment").sort_values("RevenueShare")
fig, ax = plt.subplots(figsize=(7, 3.4))
y = range(len(seg))
ax.barh([i + 0.2 for i in y], seg["CustomerShare"] * 100, height=0.38, color=LIGHT, label="% of customers")
ax.barh([i - 0.2 for i in y], seg["RevenueShare"] * 100, height=0.38, color=BLUE, label="% of revenue")
for i, (c, v) in enumerate(zip(seg["CustomerShare"], seg["RevenueShare"])):
    ax.text(c * 100 + 1, i + 0.2, f"{c:.0%}", va="center", fontsize=8, color=MUTED)
    ax.text(v * 100 + 1, i - 0.2, f"{v:.0%}", va="center", fontsize=8, color=INK)
ax.set_yticks(list(y)); ax.set_yticklabels(seg.index)
ax.set_xlabel("%"); ax.legend(frameon=False, fontsize=8, loc="lower right")
ax.set_title("Customer segments (K-Means on RFM)", loc="left", color=INK, fontsize=11, fontweight="bold")
fig.tight_layout(); fig.savefig(IMG / "segments.png", dpi=150); plt.close(fig)

# Forecast
f = pd.read_csv(ROOT / "powerbi" / "data" / "fact_forecast.csv", parse_dates=["Month"])
a, bt, fc = f[f.Type == "Actual"], f[f.Type == "Backtest"], f[f.Type == "Forecast"]
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.plot(a.Month, a.Actual / 1e6, color=BLUE, lw=2, label="Actual")
ax.plot(bt.Month, bt.Forecast / 1e6, color=MUTED, lw=1.5, ls="--",
        label=f"Backtest (MAPE {r['forecast_backtest_mape_pct']}%)")
ax.fill_between(fc.Month, fc.Lower80 / 1e6, fc.Upper80 / 1e6, color=ORANGE, alpha=0.15, label="80% interval")
ax.plot(fc.Month, fc.Forecast / 1e6, color=ORANGE, lw=2, label="Forecast Jun-Dec 2020")
ax.set_ylabel("Revenue ($M)"); ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_title("Monthly revenue: actual, backtest and forecast", loc="left", color=INK, fontsize=11, fontweight="bold")
fig.tight_layout(); fig.savefig(IMG / "forecast.png", dpi=150); plt.close(fig)
print("charts written")
