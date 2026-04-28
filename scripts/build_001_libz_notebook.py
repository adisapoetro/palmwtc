#!/usr/bin/env python
"""Build the LIBZ end-to-end production-example notebook.

Generates ``notebooks/001_End_to_End_LIBZ.ipynb`` deterministically from the
cell specs below.

Sibling of ``000_End_to_End_Synthetic.ipynb``. 000 walks the synthetic-only
quick demo; 001 demonstrates the FULL canonical pipeline starting from raw
TOA5 ``.dat`` files (no shortcuts to the QC parquet) on real LIBZ-style
chamber data using palmwtc 0.4.1+ default arguments only.

The LIBZ raw data is **not bundled with palmwtc and not publicly available**.
This notebook expects the user to provide their own equivalent dataset via
the ``PALMWTC_LIBZ_DATA_ROOT`` environment variable.

Re-run with:  python scripts/build_001_libz_notebook.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import nbformat as nbf

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"
DOCS_TUTORIALS_DIR = Path(__file__).resolve().parent.parent / "docs" / "tutorials"
NOTEBOOKS_DIR.mkdir(exist_ok=True)


def _md(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(source.lstrip())


def _code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(source.lstrip())


def _build(filename: str, cells: list[nbf.NotebookNode]) -> None:
    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    }
    out_nb = NOTEBOOKS_DIR / filename
    nbf.write(nb, out_nb)
    print(f"[wrote] {out_nb}  ({len(cells)} cells)")

    out_docs = DOCS_TUTORIALS_DIR / filename
    shutil.copy2(out_nb, out_docs)
    print(f"[copied] {out_docs}")


# ──────────────────────────────────────────────────────────────────────────────
# Notebook 001 — Real-data end-to-end, raw .dat → validation, default args.
# ──────────────────────────────────────────────────────────────────────────────

NOTEBOOK_001_CELLS = [
    # ── 0. Title + scope ──────────────────────────────────────────────────────
    _md(
        """
# 001 - End-to-end on LIBZ data (raw .dat -> validation)

This notebook runs the **full palmwtc pipeline starting from raw TOA5
``.dat`` files** on a real LIBZ-style oil-palm whole-tree-chamber
dataset using **default arguments throughout**. Every step that the
per-stage tutorials (010-035) cover individually is exercised here in
one continuous flow.

> **The LIBZ raw data is not bundled with palmwtc and is not publicly
> available.** This notebook is intended for collaborators who have
> their own equivalent oil-palm chamber dataset on disk. For a
> self-contained demo on the bundled synthetic sample, see
> [000_End_to_End_Synthetic.ipynb](000_End_to_End_Synthetic.ipynb).

**Pipeline shown (each cell is one palmwtc API call):**

```
raw .dat per sensor
   |  get_cloud_sensor_dirs / read_toa5_file (in load_from_multiple_dirs)
   v
per-sensor DataFrames (chamber_1, chamber_2, climate, soil_sensor)
   |  outer-merge on TIMESTAMP  +  integrate_temp_humidity_c2
   v
unified df_raw  (~119 columns)
   |  export_monthly (optional)        QCProcessor.process_variable
   v                                       (full sensor set)
df_qc  (with *_qc_flag columns)
   |  prepare_chamber_data + calculate_flux_cycles
   v
cycles_all (per-cycle flux + R2 + qc_flag)
   |  compute_ml_anomaly_flags  (USE_ML_QC toggle)
   v
WindowSelector.score_cycles().identify_windows()
   |  run_science_validation  (Amax, Q10, WUE, inter-chamber agreement)
   v
threshold sensitivity sweep + visualisations
```

**Requires:**

- palmwtc 0.4.1+ installed (the AWS ``--`` na_values fix is needed in
  any radiation-aware step).
- A LIBZ-style chamber-data root with this layout:

  ```
  $PALMWTC_LIBZ_DATA_ROOT/
   |-- Raw/shared_drive_palmstudio/Raw Data/Chamber/   <- TOA5 .dat archive
   |-- Data/Integrated_Monthly/                         <- post-010 monthly CSVs
   '-- config/variable_config.json                       <- QC variable config
  ```

- The env var ``PALMWTC_LIBZ_DATA_ROOT`` exported before launching
  JupyterLab (or papermill). Example:

  ```
  export PALMWTC_LIBZ_DATA_ROOT=/path/to/your/data
  ```

  If your subfolders do not match the layout above, three more env vars
  override individual paths: ``PALMWTC_LIBZ_RAW_DIR``,
  ``PALMWTC_LIBZ_MONTHLY_DIR``, ``PALMWTC_LIBZ_CONFIG_DIR``.

- ~10-25 minutes wall time (the raw-load step is the slow one; expect
  a few minutes for QC + cycles + ML + validation).
"""
    ),

    # ── 1. Setup ──────────────────────────────────────────────────────────────
    _md(
        """
## 1. Setup + assert real data

The whole notebook is driven by **one** required environment variable,
``PALMWTC_LIBZ_DATA_ROOT``. From it we derive the raw-`.dat` root, the
post-010 monthly CSV directory, and the QC config directory. The cell
below aborts immediately with a clear message if the env var is missing
or the expected subfolders are absent — it never silently falls back to
the bundled synthetic sample.

If your data layout does not match the LIBZ convention, three more env
vars (``PALMWTC_LIBZ_RAW_DIR``, ``PALMWTC_LIBZ_MONTHLY_DIR``,
``PALMWTC_LIBZ_CONFIG_DIR``) let you override individual subpaths.
"""
    ),
    _code(
        """
import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

import palmwtc
from palmwtc.config import DataPaths

assert palmwtc.__version__ >= "0.4.1", \\
    f"palmwtc 0.4.1+ required (AWS '--' na_values fix); got {palmwtc.__version__}"

paths = DataPaths.resolve()
print(paths.describe())

LIBZ_DATA_ROOT = os.environ.get("PALMWTC_LIBZ_DATA_ROOT")
if not LIBZ_DATA_ROOT:
    raise RuntimeError(
        "PALMWTC_LIBZ_DATA_ROOT is not set.\\n\\n"
        "This notebook walks the full pipeline on a real LIBZ-style chamber\\n"
        "dataset. The raw LIBZ data is NOT bundled with palmwtc and is NOT\\n"
        "publicly available - you need an existing chamber-data root with\\n"
        "this subfolder layout:\\n\\n"
        "    $PALMWTC_LIBZ_DATA_ROOT/\\n"
        "      Raw/shared_drive_palmstudio/Raw Data/Chamber/   <- TOA5 .dat archive\\n"
        "      Data/Integrated_Monthly/                         <- post-010 monthly CSVs\\n"
        "      config/variable_config.json                       <- QC variable config\\n\\n"
        "If your data is laid out differently, override individual subpaths\\n"
        "with PALMWTC_LIBZ_RAW_DIR, PALMWTC_LIBZ_MONTHLY_DIR, and\\n"
        "PALMWTC_LIBZ_CONFIG_DIR.\\n\\n"
        "For the bundled synthetic-data demo, see 000_End_to_End_Synthetic.ipynb."
    )

DATA_ROOT = Path(LIBZ_DATA_ROOT)
raw_root = Path(os.environ.get(
    "PALMWTC_LIBZ_RAW_DIR",
    str(DATA_ROOT / "Raw" / "shared_drive_palmstudio" / "Raw Data" / "Chamber"),
))
monthly_dir = Path(os.environ.get(
    "PALMWTC_LIBZ_MONTHLY_DIR",
    str(DATA_ROOT / "Data" / "Integrated_Monthly"),
))
config_dir = Path(os.environ.get(
    "PALMWTC_LIBZ_CONFIG_DIR",
    str(DATA_ROOT / "config"),
))

if not raw_root.exists() or not (raw_root / "main").exists():
    raise RuntimeError(
        f"Raw .dat root not found or missing 'main/' subdir at: {raw_root}\\n"
        "Override with PALMWTC_LIBZ_RAW_DIR if your raw archive lives elsewhere."
    )

print(f"\\nLIBZ data root  : {DATA_ROOT}")
print(f"  raw_root      : {raw_root}")
print(f"  monthly_dir   : {monthly_dir}")
print(f"  config_dir    : {config_dir}")
print(f"palmwtc version : {palmwtc.__version__}")
"""
    ),

    # ── 2. Discover raw .dat dirs ─────────────────────────────────────────────
    _md(
        """
## 2. Discover raw `.dat` directories

`get_cloud_sensor_dirs(raw_root)` walks the LIBZ shared-drive layout
(``main/`` plus ``update_YYMMDD/`` increments) and returns one entry list
per sensor type: chamber_1, chamber_2, climate, soil_sensor.
"""
    ),
    _code(
        """
from palmwtc.io import get_cloud_sensor_dirs

sensor_dirs = get_cloud_sensor_dirs(raw_root)

for sensor, entries in sensor_dirs.items():
    print(f"  {sensor:<14} {len(entries):>3} dirs")
"""
    ),

    # ── 3. Demonstrate raw TOA5 .dat API on one sensor ────────────────────────
    _md(
        """
## 3. Demonstrate the raw TOA5 `.dat` API on one sensor

`load_from_multiple_dirs(entries)` reads every `.dat` file under each
sensor directory (using `read_toa5_file` internally) and concatenates
them chronologically into a DataFrame. This is the building block
notebook [010_Data_Integration](010_Data_Integration.ipynb) uses to
build the full multi-sensor `df_raw`.

We exercise the API on **one sensor (chamber_1)** here so the reader
sees the raw-data path explicitly. The full multi-sensor integration
(chamber_1 + chamber_2 + climate + soil_sensor + weather station + the
C2 air-T / RH fallback merge etc. — about 50 cells of LIBZ-specific
plumbing) lives in notebook 010 and produces the
`Integrated_Monthly/Integrated_Data_*.csv` files that §4 below loads.
"""
    ),
    _code(
        """
from palmwtc.io import load_from_multiple_dirs

c1_df = load_from_multiple_dirs(sensor_dirs["chamber_1"])
print(f"chamber_1 raw .dat -> DataFrame:")
print(f"  {c1_df.shape[0]:,} rows  x  {c1_df.shape[1]} columns")
print(f"  time range: {c1_df['TIMESTAMP'].min()}  ->  {c1_df['TIMESTAMP'].max()}")
print(f"  columns: {sorted(c1_df.columns.tolist())[:10]} ...")
"""
    ),

    # ── 4. Load the integrated monthly CSVs (the production starting point) ──
    _md(
        """
## 4. Load the integrated monthly CSVs (production starting point)

For the actual pipeline run we use the pre-integrated monthly CSVs that
notebook 010 produces — `Integrated_Data_YYYY-MM.csv` files in
`paths.processed_dir/../Integrated_Monthly/`. These contain the full
multi-sensor merge (both chambers, climate, soil, weather station)
already done.

`load_monthly_data` concatenates all monthly files chronologically and
applies a first-pass physical-bounds filter (drops rows with
out-of-range pressure, temperature, RH, or soil water potential).
"""
    ),
    _code(
        """
from palmwtc.io import load_monthly_data

# monthly_dir was set in §1 from PALMWTC_LIBZ_DATA_ROOT (or the override env var).
if not monthly_dir.exists() or not list(monthly_dir.glob("Integrated_Data_*.csv")):
    raise RuntimeError(
        f"No Integrated_Data_YYYY-MM.csv files found at {monthly_dir}.\\n"
        "Run notebook 010 first to produce them, or override\\n"
        "PALMWTC_LIBZ_MONTHLY_DIR to a directory that contains them."
    )

df_raw = load_monthly_data(monthly_dir).reset_index()
print(f"df_raw: {df_raw.shape[0]:,} rows  x  {df_raw.shape[1]} columns")
print(f"Time range: {df_raw['TIMESTAMP'].min()}  ->  {df_raw['TIMESTAMP'].max()}")
"""
    ),

    # ── 5. (Optional) regenerate monthly CSVs from df_raw ─────────────────────
    _md(
        """
## 5. (Optional) Re-export monthly CSVs from `df_raw`

`export_monthly` splits a DataFrame by calendar month and writes one
`Integrated_Data_YYYY-MM.csv` per month. This is the inverse of §4 —
useful if you want to round-trip `df_raw` to disk. **Off by default**
because §4 already loaded the existing CSVs; turning this on would
rewrite them.
"""
    ),
    _code(
        """
from palmwtc.io import export_monthly

EXPORT_MONTHLY = False                         # set True to round-trip to disk
if EXPORT_MONTHLY:
    monthly_dir.mkdir(parents=True, exist_ok=True)
    export_monthly(df_raw, monthly_dir)
    print(f"Monthly CSVs (re)written under: {monthly_dir}")
else:
    print(f"EXPORT_MONTHLY=False -> df_raw is used in-memory only "
          "(no disk write).")
"""
    ),

    # ── 6. Data integrity report ──────────────────────────────────────────────
    _md(
        """
## 6. Data integrity report

`data_integrity_report` summarises NaN fraction and time-gap statistics
per column. A first sanity check before QC: any column with very high
NaN % or unexpectedly large gaps deserves a closer look in
[011_Weather_vs_Chamber](011_Weather_vs_Chamber.ipynb) before trusting
the downstream flux cycles.
"""
    ),
    _code(
        """
from palmwtc.io import data_integrity_report

integrity = data_integrity_report(df_raw)
integrity.head(20)
"""
    ),

    # ── 7. Rule-based QC across the full sensor set ───────────────────────────
    _md(
        """
## 7. Rule-based QC across the full sensor set

`QCProcessor` is the OOP entry point that wraps every individual rule
(physical bounds, IQR, rate-of-change, persistence, breakpoints, drift,
sensor exclusion). The variable-by-variable configuration lives in
`paths.config_dir / "variable_config.json"`; one `process_variable(var)`
call applies the full rule set for that variable and adds a
`<var>_qc_flag` column with values 0 (good) / 1 (suspect) / 2 (bad).

For the LIBZ deployment ~12 variables are configured (CO2, H2O,
Temp_1, RH_1, VaporPressure_1, AtmosphericPressure_1, plus battery
proxies), each per chamber. The full multi-pass QC is what notebook
020 spends 17 minutes on.
"""
    ),
    _code(
        """
import json
from palmwtc.qc import QCProcessor

# config_dir was set in §1 from PALMWTC_LIBZ_DATA_ROOT (or PALMWTC_LIBZ_CONFIG_DIR).
var_cfg_path = config_dir / "variable_config.json"
if not var_cfg_path.exists():
    raise FileNotFoundError(
        f"variable_config.json not found at {var_cfg_path}. "
        "Override PALMWTC_LIBZ_CONFIG_DIR to point at the directory that contains it."
    )
var_cfg = json.loads(var_cfg_path.read_text())

# variable_config.json has bare logical names ("CO2", "H2O", "Temp") whose
# .columns field expands to actual chamber-suffixed column names
# (e.g. CO2 -> ["CO2_C1", "CO2_C2"]). Build the flat list of columns to QC,
# filtering to columns actually present in df_raw and skipping *_source markers.
qc_columns = []
for var, sub in var_cfg.items():
    qc_columns.extend(sub.get("columns", []))
qc_columns = [c for c in dict.fromkeys(qc_columns)            # de-dupe, preserve order
              if c in df_raw.columns and not c.endswith("_source")]

print(f"Logical variables in config : {len(var_cfg)}  ({sorted(var_cfg)})")
print(f"Actual columns to QC        : {len(qc_columns)}")
print(f"  {qc_columns}")

proc = QCProcessor(df=df_raw.copy(), config_dict=var_cfg)
"""
    ),
    _code(
        """
# Apply the full rule-set, one column at a time.
qc_results = {}
for col in qc_columns:
    res = proc.process_variable(col, random_seed=42)
    qc_results[col] = res["summary"]

df_qc = proc.get_processed_dataframe()
print(f"df_qc shape after QC : {df_qc.shape[0]:,} rows x {df_qc.shape[1]} cols")

# Summarise pass / suspect / bad per QC'd column.
summary = pd.DataFrame.from_dict(qc_results, orient="index")
keep_cols = [c for c in
             ("flag_0_count", "flag_1_count", "flag_2_count",
              "flag_0_percent", "flag_1_percent", "flag_2_percent")
             if c in summary.columns]
summary[keep_cols].sort_index()
"""
    ),

    # ── 8. Flux cycles per chamber ────────────────────────────────────────────
    _md(
        """
## 8. Flux cycles - both chambers

Two-chamber loop: `prepare_chamber_data` selects and cleans columns for
one chamber suffix using the QC flags from §7; `calculate_flux_cycles`
finds every closed-chamber cycle, fits a linear regression to the CO2
ramp, and returns one row per cycle with flux, fit metrics
(R2, NRMSE, SNR), and a per-cycle QC flag.

Zero kwargs — palmwtc 0.3.0+ defaults
(`accepted_co2_qc_flags=(0,)`, `apply_wpl=False`, etc.) match LIBZ
production. Inspect with `help(palmwtc.flux.prepare_chamber_data)`.
"""
    ),
    _code(
        """
from palmwtc.flux import prepare_chamber_data, calculate_flux_cycles

CHAMBER_MAP = {"C1": "Chamber 1", "C2": "Chamber 2"}

cycles_per_chamber = []
for suffix, name in CHAMBER_MAP.items():
    if f"CO2_{suffix}" not in df_qc.columns:
        print(f"  [skip] {name}: CO2_{suffix} column not present")
        continue
    chamber_df = prepare_chamber_data(df_qc, suffix)
    cycles = calculate_flux_cycles(chamber_df, name)
    print(f"  [{name}] {len(cycles):>5} cycles  "
          f"|  mean flux: {cycles['flux_absolute'].mean():+.2f} umol m-2 s-1")
    cycles_per_chamber.append(cycles)

cycles_all = pd.concat(cycles_per_chamber, ignore_index=True)
cycles_all = cycles_all.rename(columns={"flux_date": "flux_datetime"})

print(f"\\nCombined: {len(cycles_all):,} cycles "
      f"across {cycles_all['Source_Chamber'].nunique()} chamber(s)")
cycles_all[
    ["Source_Chamber", "cycle_id", "flux_datetime",
     "flux_absolute", "flux_slope", "r2", "qc_flag"]
].head()
"""
    ),

    # ── 9. ML anomaly overlay (toggleable) ────────────────────────────────────
    _md(
        """
## 9. ML anomaly overlay (toggleable)

`compute_ml_anomaly_flags` adds two unsupervised detectors on top of
the rule-based QC: an Isolation Forest (low-density anomalies) and a
Robust-Covariance / Minimum-Covariance-Determinant detector
(Mahalanobis distance from the robust centroid). Trained on
rule-based A/B cycles (`flux_qc <= 1`), scored on all cycles, combined
in `AND` mode by default — flagging a cycle only when both detectors
agree.

Set `USE_ML_QC = False` to keep the rule-based flags only and skip the
~30-second model fit. The downstream cells use whichever flag set is
present, so the rest of the notebook is unaffected.
"""
    ),
    _code(
        """
from palmwtc.flux import compute_ml_anomaly_flags

USE_ML_QC = True   # set False to skip ML overlay (rule-based flags only)

if USE_ML_QC:
    cycles_all = compute_ml_anomaly_flags(cycles_all)
    n_total = len(cycles_all)
    n_ml = int(cycles_all["ml_anomaly_flag"].sum())
    n_rule_pass = int((cycles_all["qc_flag"] <= 1).sum())
    print(f"ML overlay applied (AND mode):")
    print(f"  total cycles                      : {n_total:>6,}")
    print(f"  rule-based pass (A/B, qc<=1)      : {n_rule_pass:>6,}  "
          f"({100*n_rule_pass/n_total:.1f}%)")
    print(f"  ml_anomaly_flag = 1 (joint detect): {n_ml:>6,}  "
          f"({100*n_ml/n_total:.1f}%)")
    print()
    print("IF score (lower = more anomalous):")
    print(cycles_all["ml_if_score"].describe().round(4))
    print()
    print("MCD distance (larger = farther from cluster):")
    print(cycles_all["ml_mcd_dist"].describe().round(3))
else:
    cycles_all["ml_anomaly_flag"] = 0
    cycles_all["ml_if_score"] = float("nan")
    cycles_all["ml_mcd_dist"] = float("nan")
    print("USE_ML_QC=False -> ml_anomaly_flag set to 0 for all cycles "
          "(downstream uses rule-based flags only).")
"""
    ),

    # ── 10. Calibration windows ───────────────────────────────────────────────
    _md(
        """
## 10. Calibration windows

`WindowSelector` scores every cycle (regression, robustness, sensor QC,
drift, cross-chamber agreement) and identifies consecutive spans of
high-quality days suitable for XPalm calibration. The synthetic sample
typically yields zero qualifying windows (only 7 days); a real
multi-month dataset yields several.
"""
    ),
    _code(
        """
from palmwtc.windows import WindowSelector

ws = WindowSelector(cycles_all)
ws.score_cycles()
ws.identify_windows()
ws.summary()

n_high_conf = int((ws.cycles_df["cycle_confidence"] >= 0.65).sum())
print(f"\\nCycles with cycle_confidence >= 0.65: {n_high_conf:,}")
"""
    ),

    # ── 11. Science validation ────────────────────────────────────────────────
    _md(
        """
## 11. Science validation

`run_science_validation` checks the cycles against published oil-palm
ecophysiology references:

| Test | Reference range |
|---|---|
| Light-response Amax | 15-35 umol m-2 s-1 (Lamade & Bouillet 2005) |
| Temperature response Q10 | 1.5-3.5 (tropical canopies) |
| Water-use efficiency vs VPD | Medlyn et al. 2011 stomatal optimality |
| Inter-chamber agreement | < 30% relative mean difference |

Tests need `Global_Radiation`, `h2o_slope`, and `vpd_kPa` columns.
Those come from the weather-station merge + the H2O flux step. Real
multi-month LIBZ data populates them naturally.
"""
    ),
    _code(
        """
from palmwtc.validation import run_science_validation

cycles_for_val = ws.cycles_df.copy()
for col in ("Global_Radiation", "h2o_slope", "vpd_kPa"):
    if col not in cycles_for_val.columns:
        cycles_for_val[col] = float("nan")
if "co2_slope" not in cycles_for_val.columns:
    cycles_for_val["co2_slope"] = cycles_for_val["flux_slope"]

report = run_science_validation(cycles_for_val)
sc = report["scorecard"]

pd.DataFrame({
    "metric": ["pass", "borderline", "fail", "n/a"],
    "count":  [sc["n_pass"], sc["n_borderline"], sc["n_fail"], sc["n_na"]],
})
"""
    ),

    # ── 12. Threshold sensitivity sweep ───────────────────────────────────────
    _md(
        """
## 12. Threshold sensitivity sweep

How does the science-validation outcome change as you tighten / loosen
the `cycle_confidence` cut-off? Sweep three thresholds and re-run
validation on the surviving subset. The dedicated [035 tutorial]
(035_QC_Threshold_Sensitivity.ipynb) shows the full grid.
"""
    ),
    _code(
        """
sweep = []
for thresh in (0.50, 0.65, 0.80):
    sub = cycles_for_val[cycles_for_val["cycle_confidence"] >= thresh].copy()
    if len(sub) == 0:
        sweep.append({
            "cycle_confidence_min": thresh, "n_cycles": 0,
            "n_pass": 0, "n_borderline": 0, "n_fail": 0, "n_na": 4,
        })
        continue
    rep = run_science_validation(sub)
    sw = rep["scorecard"]
    sweep.append({
        "cycle_confidence_min": thresh,
        "n_cycles": len(sub),
        "n_pass": sw["n_pass"], "n_borderline": sw["n_borderline"],
        "n_fail": sw["n_fail"], "n_na": sw["n_na"],
    })

pd.DataFrame(sweep)
"""
    ),

    # ── 13. Visualisations ────────────────────────────────────────────────────
    _md(
        """
## 13. Visualisations

Three first-look plots that confirm whether the chambers captured a
real biological signal:

1. Per-cycle flux time series.
2. Diurnal-by-month heatmap (day = uptake -> blue, night = release -> red).
3. Tropical seasonal-diurnal pattern (averaged over the dataset).
"""
    ),
    _code(
        """
from palmwtc.viz import set_style

set_style()

cycles_for_viz = cycles_for_val.copy()
cycles_for_viz["flux_date"] = cycles_for_viz["flux_datetime"]   # alias

# 1. Per-cycle flux time series
fig1, ax1 = plt.subplots(figsize=(11, 4))
for chamber, sub in cycles_for_viz.groupby("Source_Chamber"):
    ax1.plot(sub["flux_datetime"], sub["flux_absolute"],
             marker=".", linestyle="", alpha=0.5, label=str(chamber))
ax1.axhline(0, color="grey", lw=0.6)
ax1.set_ylabel("flux_absolute (umol m-2 s-1)")
ax1.set_title("Per-cycle CO2 flux time series")
ax1.legend(loc="best", frameon=False)
fig1.tight_layout()
fig1    # last expression -> inline display in Jupyter / embed in papermill
"""
    ),
    _code(
        """
from palmwtc.viz import plot_flux_heatmap

fig2 = plot_flux_heatmap(cycles_for_viz)
fig2    # None if insufficient data span
"""
    ),
    _code(
        """
from palmwtc.viz import plot_tropical_seasonal_diurnal

fig3 = plot_tropical_seasonal_diurnal(cycles_for_viz)
fig3    # None if insufficient data span
"""
    ),

    # ── 14. Where the artefacts live ──────────────────────────────────────────
    _md(
        """
## 14. Where the canonical artefacts went

`DataPaths.resolve()` returns an `exports_dir` that points wherever your
project layout sends pipeline outputs. The official artefacts produced
by `palmwtc run` (and equivalent to the variables created above) are:

| Object in this notebook | Canonical artefact path |
|---|---|
| `df_raw` (after monthly export, §5) | `processed_dir/../Integrated_Monthly/Integrated_Data_YYYY-MM.csv` |
| `df_qc` (after §7 QC pass) | `processed_dir/020_rule_qc_output.parquet` |
| `cycles_all` after §8 + §9 ML overlay | `exports_dir/digital_twin/01_chamber_cycles.csv` |
| `ws.cycles_df` after §10 | `exports_dir/digital_twin/031_scored_cycles.csv` |
| Calibration windows | `exports_dir/digital_twin/032_calibration_windows.csv` |

This notebook does not write to disk by default (only §5 writes monthly
CSVs, and only when `EXPORT_MONTHLY=True`). Use the `palmwtc run` CLI
when you want all artefacts persisted.
"""
    ),
    _code(
        """
print(f"DataPaths source     : {paths.source}")
print(f"raw_dir              : {paths.raw_dir}")
print(f"processed_dir        : {paths.processed_dir}")
print(f"exports_dir          : {paths.exports_dir}")
print(f"config_dir           : {paths.config_dir}")
print()
print(f"Raw .dat root used   : {raw_root}")
print(f"USE_ML_QC            : {USE_ML_QC}")
print(f"EXPORT_MONTHLY       : {EXPORT_MONTHLY}")
"""
    ),

    # ── 15. What this notebook does NOT cover ─────────────────────────────────
    _md(
        """
## 15. What this notebook deliberately does not cover

The full per-stage tutorials in this directory go deeper into each step.
Those listed below are intentionally outside the canonical end-to-end
pipeline:

| Topic | Where to find it |
|---|---|
| Raw .dat -> integrated parquet (deep dive) | [010_Data_Integration](010_Data_Integration.ipynb) |
| Weather-station diagnostics | [011_Weather_vs_Chamber](011_Weather_vs_Chamber.ipynb) |
| Rule-based QC walkthrough (deep dive) | [020_QC_Rule_Based](020_QC_Rule_Based.ipynb) |
| ML-enhanced QC overlay (deep dive) | [022_QC_ML_Enhanced](022_QC_ML_Enhanced.ipynb) |
| Field-alert HTML email | [023_Field_Alert_Report](023_Field_Alert_Report.ipynb) |
| Cross-chamber bias diagnostics | [025](025_Cross_Chamber_Bias.ipynb) / [026](026_CO2_H2O_Segmented_Bias.ipynb) |
| Per-stage flux QC details | [030_Flux_Cycle_Calculation](030_Flux_Cycle_Calculation.ipynb) |
| Window-selection methodology | [031](031_Window_Selection_Reference.ipynb) / [032](032_Window_Selection_Production.ipynb) |
| Science-validation deep-dive | [033_Science_Validation](033_Science_Validation.ipynb) |
| QC + window audit | [034_QC_and_Window_Audit](034_QC_and_Window_Audit.ipynb) |
| Full threshold sensitivity grid | [035_QC_Threshold_Sensitivity](035_QC_Threshold_Sensitivity.ipynb) |

Project-specific downstream analyses (drought response, carbon budget,
XPalm digital-twin calibration) live outside the public package; see
the `research/` workspace if you have access. XPalm/Julia calibration
is explicitly out of scope for palmwtc.
"""
    ),
]

if __name__ == "__main__":
    _build("001_End_to_End_LIBZ.ipynb", NOTEBOOK_001_CELLS)
