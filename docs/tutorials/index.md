# Tutorials

Four first-class tutorials walk through the core pipeline. Each is an
executable notebook that runs against the bundled synthetic sample
(except 010 and 020, which need real chamber data — see notes below).

| # | Title | Runs on synthetic? |
|---|---|---|
| 010 | [Core data integration](010_Data_Integration.ipynb) | No (needs real raw chamber files) |
| 020 | [QC (rule-based)](020_QC_Rule_Based.ipynb) | No (needs real raw chamber files) |
| 030 | [CO2 / H2O flux cycle calculation](030_Flux_Cycle_Calculation.ipynb) | **Yes** |
| 033 | [Science validation](033_Science_Validation.ipynb) | **Yes** (reports skip on synthetic; full output on real data) |

The tutorials follow a thin-notebook convention: each cell is either
narrative, a single library call, or a plot. All algorithmic logic lives
in the `palmwtc.*` package — the notebook is the scientific story
wrapped around `palmwtc.pipeline.run_step(...)` calls.

```{toctree}
:maxdepth: 1
:hidden:

010_Data_Integration
020_QC_Rule_Based
030_Flux_Cycle_Calculation
033_Science_Validation
```
