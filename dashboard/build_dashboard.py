"""
Builds dashboard/index.html: a self-contained interactive version of the 4-page report.
Reads the CSVs produced by ml/pipeline.py, pre-aggregates them, and injects the data
into dashboard/template.html.   Run:  python dashboard/build_dashboard.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "powerbi" / "data"
HERE = Path(__file__).parent

f = pd.read_csv(D / "fact_sales.csv", parse_dates=["OrderDate"])
p = pd.read_csv(D / "dim_product.csv")
t = pd.read_csv(D / "dim_territory.csv")
dt = pd.read_csv(D / "dim_date.csv")
c = pd.read_csv(D / "dim_customer.csv")
fc = pd.read_csv(D / "fact_forecast.csv")
results = json.loads((ROOT / "ml" / "results.json").read_text())

f = (f.merge(p[["ProductKey", "Product", "Subcategory", "Category"]], on="ProductKey")
      .merge(t[["SalesTerritoryKey", "Country"]], on="SalesTerritoryKey")
      .merge(dt[["DateKey", "Fiscal Year", "MonthKey"]], on="DateKey"))
f["FY"] = f["Fiscal Year"]

# Monthly cube: month x channel x category x country (additive measures)
cube = (f.groupby(["MonthKey", "FY", "Channel", "Category", "Country"])
          .agg(r=("SalesAmount", "sum"), pr=("Profit", "sum"), q=("Quantity", "sum")).reset_index())
cube[["r", "pr"]] = cube[["r", "pr"]].round(0)

# Orders are distinct counts, so they get their own cube without category
orders = (f.groupby(["MonthKey", "FY", "Channel", "Country"])["SalesOrder"].nunique()
            .reset_index(name="o"))

# Subcategory profitability by FY x channel
sub = (f.groupby(["FY", "Channel", "Category", "Subcategory"])
         .agg(r=("SalesAmount", "sum"), pr=("Profit", "sum"), q=("Quantity", "sum")).reset_index())
sub[["r", "pr"]] = sub[["r", "pr"]].round(0)

# Top products for each FY / channel filter combination (incl. "All")
top = {}
for fy in ["All"] + sorted(f["FY"].unique()):
    for ch in ["All", "Internet", "Reseller"]:
        s = f if fy == "All" else f[f["FY"] == fy]
        s = s if ch == "All" else s[s["Channel"] == ch]
        g = s.groupby("Product").agg(r=("SalesAmount", "sum"), pr=("Profit", "sum")).nlargest(10, "r")
        top[f"{fy}|{ch}"] = [[k, round(v.r), round(v.pr)] for k, v in g.iterrows()]

# Segments (Internet customers)
seg = results["segments"]
cust = c[c["Segment"] != "No Internet orders"]
sample = pd.concat([g.sample(min(len(g), 350), random_state=1) for _, g in cust.groupby("Segment")])
scatter = [[s, int(r), round(m)] for s, r, m in zip(sample["Segment"], sample["RecencyDays"], sample["Monetary"])]

# Segment revenue by FY (Internet orders)
seg_fy = (f[f["Channel"] == "Internet"].merge(c[["CustomerKey", "Segment"]], on="CustomerKey")
            .groupby(["FY", "Segment"])["SalesAmount"].sum().round(0).reset_index())

data = {
    "cube": cube.values.tolist(), "cubeCols": list(cube.columns),
    "orders": orders.values.tolist(), "ordersCols": list(orders.columns),
    "sub": sub.values.tolist(), "subCols": list(sub.columns),
    "top": top,
    "segments": seg, "scatter": scatter, "segFy": seg_fy.values.tolist(),
    "forecast": fc.fillna("").values.tolist(), "forecastCols": list(fc.columns),
    "mape": results["forecast_backtest_mape_pct"], "naiveMape": results["naive_same_month_last_year_mape_pct"],
    "fys": sorted(f["FY"].unique()),
    "lastDate": str(f["OrderDate"].max().date()),
}
js = json.dumps(data, separators=(",", ":"), default=str)
html = (HERE / "template.html").read_text().replace("/*__DATA__*/null", js)
# index.html: standalone page for GitHub Pages / local use
(HERE / "index.html").write_text('<!doctype html>\n<html lang="en">\n' + html + "\n</html>\n")
print(f"index.html written ({len(html) / 1024:.0f} KB)")
