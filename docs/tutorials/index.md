# Tutorials

Thirteen tutorial notebooks cover the full palmwtc workflow. Each is a
thin wrapper around the library API: `DataPaths.resolve()` →
`run_step(...)` → plot → narrative. All algorithmic logic stays in the
`palmwtc.*` package.

## Pipeline spine (run in order)

| # | Title | Runs on synthetic? |
|---|---|---|
| [010](010_Data_Integration.ipynb) | Core data integration (raw → unified monthly) | Stub (needs raw chamber files) |
| [020](020_QC_Rule_Based.ipynb) | Rule-based QC | Stub (needs raw chamber files) |
| [030](030_Flux_Cycle_Calculation.ipynb) | CO₂ / H₂O flux cycle calculation | **Yes** |
| [032](032_Window_Selection_Production.ipynb) | Calibration window selection (production) | Yes (0 windows on toy data) |
| [033](033_Science_Validation.ipynb) | Science validation against literature | Yes (reports skip on synthetic) |

## Diagnostics & audits

| # | Title | Purpose |
|---|---|---|
| [011](011_Weather_vs_Chamber.ipynb) | Weather station vs chamber | Microclimate-artifact diagnostic |
| [025](025_Cross_Chamber_Bias.ipynb) | Cross-chamber bias | Sensor calibration consistency check |
| [026](026_CO2_H2O_Segmented_Bias.ipynb) | CO₂/H₂O segmented bias | Time-localised drift detection |
| [034](034_QC_and_Window_Audit.ipynb) | QC + window audit | Pre-calibration sanity check |

## Optional / opt-in

| # | Title | Purpose |
|---|---|---|
| [022](022_QC_ML_Enhanced.ipynb) | ML-enhanced QC (optional) | IsolationForest contextual outliers (`palmwtc[ml]`) |
| [023](023_Field_Alert_Report.ipynb) | Field alert HTML report | Email-able operator report |
| [031](031_Window_Selection_Reference.ipynb) | Window selection (reference) | Methodology audit; superseded by 032 |
| [035](035_QC_Threshold_Sensitivity.ipynb) | QC threshold sensitivity sweep | Operating-point tuning |

```{toctree}
:maxdepth: 1
:hidden:

010_Data_Integration
011_Weather_vs_Chamber
020_QC_Rule_Based
022_QC_ML_Enhanced
023_Field_Alert_Report
025_Cross_Chamber_Bias
026_CO2_H2O_Segmented_Bias
030_Flux_Cycle_Calculation
031_Window_Selection_Reference
032_Window_Selection_Production
033_Science_Validation
034_QC_and_Window_Audit
035_QC_Threshold_Sensitivity
```
