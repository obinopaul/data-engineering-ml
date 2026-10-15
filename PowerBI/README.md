# Power BI practice

Open these files in **Power BI Desktop on Windows**. They were selected from the repository's `powerbi_files/` folder. The two `.pbix` files are existing reports; the `.pbit` is a genuine reusable template. Their layouts were inspected and their archives checked, but Desktop rendering and refresh have not been tested here on Linux.

## Three examples to study

| Start here | What to learn | Data and adaptation |
|---|---|---|
| [Oil-production report](OilProduction/Oil%20Production%20Analysis%20Report.pbix) | Four pages: summary, dashboard, trends and forecast; 70 visual containers | Includes `OilProduction/Dataset.csv`. Original author attributes data to Saudi public sources. These are aggregate production figures, not wireline telemetry. Inspect forecast assumptions rather than treating its forecasts as validated. |
| [Operations/safety report](OperationsSafety/Oil%20%26%20Gas%20Data%20Intelligence%20Dashboard.pbix) | Six pages: executive overview, observations, verifications, dropped objects, training and change control; 58 visual containers | Five CSVs are included. The author explicitly describes these as **simulated operational records**. Useful dashboard design, not measured sensor data. |
| [Snowflake DirectQuery template](SnowflakeTemplate/Tasty%20Bytes%20Direct%20Query%20Quickstart.pbit) | Three pages: order summary/detail and time intelligence; Snowflake connection parameters and a dimensional model | Food-truck sales example. Requires its Tasty Bytes tables or deliberate query/model changes; changing the server alone does not turn it into an oilfield dashboard. |

For either PBIX: open → **Transform data → Data source settings → Change Source** (or edit its Source step) → point to the corresponding local CSVs → check column types and relationships → Close & Apply. Save a working copy. To reuse only its design, replace queries and rebind each visual's fields. To create your own data-free template, use **File → Export → Power BI template** after checking parameters and queries.

The PBIT exposes five parameters: `Snowflake Server`, `Snowflake Warehouse`, `Snowflake Role`, `Snowflake Database`, `Snowflake Schema`. Its tables include Customer, Date, Franchise, Location, Menu Item, Time, Truck and three Order tables. The original setup SQL remains in `../../powerbi_files/sfguide-end-to-end-analytics-with-snowflake-and-power-bi/`; do not run its full warehouse setup just to practice our prediction dashboard.

## Connect directly to our Snowflake tables

1. Get data → **Snowflake**. Server: your account's full hostname, such as `organization-account.snowflakecomputing.com` (no `https://`). Warehouse: `COMPUTE_WH`.
2. Use the existing permitted role, database `INTERVIEW_DB` and schema `ANALYTICS`. Authenticate using an option supported by the connector and your account policy. Power BI manages its own credentials; it does not read Python's `.env` or dbt profile.
3. Choose **Import** for an easy local rehearsal, or **DirectQuery** to query warehouse data as visuals run. Select the actual dbt mart/prediction table in Navigator. It must already exist, and your role needs USAGE and SELECT privileges.
4. Publish when ready; configure the semantic model's data-source credentials in the Power BI service. Import needs scheduled/on-demand refresh. DirectQuery still needs valid credentials, an available warehouse and deliberate page-refresh settings. Private-network access can require additional gateway/network configuration.

[Microsoft's Snowflake connector guide](https://learn.microsoft.com/en-us/power-query/connectors/snowflake) documents connection/authentication options. [Automatic page refresh](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-automatic-page-refresh) depends on mode, capacity and administrator settings; a one-second Desktop setting does not promise one-second refresh in the service.

## Visualize our actual ML outputs

Run [the study notebook](../oilfield_ml_case_study.ipynb) first. Get data → Text/CSV → select `main/.cache/oilfield_ml/log_predictions.csv`. Name the table **LogPredictions**. Keep `id` as **Text** (for example `force2020:55071`), set DEPTH_MD/probability to decimal, and actual/predicted labels to whole numbers. Each row represents one depth sample in the held-out well.

Add a well slicer, class-count cards, a probability-versus-depth scatter plot and an actual-vs-predicted matrix. Turn off automatic summing for depth/probability. Suggested measures:

```dax
Samples = COUNTROWS(LogPredictions)
Correct = COUNTROWS(FILTER(LogPredictions,
    LogPredictions[actual_sandstone] = LogPredictions[predicted_sandstone]))
Accuracy = DIVIDE([Correct], [Samples])
TP = COUNTROWS(FILTER(LogPredictions,
    LogPredictions[actual_sandstone] = 1 && LogPredictions[predicted_sandstone] = 1))
FN = COUNTROWS(FILTER(LogPredictions,
    LogPredictions[actual_sandstone] = 1 && LogPredictions[predicted_sandstone] = 0))
Sensitivity = DIVIDE([TP], [TP] + [FN])
```

Load `telemetry_predictions.csv` as a **separate fact table**. Set timestamp to Date/Time; make a line chart with timestamp, probability_slugging and actual_slugging, filtered to one source_file. Do not connect these unrelated fact tables by ID. Their models and targets differ. To use Snowflake instead, the notebook's optional `PUBLISH_PREDICTIONS` cell uploads the well-log predictions to `ANALYTICS.ML_LOG_PREDICTIONS` with a repeatable MERGE. It is disabled by default and has not been run remotely. After that upload succeeds, bind the log visuals to this Snowflake table instead of the CSV.

## Third-party applications

Power Query has [native connectors](https://learn.microsoft.com/en-us/power-query/connectors/), Web and OData readers. Vendor OAuth, pagination and refresh support vary. For NetSuite/ADP, our simpler shared route is **Ingestion → Snowflake RAW → dbt → ANALYTICS → Power BI**. This keeps vendor credentials and extraction logic in the existing ingestion layer. Power BI connects to Snowflake independently; there is one shared data destination, not a single universal login.

## Source credits and inspection

Reports are unchanged copies of the local sources: [Arafat3-DA oil production](https://github.com/Arafat3-DA/Oil-Production-Analysis-Report), `powerbi_files/Oil-Gas-Data-Intelligence-Power-BI-Dashboard` (author's source README retained there), and [Snowflake Labs Tasty Bytes](https://github.com/Snowflake-Labs/sfguide-end-to-end-analytics-with-snowflake-and-power-bi). The template's original license is retained in [its guide](SnowflakeTemplate/README.md). [inspection.json](inspection.json) records hashes and actual page names/counts. These counts include layout/text containers, not only charts.
