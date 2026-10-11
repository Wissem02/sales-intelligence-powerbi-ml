"""
Sales Intelligence: Power BI + Machine Learning pipeline
Source: Microsoft AdventureWorks Sales sample (Jul 2017 - Jun 2020, 121,253 order lines)

This script prepares everything the Power BI report loads:
  1. Cleans the raw Excel model and exports a star schema (fact + dimension CSVs)
  2. ML #1  Customer segmentation: RFM features + K-Means (Internet customers)
  3. ML #2  Monthly revenue forecast: trend + seasonality regression, backtested,
            with an 80% prediction interval
Outputs go to powerbi/data/. Run:  python ml/pipeline.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import Ridge
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "AdventureWorks Sales.xlsx"
OUT = ROOT / "powerbi" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------ 1. Star schema
x = pd.read_excel(RAW, sheet_name=None)
sales = x["Sales_data"].merge(x["Sales Order_data"], on="SalesOrderLineKey", how="left")
quality = {
    "order_lines": len(sales),
    "lines_without_order_header": int(sales["Channel"].isna().sum()),
    "missing_ship_date": int(sales["ShipDateKey"].isna().sum()),
    "negative_amounts": int((sales["Sales Amount"] < 0).sum()),
    "duplicate_line_keys": int(sales["SalesOrderLineKey"].duplicated().sum()),
}

sales["OrderDate"] = pd.to_datetime(sales["OrderDateKey"].astype(str), format="%Y%m%d")
fact_sales = pd.DataFrame({
    "SalesOrderLineKey": sales["SalesOrderLineKey"],
    "SalesOrder": sales["Sales Order"],
    "Channel": sales["Channel"],
    "OrderDate": sales["OrderDate"].dt.date,
    "DateKey": sales["OrderDateKey"],
    "CustomerKey": sales["CustomerKey"],
    "ResellerKey": sales["ResellerKey"],
    "ProductKey": sales["ProductKey"],
    "SalesTerritoryKey": sales["SalesTerritoryKey"],
    "Quantity": sales["Order Quantity"],
    "SalesAmount": sales["Sales Amount"].round(2),
    "TotalCost": sales["Total Product Cost"].round(2),
})
fact_sales["Profit"] = (fact_sales["SalesAmount"] - fact_sales["TotalCost"]).round(2)
fact_sales.to_csv(OUT / "fact_sales.csv", index=False)

dim_date = x["Date_data"].copy()
dim_date["Date"] = pd.to_datetime(dim_date["Date"]).dt.date
dim_date["Year"] = pd.to_datetime(dim_date["Date"]).dt.year
dim_date["MonthNumber"] = pd.to_datetime(dim_date["Date"]).dt.month
dim_date["MonthName"] = pd.to_datetime(dim_date["Date"]).dt.strftime("%b")
dim_date.to_csv(OUT / "dim_date.csv", index=False)
x["Product_data"].to_csv(OUT / "dim_product.csv", index=False)
x["Reseller_data"].to_csv(OUT / "dim_reseller.csv", index=False)
x["Sales Territory_data"].to_csv(OUT / "dim_territory.csv", index=False)

# --------------------------------------- 2. ML #1 RFM + K-Means segmentation
internet = sales[sales["Channel"] == "Internet"]
snapshot = internet["OrderDate"].max() + pd.Timedelta(days=1)
rfm = internet.groupby("CustomerKey").agg(
    LastOrder=("OrderDate", "max"),
    Frequency=("Sales Order", "nunique"),
    Monetary=("Sales Amount", "sum"),
)
rfm["RecencyDays"] = (snapshot - rfm["LastOrder"]).dt.days
features = np.log1p(rfm[["RecencyDays", "Frequency", "Monetary"]])
Xs = StandardScaler().fit_transform(features)

sil = {}
for k in range(3, 7):
    labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(Xs)
    sil[k] = round(float(silhouette_score(Xs, labels, sample_size=6000, random_state=42)), 3)
# Silhouette rises slowly with k (0.42 at k=4, 0.46 at k=6); 4 segments are kept
# because each one maps to a distinct marketing action
K = 4
km = KMeans(n_clusters=K, n_init=10, random_state=42).fit(Xs)
rfm["Cluster"] = km.labels_

# Name clusters from their profile with explicit business rules
prof = rfm.groupby("Cluster")[["RecencyDays", "Frequency", "Monetary"]].mean()
mapping, left = {}, list(prof.index)
champ = prof.loc[left, "Frequency"].idxmax(); mapping[champ] = "Champions"; left.remove(champ)
new = prof.loc[left, "RecencyDays"].idxmin(); mapping[new] = "New Customers"; left.remove(new)
big = prof.loc[left, "Monetary"].idxmax(); mapping[big] = "Lapsed Big Spenders"; left.remove(big)
mapping[left[0]] = "Low-Value Occasional"
rfm["Segment"] = rfm["Cluster"].map(mapping)

seg_profile = rfm.groupby("Segment").agg(
    Customers=("Frequency", "size"),
    AvgRecencyDays=("RecencyDays", "mean"),
    AvgOrders=("Frequency", "mean"),
    AvgRevenue=("Monetary", "mean"),
    TotalRevenue=("Monetary", "sum"),
).round(1)
seg_profile["RevenueShare"] = (seg_profile["TotalRevenue"] / seg_profile["TotalRevenue"].sum()).round(4)
seg_profile["CustomerShare"] = (seg_profile["Customers"] / seg_profile["Customers"].sum()).round(4)
print(seg_profile.sort_values("AvgRevenue", ascending=False))

dim_customer = x["Customer_data"].merge(
    rfm[["RecencyDays", "Frequency", "Monetary", "Segment"]].round(2),
    left_on="CustomerKey", right_index=True, how="left")
dim_customer["Segment"] = dim_customer["Segment"].fillna("No Internet orders")
dim_customer.to_csv(OUT / "dim_customer.csv", index=False)

# -------------------------------------------- 3. ML #2 monthly revenue forecast
monthly = (fact_sales.assign(Month=pd.to_datetime(fact_sales["OrderDate"]).dt.to_period("M"))
           .groupby("Month")["SalesAmount"].sum())
monthly = monthly[monthly.index < pd.Period("2020-06", "M")]   # June 2020 is a partial month


def design(periods, start):
    t = np.array([(p - start).n for p in periods])
    month = np.array([p.month for p in periods])
    dummies = (month[:, None] == np.arange(1, 13)[None, :]).astype(float)
    return np.column_stack([t, dummies])


start = monthly.index[0]
# Backtest: train to Dec 2019, predict Jan-May 2020
train, test = monthly[monthly.index <= pd.Period("2019-12", "M")], monthly[monthly.index > pd.Period("2019-12", "M")]
m_bt = Ridge(alpha=1.0).fit(design(train.index, start), train.values)
pred_bt = m_bt.predict(design(test.index, start))
mape = float(np.mean(np.abs(pred_bt - test.values) / test.values))
naive = float(np.mean(np.abs(train.values[-12:-7] - test.values) / test.values))  # same month last year

# Final model on all complete months, forecast Jun-Dec 2020
model = Ridge(alpha=1.0).fit(design(monthly.index, start), monthly.values)
resid_sd = float(np.std(monthly.values - model.predict(design(monthly.index, start)), ddof=13))
future = pd.period_range("2020-06", "2020-12", freq="M")
fc = model.predict(design(future, start))
z = 1.2816  # 80% interval

fact_forecast = pd.concat([
    pd.DataFrame({"Month": monthly.index.to_timestamp().date, "Actual": monthly.values.round(0),
                  "Forecast": np.nan, "Lower80": np.nan, "Upper80": np.nan, "Type": "Actual"}),
    pd.DataFrame({"Month": test.index.to_timestamp().date, "Actual": np.nan, "Forecast": pred_bt.round(0),
                  "Lower80": np.nan, "Upper80": np.nan, "Type": "Backtest"}),
    pd.DataFrame({"Month": future.to_timestamp().date, "Actual": np.nan, "Forecast": fc.round(0),
                  "Lower80": (fc - z * resid_sd).round(0), "Upper80": (fc + z * resid_sd).round(0),
                  "Type": "Forecast"}),
])
fact_forecast.to_csv(OUT / "fact_forecast.csv", index=False)

# ---------------------------------------------------------------- summary
fs = fact_sales
summary = {
    "data_quality": quality,
    "revenue_total": round(fs["SalesAmount"].sum(), 0),
    "profit_total": round(fs["Profit"].sum(), 0),
    "margin_pct": round(100 * fs["Profit"].sum() / fs["SalesAmount"].sum(), 1),
    "orders": int(fs["SalesOrder"].nunique()),
    "revenue_by_channel": fs.groupby("Channel")["SalesAmount"].sum().round(0).to_dict(),
    "margin_by_channel_pct": (100 * fs.groupby("Channel")["Profit"].sum() / fs.groupby("Channel")["SalesAmount"].sum()).round(1).to_dict(),
    "internet_customers": int(len(rfm)),
    "silhouette_by_k": sil,
    "segments": seg_profile.reset_index().to_dict(orient="records"),
    "forecast_backtest_mape_pct": round(100 * mape, 1),
    "naive_same_month_last_year_mape_pct": round(100 * naive, 1),
    "forecast_jun_dec_2020_total": round(float(fc.sum()), 0),
    "forecast_monthly": {str(p): round(float(v), 0) for p, v in zip(future, fc)},
    "monthly_actual": {str(p): round(float(v), 0) for p, v in monthly.items()},
}
(ROOT / "ml" / "results.json").write_text(json.dumps(summary, indent=2, default=str))
print(json.dumps({k: v for k, v in summary.items() if k not in ("monthly_actual",)}, indent=2, default=str))
