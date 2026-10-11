# Power BI build guide

Time needed: about 1.5 hours. Requires **Power BI Desktop** (free, Windows).
Everything the report needs is in `powerbi/data/` (created by `python ml/pipeline.py`).

---

## Step 1: Load the data (Power Query)

1. **Home → Get data → Text/CSV** and load each file in `powerbi/data/`:
   `fact_sales`, `fact_forecast`, `dim_date`, `dim_product`, `dim_customer`, `dim_reseller`, `dim_territory`.
2. For each file, click **Transform Data** (not Load) and check the column types:
   - `fact_sales[OrderDate]`, `dim_date[Date]`, `fact_forecast[Month]` → **Date**
   - `SalesAmount`, `TotalCost`, `Profit`, `Actual`, `Forecast`, `Lower80`, `Upper80`, `Monetary` → **Fixed decimal number**
   - All `...Key` columns → **Whole number**
3. Rename the queries exactly as the file names above (no `.csv`). The DAX measures use these names.
4. **Close & Apply**.

Optional, to make the folder path easy to change: **Home → Manage Parameters → New**, name it `DataFolder`,
type Text, value = the full path to `powerbi\data\`. Then, in each query's Source step, replace the hard-coded path with:

```m
Source = Csv.Document(File.Contents(DataFolder & "fact_sales.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true])
```

## Step 2: Build the star schema (Model view)

Create these relationships (all **many-to-one, single direction**, from fact to dimension):

| From (many) | To (one) |
|---|---|
| `fact_sales[DateKey]` | `dim_date[DateKey]` |
| `fact_sales[ProductKey]` | `dim_product[ProductKey]` |
| `fact_sales[CustomerKey]` | `dim_customer[CustomerKey]` |
| `fact_sales[ResellerKey]` | `dim_reseller[ResellerKey]` |
| `fact_sales[SalesTerritoryKey]` | `dim_territory[SalesTerritoryKey]` |
| `fact_forecast[Month]` | `dim_date[Date]` |

Then:
- Select `dim_date` → **Table tools → Mark as date table** → column `Date`. (Required for the time-intelligence measures.)
- In `dim_date`, select `MonthName` → **Sort by column → MonthNumber**.
- Hide every `...Key` column in the fact tables (right-click → Hide in report view).

## Step 3: Add the measures

1. **Home → Enter data**, name the table `_Measures`, load it, then delete its default column.
2. Copy each measure from `dax/measures.dax` into **Modeling → New measure** (one measure per block).
3. Format: `Revenue`, `Profit`, `Avg Order Value`, forecast measures → Currency, 0 decimals.
   `Margin %`, `Revenue YoY %`, `Category Share %`, `Segment Revenue Share %`, `Backtest MAPE %` → Percentage, 1 decimal.

## Step 4: Apply the theme

**View → Themes → Browse for themes** → `powerbi/theme.json`.

## Step 5: Build the 4 report pages

Canvas size 16:9. Put slicers for **Fiscal Year** and **Channel** at the top of every page
(select both slicers → **View → Sync slicers** so they apply to all pages).

### Page 1: Executive Overview
| Visual | Fields |
|---|---|
| 5 KPI cards | `Revenue`, `Profit`, `Margin %`, `Orders`, `Revenue YoY %` |
| Line chart | X: `dim_date[Month]` (sorted by MonthKey), Y: `Revenue` and `Revenue PY` |
| Clustered bar | Y: `dim_product[Category]`, X: `Revenue`; tooltip: `Margin %` |
| Filled map or bar | `dim_territory[Country]`, `Revenue` |
| Donut | Legend: `fact_sales[Channel]`, Values: `Revenue` |

### Page 2: Profitability
| Visual | Fields |
|---|---|
| Matrix | Rows: `Channel`, `Category`, `Subcategory`; Values: `Revenue`, `Profit`, `Margin %` |
| Conditional formatting | On `Margin %`: background color rules, red < 0, amber < 10%, green otherwise |
| Scatter | X: `Revenue`, Y: `Margin %`, Details: `dim_product[Subcategory]`, Size: `Units Sold` |
| Table | Top 10 products: `Product`, `Revenue`, `Margin %`, `Product Rank` (filter Product Rank <= 10) |

Key story for this page: **Reseller bike sales lose money** (about -1.5% margin on $66M). Put a text box with that finding.

### Page 3: Customer Segments (ML)
| Visual | Fields |
|---|---|
| Cards | `Segment Customers`, `Avg Revenue per Customer`, `Avg Recency (days)` |
| Clustered bar | Y: `dim_customer[Segment]`, X: `Segment Customers` and `Revenue` |
| Scatter | X: `RecencyDays`, Y: `Monetary`, Legend: `Segment` (use `dim_customer` columns, Details: `CustomerKey`) |
| Table | `Segment`, `Segment Customers`, `Avg Revenue per Customer`, `Avg Recency (days)`, `Segment Revenue Share %` |
| Text box | One recommended action per segment (see README) |

Add a page-level filter `fact_sales[Channel] = Internet` (segments are built on Internet customers).

### Page 4: Revenue Forecast (ML)
| Visual | Fields |
|---|---|
| Line chart | X: `fact_forecast[Month]`, Y: `Actual (monthly)`, `Forecast (monthly)`, `Forecast Lower 80`, `Forecast Upper 80` |
| Format | Lower/Upper lines: thin, dashed, light orange. Forecast: orange. Actual: blue |
| Cards | `Forecast Jun-Dec 2020`, `Backtest MAPE %` |
| Text box | "Trend + seasonality model, backtested on Jan-May 2020: 12% MAPE vs 40% for a same-month-last-year baseline." |

Turn off the Fiscal Year slicer interaction on this page (**Format → Edit interactions**), so the forecast always shows.

## Step 6: Finish

- Add a title text box on each page and the page name in the navigator.
- **File → Save as** `SalesIntelligence.pbix` in the `powerbi/` folder.
- Take a screenshot of each page and save them as `images/page1_overview.png`, `images/page2_profitability.png`,
  `images/page3_segments.png`, `images/page4_forecast.png`. Then, in README.md, delete the two comment lines `<!--` and `-->` around the "Dashboard" images so they appear.
- Optional: **File → Publish to web** (needs a free Power BI account) and add the public link to the README.

## Refreshing with new data

Re-run `python ml/pipeline.py` (it rebuilds all CSVs, segments and the forecast), then **Home → Refresh** in Power BI.
