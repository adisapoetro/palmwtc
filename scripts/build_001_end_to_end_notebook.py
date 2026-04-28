#!/usr/bin/env python
"""Build the 001 end-to-end production-example notebook.

Generates ``notebooks/001_End_to_End_Real_Chamber_Data.ipynb`` deterministically
from the cell specs below.

The notebook is the real-data sibling of ``000_Integrated_End_to_End.ipynb``.
000 walks the synthetic-only quick demo; 001 demonstrates the canonical
pipeline (prepare -> flux cycles -> windows -> validation -> viz) on
real LIBZ-style chamber data using palmwtc 0.3.0+ default arguments only.

Re-run with:  python scripts/build_001_end_to_end_notebook.py
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
# Notebook 001 — End-to-end on real chamber data, default arguments throughout.
# ──────────────────────────────────────────────────────────────────────────────

NOTEBOOK_001_CELLS = [
    # ── 0. Title + scope ──────────────────────────────────────────────────────
    _md(
        """
# 001 - End-to-end pipeline on real chamber data

This notebook runs the complete palmwtc pipeline (chamber prep -> flux
cycles -> calibration windows -> science validation -> visualisation) on
a real chamber dataset using **default arguments throughout**. Each cell
is one palmwtc API call; no kwargs are passed unless absolutely required.

It is the real-data counterpart to
[000_Integrated_End_to_End.ipynb](000_Integrated_End_to_End.ipynb), which
runs on the bundled synthetic sample.

**What this notebook is for:**
- A canonical "this is how palmwtc is used end-to-end" reference for new
  collaborators or anyone adapting palmwtc to their own oil-palm or
  whole-tree-chamber deployment.
- A demonstration that palmwtc 0.3.0+ defaults are LIBZ-production-correct:
  no per-call argument tuning needed for the standard workflow.

**What it requires:**
- palmwtc 0.4.1+ (the AWS `'--'` na_values fix is needed for radiation join).
- Either a real `Integrated_QC_Data/020_rule_qc_output.parquet` produced by
  notebook 020 (or palmwtc's `palmwtc qc run` step), **or** the bundled
  synthetic sample (auto-fallback). The notebook detects which is available.

**What it deliberately does not cover** - see section 10.
"""
    ),

    # ── 1. Setup ──────────────────────────────────────────────────────────────
    _md(
        """
## 1. Setup

`DataPaths.resolve()` walks the layered config (kwargs -> `PALMWTC_DATA_DIR`
env -> `palmwtc.yaml` -> bundled synthetic). Last layer always succeeds, so
this notebook runs out-of-the-box on a fresh `pip install palmwtc`.
"""
    ),
    _code(
        """
import pandas as pd
import matplotlib
matplotlib.use("Agg")        # headless rendering - safe in all environments

import palmwtc
from palmwtc.config import DataPaths

print(f"palmwtc version: {palmwtc.__version__}")

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),

    # ── 2. Load QC-flagged data (real or synthetic) ───────────────────────────
    _md(
        """
## 2. Load the QC-flagged dataset

The pipeline starts from a quality-controlled parquet. If you have run
notebook [020](020_QC_Rule_Based.ipynb) (or the `palmwtc qc run` CLI), the
file lives at `processed_dir/020_rule_qc_output.parquet`. Otherwise this
falls back to the bundled synthetic sample so every cell still runs.

For raw -> QC details see [010](010_Data_Integration.ipynb) (data
integration) and [020](020_QC_Rule_Based.ipynb) (rule-based QC).
"""
    ),
    _code(
        """
real_qc_path = paths.processed_dir / "020_rule_qc_output.parquet"
synthetic_path = paths.raw_dir / "QC_Flagged_Data_synthetic.parquet"

if real_qc_path.exists():
    print(f"Using real QC parquet: {real_qc_path}")
    df = pd.read_parquet(real_qc_path)
    if "TIMESTAMP" in df.columns:
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    DATA_SOURCE = "real"
else:
    print(f"Real parquet not found - falling back to bundled synthetic")
    print(f"  ({synthetic_path})")
    df = pd.read_parquet(synthetic_path)
    DATA_SOURCE = "synthetic"

print()
print(f"Rows: {df.shape[0]:,}")
print(f"Columns: {df.shape[1]}")
if "TIMESTAMP" in df.columns:
    print(f"Time range: {df['TIMESTAMP'].min()}  ->  {df['TIMESTAMP'].max()}")
df.head()
"""
    ),

    # ── 3. Flux cycles per chamber ────────────────────────────────────────────
    _md(
        """
## 3. Flux cycles - both chambers

Two-chamber loop: `prepare_chamber_data` selects and cleans columns for one
chamber suffix, `calculate_flux_cycles` finds every closed-chamber cycle,
fits a linear regression to the CO2 ramp, and returns one row per cycle
with flux, fit metrics (R2, NRMSE, SNR), and a per-cycle QC flag.

**Zero kwargs.** palmwtc 0.3.0+ default values
(`accepted_co2_qc_flags=(0,)`, `apply_wpl=False`, etc.) match the LIBZ
production configuration. The exact defaults are documented in the
function signature - inspect with
`help(palmwtc.flux.prepare_chamber_data)`.
"""
    ),
    _code(
        """
from palmwtc.flux import prepare_chamber_data, calculate_flux_cycles

CHAMBER_MAP = {"C1": "Chamber 1", "C2": "Chamber 2"}

cycles_per_chamber = []
for suffix, name in CHAMBER_MAP.items():
    if f"CO2_{suffix}" not in df.columns:
        print(f"  [skip] {name}: CO2_{suffix} column not present")
        continue
    chamber_df = prepare_chamber_data(df, suffix)
    cycles = calculate_flux_cycles(chamber_df, name)
    print(f"  [{name}] {len(cycles):>5} cycles "
          f"| mean flux: {cycles['flux_absolute'].mean():+.2f} umol m-2 s-1")
    cycles_per_chamber.append(cycles)

cycles_all = pd.concat(cycles_per_chamber, ignore_index=True)
cycles_all = cycles_all.rename(columns={"flux_date": "flux_datetime"})

print(f"\\nCombined: {len(cycles_all)} cycles "
      f"across {cycles_all['Source_Chamber'].nunique()} chamber(s)")
cycles_all[
    ["Source_Chamber", "cycle_id", "flux_datetime",
     "flux_absolute", "flux_slope", "r2", "qc_flag"]
].head()
"""
    ),

    # ── 4. Calibration windows ────────────────────────────────────────────────
    _md(
        """
## 4. Calibration windows

`WindowSelector` scores every cycle (regression quality, robustness, sensor
QC, drift, cross-chamber agreement) and identifies consecutive spans of
high-quality days suitable for XPalm calibration.

The synthetic sample is too short to qualify any windows - that is the
expected scientific response, not an error. Real multi-month data
typically yields several windows.
"""
    ),
    _code(
        """
from palmwtc.windows import WindowSelector

ws = WindowSelector(cycles_all)
ws.score_cycles()
ws.identify_windows()
ws.summary()

n_high_conf = (ws.cycles_df["cycle_confidence"] >= 0.65).sum()
print(f"\\nCycles with cycle_confidence >= 0.65: {n_high_conf}")
"""
    ),

    # ── 5. Science validation ─────────────────────────────────────────────────
    _md(
        """
## 5. Science validation

`run_science_validation` checks the cycle data against published oil-palm
ecophysiology references:

| Test | Reference range |
|---|---|
| Light-response Amax | 15-35 umol m-2 s-1 (Lamade & Bouillet 2005) |
| Temperature response Q10 | 1.5-3.5 (tropical canopies) |
| Water-use efficiency vs VPD | Medlyn et al. 2011 stomatal optimality |
| Inter-chamber agreement | < 30% relative mean difference |

Tests need `Global_Radiation`, `h2o_slope`, and `vpd_kPa` columns. On the
synthetic sample those columns are absent and the validator correctly
returns N/A. On real data merged with weather + H2O flux, you get
PASS/FAIL/BORDERLINE per test.
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

    # ── 6. Threshold sensitivity ──────────────────────────────────────────────
    _md(
        """
## 6. Threshold sensitivity sweep

How does the science-validation outcome change as you tighten/loosen the
`cycle_confidence` cut-off? Sweep three thresholds and re-run validation
on the surviving subset. A robust dataset shows monotonic behaviour
(more strict -> fewer cycles -> validation results stable or improving).

This is the cheapest sensitivity check; the dedicated
[035](035_QC_Threshold_Sensitivity.ipynb) tutorial shows the full grid.
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

    # ── 7. Visualisations ─────────────────────────────────────────────────────
    _md(
        """
## 7. Visualisations

Three first-look plots that confirm whether the chambers captured a real
biological signal:

1. Per-cycle flux time series.
2. Diurnal-by-month heatmap (day = uptake -> blue, night = release -> red).
3. Tropical seasonal-diurnal pattern (averaged over the dataset).
"""
    ),
    _code(
        """
import matplotlib.pyplot as plt
from palmwtc.viz import set_style, plot_flux_heatmap, plot_tropical_seasonal_diurnal

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
fig1.savefig("/tmp/001_flux_timeseries.png", dpi=100, bbox_inches="tight")
print("Saved /tmp/001_flux_timeseries.png")
"""
    ),
    _code(
        """
# 2. Diurnal-by-month heatmap
fig2 = plot_flux_heatmap(cycles_for_viz)
if fig2 is not None:
    fig2.savefig("/tmp/001_flux_heatmap.png", dpi=100, bbox_inches="tight")
    print("Saved /tmp/001_flux_heatmap.png")
else:
    print("Heatmap skipped (insufficient data span)")
"""
    ),
    _code(
        """
# 3. Tropical seasonal-diurnal pattern
fig3 = plot_tropical_seasonal_diurnal(cycles_for_viz)
if fig3 is not None:
    fig3.savefig("/tmp/001_seasonal_diurnal.png", dpi=100, bbox_inches="tight")
    print("Saved /tmp/001_seasonal_diurnal.png")
else:
    print("Seasonal-diurnal skipped (insufficient data span)")
"""
    ),

    # ── 8. Where the artifacts live ───────────────────────────────────────────
    _md(
        """
## 8. Where the canonical artefacts went

`DataPaths.resolve()` returns an `exports_dir` that points wherever your
project layout sends pipeline outputs. The official artefacts produced by
`palmwtc run` (and equivalent to the variables created above) are:

| Object in this notebook | Canonical artefact path |
|---|---|
| `cycles_all` (after rename) | `exports_dir/digital_twin/01_chamber_cycles.csv` |
| `ws.cycles_df` (with confidence) | `exports_dir/digital_twin/031_scored_cycles.csv` |
| Calibration windows | `exports_dir/digital_twin/032_calibration_windows.csv` |

This notebook does not write to disk - it stays in-memory so each cell's
intermediate result is visible. Use the `palmwtc run` CLI when you want
the artefacts persisted to `exports_dir`.
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
print(f"Notebook data source : {DATA_SOURCE}")
"""
    ),

    # ── 9. What this notebook does NOT cover ──────────────────────────────────
    _md(
        """
## 9. What this notebook deliberately does not cover

The full per-stage tutorials in this directory go deeper into each step.
Those listed below are intentionally outside the canonical end-to-end
pipeline:

| Topic | Where to find it |
|---|---|
| Raw TOA5 -> integrated parquet | [010_Data_Integration](010_Data_Integration.ipynb) |
| Weather-station diagnostics | [011_Weather_vs_Chamber](011_Weather_vs_Chamber.ipynb) |
| Rule-based QC walkthrough | [020_QC_Rule_Based](020_QC_Rule_Based.ipynb) |
| ML-enhanced QC overlay | [022_QC_ML_Enhanced](022_QC_ML_Enhanced.ipynb) |
| Field-alert HTML email | [023_Field_Alert_Report](023_Field_Alert_Report.ipynb) |
| Cross-chamber bias diagnostics | [025](025_Cross_Chamber_Bias.ipynb) / [026](026_CO2_H2O_Segmented_Bias.ipynb) |
| Per-stage flux QC details | [030_Flux_Cycle_Calculation](030_Flux_Cycle_Calculation.ipynb) |
| Window-selection methodology | [031](031_Window_Selection_Reference.ipynb) / [032](032_Window_Selection_Production.ipynb) |
| Science-validation deep-dive | [033_Science_Validation](033_Science_Validation.ipynb) |
| QC + window audit | [034_QC_and_Window_Audit](034_QC_and_Window_Audit.ipynb) |
| Full threshold sensitivity grid | [035_QC_Threshold_Sensitivity](035_QC_Threshold_Sensitivity.ipynb) |

Project-specific downstream analyses (drought response, carbon budget,
XPalm digital-twin calibration) live outside the public package; see the
`research/` workspace if you have access. XPalm/Julia calibration is
explicitly out of scope for palmwtc.
"""
    ),
]

if __name__ == "__main__":
    _build("001_End_to_End_Real_Chamber_Data.ipynb", NOTEBOOK_001_CELLS)
