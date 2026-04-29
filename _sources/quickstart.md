# Quickstart — your first flux number in 3 minutes

palmwtc is a Python library for automated whole-tree chamber measurements
on individual oil palm trees. Each chamber encloses one tree and measures
CO₂ and H₂O concentrations every 30 seconds using a LI-COR LI-850 analyser.
This guide takes you from installation to a validated CO₂ flux number using
the bundled synthetic sample — no field data required.

---

## 1. Install

```bash
pip install 'palmwtc[ml,interactive]'
```

The `ml` extra adds scikit-learn (for ML-assisted QC outlier detection).
The `interactive` extra adds Plotly (for the interactive dashboard).
If you have an NVIDIA or Apple Silicon GPU, add `[gpu]` as well — it
accelerates the Isolation Forest step in large datasets.

Requires Python 3.11–3.13.

---

## 2. Load the bundled synthetic sample

palmwtc ships with a one-week synthetic dataset (30-second cadence, 2 chambers)
so every step below works immediately after install — no config file needed.

```python
from palmwtc.config import DataPaths

paths = DataPaths.resolve()
print(paths.describe())
```

Expected output:

```
DataPaths (source=sample (bundled synthetic), site=libz):
  raw_dir       = .../palmwtc/data/sample/synthetic
  processed_dir = .../palmwtc/data/sample/Data/Integrated_QC_Data
  exports_dir   = .../palmwtc/data/sample/exports
  config_dir    = .../palmwtc/data/sample/config
  extras        = <none>
```

When `source=sample (bundled synthetic)` appears, you are working with the
bundled data. To point palmwtc at your own chamber data, set the
`PALMWTC_DATA_DIR` environment variable or create a `palmwtc.yaml` config
file — see the [tutorials](tutorials/index.md) for details.

Load the raw sensor parquet:

```python
import pandas as pd

df = pd.read_parquet(paths.raw_dir / "QC_Flagged_Data_synthetic.parquet")
print(df.shape)          # (20160, 19)  — 7 days × 2880 rows/day × 30 s
print(df.columns.tolist())
```

The dataset has one row per 30-second interval. Columns follow the pattern
`CO2_C1`, `H2O_C1` (chamber 1) and `CO2_C2`, `H2O_C2` (chamber 2), plus
temperature, humidity, atmospheric pressure, battery voltage, and existing
QC flag columns for each chamber.

---

## 3. Quality-control the CO₂ signal

`QCProcessor` checks each sensor variable against physical limits, rate-of-change
thresholds, and a stuck-sensor (persistence) test. It adds a flag column for every
variable you process:

- **0** = good
- **1** = suspect (minor deviation)
- **2** = bad (reject)

```python
from palmwtc.qc import QCProcessor

# Define limits for CO2 from chamber 1.
# hard = absolute physical bounds (any value outside → flag 2).
# soft = expected operating range (outlier scoring uses this range).
co2_config = {
    "co2": {
        "columns": ["CO2_C1"],
        "hard": [300, 600],          # ppm — hard physical limits
        "soft": [350, 550],          # ppm — expected operating range
        "rate_of_change": {"limit": 50},   # max ppm per 30-s step
        "persistence": {"window": 5},      # flag if stuck for 5+ steps
    }
}

qc = QCProcessor(df=df, config_dict=co2_config)
result = qc.process_variable("CO2_C1", random_seed=42)

flagged_df = qc.get_processed_dataframe()
print(flagged_df[["TIMESTAMP", "CO2_C1", "CO2_C1_rule_flag", "CO2_C1_qc_flag"]].head(5))
```

Expected output:

```
            TIMESTAMP      CO2_C1  CO2_C1_rule_flag  CO2_C1_qc_flag
0 2026-03-01 00:00:00  401.461633                 0               0
1 2026-03-01 00:00:30  401.923752                 0               0
2 2026-03-01 00:01:00  403.618192                 0               0
3 2026-03-01 00:01:30  404.694238                 0               0
4 2026-03-01 00:02:00  404.516029                 0               0
```

Check how many points were flagged:

```python
summary = result["summary"]
print(f"Good (flag 0): {summary['flag_0_count']} ({summary['flag_0_percent']:.1f} %)")
print(f"Suspect (flag 1): {summary['flag_1_count']} ({summary['flag_1_percent']:.2f} %)")
print(f"Bad (flag 2): {summary['flag_2_count']} ({summary['flag_2_percent']:.2f} %)")
```

Expected output (bundled synthetic sample):

```
Good (flag 0): 20155 (100.0 %)
Suspect (flag 1): 1 (0.00 %)
Bad (flag 2): 4 (0.02 %)
```

---

## 4. Compute CO₂ fluxes

Each measurement cycle is one closed-chamber period (typically ~5 minutes of
continuous 30-second readings). palmwtc fits a linear regression to the rising or
falling CO₂ curve inside each cycle, converts the slope (ppm s⁻¹) to an absolute
flux (µmol m⁻² s⁻¹), and returns one row per cycle.

First, prepare the single-chamber data stream:

```python
from palmwtc.flux import prepare_chamber_data, calculate_flux_cycles

# Select chamber 1 columns, apply QC flag filtering, and run WPL correction.
chamber_df = prepare_chamber_data(flagged_df, "C1", require_h2o_for_wpl=False)
```

Then compute fluxes for every cycle:

```python
cycles = calculate_flux_cycles(chamber_df, "Chamber 1", use_multiprocessing=False)

# "flux_date" is the output column name from calculate_flux_cycles.
# Rename it to "flux_datetime" — the name that WindowSelector and
# run_science_validation expect — so the same DataFrame works for all steps.
cycles = cycles.rename(columns={"flux_date": "flux_datetime"})

print(cycles[["cycle_id", "flux_datetime", "flux_absolute", "flux_slope", "r2", "qc_flag"]].head(5))
```

Expected output (values vary with the synthetic sample):

```
   cycle_id       flux_datetime  flux_absolute  flux_slope        r2  qc_flag
0         1 2026-03-01 00:00:00      -2.358445   -0.009627  0.512461        0
1         2 2026-03-03 12:45:00       0.036619    0.000150  0.109499        1
```

Key columns:

| Column | Unit | Meaning |
|---|---|---|
| `flux_absolute` | µmol m⁻² s⁻¹ | CO₂ flux (negative = uptake by tree) |
| `flux_slope` | ppm s⁻¹ | raw CO₂ slope inside the cycle |
| `r2` | — | R² of the linear fit (higher = more linear cycle) |
| `qc_flag` | 0/1/2 | 0 = A-grade, 1 = B-grade, 2 = rejected |

---

## 5. Select calibration windows

A calibration window is a consecutive span of high-quality days whose cycle data
can be used to train the XPalm digital-twin model. `WindowSelector` scores every
cycle across five components (regression quality, robustness, sensor QC, drift, and
cross-chamber agreement), then identifies qualifying date ranges.

```python
from palmwtc.windows import WindowSelector

ws = WindowSelector(cycles)
ws.score_cycles()
ws.identify_windows()
ws.summary()
```

After `score_cycles()`, your cycles DataFrame gains a `cycle_confidence` column
(0–1 scale). After `identify_windows()`, `ws.windows_df` lists every qualifying
window with its `start_date`, `end_date`, `n_cycles`, and `window_score`.

```python
print(ws.cycles_df[["cycle_id", "flux_datetime", "cycle_confidence"]].head(5))
```

> **Note:** the bundled one-week synthetic sample is too short for the minimum
> 5-day window requirement, so `ws.windows_df` will be empty on this dataset.
> Run `WindowSelector` on a real multi-week dataset to see qualifying windows.
> See `tutorials/032_Window_Selection_Production.ipynb` for a worked example.

---

## 6. Validate against ecophysiology literature

`run_science_validation` runs four tests that check whether your flux data is
consistent with published values for oil palm:

1. **Light-response curve** — does Amax fall within the expected range?
2. **Temperature response (Q10)** — is the nighttime respiration temperature
   sensitivity between 1.5 and 3.5?
3. **Water-use efficiency (WUE)** — does WUE decrease as VPD increases?
4. **Inter-chamber agreement** — are the two chambers tracking each other?

The validator needs several columns beyond the basic flux output. In a full
pipeline run these come from the QC and H₂O steps; here we add them as
placeholders so the validator can run and demonstrate the scorecard structure:

```python
from palmwtc.validation import run_science_validation

# Columns required by run_science_validation but not produced by
# calculate_flux_cycles alone — in a real run, these come from the full
# pipeline (radiation logger, H2O flux, VPD from weather station).
cycles["Global_Radiation"] = float("nan")  # W m⁻²
cycles["h2o_slope"] = float("nan")         # mmol m⁻² s⁻¹
cycles["co2_slope"] = cycles["flux_slope"] # µmol m⁻² s⁻¹ (alias)
cycles["vpd_kPa"] = float("nan")           # kPa

report = run_science_validation(cycles)

scorecard = report["scorecard"]
print(f"Tests passed: {scorecard['n_pass']}")
print(f"Borderline:   {scorecard['n_borderline']}")
print(f"Failed:       {scorecard['n_fail']}")
print(f"Insufficient data (N/A): {scorecard['n_na']}")
```

Expected output (bundled sample — all tests return N/A because the
one-week dataset has too few cycles to fit any curve):

```
Tests passed: 0
Borderline:   0
Failed:       0
Insufficient data (N/A): 7
```

That is the correct scientific response — palmwtc never fabricates a pass.
Run the validator on at least two weeks of continuous data with radiation,
temperature, and H₂O columns populated to get meaningful PASS/FAIL results.
See `tutorials/033_Science_Validation.ipynb` for a full worked example.

---

## 7. Plot the flux heatmap

The flux heatmap shows mean CO₂ flux by hour-of-day (y-axis) and month-year
(x-axis). Blue cells indicate uptake (photosynthesis during the day), red cells
indicate efflux (respiration at night). The diurnal pattern is the first visual
check that the system is capturing a real biological signal.

```python
from palmwtc.viz import set_style, plot_flux_heatmap

set_style()   # apply the palmwtc matplotlib theme

# plot_flux_heatmap reads the "flux_date" column.
# Add it back as an alias of "flux_datetime" so the plot function works.
cycles["flux_date"] = cycles["flux_datetime"]

fig = plot_flux_heatmap(cycles)
fig.savefig("flux_heatmap.png", dpi=150, bbox_inches="tight")
```

You should see three vertically stacked subplots — one for both chambers combined,
one for chamber 1, and one for chamber 2. With only one week of synthetic data the
x-axis will show a single month column, but the diurnal pattern (negative flux
during the day, near-zero at night) should be visible even in the short sample.

---

## Next steps

The executable version of this walkthrough — with all outputs already run — is
in `tutorials/000_Integrated_End_to_End.ipynb` (coming soon).

For deeper dives into each step, the individual tutorials are good starting points:

- `tutorials/020_QC_Rule_Based.ipynb` — full QC pipeline with multi-variable config
- `tutorials/022_QC_ML_Enhanced.ipynb` — add ML-assisted outlier detection
- `tutorials/030_Flux_Cycle_Calculation.ipynb` — flux calculation in detail
- `tutorials/032_Window_Selection_Production.ipynb` — calibration window selection
- `tutorials/033_Science_Validation.ipynb` — ecophysiology validation scorecard

To use your own chamber data, set `PALMWTC_DATA_DIR` to your data directory
or write a `palmwtc.yaml` config file in your working directory, then
re-run the steps above. The [Science Reference](science/index.md) explains
the methods and the thresholds behind each QC rule.
