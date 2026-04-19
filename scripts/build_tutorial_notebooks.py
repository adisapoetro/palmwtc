#!/usr/bin/env python
"""Build the four Phase 4 tutorial notebooks from cell-list specs.

The notebooks are thin wrappers around ``palmwtc.pipeline.run_step``.
They demonstrate the canonical user workflow:
1. ``DataPaths.resolve()`` to find data
2. One library call per pipeline stage
3. Plot results
4. Narrative interpretation

Notebook ↔ pipeline-step mapping:
- 010_Data_Integration       → no pipeline step yet (raw → QC parquet, requires real data)
- 020_QC_Rule_Based          → no pipeline step yet (raw → QC flags, requires real data)
- 030_Flux_Cycle_Calculation → run_step("flux"), runs against bundled sample
- 033_Science_Validation     → run_step("validation"), runs against bundled sample

Re-run with:  python scripts/build_tutorial_notebooks.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

OUT_DIR = Path(__file__).resolve().parent.parent / "notebooks"
OUT_DIR.mkdir(exist_ok=True)


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
    out = OUT_DIR / filename
    nbf.write(nb, out)
    print(f"[wrote] {out.name}  ({len(cells)} cells)")


# ──────────────────────────────────────────────────────────────────────────────
# Tutorial 030: Flux cycle calculation
# Runs end-to-end on the bundled synthetic sample.
# ──────────────────────────────────────────────────────────────────────────────

NOTEBOOK_030_CELLS = [
    _md(
        """
# 030 — Flux cycle calculation

This tutorial computes CO2 + H2O fluxes from quality-controlled chamber
concentration cycles. It runs end-to-end on the **bundled synthetic
sample** (no setup required) — set ``PALMWTC_DATA_DIR`` to point at your
own QC parquet to use real data instead.

What you'll see:
1. Resolve I/O paths (config layered: kwargs → env → yaml → bundled).
2. Run the ``"flux"`` pipeline step (under the hood: cycle identification,
   linear-fit slope per cycle, scoring, optional ML outlier flagging).
3. Plot the resulting per-cycle flux time series and a diurnal heatmap.
4. Inspect the cycles dataframe for downstream calibration.
"""
    ),
    _code(
        """
import pandas as pd
import matplotlib.pyplot as plt

from palmwtc.config import DataPaths
from palmwtc.pipeline import run_step
from palmwtc.viz import set_style

set_style()
pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 20)
"""
    ),
    _md(
        """
## 1. Resolve I/O paths

`DataPaths.resolve()` walks: explicit kwargs → `PALMWTC_DATA_DIR` env →
`palmwtc.yaml` → bundled synthetic sample. The last layer always succeeds,
so this notebook runs even on a fresh `pip install palmwtc` with no setup.
"""
    ),
    _code(
        """
paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _md(
        """
## 2. Run the flux step

`run_step("flux")` does the work: load QC parquet → discover chambers from
`CO2_C<n>` columns → for each chamber, prepare data + identify cycles +
fit slopes + score quality → write `01_chamber_cycles.csv`.

This is one library call, fully testable, no notebook-cell-resident logic.
"""
    ),
    _code(
        """
result = run_step("flux", paths)
print(f"Step status: {'OK' if result.ok else 'FAILED'}")
print(f"Elapsed:      {result.elapsed_seconds:.1f}s")
print(f"Rows in:      {result.rows_in:,}")
print(f"Rows out:     {result.rows_out}")
print(f"Artefact:     {result.artefacts[0]}")
print(f"Chambers:     {result.metrics.get('chambers')}")
"""
    ),
    _md(
        """
## 3. Inspect the cycle output
"""
    ),
    _code(
        """
cycles = pd.read_csv(result.artefacts[0])
print(f"{len(cycles)} cycles across {cycles['chamber'].nunique()} chamber(s)")
cycles[["chamber", "cycle_id", "flux_date", "flux_slope", "r2", "qc_flag", "flux_absolute"]].head()
"""
    ),
    _md(
        """
## 4. Plot the per-cycle flux series

The synthetic sample only produces a handful of cycles (it's 1 week of
toy data). Real LIBZ data yields thousands — try setting
`PALMWTC_DATA_DIR` to a real chamber dataset.
"""
    ),
    _code(
        """
fig, ax = plt.subplots(figsize=(10, 4))
for chamber, group in cycles.groupby("chamber"):
    ax.scatter(
        pd.to_datetime(group["flux_date"]),
        group["flux_absolute"],
        label=f"Chamber {chamber}",
        s=60,
        alpha=0.7,
    )
ax.axhline(0, color="grey", linewidth=0.6, linestyle="--")
ax.set_xlabel("Date")
ax.set_ylabel("Absolute CO2 flux  (\u03bcmol m\u207b\u00b2 s\u207b\u00b9)")
ax.set_title("Per-cycle CO2 flux (synthetic sample)")
ax.legend()
plt.tight_layout()
plt.show()
"""
    ),
    _md(
        """
## 5. Cycle-quality summary

`qc_flag` is the per-cycle pass/fail flag (0 = pass, 1 = warn, 2 = fail).
`r2` is the linear-fit goodness on the closed-phase concentration ramp;
high R² + low NRMSE + appropriate SNR → cycle accepted into calibration windows.
"""
    ),
    _code(
        """
cycles[["chamber", "qc_flag", "r2", "nrmse", "snr"]].groupby("chamber").describe()
"""
    ),
    _md(
        """
## Next

- **031 / 032** — promote high-confidence cycles into calibration windows
  (`run_step("windows", paths)`).
- **033** — validate against literature ecophysiology bounds
  (`run_step("validation", paths)`).
- **CLI shortcut** — `palmwtc run` runs all four steps end-to-end.
"""
    ),
]
_build("030_Flux_Cycle_Calculation.ipynb", NOTEBOOK_030_CELLS)


# ──────────────────────────────────────────────────────────────────────────────
# Tutorial 033: Science validation
# Runs against the bundled synthetic sample (gracefully reports the
# documented limitation that synthetic lacks h2o_slope + Global_Radiation).
# ──────────────────────────────────────────────────────────────────────────────

NOTEBOOK_033_CELLS = [
    _md(
        """
# 033 — Science validation

This tutorial runs the four ecophysiology validation tests
(light response, Q10, WUE, inter-chamber agreement) against literature
bounds. It depends on the cycles output from notebook 030.

The bundled synthetic sample is intentionally minimal — it lacks the
H2O slope and `Global_Radiation` columns that real LIBZ data has — so
this notebook will report "skipped (insufficient input columns)" at the
end. **That's expected.** Run against real LIBZ data to see the actual
validation scorecard.
"""
    ),
    _code(
        """
import json
from palmwtc.config import DataPaths
from palmwtc.pipeline import run_step

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _md(
        """
## Run the validation step

`run_step("validation")` reads the cycles CSV produced by notebook 030,
checks for the required columns, and either runs the four tests or
gracefully reports which columns are missing.
"""
    ),
    _code(
        """
result = run_step("validation", paths)
print(f"Status:    {'OK' if result.ok else 'FAILED'}")
print(f"Elapsed:   {result.elapsed_seconds:.1f}s")
print(f"Rows in:   {result.rows_in}")
print(f"Metrics:")
print(json.dumps(result.metrics, indent=2, default=str))
"""
    ),
    _md(
        """
## What the validation tests check

When run against full LIBZ data (with `h2o_slope` + `Global_Radiation`
columns), `run_science_validation` produces a JSON report with four
scorecards:

| Test | Literature bound | Pass criterion |
|---|---|---|
| `light_response` | A_max 15-35 µmol/m² ground/s (Lamade & Bouillet 2005) | Per-chamber A_max within range |
| `q10` | 1.4-2.5 (tropical canopy) | Q10 fit value within range |
| `wue` | Medlyn g₁ formulation | Slope coefficient within published bounds |
| `inter_chamber` | < 30% relative difference | Cross-chamber means agree |

The full report writes to `exports/digital_twin/033_science_validation_summary.json`.
"""
    ),
    _md(
        """
## Next

- **CLI shortcut** — `palmwtc run --only validation` re-runs just this step.
- **For real data**: see the `palmwtc run` end-to-end output for a full pipeline summary.
"""
    ),
]
_build("033_Science_Validation.ipynb", NOTEBOOK_033_CELLS)


# ──────────────────────────────────────────────────────────────────────────────
# Tutorial 010: Data integration (stub — requires real data)
# ──────────────────────────────────────────────────────────────────────────────

NOTEBOOK_010_CELLS = [
    _md(
        """
# 010 — Core data integration (raw → unified monthly)

This tutorial covers the **data ingestion** stage: read raw chamber TOA5
files, climate station outputs, and soil-sensor readings, then produce a
unified monthly dataset that downstream notebooks consume.

> **Requires real data.** The bundled synthetic sample skips this stage
> (it ships post-QC parquet directly). Set `PALMWTC_DATA_DIR` to point at
> a directory of raw chamber files to follow along. See
> `docs/quickstart.md` for the expected directory layout.

Phase 4 ships this notebook as a thin scaffold; the full ingest pipeline
will land in Phase 5 alongside the `palmwtc.pipeline.step_ingest` library
function.
"""
    ),
    _code(
        """
from palmwtc.config import DataPaths
from palmwtc.io import find_latest_qc_file, get_cloud_sensor_dirs

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
# Example: locate raw chamber + climate + soil dirs (only meaningful with real data).
# `get_cloud_sensor_dirs(chamber_base)` walks a Google-Drive-mounted root
# and returns {kind: [dirs]} for chamber_1/, chamber_2/, climate/, soil_sensor/.
# The bundled synthetic sample doesn't ship raw chamber dirs, so this is a no-op
# under zero-config.

try:
    sensor_dirs = get_cloud_sensor_dirs(paths.raw_dir)
    print("Sensor directories found:")
    for kind, dirs in sensor_dirs.items():
        print(f"  {kind}: {len(dirs)} directories")
except (FileNotFoundError, TypeError) as e:
    print(f"[bundled synthetic sample]  get_cloud_sensor_dirs not applicable: {type(e).__name__}")
    print("Set PALMWTC_DATA_DIR to a real chamber root to follow this path end-to-end.")
"""
    ),
    _md(
        """
The full notebook (Phase 5) calls `palmwtc.io.load_from_multiple_dirs` to
read every monthly chunk, then `integrate_temp_humidity_c2` to fuse climate
+ chamber temperature/humidity, then `export_monthly` to write the unified
monthly parquet that notebook 020 reads.
"""
    ),
]
_build("010_Data_Integration.ipynb", NOTEBOOK_010_CELLS)


# ──────────────────────────────────────────────────────────────────────────────
# Tutorial 020: Rule-based QC (stub — requires real data)
# ──────────────────────────────────────────────────────────────────────────────

NOTEBOOK_020_CELLS = [
    _md(
        """
# 020 — Rule-based QC

This tutorial applies the multi-stage QC pipeline to the unified monthly
data from notebook 010: physical-bounds checks, IQR outliers, breakpoint
detection (ruptures), drift detection, sensor-exclusion masks, and
combined flag synthesis.

> **Requires real data.** The bundled synthetic sample ships post-QC
> parquet, skipping this stage. The synthetic generator
> (`scripts/make_sample_data.py`) injects realistic edge cases — NaN
> bursts, drift segments, OOB spikes — that exercise the QC code paths
> when this notebook is run against real data.

Phase 5 will fully thin this notebook by adding `palmwtc.pipeline.step_qc_full`
that wraps the joblib-parallel `process_variable_qc` loop.
"""
    ),
    _code(
        """
from palmwtc.config import DataPaths
from palmwtc.qc import (
    QCProcessor,
    apply_iqr_flags,
    apply_physical_bounds_flags,
    detect_breakpoints_ruptures,
)

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _md(
        """
## QC components (preview)

The full notebook iterates over each variable in `config/variable_config.json`
and runs:

```python
result = QCProcessor(paths).run("CO2_C1")
```

which under the hood calls (in order):
1. `apply_physical_bounds_flags` — out-of-range values
2. `apply_iqr_flags` — IQR outliers per rolling window
3. `apply_rate_of_change_flags` — implausible jumps
4. `apply_persistence_flags` — stuck-sensor detection
5. `apply_battery_proxy_flags` — datalogger health proxy
6. `apply_sensor_exclusion_flags` — manual + auto exclusion windows
7. `combine_qc_flags` — synthesis into one composite flag
8. `detect_breakpoints_ruptures` — step-change detection
9. `detect_drift_windstats` — slow-baseline-drift detection

Joblib parallelism (`process_variable_qc`) keeps the loop fast over many variables.
"""
    ),
]
_build("020_QC_Rule_Based.ipynb", NOTEBOOK_020_CELLS)


print(f"\nDone. {len(list(OUT_DIR.glob('*.ipynb')))} notebooks in {OUT_DIR}")
