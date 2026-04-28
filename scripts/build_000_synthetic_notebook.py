#!/usr/bin/env python
"""Build the synthetic-data end-to-end tutorial (000_End_to_End_Synthetic.ipynb).

This notebook walks through the full palmwtc pipeline against the bundled
synthetic sample, with markdown cells explaining the scientific meaning of
each step (not just code mechanics).

Sibling of ``001_End_to_End_LIBZ.ipynb`` (which runs the same pipeline on
real LIBZ-style chamber data and requires its own dataset on disk).

Re-run with:  python scripts/build_000_synthetic_notebook.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import nbformat as nbf

# Write to notebooks/ (convention), then copy to docs/tutorials/
NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"
DOCS_TUTORIALS_DIR = Path(__file__).resolve().parent.parent / "docs" / "tutorials"
NOTEBOOKS_DIR.mkdir(exist_ok=True)

FILENAME = "000_End_to_End_Synthetic.ipynb"


def _md(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(source.lstrip())


def _code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(source.lstrip())


def _build(filename: str, cells: list[nbf.NotebookNode]) -> None:
    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.13"},
    }
    out_nb = NOTEBOOKS_DIR / filename
    nbf.write(nb, out_nb)
    print(f"[wrote] {out_nb}  ({len(cells)} cells)")

    out_docs = DOCS_TUTORIALS_DIR / filename
    shutil.copy2(out_nb, out_docs)
    print(f"[copied] {out_docs}")


# ──────────────────────────────────────────────────────────────────────────────
# Cell definitions
# ──────────────────────────────────────────────────────────────────────────────

CELLS = [
    # Cell 1 — Title + scientific framing
    _md(
        """
# 000 — End-to-end on synthetic data

This notebook walks through the complete palmwtc pipeline using the bundled
synthetic sample — no field data needed. Each section shows one step of the
pipeline and explains what it is doing scientifically, not just technically.

The system these tools were built for: two automated whole-tree flux chambers
around individual oil palm trees, each measuring CO₂ and H₂O concentration
every 30 seconds with a LI-COR LI-850 analyser. The pipeline converts those
raw concentration readings into calibrated net CO₂ exchange values — and then
checks whether those values are consistent with what the plant physiology
literature says oil palms should be doing.

For the same pipeline applied to **real chamber data**, see the sibling
notebook [001_End_to_End_LIBZ.ipynb](001_End_to_End_LIBZ.ipynb) — that one
requires a LIBZ-style dataset on disk and is not bundled with the package.

After this notebook, the per-stage tutorials (010–035) each cover one step in
much more depth.
"""
    ),
    # Cell 2 — Imports + DataPaths
    _code(
        """
import pandas as pd
import matplotlib
matplotlib.use("Agg")      # headless rendering — safe in all environments

from palmwtc.config import DataPaths

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    # Cell 3 — Load markdown
    _md(
        """
## Step 1: Load the synthetic sample

palmwtc ships a one-week synthetic dataset (30-second cadence, 2 chambers)
so every step in this notebook runs immediately after `pip install palmwtc`
— no config file needed. The data was generated with a realistic diurnal CO₂
curve plus injected noise, spikes, and a small drift segment to exercise the
QC rules. It is not real plantation data.

The main file is a single parquet with one row per 30-second interval.
Columns follow the pattern `CO2_C1`, `H2O_C1` (chamber 1) and `CO2_C2`,
`H2O_C2` (chamber 2), plus temperature, humidity, atmospheric pressure, and
battery voltage for each chamber.
"""
    ),
    # Cell 4 — Load data
    _code(
        """
df = pd.read_parquet(paths.raw_dir / "QC_Flagged_Data_synthetic.parquet")

print(f"Rows: {df.shape[0]:,}  (7 days × 2,880 rows/day × 30 s)")
print(f"Columns: {df.shape[1]}")
print()
df.head()
"""
    ),
    # Cell 5 — QC markdown
    _md(
        """
## Step 2: Quality control

Before any flux calculation, every raw CO₂ reading needs to be checked for
problems. `QCProcessor` runs several rule-based tests in sequence:

- **Physical bounds** — any reading below 300 ppm or above 600 ppm is
  outside the physical operating range of the LI-850 and is flagged bad (2).
- **IQR outliers** — readings more than 1.5 × IQR away from the local median
  are flagged suspect (1). This catches momentary spikes that pass the hard
  bounds but are still implausible.
- **Rate-of-change** — if the CO₂ concentration jumps by more than 50 ppm in
  one 30-second step, that step is flagged.
- **Persistence (stuck sensor)** — if the value stays identical for 5 or more
  consecutive steps, the sensor is probably frozen; those rows are flagged bad.

The output flag values are 0 (good), 1 (suspect), and 2 (bad). Only flag-0
rows are carried forward into the flux calculation.
"""
    ),
    # Cell 6 — QC code
    _code(
        """
from palmwtc.qc import QCProcessor

co2_config = {
    "co2": {
        "columns": ["CO2_C1"],
        "hard": [300, 600],          # ppm — absolute physical limits
        "soft": [350, 550],          # ppm — expected operating range
        "rate_of_change": {"limit": 50},   # max ppm per 30-s step
        "persistence": {"window": 5},      # flag if stuck for 5+ steps
    }
}

qc = QCProcessor(df=df, config_dict=co2_config)
result = qc.process_variable("CO2_C1", random_seed=42)
flagged_df = qc.get_processed_dataframe()

summary = result["summary"]
print(f"Total points : {summary['total_points']:,}")
print(f"Good  (0)    : {summary['flag_0_count']:,}  ({summary['flag_0_percent']:.1f} %)")
print(f"Suspect (1)  : {summary['flag_1_count']:,}  ({summary['flag_1_percent']:.2f} %)")
print(f"Bad (2)      : {summary['flag_2_count']:,}  ({summary['flag_2_percent']:.2f} %)")
"""
    ),
    # Cell 7 — Flux markdown
    _md(
        """
## Step 3: Flux calculation

Inside the chamber, CO₂ concentration rises (or falls) during each closed
measurement cycle — typically over about 5 minutes. The slope of that rise
(in ppm per second) is converted to an absolute gas exchange rate (in
µmol m⁻² s⁻¹) using the ideal gas law:

```
flux = slope × (P / RT) × V / A
```

where P is atmospheric pressure, R is the gas constant, T is air temperature
inside the chamber, V is the chamber volume, and A is the enclosed ground area.
A negative flux means CO₂ is going into the tree (photosynthesis); a positive
flux means CO₂ is leaving the tree (respiration).

`prepare_chamber_data` selects and cleans the chamber-1 columns from the
flagged DataFrame. `calculate_flux_cycles` then finds every closed-chamber
period, fits a linear regression to the CO₂ ramp, and returns one row per
cycle with the flux, fit quality metrics (R², NRMSE, SNR), and a per-cycle
QC flag.

The output column is called `flux_date` in the raw cycles DataFrame.
We rename it to `flux_datetime` here because `WindowSelector` and
`run_science_validation` both expect that name.
"""
    ),
    # Cell 8 — Flux code
    _code(
        """
from palmwtc.flux import prepare_chamber_data, calculate_flux_cycles

# Select chamber-1 columns, remove flagged rows, apply WPL correction.
chamber_df = prepare_chamber_data(flagged_df, "C1", require_h2o_for_wpl=False)

# Fit one linear regression per closed-chamber cycle.
cycles = calculate_flux_cycles(chamber_df, "Chamber 1", use_multiprocessing=False)

# Rename flux_date → flux_datetime so WindowSelector + validation both work.
cycles = cycles.rename(columns={"flux_date": "flux_datetime"})

print(f"{len(cycles)} cycles extracted")
cycles[["cycle_id", "flux_datetime", "flux_absolute", "flux_slope", "r2", "qc_flag"]].head()
"""
    ),
    # Cell 9 — Windows markdown
    _md(
        """
## Step 4: Calibration window selection

A calibration window is a consecutive span of high-quality days whose cycle
data is suitable for training the XPalm digital-twin model. Not every day
qualifies — a window requires enough cycles with high statistical confidence,
no sensor drift, and reasonable agreement between the two chambers.

`WindowSelector` scores every cycle across five components:

| Component | What it measures |
|---|---|
| `score_regression` | R², p-value, and NRMSE of the linear fit |
| `score_robustness` | Consistency across sub-windows of the cycle |
| `score_sensor_qc` | Fraction of good-flagged raw points inside the cycle |
| `score_drift` | Absence of systematic slope drift across the day |
| `score_cross_chamber` | Agreement between chamber 1 and chamber 2 |

The individual scores combine into a single `cycle_confidence` (0–1). A window
qualifies only when enough consecutive high-confidence cycles are available
(minimum 5 days by default). The one-week synthetic sample is too short to
produce qualifying windows — that is the expected scientific response, not an
error.
"""
    ),
    # Cell 10 — Windows code
    _code(
        """
from palmwtc.windows import WindowSelector

ws = WindowSelector(cycles)
ws.score_cycles()
ws.identify_windows()
ws.summary()

print()
print(f"Cycles with confidence ≥ 0.65: {(ws.cycles_df['cycle_confidence'] >= 0.65).sum()}")
print()
ws.cycles_df[["cycle_id", "flux_datetime", "cycle_confidence",
              "score_regression", "score_sensor_qc"]].head()
"""
    ),
    # Cell 11 — Validation markdown
    _md(
        """
## Step 5: Science validation

`run_science_validation` checks whether the flux data is consistent with
published oil-palm physiology. It runs four independent tests:

1. **Light-response curve (Amax)** — the maximum photosynthetic rate at
   light saturation should fall between 15 and 35 µmol m⁻² s⁻¹ for oil palm
   at the whole-tree scale (Lamade & Bouillet, 2005). A fitted A_max outside
   this range suggests a systematic measurement error or an unusual
   physiological state.

2. **Temperature response (Q10)** — nighttime respiration should roughly
   double for every 10 °C increase in temperature (Q10 ≈ 2). The acceptable
   range for tropical canopies is 1.5–3.5. A Q10 outside that range suggests
   sensor noise or a confounding effect (e.g., water stress, phenological
   transition).

3. **Water-use efficiency vs VPD** — stomatal conductance and WUE should
   follow the Medlyn et al. (2011) unified stomatal optimality model. As VPD
   rises, stomata close and WUE increases — any data where WUE is flat or
   falls with VPD indicates a measurement problem.

4. **Inter-chamber agreement** — the two chambers around different oil palms
   are not identical, but mean fluxes during the same weather conditions
   should agree within 30% (relative difference). A larger divergence points
   to a calibration offset or a blockage in one chamber.

The validator requires `Global_Radiation`, `h2o_slope`, and `vpd_kPa` columns
for tests 1–3. In a full pipeline run those come from the weather station and
H₂O flux calculation. Here we add NaN placeholders so the validator runs and
shows the scorecard structure — all tests correctly return N/A.
"""
    ),
    # Cell 12 — Validation code
    _code(
        """
from palmwtc.validation import run_science_validation

# Columns required by the validator but not produced by calculate_flux_cycles
# alone.  In a real run these come from the weather station and H2O flux step.
cycles["Global_Radiation"] = float("nan")   # W m⁻²  — PAR / shortwave incoming
cycles["h2o_slope"] = float("nan")          # mmol m⁻² s⁻¹  — H2O flux
cycles["co2_slope"] = cycles["flux_slope"]  # µmol m⁻² s⁻¹  — alias for CO2 flux
cycles["vpd_kPa"] = float("nan")            # kPa  — vapour pressure deficit

report = run_science_validation(cycles)
scorecard = report["scorecard"]

print(f"Tests passed         : {scorecard['n_pass']}")
print(f"Borderline           : {scorecard['n_borderline']}")
print(f"Failed               : {scorecard['n_fail']}")
print(f"Insufficient data (N/A): {scorecard['n_na']}")
print()
print("N/A is the correct result on the one-week synthetic sample.")
print("Run against ≥2 weeks of real data with radiation + H2O columns")
print("to obtain PASS/FAIL scores.")
"""
    ),
    # Cell 13 — Plot markdown
    _md(
        """
## Step 6: Flux heatmap

The flux heatmap is the first visual sanity check. It shows mean CO₂ flux by
hour of day (y-axis) and by month (x-axis). Blue cells indicate net CO₂
uptake (photosynthesis during the day); red/warm cells indicate net CO₂
release (respiration at night). A clear diurnal pattern — negative fluxes in
the middle of the day, near-zero or slightly positive at night — is the
primary visual confirmation that the chambers are capturing a real biological
signal.

`plot_flux_heatmap` reads the `flux_date` column, so we add it back as an
alias of `flux_datetime` before calling the function. The synthetic sample
spans only one week, so the x-axis will show a single month column — but the
diurnal pattern should still be visible.
"""
    ),
    # Cell 14 — Plot code
    _code(
        """
from palmwtc.viz import set_style, plot_flux_heatmap

set_style()   # apply the palmwtc matplotlib theme

# plot_flux_heatmap reads "flux_date"; add it back as an alias of flux_datetime.
cycles["flux_date"] = cycles["flux_datetime"]

fig = plot_flux_heatmap(cycles)
fig.savefig("/tmp/flux_heatmap_tutorial.png", dpi=100, bbox_inches="tight")
print("Heatmap saved to /tmp/flux_heatmap_tutorial.png")
"""
    ),
    # Cell 15 — Where to go next
    _md(
        """
## Where to go next

This notebook gave a single pass through the pipeline. The thirteen
per-stage tutorials go deeper into each step:

**Data preparation**
- [010 — Core data integration](010_Data_Integration.ipynb): read raw LI-850
  TOA5 files, fuse climate station data, and produce the unified parquet that
  feeds QC.
- [011 — Weather station vs chamber](011_Weather_vs_Chamber.ipynb): compare
  temperature and humidity inside the chamber against the open-air weather
  station to catch microclimate artifacts.

**Quality control**
- [020 — Rule-based QC](020_QC_Rule_Based.ipynb): full multi-variable QC
  with physical bounds, IQR outliers, breakpoint detection, and drift checks.
- [022 — ML-enhanced QC](022_QC_ML_Enhanced.ipynb): add IsolationForest
  contextual outlier detection on top of the rule-based flags.
- [023 — Field alert report](023_Field_Alert_Report.ipynb): generate an
  email-able HTML report for field operators when sensor problems appear.
- [025 — Cross-chamber bias](025_Cross_Chamber_Bias.ipynb): check whether
  the two chambers have a systematic offset that would bias calibration.
- [026 — CO₂/H₂O segmented bias](026_CO2_H2O_Segmented_Bias.ipynb): detect
  time-localised drift in the CO₂ or H₂O signal.

**Flux calculation and windows**
- [030 — Flux cycle calculation](030_Flux_Cycle_Calculation.ipynb): cycle
  identification, slope fitting, WPL correction, and quality scoring in detail.
- [031 — Window selection (reference)](031_Window_Selection_Reference.ipynb):
  methodology behind the calibration-window algorithm.
- [032 — Window selection (production)](032_Window_Selection_Production.ipynb):
  selecting windows on a real multi-week dataset.

**Validation and auditing**
- [033 — Science validation](033_Science_Validation.ipynb): ecophysiology
  validation scorecard with a full real-data example.
- [034 — QC and window audit](034_QC_and_Window_Audit.ipynb): pre-calibration
  sanity check — how many cycles survive QC, how many windows qualify.
- [035 — QC threshold sensitivity](035_QC_Threshold_Sensitivity.ipynb):
  sweep QC thresholds to understand the operating-point trade-off.

The **[API reference](../api/index.md)** documents every public function in
`palmwtc.*`.

The bundled synthetic sample is sufficient to learn the pipeline. Real LIBZ
data is available via the future Zenodo DOI for serious analyses.
"""
    ),
    # Cell 16 — References
    _md(
        """
## References

**Lamade, E., & Bouillet, J.-P. (2005).** Carbon storage and global change:
the role of oil palm. *OCL — Oilseeds & fats, Crops and Lipids*, 12(2),
154–160. https://doi.org/10.1051/ocl.2005.0154
*(Source for the Amax range 15–35 µmol m⁻² s⁻¹ used in the light-response
validation test.)*

**Medlyn, B. E., Duursma, R. A., Eamus, D., Ellsworth, D. S., Prentice, I.
C., Barton, C. V. M., Crous, K. Y., De Angelis, P., Freeman, M., &
Wingate, L. (2011).** Reconciling the optimal and empirical approaches to
modelling stomatal conductance. *Global Change Biology*, 17(6), 2134–2144.
https://doi.org/10.1111/j.1365-2486.2010.02375.x
*(Source for the Medlyn g₁ formulation used in the WUE validation test.)*
"""
    ),
]

# ──────────────────────────────────────────────────────────────────────────────
# Build
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _build(FILENAME, CELLS)
    print(f"\nDone. {FILENAME} written to notebooks/ and docs/tutorials/")
