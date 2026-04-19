#!/usr/bin/env python
"""Build Phase 5 thin tutorial notebooks: 011, 022, 023, 025, 026, 031, 032, 034, 035.

Same pattern as Phase 4: each notebook is a thin wrapper around the library
API, with narrative cells + minimal compute + plot cells. Notebook 036
(manual cycle QC labelling, interactive widget) is intentionally NOT
generated — it stays in flux_chamber/notebooks as internal-only.

Re-run with:  python scripts/build_phase5_notebooks.py
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
# 011: Weather station vs chamber comparison
# Runs on synthetic — both weather + chamber data shipped.
# ──────────────────────────────────────────────────────────────────────────────

_011 = [
    _md(
        """
# 011 — Weather station vs chamber

Cross-check the climate variables measured *inside* each chamber against
the open-air weather station, to detect chamber-induced microclimate
artifacts (e.g. solar heating, RH suppression). A well-vented chamber
tracks ambient closely; large divergences suggest sensor drift, blocked
ventilation, or condensation.

Runs on the bundled synthetic sample.
"""
    ),
    _code(
        """
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

from palmwtc.config import DataPaths
from palmwtc.viz import set_style

set_style()
paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
# Load chamber QC parquet and weather CSV.
qc_path = paths.raw_dir / "QC_Flagged_Data_synthetic.parquet"
weather_path = paths.raw_dir / "weather_30min.csv"

if not qc_path.exists():
    from palmwtc.io import find_latest_qc_file
    qc_path = Path(find_latest_qc_file(processed_dir=paths.processed_dir))

chamber = pd.read_parquet(qc_path, columns=["TIMESTAMP", "Temp_1_C1", "Temp_1_C2", "RH_1_C1", "RH_1_C2"])
weather = pd.read_csv(weather_path, parse_dates=["TIMESTAMP"])
print(f"Chamber: {len(chamber)} rows | Weather: {len(weather)} rows")
"""
    ),
    _md(
        """
## Compare temperature
"""
    ),
    _code(
        """
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(weather["TIMESTAMP"], weather["AirTC_Avg"], label="Weather (open air)", lw=1.2)
ax.plot(chamber["TIMESTAMP"][::60], chamber["Temp_1_C1"][::60], label="Chamber 1 (every 30 min)", alpha=0.6)
ax.plot(chamber["TIMESTAMP"][::60], chamber["Temp_1_C2"][::60], label="Chamber 2 (every 30 min)", alpha=0.6)
ax.set_xlabel("Time")
ax.set_ylabel("Temperature (\u00b0C)")
ax.set_title("Temperature: chamber vs open-air weather")
ax.legend()
plt.tight_layout()
plt.show()
"""
    ),
    _md(
        """
A 1-2 \u00b0C offset between chamber and ambient is normal during the day
(chamber walls heat slightly under direct sun). Persistent > 5 \u00b0C
divergence is a red flag for ventilation or shading issues.
"""
    ),
]
_build("011_Weather_vs_Chamber.ipynb", _011)


# ──────────────────────────────────────────────────────────────────────────────
# 022: ML-enhanced QC (optional pipeline branch)
# Stub that documents the ML path; actual ML lives in QCProcessor / ml.py.
# ──────────────────────────────────────────────────────────────────────────────

_022 = [
    _md(
        """
# 022 — ML-enhanced QC (optional)

This **opt-in** QC pipeline branch supplements the rule-based QC (notebook
020) with ML outlier detection — IsolationForest on a feature matrix per
variable. It catches contextual outliers that physical-bounds + IQR
would miss (e.g. a CO2 reading that's in-range but inconsistent with the
trend).

> Requires `palmwtc[ml]` extra (sklearn). Real chamber data recommended.
"""
    ),
    _code(
        """
from palmwtc.config import DataPaths
from palmwtc.qc import QCProcessor
from palmwtc.hardware.gpu import DEVICE, get_isolation_forest

paths = DataPaths.resolve()
print(paths.describe())
print(f"Compute device: {DEVICE}")
"""
    ),
    _code(
        """
# Build an IsolationForest with the package's GPU-aware factory.
# Falls back to CPU sklearn if [gpu] (cuML) isn't installed.
try:
    iso = get_isolation_forest(n_estimators=100, contamination=0.05, random_state=42)
    print(f"IsolationForest backend: {type(iso).__module__}")
except ImportError as e:
    print(f"[skip] sklearn not installed: {e}")
    print("Install with: pip install 'palmwtc[ml]'")
"""
    ),
    _md(
        """
## Wiring into QCProcessor

The ML branch is invoked by setting `enable_ml=True` in the QCProcessor
config. On real data this would look like:

```python
processor = QCProcessor(paths)
result = processor.run("CO2_C1", enable_ml=True)
```

Phase 5 documents the API surface; production ML thresholds are tuned
in notebook 035 (sensitivity sweep).
"""
    ),
]
_build("022_QC_ML_Enhanced.ipynb", _022)


# ──────────────────────────────────────────────────────────────────────────────
# 023: Field alert HTML report
# Runs on synthetic — uses qc_reporting module.
# ──────────────────────────────────────────────────────────────────────────────

_023 = [
    _md(
        """
# 023 — Field alert report

Generate a lightweight HTML report summarising recent QC flags + sensor
health, suitable for emailing to field operators. Uses the Jinja2
templates in `palmwtc.qc.reporting`.

Runs on the bundled synthetic sample.
"""
    ),
    _code(
        """
from palmwtc.config import DataPaths
from palmwtc.qc import build_field_alert_context, render_field_alert_html

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
# Build minimal context (real reports pull from QC summary + sensor exclusions YAML).
context = {
    "site": paths.site,
    "report_date": "2026-04-20",
    "rec_df": None,
    "sensor_health": [],
    "summary_text": "Synthetic sample: no real alerts.",
}
print("Context keys:", list(context.keys()))
"""
    ),
    _md(
        """
## Render HTML

The default template lives at
`flux_chamber/dashboard/email_report/templates/field_alert.html` (Phase 6
moves it inside the package via `importlib.resources`). Until then,
real-data callers must pass an explicit `template_dir`.
"""
    ),
    _code(
        """
print("[note] Phase 6 wires bundled HTML templates into the package.")
print("Real-data callers: pass template_dir to render_field_alert_html().")
"""
    ),
]
_build("023_Field_Alert_Report.ipynb", _023)


# ──────────────────────────────────────────────────────────────────────────────
# 025: Cross-chamber bias diagnostic
# Runs on synthetic.
# ──────────────────────────────────────────────────────────────────────────────

_025 = [
    _md(
        """
# 025 — Cross-chamber bias comparison (diagnostic)

Compare CO2 / H2O / temperature time series between chambers C1 and C2
to detect systematic between-chamber bias (sensor calibration drift,
analyzer differences, mechanical seal differences). Output is
diagnostic only — no corrected data is exported. Bias correction
cannot distinguish drift from biology.

Runs on the bundled synthetic sample.
"""
    ),
    _code(
        """
import pandas as pd
import matplotlib.pyplot as plt

from palmwtc.config import DataPaths
from palmwtc.viz import set_style

set_style()
paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
qc_path = paths.raw_dir / "QC_Flagged_Data_synthetic.parquet"
df = pd.read_parquet(qc_path, columns=["TIMESTAMP", "CO2_C1", "CO2_C2", "H2O_C1", "H2O_C2"])
df = df.dropna(subset=["CO2_C1", "CO2_C2"]).iloc[::60]  # sample to 30-min cadence
print(f"{len(df)} comparison rows")
"""
    ),
    _code(
        """
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].scatter(df["CO2_C1"], df["CO2_C2"], s=5, alpha=0.4)
axes[0].plot([df["CO2_C1"].min(), df["CO2_C1"].max()], [df["CO2_C1"].min(), df["CO2_C1"].max()], "r--", lw=0.8)
axes[0].set_xlabel("CO2 Chamber 1 (ppm)")
axes[0].set_ylabel("CO2 Chamber 2 (ppm)")
axes[0].set_title(f"CO2 cross-chamber (slope={(df['CO2_C2'] / df['CO2_C1']).median():.3f})")

axes[1].scatter(df["H2O_C1"], df["H2O_C2"], s=5, alpha=0.4)
axes[1].plot([df["H2O_C1"].min(), df["H2O_C1"].max()], [df["H2O_C1"].min(), df["H2O_C1"].max()], "r--", lw=0.8)
axes[1].set_xlabel("H2O Chamber 1 (mmol/mol)")
axes[1].set_ylabel("H2O Chamber 2 (mmol/mol)")
axes[1].set_title("H2O cross-chamber")

plt.tight_layout()
plt.show()
"""
    ),
    _md(
        """
On real data, persistent off-diagonal scatter (slope != 1, large RMSE)
flags between-chamber bias. A flagged window can then be added to
`config/sensor_exclusions.yaml` for follow-up investigation.
"""
    ),
]
_build("025_Cross_Chamber_Bias.ipynb", _025)


# ──────────────────────────────────────────────────────────────────────────────
# 026: CO2/H2O segmented bias diagnostic
# Stub — runs on synthetic but the segmented analysis needs more rows.
# ──────────────────────────────────────────────────────────────────────────────

_026 = [
    _md(
        """
# 026 — CO2/H2O segmented bias comparison (diagnostic)

Detect *time-segmented* between-chamber bias by running breakpoint
detection on the chamber-difference series. Identifies when a sensor
started drifting (vs. always offset). Diagnostic only.

Runs on the bundled synthetic sample (the synthetic dataset includes a
deliberate `CO2_C2` linear drift segment in the second half of the week
— the breakpoint detector should find it).
"""
    ),
    _code(
        """
import pandas as pd
from palmwtc.config import DataPaths
from palmwtc.qc import detect_breakpoints_ruptures, filter_major_breakpoints

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
qc_path = paths.raw_dir / "QC_Flagged_Data_synthetic.parquet"
df = pd.read_parquet(qc_path, columns=["TIMESTAMP", "CO2_C1", "CO2_C2"])
df = df.dropna()
df["co2_diff"] = df["CO2_C2"] - df["CO2_C1"]
print(f"{len(df)} rows | mean(C2-C1) = {df['co2_diff'].mean():.2f} ppm")
"""
    ),
    _code(
        """
# Detect breakpoints in the inter-chamber difference series.
try:
    bps = detect_breakpoints_ruptures(df["co2_diff"].values, n_bkps=2, model="rbf")
    major = filter_major_breakpoints(bps, df["co2_diff"].values, min_jump=0.5)
    print(f"Detected {len(bps)} candidate breakpoints, {len(major)} major")
    if len(major):
        idx = major[0]
        print(f"First major breakpoint at row {idx} ~= {df['TIMESTAMP'].iloc[idx]}")
except Exception as e:
    print(f"[skip] breakpoint detection: {e}")
"""
    ),
    _md(
        """
On real data, a sudden breakpoint (vs gradual) typically points at a
sensor swap or recalibration event; a gradual breakpoint points at
slow drift. Cross-reference with `docs/measurement_log/` to attribute.
"""
    ),
]
_build("026_CO2_H2O_Segmented_Bias.ipynb", _026)


# ──────────────────────────────────────────────────────────────────────────────
# 031: Reference high-confidence window selection (superseded by 032)
# ──────────────────────────────────────────────────────────────────────────────

_031 = [
    _md(
        """
# 031 — High-confidence window selection (reference)

Reference implementation of calibration-window selection from cycle
quality scores. **Superseded by notebook 032** (physically grounded
selector) for production runs; kept here for methodology audit.

The library function is the same — `WindowSelector.score_cycles()` +
`identify_windows()` — only the config thresholds differ.
"""
    ),
    _code(
        """
import pandas as pd
from palmwtc.config import DataPaths
from palmwtc.windows import WindowSelector

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
cycles_path = paths.exports_dir / "digital_twin" / "01_chamber_cycles.csv"
if not cycles_path.exists():
    print("[note] cycles not built yet; run notebook 030 first or `palmwtc run`.")
else:
    cycles = pd.read_csv(cycles_path)
    if "flux_datetime" not in cycles.columns and "flux_date" in cycles.columns:
        cycles["flux_datetime"] = pd.to_datetime(cycles["flux_date"])

    selector = WindowSelector(cycles_df=cycles)
    selector.score_cycles()
    selector.identify_windows()
    n_windows = len(selector.windows_df) if selector.windows_df is not None else 0
    print(f"{n_windows} windows selected from {len(cycles)} cycles (reference config)")
"""
    ),
    _md(
        """
032 is the production selector — it adds physical-grounding constraints
(SNR floor, duration, cross-chamber agreement) on top of these scores.
"""
    ),
]
_build("031_Window_Selection_Reference.ipynb", _031)


# ──────────────────────────────────────────────────────────────────────────────
# 032: Physically grounded window selection (production, opt-in)
# ──────────────────────────────────────────────────────────────────────────────

_032 = [
    _md(
        """
# 032 — Physically grounded window selection (production)

Production calibration-window selector. Same `WindowSelector` library
class as 031 but with stricter physically-grounded thresholds (SNR
floor, minimum cycle count per day, cross-chamber agreement
requirement).

Output is the canonical `032_calibration_windows.csv` consumed by the
XPalm digital-twin calibration step (Julia notebook 040, out of scope
for palmwtc 0.1).

Runs against the bundled synthetic sample but produces 0 windows
(synthetic cycles are too short for high-confidence selection).
"""
    ),
    _code(
        """
from palmwtc.config import DataPaths
from palmwtc.pipeline import run_step

paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
result = run_step("windows", paths)
print(f"Status:   {'OK' if result.ok else 'FAILED'}")
print(f"Elapsed:  {result.elapsed_seconds:.2f}s")
print(f"In:  {result.rows_in:>4} cycles")
print(f"Out: {result.rows_out:>4} windows")
print(f"Artefacts:")
for a in result.artefacts:
    print(f"  - {a}")
"""
    ),
    _md(
        """
The two artefacts are the *scored cycles* (031-style output) and the
*identified windows* (032 output). Real LIBZ data typically yields
50-200 high-confidence windows per month.
"""
    ),
]
_build("032_Window_Selection_Production.ipynb", _032)


# ──────────────────────────────────────────────────────────────────────────────
# 034: QC + window audit (visualization-only)
# ──────────────────────────────────────────────────────────────────────────────

_034 = [
    _md(
        """
# 034 — QC + window audit (visualization)

Visual audit of QC flags + calibration window selection results across
the full dataset. Used for periodic sanity checks before XPalm
calibration runs.

Runs on the bundled synthetic sample.
"""
    ),
    _code(
        """
import pandas as pd
import matplotlib.pyplot as plt

from palmwtc.config import DataPaths
from palmwtc.viz import set_style

set_style()
paths = DataPaths.resolve()
print(paths.describe())
"""
    ),
    _code(
        """
# Read QC flag summary from the synthetic parquet.
qc_path = paths.raw_dir / "QC_Flagged_Data_synthetic.parquet"
df = pd.read_parquet(qc_path, columns=["TIMESTAMP", "CO2_C1_qc_flag", "CO2_C2_qc_flag", "H2O_C1_qc_flag", "H2O_C2_qc_flag"])
counts = df[["CO2_C1_qc_flag", "CO2_C2_qc_flag", "H2O_C1_qc_flag", "H2O_C2_qc_flag"]].sum()
print("QC flag totals (1 = fail):")
print(counts.to_string())
"""
    ),
    _code(
        """
fig, ax = plt.subplots(figsize=(8, 3))
counts.plot(kind="barh", ax=ax, color="#a23b72")
ax.set_xlabel("Flagged rows")
ax.set_title("QC flag counts per variable (synthetic sample, 1 week)")
plt.tight_layout()
plt.show()
"""
    ),
    _md(
        """
Real LIBZ data typically shows < 5% flagged rows per variable. Sudden
spikes in any column point at a specific instrument event — chase via
`docs/measurement_log/<sensor>.md` to attribute.
"""
    ),
]
_build("034_QC_and_Window_Audit.ipynb", _034)


# ──────────────────────────────────────────────────────────────────────────────
# 035: QC threshold sensitivity sweep
# ──────────────────────────────────────────────────────────────────────────────

_035 = [
    _md(
        """
# 035 — QC threshold sensitivity sweep

Run the four science-validation tests across a grid of QC threshold
combinations (cycle-confidence x day-score) to identify the operating
point that maximises validation pass-rate without over-pruning data.

Output: `035_threshold_sensitivity.csv` + `.json` for the
publication-quality scorecard.

Runs on the bundled synthetic sample (sweep grid produces a small
output since validation skips on synthetic).
"""
    ),
    _code(
        """
from palmwtc.config import DataPaths
from palmwtc.validation import DEFAULT_CONFIG

paths = DataPaths.resolve()
print(paths.describe())
print(f"Validation DEFAULT_CONFIG keys: {list(DEFAULT_CONFIG)[:6]}...")
"""
    ),
    _code(
        """
# Sensitivity sweep across (cycle_confidence, day_score) grid
# uses run_science_validation under the hood. On synthetic, all
# validation runs report "skipped" — sweep returns an empty grid.

print("[stub] full sensitivity sweep is run-on-real-data only.")
print("API: from palmwtc.validation import run_science_validation")
print("     for thr_cyc in [0.4, 0.5, 0.6]:")
print("       for thr_day in [0.5, 0.6, 0.7]:")
print("         result = run_science_validation(cycles, ...)")
"""
    ),
    _md(
        """
The sweep output drives the production threshold choice in
`palmwtc.windows.DEFAULT_CONFIG`. For palmwtc 0.1 the defaults match
those validated on the LIBZ dataset; updates require a fresh sweep.
"""
    ),
]
_build("035_QC_Threshold_Sensitivity.ipynb", _035)


print(f"\nDone. {len(list(OUT_DIR.glob('*.ipynb')))} total notebooks in {OUT_DIR}")
