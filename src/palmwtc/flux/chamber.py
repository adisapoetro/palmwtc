"""Chamber data preparation, WPL correction, and per-cycle flux batch computation.

This module is the entry point for the full CO₂ and H₂O flux calculation
pipeline for automated whole-tree chambers instrumented with LI-COR LI-850.
It ties together sensor-stream preparation, WPL dilution correction, cycle
identification, regression-based flux extraction, QC scoring, and tree
biophysical data.

Pipeline overview
-----------------
1. :func:`prepare_chamber_data` — selects the correct sensor columns for one
   chamber (``C1`` or ``C2``), applies QC flag filtering, runs WPL correction,
   and returns a clean DataFrame ready for cycle identification.
2. :func:`calculate_flux_cycles` — identifies measurement cycles inside the
   prepared DataFrame and runs :func:`palmwtc.flux.cycles.evaluate_cycle`
   on every cycle (in parallel when the dataset is large), returning one row
   per cycle with slope, R², AICc, monotonicity, flux, and QC fields.
3. :func:`calculate_h2o_flux_cycles` — H₂O analogue: uses Theil-Sen + OLS
   regression with relaxed QC thresholds appropriate for water-vapour noise
   levels.
4. :func:`compute_closure_confidence` — converts per-cycle R², NRMSE, and
   global radiation into a 0–1 confidence score for chamber closure quality.

Tree biophysics helpers
-----------------------
- :func:`load_tree_biophysics` — reads ``Vigor_Index_PalmStudio.xlsx`` and
  returns palm geometry time series (height, radius, estimated volume).
- :func:`get_tree_volume_at_date` — time-interpolates the Vigor Index (m³)
  for a specific tree and date from the biophysics table.

WPL diagnostic helpers
----------------------
- :func:`summarize_wpl_correction` — dataset-level WPL statistics (median
  factor, p95 relative change, valid-point count).
- :func:`build_cycle_wpl_metrics` — cycle-level WPL diagnostics table used
  to detect humidity-driven flux artefacts.

Configuration constants
-----------------------
All functions accept explicit parameters.  Use the constants below as
starting points and override what you need:

- :data:`DEFAULT_CONFIG` — cycle detection, regression window, QC flag
  filtering, WPL, and parallel-processing defaults.
- :data:`DEFAULT_CO2_QC_THRESHOLDS` — daytime CO₂ grading thresholds
  (R², NRMSE, SNR, monotonicity, outlier fraction).
- :data:`NIGHTTIME_CO2_QC_THRESHOLDS` — relaxed CO₂ thresholds for cycles
  where Global_Radiation < 10 W m⁻² (respiration-only, smaller dynamic range).
- :data:`DEFAULT_H2O_QC_THRESHOLDS` — daytime H₂O grading thresholds.
- :data:`NIGHTTIME_H2O_QC_THRESHOLDS` — relaxed H₂O thresholds for nighttime
  (near-zero transpiration means tiny, flat H₂O signals are expected).
- :data:`DEFAULT_WPL_QC_THRESHOLDS` — per-cycle WPL validity thresholds
  (valid-data fraction, p95 relative correction, maximum WPL factor).

Quick start::

    from palmwtc.flux.chamber import (
        prepare_chamber_data,
        calculate_flux_cycles,
        calculate_h2o_flux_cycles,
    )

    # Use default config, override just one key:
    cfg = {**DEFAULT_CONFIG, "min_points": 10, "cycle_gap_sec": 240}
    chamber_df = prepare_chamber_data(raw_df, "C1", **cfg)
    flux_df    = calculate_flux_cycles(chamber_df, "Chamber 1", **cfg)
    h2o_df     = calculate_h2o_flux_cycles(chamber_df, "Chamber 1", **cfg)
"""

# ruff: noqa: RUF001, RUF002
# Scientific Unicode (EN DASH, multiplication sign, minus sign) is used in
# docstrings and inline comments for numerical ranges and units.  Replacing
# them with hyphens or "x" would degrade readability of scientific documentation.

import os
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress, theilslopes

from palmwtc.flux.cycles import (
    NIGHTTIME_QC_THRESHOLDS,
    _evaluate_cycle_wrapper,
    identify_cycles,
    score_cycle,  # noqa: F401  — re-exported for notebooks that import via chamber
)

# ---------------------------------------------------------------------------
# Default Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    # Cycle detection
    "cycle_gap_sec": 300,
    # Regression window
    "start_cutoff_sec": 50,
    "start_search_sec": 60,
    "min_points": 20,
    "min_duration_sec": 180,
    "outlier_z": 2,
    "max_outlier_refit_frac": 0.2,
    "noise_eps_ppm": 0.5,
    # QC flag filtering  (None = keep all)
    "accepted_co2_qc_flags": [0],
    "accepted_h2o_qc_flags": [0, 1],
    # WPL correction
    "prefer_corrected_h2o": True,
    "require_h2o_for_wpl": True,
    "h2o_valid_range": (0.0, 60.0),
    "max_abs_wpl_rel_change": 0.12,
    # Parallel processing
    "use_multiprocessing": True,
    "n_jobs": min(8, os.cpu_count() or 4),
}
"""Default pipeline configuration for cycle detection, regression, and WPL.

Pass ``{**DEFAULT_CONFIG, "key": new_value}`` to any pipeline function to
override individual settings without losing the other defaults.

Keys
----
cycle_gap_sec : int
    Minimum gap in seconds between two successive measurements that
    triggers the start of a new measurement cycle (default ``300``).
start_cutoff_sec : int
    Number of seconds to skip from the beginning of a cycle before
    starting the regression window search (default ``50``).
    Skips the initial chamber-mixing transient.
start_search_sec : int
    How far into the cycle (seconds) the window-start search extends
    (default ``60``).
min_points : int
    Minimum number of valid data points required to attempt a flux
    regression (default ``20``).
min_duration_sec : int
    Minimum regression window length in seconds (default ``180``).
outlier_z : float
    Z-score threshold for iterative outlier removal before re-fitting
    (default ``2``).
max_outlier_refit_frac : float
    Maximum fraction of points that may be removed as outliers; if
    exceeded the original fit is kept (default ``0.2``).
noise_eps_ppm : float
    Noise floor in ppm used when computing the monotonicity fraction
    (steps smaller than this are treated as noise, not signal direction,
    default ``0.5``).
accepted_co2_qc_flags : list of int
    Only rows whose ``CO2_{suffix}_qc_flag`` is in this list are kept
    (default ``[0]``; ``None`` keeps all rows).
accepted_h2o_qc_flags : list of int
    Same for ``H2O_{suffix}_qc_flag`` (default ``[0, 1]``; H₂O flag 1
    is a minor sensor warning that still produces usable data).
prefer_corrected_h2o : bool
    When ``True``, use ``H2O_{suffix}_corrected`` over raw
    ``H2O_{suffix}`` if the corrected column is present (default
    ``True``).
require_h2o_for_wpl : bool
    When ``True``, :func:`prepare_chamber_data` raises ``ValueError``
    if no H₂O column is found and WPL correction is requested (default
    ``True``). Set to ``False`` to fall back to wet CO₂.
h2o_valid_range : tuple of float
    Physical validity bounds for H₂O in mmol mol⁻¹ as ``(lo, hi)``
    (default ``(0.0, 60.0)``). Values outside this range are set to
    NaN before WPL correction.
max_abs_wpl_rel_change : float
    Maximum plausible absolute relative WPL correction (default
    ``0.12``, i.e. 12 %). Rows with larger corrections get a Flag
    upgrade to 2.
use_multiprocessing : bool
    Use :class:`multiprocessing.Pool` for cycle batches larger than 50
    cycles (default ``True``).
n_jobs : int
    Number of parallel worker processes (default ``min(8, cpu_count)``).
"""

DEFAULT_CO2_QC_THRESHOLDS = {
    "r2_A": 0.90,
    "r2_B": 0.70,
    "nrmse_A": 0.10,
    "nrmse_B": 0.20,
    "snr_A": 10.0,
    "snr_B": 3.0,  # relaxed from 5.0: physics-justified for low-flux / night cycles
    "monotonic_A": 0.80,
    "monotonic_B": 0.45,  # relaxed from 0.60: ~10 ppm signal + 1 ppm noise → ~0.50 mono
    "outlier_A": 0.05,
    "outlier_B": 0.15,
    "curvature_aicc": -4.0,
    "slope_diff_A": 0.30,
    "slope_diff_B": 0.60,
    "signal_ppm_guard": 5.0,  # total CO2 change (ppm) below which mono threshold is scaled down
}
"""Daytime CO₂ QC grading thresholds for :func:`palmwtc.flux.cycles.score_cycle`.

Each threshold has an ``_A`` (Grade A boundary) and ``_B`` (Grade B boundary)
variant. A cycle that passes all ``_A`` tests is Grade A (tier 0). A cycle
that fails one or more ``_A`` tests but passes all ``_B`` tests is Grade B
(tier 1). Failing any ``_B`` test downgrades to Grade C (tier 2).

Keys
----
r2_A, r2_B : float
    Minimum R² of the OLS linear fit. Daytime photosynthesis and respiration
    cycles have large, clean CO₂ signals so the bar is high (0.90 / 0.70).
nrmse_A, nrmse_B : float
    Maximum normalized RMSE (RMSE divided by CO₂ concentration range). Low
    values (0.10 / 0.20) indicate a clean linear trend.
snr_A, snr_B : float
    Minimum signal-to-noise ratio, defined as (|slope| × duration) / RMSE.
    Measures whether the CO₂ trend is distinguishable from measurement noise.
monotonic_A, monotonic_B : float
    Minimum fraction of consecutive concentration steps that move in the
    direction of the fitted slope (steps smaller than ``noise_eps_ppm`` are
    ignored). Daytime CO₂ should rise or fall steadily inside a closed chamber.
outlier_A, outlier_B : float
    Maximum fraction of points removed as statistical outliers before
    re-fitting (0.05 / 0.15).
curvature_aicc : float
    AICc difference (quadratic minus linear) threshold. Values more negative
    than this indicate significant curvature, flagging possible leaks or
    mixing issues. Note: this key is read by
    :func:`palmwtc.flux.cycles.score_cycle`, not by functions in this module
    directly.
slope_diff_A, slope_diff_B : float
    Maximum relative difference between OLS slope and Theil-Sen slope
    (``|slope_ols - slope_ts| / |slope_ols|``). Large differences indicate
    leverage points or non-linearity.
signal_ppm_guard : float
    Total CO₂ change (ppm) below which the ``monotonic_A/B`` thresholds are
    scaled down proportionally. Prevents mass rejection of low-flux cycles
    where noise-to-signal ratio is inherently higher.

See Also
--------
NIGHTTIME_CO2_QC_THRESHOLDS : Relaxed version for dark/respiration cycles.
palmwtc.flux.cycles.score_cycle : Function that consumes these thresholds.
"""

# Relaxed thresholds for nighttime measurements (Global_Radiation < 10 W/m²).
# Respiration signals are smaller; strict daytime criteria cause mass rejection.
NIGHTTIME_CO2_QC_THRESHOLDS = NIGHTTIME_QC_THRESHOLDS
"""Relaxed CO₂ QC thresholds for nighttime cycles (Global_Radiation < 10 W m⁻²).

This is an alias for :data:`palmwtc.flux.cycles.NIGHTTIME_QC_THRESHOLDS`.
It is exposed here so callers that work only with :mod:`palmwtc.flux.chamber`
do not need to import from the lower-level :mod:`palmwtc.flux.cycles` module.

Why nighttime cycles need relaxed thresholds
--------------------------------------------
During the day, photosynthesis drives a strong, fast CO₂ drawdown inside the
closed chamber (often 20–100 ppm over 5 minutes). This yields high R², SNR,
and monotonicity, making the daytime ``_A`` thresholds easy to meet.

At night, only leaf + soil respiration remain. CO₂ rise rates are typically
3–15 ppm over 5 minutes — a much smaller signal that sits closer to instrument
noise (~0.2–0.5 ppm RMS for LI-COR LI-850). Applying daytime thresholds to
these cycles rejects most valid nighttime measurements.

Relaxed values (compared to :data:`DEFAULT_CO2_QC_THRESHOLDS`)
---------------------------------------------------------------
- ``r2_A`` 0.90 → 0.70, ``r2_B`` 0.70 → 0.40 — lower R² is expected when
  the signal is small relative to noise.
- ``snr_A`` 10.0 → 5.0, ``snr_B`` 3.0 → 2.0 — smaller CO₂ trends mean
  lower SNR even in well-sealed chambers.
- ``monotonic_A`` 0.80 → 0.50, ``monotonic_B`` 0.45 → 0.30 — a 5 ppm
  respiration signal with 0.5 ppm noise gives ~50 % monotonicity even when
  the signal is real.
- ``signal_ppm_guard`` 5.0 → 3.0 — the guard activates earlier for the
  smaller nighttime signals.

See Also
--------
DEFAULT_CO2_QC_THRESHOLDS : Daytime thresholds.
palmwtc.flux.cycles.NIGHTTIME_QC_THRESHOLDS : Canonical source of these values.
"""

DEFAULT_H2O_QC_THRESHOLDS = {
    "r2_A": 0.70,
    "r2_B": 0.50,
    "nrmse_A": 0.15,
    "nrmse_B": 0.25,
    "snr_A": 5.0,
    "snr_B": 3.0,
    "monotonic_A": 0.70,
    "monotonic_B": 0.40,  # relaxed from 0.60: H2O has higher noise than CO2 (0.45)
    "outlier_A": 0.15,
    "outlier_B": 0.25,
    "signal_mmol_guard": 0.3,  # H2O range (mmol/mol) below which NRMSE/mono relaxed
}
"""Daytime H₂O QC grading thresholds for :func:`score_h2o_flux_qc`.

H₂O thresholds are systematically looser than the CO₂ counterparts in
:data:`DEFAULT_CO2_QC_THRESHOLDS`. Two reasons:

1. The LI-COR LI-850 H₂O channel has higher absolute noise (~0.1–0.2 mmol
   mol⁻¹ RMS) than the CO₂ channel, reducing R² and SNR for the same
   physical signal size.
2. Transpiration signals in humid tropical conditions are often 0.5–3 mmol
   mol⁻¹ over a 5-minute cycle — smaller fractional change than CO₂ during
   active photosynthesis.

Keys
----
r2_A, r2_B : float
    Minimum R² of the OLS linear fit (0.70 / 0.50).
nrmse_A, nrmse_B : float
    Maximum normalized RMSE (0.15 / 0.25).
snr_A, snr_B : float
    Minimum SNR, computed as (|Theil-Sen slope| × duration) / residual std
    (5.0 / 3.0).
monotonic_A, monotonic_B : float
    Minimum fraction of H₂O steps larger than 0.05 mmol mol⁻¹ that move in
    the fitted-slope direction (0.70 / 0.40). The 0.05 mmol mol⁻¹ noise floor
    prevents sensor jitter from deflating the fraction.
outlier_A, outlier_B : float
    Maximum fraction of outlier points allowed before downgrading (0.15 /
    0.25). Looser than CO₂ because H₂O droplets on the optical path can
    cause isolated spikes.
signal_mmol_guard : float
    H₂O concentration range (mmol mol⁻¹) below which ``nrmse_B`` and
    ``monotonic_B`` are relaxed proportionally (default 0.3). Prevents mass
    rejection of valid but low-transpiration cycles.

See Also
--------
NIGHTTIME_H2O_QC_THRESHOLDS : Relaxed version for nocturnal cycles.
score_h2o_flux_qc : Function that consumes these thresholds.
"""

# Nighttime H2O: transpiration is near-zero so H2O slopes are tiny/flat.
# Without relaxed thresholds, all nighttime cycles get Grade C.
NIGHTTIME_H2O_QC_THRESHOLDS = {
    "r2_A": 0.50,
    "r2_B": 0.25,  # flat H2O at night is expected, not an error
    "nrmse_A": 0.25,
    "nrmse_B": 0.45,
    "snr_A": 3.0,
    "snr_B": 1.5,  # near-zero transpiration = tiny signal
    "monotonic_A": 0.50,
    "monotonic_B": 0.30,
    "outlier_A": 0.20,
    "outlier_B": 0.30,
    "signal_mmol_guard": 0.15,  # even smaller signals expected at night
}
"""Relaxed H₂O QC thresholds for nighttime cycles (Global_Radiation < 10 W m⁻²).

Why nighttime H₂O needs the most relaxed thresholds
----------------------------------------------------
Stomata close at night, so transpiration drops to near zero.  A typical
nighttime H₂O slope is 0.0–0.1 mmol mol⁻¹ min⁻¹ — often indistinguishable
from sensor drift.  Applying daytime thresholds to these cycles would grade
nearly all of them C, making nighttime water-balance closure impossible.
The physical expectation at night is a **flat or very slowly rising** H₂O
trace, not a steep linear increase.

Relaxed values (compared to :data:`DEFAULT_H2O_QC_THRESHOLDS`)
--------------------------------------------------------------
- ``r2_A`` 0.70 → 0.50, ``r2_B`` 0.50 → 0.25 — a flat trace has R² ≈ 0
  by definition; low R² at night is not a data-quality failure.
- ``nrmse_A`` 0.15 → 0.25, ``nrmse_B`` 0.25 → 0.45 — when the H₂O range
  is 0.1–0.2 mmol mol⁻¹, sensor noise dominates NRMSE.
- ``snr_A`` 5.0 → 3.0, ``snr_B`` 3.0 → 1.5 — near-zero signal means SNR
  is near noise floor even in a well-sealed chamber.
- ``monotonic_A`` 0.50 → 0.50, ``monotonic_B`` 0.40 → 0.30 — random-walk
  noise on a flat trace produces ~50 % monotonicity by chance.
- ``signal_mmol_guard`` 0.30 → 0.15 — the guard activates at even smaller
  H₂O changes to protect valid low-transpiration cycles.

See Also
--------
DEFAULT_H2O_QC_THRESHOLDS : Daytime thresholds.
score_h2o_flux_qc : Function that applies these thresholds.
"""

DEFAULT_WPL_QC_THRESHOLDS = {
    "valid_frac_A": 0.98,
    "valid_frac_B": 0.95,
    "rel_change_p95_A": 0.04,
    "rel_change_p95_B": 0.07,
    "factor_max_B": 1.08,
}
"""Per-cycle WPL correction validity thresholds used by :func:`apply_wpl_qc_overrides`.

These thresholds check whether the WPL correction was well-conditioned for a
given cycle, not whether the underlying CO₂ flux regression was good. A cycle
can have perfect R² but still have a poor WPL correction if many H₂O readings
were out-of-range or the humidity was unusually high.

Keys
----
valid_frac_A, valid_frac_B : float
    Minimum fraction of points in the cycle for which a valid WPL factor
    could be computed (i.e. H₂O was within ``h2o_valid_range`` and non-NaN).
    Grade A requires 98 % coverage; Grade B requires 95 %.
rel_change_p95_A, rel_change_p95_B : float
    95th percentile of the absolute relative WPL correction
    (``|wpl_delta_ppm / CO2_raw|``) within the cycle.  Values above 7 %
    indicate unusually large humidity-driven adjustments that can distort
    the flux.  Values above 4 % are flagged as moderate (Grade B).
factor_max_B : float
    Maximum WPL multiplication factor (``1 + χ_w / (1000 − χ_w)``) seen in
    the cycle.  A factor above 1.08 corresponds to approximately 86 mmol
    mol⁻¹ H₂O (86 % relative humidity at ~30 °C at sea level), which is
    outside the normal operating range and may indicate a wet-sensor event.

See Also
--------
apply_wpl_qc_overrides : Function that applies these thresholds.
DEFAULT_CONFIG : Contains ``h2o_valid_range`` and ``max_abs_wpl_rel_change``
    which are checked at the point level (before cycle aggregation) by
    :func:`prepare_chamber_data`.
"""


# ---------------------------------------------------------------------------
# WPL Correction
# ---------------------------------------------------------------------------


def apply_wpl_correction(co2_wet, h2o_mmol_mol):
    """Convert wet CO₂ (ppm) to dry CO₂ using the WPL dilution correction.

    The Webb-Pearman-Leuning (WPL) correction removes the apparent dilution
    of CO₂ caused by the simultaneous presence of water vapour in the air
    sample. The formula is:

    .. math::

        CO_{2,dry} = CO_{2,wet} \\times \\left(1 + \\frac{\\chi_w}{1000 - \\chi_w}\\right)

    where :math:`\\chi_w` is the H₂O mole fraction in mmol mol⁻¹.

    This is a simplified single-pass WPL for closed-chamber systems where
    temperature and pressure are treated as constant within a cycle.

    Parameters
    ----------
    co2_wet : array-like
        Wet CO₂ mole fraction in ppm (µmol mol⁻¹).
    h2o_mmol_mol : array-like
        Water vapour mole fraction in mmol mol⁻¹.  Values that would make
        the denominator ``(1000 - χ_w)`` non-positive are treated as invalid.

    Returns
    -------
    co2_dry : pd.Series
        Dry CO₂ in ppm.  NaN where either input is NaN or H₂O ≥ 1000 mmol
        mol⁻¹ (physically impossible, but guarded against).
    factor : pd.Series
        WPL multiplication factor ``1 + χ_w / (1000 - χ_w)``.  NaN where
        inputs are invalid.
    valid : pd.Series of bool
        ``True`` for rows where both inputs were valid and a WPL factor could
        be computed.

    Notes
    -----
    The WPL factor for typical tropical conditions (25 mmol mol⁻¹ H₂O,
    ~50 % RH at 30 °C) is approximately 1.026, adding ~2.6 % to the raw CO₂
    reading.  At 40 mmol mol⁻¹ (high humidity), the factor is ~1.042.

    See Also
    --------
    prepare_chamber_data : Calls this function and attaches outputs as columns.
    """
    co2 = pd.to_numeric(co2_wet, errors="coerce")
    h2o = pd.to_numeric(h2o_mmol_mol, errors="coerce")

    denom = 1000.0 - h2o
    valid = co2.notna() & h2o.notna() & denom.notna() & (denom > 0)

    factor = pd.Series(np.nan, index=co2.index, dtype=float)
    factor.loc[valid] = 1.0 + (h2o.loc[valid] / denom.loc[valid])

    co2_dry = pd.Series(np.nan, index=co2.index, dtype=float)
    co2_dry.loc[valid] = co2.loc[valid] * factor.loc[valid]
    return co2_dry, factor, valid


# ---------------------------------------------------------------------------
# Chamber Data Preparation
# ---------------------------------------------------------------------------


def _choose_h2o_column(data, chamber_suffix, prefer_corrected=True):
    """Pick the best available H2O column for *chamber_suffix*."""
    preferred = f"H2O_{chamber_suffix}_corrected"
    raw = f"H2O_{chamber_suffix}"

    if prefer_corrected and preferred in data.columns:
        return preferred
    if raw in data.columns:
        return raw
    if preferred in data.columns:
        return preferred
    return None


def prepare_chamber_data(
    data,
    chamber_suffix,
    accepted_co2_qc_flags=(0,),
    accepted_h2o_qc_flags=(0, 1),
    prefer_corrected_h2o=True,
    require_h2o_for_wpl=False,
    apply_wpl=False,
    h2o_valid_range=(0.0, 60.0),
    max_abs_wpl_rel_change=0.12,
    **kwargs,
):
    """Select, filter, and WPL-correct sensor streams for one chamber.

    This is the first step in the flux pipeline.  It takes the full
    multi-chamber dataset (as loaded by :mod:`palmwtc.io`), extracts the
    columns for a single chamber, applies QC flag row-filtering, and runs the
    WPL dilution correction.  The returned DataFrame is the direct input for
    :func:`calculate_flux_cycles` and :func:`calculate_h2o_flux_cycles`.

    Parameters
    ----------
    data : pd.DataFrame
        Full QC-flagged dataset.  Expected columns (where ``{s}`` = suffix):

        - ``TIMESTAMP`` — datetime column.
        - ``CO2_{s}`` — raw (wet) CO₂ in ppm.
        - ``H2O_{s}`` or ``H2O_{s}_corrected`` — water vapour in mmol mol⁻¹.
        - ``Temp_1_{s}`` — air temperature inside the chamber in °C.
        - ``CO2_{s}_qc_flag`` — integer QC flag for CO₂ (0 = good).
        - ``H2O_{s}_qc_flag`` — integer QC flag for H₂O (0 = good, 1 = minor).

        Missing columns are silently skipped; only ``TIMESTAMP`` and ``CO2``
        are required in the output.
    chamber_suffix : str
        Chamber identifier appended to column names.  Typically ``'C1'`` or
        ``'C2'`` for the two whole-tree chambers.
    accepted_co2_qc_flags : list of int or None
        Keep only rows whose ``CO2_{suffix}_qc_flag`` is in this list.
        Pass ``None`` to skip CO₂ flag filtering entirely.
        Default from :data:`DEFAULT_CONFIG`: ``[0]``.
    accepted_h2o_qc_flags : list of int or None
        Same for H₂O.  Default from :data:`DEFAULT_CONFIG`: ``[0, 1]``
        (flag 1 is a minor sensor warning that still yields usable H₂O).
    prefer_corrected_h2o : bool
        When ``True`` (default), use ``H2O_{suffix}_corrected`` if present;
        fall back to ``H2O_{suffix}`` otherwise.
    require_h2o_for_wpl : bool
        When ``True`` (default), raise :exc:`ValueError` if no H₂O column
        is found and ``apply_wpl=True``.  Set to ``False`` to fall back to
        the uncorrected wet CO₂ value.
    apply_wpl : bool
        When ``True`` (default), run :func:`apply_wpl_correction` and expose
        diagnostic columns.  When ``False``, ``CO2`` is set equal to
        ``CO2_raw`` and all WPL columns are NaN/0.
    h2o_valid_range : tuple of float
        ``(lo, hi)`` physical validity range for H₂O in mmol mol⁻¹.
        Values outside this range are set to NaN before WPL correction.
        Default: ``(0.0, 60.0)``.
    max_abs_wpl_rel_change : float
        Rows where ``|wpl_delta_ppm / CO2_raw|`` exceeds this value get
        their ``Flag`` upgraded to 2 (bad).  Default: ``0.12`` (12 %).
    **kwargs
        Extra keyword arguments are accepted but ignored.  This allows
        passing ``**DEFAULT_CONFIG`` directly without unpacking individual
        keys.

    Returns
    -------
    pd.DataFrame
        One row per retained timestamp, sorted by ``TIMESTAMP``, with a
        reset integer index.  Columns:

        - ``TIMESTAMP`` — datetime.
        - ``CO2`` — working CO₂ in ppm: WPL-corrected when possible, raw
          when WPL is disabled or H₂O is unavailable.
        - ``CO2_raw`` — original wet CO₂ measurement in ppm.
        - ``CO2_corrected`` — WPL-corrected CO₂ in ppm (NaN if WPL
          disabled or H₂O missing for a given row).
        - ``H2O`` — water vapour in mmol mol⁻¹ (NaN outside valid range).
        - ``Temp`` — air temperature in °C (NaN if column absent in input).
        - ``CO2_Flag`` — original CO₂ hardware QC flag (int).
        - ``H2O_Flag`` — original H₂O hardware QC flag (int).
        - ``Flag`` — combined flag: max(CO2_Flag, H2O_Flag), upgraded to 2
          for rows with excessive WPL correction.
        - ``wpl_factor`` — WPL multiplication factor per row (NaN if WPL
          disabled or H₂O missing).
        - ``wpl_valid_input`` — 1 where a valid WPL factor was computed, 0
          otherwise.
        - ``wpl_delta_ppm`` — ``CO2_corrected - CO2_raw`` in ppm.
        - ``wpl_rel_change`` — ``wpl_delta_ppm / CO2_raw`` (dimensionless).

    Raises
    ------
    ValueError
        If ``apply_wpl=True`` and ``require_h2o_for_wpl=True`` but no H₂O
        column is found for the requested ``chamber_suffix``.

    See Also
    --------
    calculate_flux_cycles : Consumes the output of this function for CO₂ flux.
    calculate_h2o_flux_cycles : Consumes the output for H₂O flux.
    summarize_wpl_correction : Computes dataset-level WPL statistics.

    Examples
    --------
    # doctest: +SKIP
    # Requires a real multi-chamber DataFrame from palmwtc.io.load_chamber_data.
    chamber_df = prepare_chamber_data(raw_df, "C1")
    print(chamber_df.columns.tolist())
    """
    if accepted_co2_qc_flags is None:
        accepted_co2_qc_flags = DEFAULT_CONFIG["accepted_co2_qc_flags"]
    if accepted_h2o_qc_flags is None:
        accepted_h2o_qc_flags = DEFAULT_CONFIG["accepted_h2o_qc_flags"]

    h2o_col = _choose_h2o_column(data, chamber_suffix, prefer_corrected_h2o)

    if apply_wpl and h2o_col is None and require_h2o_for_wpl:
        raise ValueError(
            f"Missing H2O input for chamber {chamber_suffix}. "
            "Set require_h2o_for_wpl=False if wet-CO2 fallback is intentional."
        )

    cols = {
        "TIMESTAMP": "TIMESTAMP",
        f"CO2_{chamber_suffix}": "CO2_raw",
        f"Temp_1_{chamber_suffix}": "Temp",
        f"CO2_{chamber_suffix}_qc_flag": "CO2_Flag",
        f"H2O_{chamber_suffix}_qc_flag": "H2O_Flag",
    }
    if h2o_col is not None:
        cols[h2o_col] = "H2O"

    cols = {k: v for k, v in cols.items() if k in data.columns}
    sub_df = data[list(cols.keys())].rename(columns=cols).copy()

    # QC flag filtering
    if "CO2_Flag" in sub_df.columns and accepted_co2_qc_flags is not None:
        sub_df = sub_df[sub_df["CO2_Flag"].isin(accepted_co2_qc_flags)]
    if "H2O_Flag" in sub_df.columns and accepted_h2o_qc_flags is not None:
        sub_df = sub_df[sub_df["H2O_Flag"].isin(accepted_h2o_qc_flags)]

    sub_df["CO2_raw"] = pd.to_numeric(sub_df["CO2_raw"], errors="coerce")

    # Build combined Flag
    if "CO2_Flag" in sub_df.columns:
        co2_flag = pd.to_numeric(sub_df["CO2_Flag"], errors="coerce").fillna(0)
    else:
        co2_flag = pd.Series(0, index=sub_df.index, dtype=float)
    sub_df["Flag"] = co2_flag

    if "H2O_Flag" in sub_df.columns:
        h2o_flag = pd.to_numeric(sub_df["H2O_Flag"], errors="coerce").fillna(0)
        sub_df["Flag"] = np.maximum(sub_df["Flag"], h2o_flag)

    # WPL correction
    if apply_wpl and "H2O" in sub_df.columns:
        sub_df["H2O"] = pd.to_numeric(sub_df["H2O"], errors="coerce")
        lo, hi = h2o_valid_range
        sub_df.loc[(sub_df["H2O"] < lo) | (sub_df["H2O"] > hi), "H2O"] = np.nan

        co2_dry, factor, valid = apply_wpl_correction(sub_df["CO2_raw"], sub_df["H2O"])
        sub_df["CO2_corrected"] = co2_dry
        sub_df["wpl_factor"] = factor
        sub_df["wpl_valid_input"] = valid.astype(int)
        sub_df["wpl_delta_ppm"] = sub_df["CO2_corrected"] - sub_df["CO2_raw"]
        sub_df["wpl_rel_change"] = sub_df["wpl_delta_ppm"] / sub_df["CO2_raw"].replace(0, np.nan)

        anomaly = sub_df["wpl_rel_change"].abs() > max_abs_wpl_rel_change
        anomaly = anomaly.fillna(False)
        sub_df.loc[anomaly, "Flag"] = np.maximum(sub_df.loc[anomaly, "Flag"], 2)
    else:
        sub_df["CO2_corrected"] = np.nan
        sub_df["wpl_factor"] = np.nan
        sub_df["wpl_valid_input"] = 0
        sub_df["wpl_delta_ppm"] = np.nan
        sub_df["wpl_rel_change"] = np.nan

    if apply_wpl and require_h2o_for_wpl:
        sub_df["CO2"] = sub_df["CO2_corrected"]
    elif apply_wpl:
        sub_df["CO2"] = sub_df["CO2_corrected"].fillna(sub_df["CO2_raw"])
    else:
        sub_df["CO2"] = sub_df["CO2_raw"]

    sub_df["Flag"] = pd.to_numeric(sub_df["Flag"], errors="coerce").fillna(0).astype(int)
    sub_df = sub_df.dropna(subset=["TIMESTAMP", "CO2"])
    return sub_df.sort_values("TIMESTAMP").reset_index(drop=True)


# ---------------------------------------------------------------------------
# WPL Diagnostics
# ---------------------------------------------------------------------------


def summarize_wpl_correction(chamber_df):
    """Return a dataset-level summary of WPL correction statistics.

    Useful for a quick sanity check: if the median WPL factor or p95
    relative change looks unusual, it may indicate sensor drift, water
    condensation on the optical path, or a humidity calibration issue.

    Parameters
    ----------
    chamber_df : pd.DataFrame
        Output of :func:`prepare_chamber_data`.  Must contain columns
        ``wpl_delta_ppm``, ``wpl_rel_change``, ``wpl_factor``, and
        optionally ``CO2_corrected``.

    Returns
    -------
    dict
        Empty dict if *chamber_df* is empty or missing WPL columns.
        Otherwise, keys are:

        - ``n_points`` — total row count.
        - ``valid_points`` — rows where ``CO2_corrected`` is not NaN.
        - ``median_factor`` — median WPL multiplication factor.
        - ``median_delta_ppm`` — median WPL additive correction (ppm).
        - ``p95_abs_rel_change`` — 95th percentile of ``|wpl_rel_change|``.

    See Also
    --------
    build_cycle_wpl_metrics : Per-cycle version of the same diagnostics.
    apply_wpl_qc_overrides : Uses per-cycle metrics to upgrade QC tiers.
    """
    if chamber_df.empty or "wpl_delta_ppm" not in chamber_df.columns:
        return {}

    rel = chamber_df["wpl_rel_change"].abs().dropna()
    delta = chamber_df["wpl_delta_ppm"].dropna()
    factor = chamber_df["wpl_factor"].dropna()

    return {
        "n_points": int(len(chamber_df)),  # noqa: RUF046  — verbatim from upstream
        "valid_points": (
            int(chamber_df["CO2_corrected"].notna().sum())
            if "CO2_corrected" in chamber_df.columns
            else 0
        ),
        "median_factor": float(factor.median()) if not factor.empty else np.nan,
        "median_delta_ppm": float(delta.median()) if not delta.empty else np.nan,
        "p95_abs_rel_change": (float(np.nanpercentile(rel, 95)) if not rel.empty else np.nan),
    }


def build_cycle_wpl_metrics(chamber_df, chamber_name, cycle_gap_sec=300):
    """Aggregate WPL correction metrics per measurement cycle.

    Produces one row per cycle with mean/max WPL factor, mean/max WPL
    delta, valid-data fraction, p95 relative change, and H₂O statistics.
    These per-cycle values are the input for :func:`apply_wpl_qc_overrides`.

    Parameters
    ----------
    chamber_df : pd.DataFrame
        Output of :func:`prepare_chamber_data`.
    chamber_name : str
        Chamber label (e.g. ``'Chamber 1'``), stored in the output column
        ``Source_Chamber``.
    cycle_gap_sec : int
        Gap in seconds that marks the boundary between cycles, passed to
        :func:`palmwtc.flux.cycles.identify_cycles`.

    Returns
    -------
    pd.DataFrame
        One row per cycle.  Columns:

        - ``cycle_id`` — integer cycle identifier.
        - ``Source_Chamber`` — *chamber_name*.
        - ``wpl_factor_mean`` — mean WPL factor within the cycle.
        - ``wpl_factor_max`` — maximum WPL factor within the cycle.
        - ``wpl_delta_ppm_mean`` — mean WPL additive correction (ppm).
        - ``wpl_delta_ppm_max`` — maximum WPL additive correction (ppm).
        - ``wpl_valid_fraction`` — fraction of rows with a non-NaN
          ``CO2_corrected`` value.
        - ``wpl_abs_rel_change_p95`` — 95th percentile of absolute relative
          WPL correction within the cycle.
        - ``h2o_mean`` — mean H₂O (mmol mol⁻¹) within the cycle.
        - ``h2o_max`` — maximum H₂O (mmol mol⁻¹) within the cycle.

        Returns an empty DataFrame if *chamber_df* is empty.

    See Also
    --------
    apply_wpl_qc_overrides : Consumes the per-cycle metrics produced here.
    summarize_wpl_correction : Dataset-level WPL summary.
    """
    if chamber_df.empty:
        return pd.DataFrame()

    cyc = identify_cycles(chamber_df, gap_sec=cycle_gap_sec)

    def _p95_abs_rel(series):
        arr = series.dropna().abs().to_numpy()
        return float(np.percentile(arr, 95)) if arr.size else np.nan

    out = cyc.groupby("cycle_id", as_index=False).agg(
        wpl_factor_mean=("wpl_factor", "mean"),
        wpl_factor_max=("wpl_factor", "max"),
        wpl_delta_ppm_mean=("wpl_delta_ppm", "mean"),
        wpl_delta_ppm_max=("wpl_delta_ppm", "max"),
        wpl_valid_fraction=(
            "CO2_corrected",
            lambda s: float(s.notna().mean()),
        ),
        wpl_abs_rel_change_p95=("wpl_rel_change", _p95_abs_rel),
        h2o_mean=("H2O", "mean"),
        h2o_max=("H2O", "max"),
    )
    out["Source_Chamber"] = chamber_name
    return out


# ---------------------------------------------------------------------------
# CO2 Flux Calculation
# ---------------------------------------------------------------------------


def calculate_flux_cycles(
    chamber_df,
    chamber_name,
    cycle_gap_sec=300,
    start_cutoff_sec=50,
    start_search_sec=60,
    min_points=20,
    min_duration_sec=180,
    outlier_z=2,
    max_outlier_refit_frac=0.2,
    use_multiprocessing=True,
    n_jobs=None,
    **kwargs,
):
    """Identify measurement cycles and compute CO₂ flux for each cycle.

    This is the main CO₂ flux batch function.  It calls
    :func:`palmwtc.flux.cycles.identify_cycles` to segment the time series
    into closed-chamber measurement cycles, then dispatches each cycle to
    :func:`palmwtc.flux.cycles.evaluate_cycle` (optionally in parallel via
    :class:`multiprocessing.Pool`).

    Parameters
    ----------
    chamber_df : pd.DataFrame
        Output of :func:`prepare_chamber_data`.  Must contain ``TIMESTAMP``,
        ``CO2``, and optionally ``Temp`` and ``Flag``.
    chamber_name : str
        Human-readable chamber label, stored in the output column
        ``Source_Chamber`` (e.g. ``'Chamber 1'``).
    cycle_gap_sec : int
        Time gap in seconds that triggers a new cycle boundary.  Default
        ``300`` (5 minutes).
    start_cutoff_sec : int
        Seconds to skip from cycle start before beginning the regression
        window search.  Removes the initial chamber-mixing transient.
        Default ``50``.
    start_search_sec : int
        How far into the cycle (seconds) the window-start search extends.
        Default ``60``.
    min_points : int
        Minimum number of valid points required for a cycle to be processed.
        Default ``20``.
    min_duration_sec : int
        Minimum regression window length in seconds.  Default ``180``.
    outlier_z : float
        Z-score threshold for iterative outlier removal.  Default ``2``.
    max_outlier_refit_frac : float
        Maximum fraction of points that may be removed as outliers; if
        exceeded the original fit is used.  Default ``0.2``.
    use_multiprocessing : bool
        When ``True`` and there are more than 50 cycles, process in parallel
        using :class:`multiprocessing.Pool`.  Falls back to serial on any
        multiprocessing error.  Default ``True``.
    n_jobs : int or None
        Number of parallel workers.  Defaults to ``min(8, cpu_count)``.
    **kwargs
        Absorbed silently so callers can pass ``**DEFAULT_CONFIG`` directly.

    Returns
    -------
    pd.DataFrame
        One row per successfully processed cycle.  Columns (from
        :func:`palmwtc.flux.cycles.evaluate_cycle`):

        - ``Source_Chamber`` — *chamber_name*.
        - ``cycle_id`` — integer cycle identifier.
        - ``flux_date`` — start timestamp of the cycle.
        - ``cycle_end`` — end timestamp of the cycle.
        - ``cycle_duration_sec`` — total cycle duration in seconds.
        - ``window_start_sec``, ``window_end_sec`` — regression window
          boundaries relative to cycle start.
        - ``duration_sec`` — regression window duration in seconds.
        - ``n_points_total`` — total points in the full cycle.
        - ``n_points_used`` — points used in the final regression.
        - ``flux_slope`` — OLS slope of CO₂ vs. time (ppm s⁻¹).
        - ``flux_intercept`` — OLS intercept (ppm).
        - ``r2`` — R² of the OLS linear fit.
        - ``p_value``, ``std_err`` — regression statistics.
        - ``rmse`` — root-mean-square error of the fit (ppm).
        - ``nrmse`` — RMSE normalized by the CO₂ range in the window.
        - ``snr`` — signal-to-noise ratio: ``|slope| × duration / rmse``.
        - ``snr_noise`` — SNR using early-cycle noise estimate (NaN if
          not computed).
        - ``noise_sigma`` — early-cycle noise standard deviation (ppm).
        - ``monotonicity`` — fraction of consecutive CO₂ steps moving in
          the slope direction (noise-filtered).
        - ``outlier_frac`` — fraction of points removed as outliers.
        - ``aicc_linear``, ``aicc_quadratic``, ``delta_aicc`` — AICc of
          the linear and quadratic fits; large negative ``delta_aicc``
          flags curvature.
        - ``slope_ts``, ``slope_ts_low``, ``slope_ts_high`` — Theil-Sen
          slope and 95 % confidence interval (ppm s⁻¹).
        - ``slope_diff_pct`` — relative difference between OLS and
          Theil-Sen slopes.
        - ``mean_temp`` — mean air temperature in the cycle (°C).
        - ``qc_flag`` — max hardware QC flag in the cycle.
        - ``co2_range`` — CO₂ concentration range in the window (ppm).
        - ``bimodal_flag`` — ``True`` if a bimodal CO₂ distribution was
          detected (possible closure gap).
        - ``bimodal_gap_ppm``, ``bimodal_lower_mean``,
          ``bimodal_upper_mean`` — bimodal split statistics.
        - ``flux_absolute`` — absolute flux in µmol m⁻² s⁻¹ computed by
          :func:`palmwtc.flux.absolute.calculate_absolute_flux`.

        Returns an empty DataFrame if *chamber_df* is empty or contains no
        valid cycles.

    See Also
    --------
    prepare_chamber_data : Produces the required *chamber_df* input.
    calculate_h2o_flux_cycles : H₂O analogue.
    palmwtc.flux.cycles.evaluate_cycle : Called for each individual cycle.
    palmwtc.flux.cycles.score_cycle : QC scoring applied after this step.

    Examples
    --------
    # doctest: +SKIP
    # Requires prepared chamber data from prepare_chamber_data().
    flux_df = calculate_flux_cycles(chamber_df, "Chamber 1")
    print(flux_df[["flux_date", "flux_slope", "r2", "flux_absolute"]].head())
    """
    if chamber_df.empty:
        print(f"{chamber_name}: no data")
        return pd.DataFrame()

    if n_jobs is None:
        n_jobs = min(8, os.cpu_count() or 4)

    df_cycles = identify_cycles(chamber_df, gap_sec=cycle_gap_sec)

    options = {
        "min_points": min_points,
        "min_duration_sec": min_duration_sec,
        "start_cutoff_sec": start_cutoff_sec,
        "start_search_sec": start_search_sec,
        "outlier_z": outlier_z,
        "max_outlier_refit_frac": max_outlier_refit_frac,
    }

    cycle_groups = [
        (cid, group, chamber_name, options) for cid, group in df_cycles.groupby("cycle_id")
    ]

    if len(cycle_groups) == 0:
        print(f"{chamber_name}: no cycles")
        return pd.DataFrame()

    if use_multiprocessing and len(cycle_groups) > 50:
        try:
            with Pool(n_jobs) as pool:
                results = pool.map(
                    _evaluate_cycle_wrapper,
                    cycle_groups,
                    chunksize=max(1, len(cycle_groups) // (n_jobs * 4)),
                )
        except Exception as e:
            print(f"Multiprocessing failed ({e}), falling back to serial")
            results = [_evaluate_cycle_wrapper(a) for a in cycle_groups]
    else:
        results = [_evaluate_cycle_wrapper(a) for a in cycle_groups]

    results = [r for r in results if r is not None]

    if not results:
        print(f"{chamber_name}: no valid cycles")
        return pd.DataFrame()

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# H2O (Water Vapor) Flux Calculation
# ---------------------------------------------------------------------------


def calculate_h2o_flux_for_cycle(
    cycle_data,
    gas_col="H2O",
    min_points=20,
    min_duration_sec=180,
):
    """Compute H₂O slope and fit statistics for a single measurement cycle.

    Uses Theil-Sen regression to estimate the slope (robust to outliers) and
    OLS for R², RMSE, and residual statistics.  SNR is computed as
    ``|slope_ts × duration| / residual_std``, matching the CO₂ definition.
    Monotonicity is computed only on H₂O steps larger than 0.05 mmol mol⁻¹
    (approximately 5× LI-COR H₂O RMS noise) to avoid deflation by sensor
    jitter.

    Parameters
    ----------
    cycle_data : pd.DataFrame
        Single-cycle data slice.  Must contain ``TIMESTAMP`` and *gas_col*.
    gas_col : str
        Name of the H₂O column (default ``'H2O'``).
    min_points : int
        Minimum number of non-NaN H₂O values required (default ``20``).
    min_duration_sec : float
        Minimum span of the cycle in seconds (default ``180``).

    Returns
    -------
    dict or None
        ``None`` if the cycle has fewer than *min_points* valid rows or
        shorter than *min_duration_sec*.  Otherwise a dict with keys:

        - ``h2o_slope`` — Theil-Sen slope (mmol mol⁻¹ s⁻¹).
        - ``h2o_intercept`` — Theil-Sen intercept (mmol mol⁻¹).
        - ``h2o_r2`` — OLS R² (dimensionless, 0–1).
        - ``h2o_nrmse`` — NRMSE: OLS RMSE divided by H₂O range; NaN if
          range is zero.
        - ``h2o_snr`` — signal-to-noise ratio.
        - ``h2o_outlier_frac`` — fraction of points more than 2.5× MAD
          from the OLS fit.
        - ``h2o_monotonic_frac`` — fraction of noise-filtered consecutive
          steps in the slope direction; NaN if all steps are below the
          noise floor.
        - ``h2o_n_points`` — number of non-NaN points used.
        - ``h2o_duration`` — cycle duration in seconds.
        - ``h2o_conc_mean`` — mean H₂O concentration (mmol mol⁻¹).
        - ``h2o_conc_range`` — H₂O concentration range in the cycle
          (mmol mol⁻¹).

    See Also
    --------
    calculate_h2o_flux_cycles : Calls this function for every cycle.
    score_h2o_flux_qc : Uses the returned dict to assign a QC grade.
    """
    valid_data = cycle_data[cycle_data[gas_col].notna()].copy()

    if len(valid_data) < min_points:
        return None

    t0 = valid_data["TIMESTAMP"].iloc[0]
    valid_data["time_sec"] = (valid_data["TIMESTAMP"] - t0).dt.total_seconds()

    duration = valid_data["time_sec"].iloc[-1] - valid_data["time_sec"].iloc[0]
    if duration < min_duration_sec:
        return None

    x = valid_data["time_sec"].values
    y = valid_data[gas_col].values

    try:
        slope_ts, intercept_ts, _, _ = theilslopes(y, x)
        slope_ols, _, r_value, _, _ = linregress(x, y)

        y_pred = slope_ols * x + (y.mean() - slope_ols * x.mean())
        residuals = y - y_pred
        r2 = r_value**2
        rmse = np.sqrt(np.mean(residuals**2))
        y_range = y.max() - y.min()
        nrmse = rmse / y_range if y_range > 0 else np.nan

        noise = np.std(residuals)
        # FIX: use slope-based SNR (signal change / noise) matching CO2 definition.
        # Old formula (abs(y.mean())/noise) measured concentration level, not trend.
        snr = (abs(slope_ts) * duration) / noise if noise > 0 else np.nan

        mad = np.median(np.abs(residuals - np.median(residuals)))
        outlier_threshold = 2.5 * mad if mad > 0 else 1e-9
        outlier_frac = np.sum(np.abs(residuals) > outlier_threshold) / len(residuals)

        # FIX: add noise epsilon filter matching CO2's monotonic_fraction().
        # Without this, sensor noise produces random sign flips that deflate
        # monotonicity for small H2O signals.
        h2o_noise_eps = 0.05  # mmol/mol — ~5x LI-COR H2O RMS noise
        diffs = np.diff(y)
        valid_diffs = np.abs(diffs) > h2o_noise_eps
        if valid_diffs.sum() == 0:
            monotonic_frac = np.nan
        elif slope_ts > 0:
            monotonic_frac = np.sum(diffs[valid_diffs] > 0) / valid_diffs.sum()
        else:
            monotonic_frac = np.sum(diffs[valid_diffs] < 0) / valid_diffs.sum()

        return {
            "h2o_slope": slope_ts,
            "h2o_intercept": intercept_ts,
            "h2o_r2": r2,
            "h2o_nrmse": nrmse,
            "h2o_snr": snr,
            "h2o_outlier_frac": outlier_frac,
            "h2o_monotonic_frac": monotonic_frac,
            "h2o_n_points": len(valid_data),
            "h2o_duration": duration,
            "h2o_conc_mean": float(y.mean()),
            "h2o_conc_range": float(y_range),
        }
    except Exception:
        return None


def score_h2o_flux_qc(h2o_metrics, h2o_qc_thresholds=None, is_nighttime=False):
    """Assign a QC grade to a single H₂O flux cycle.

    Applies a two-tier threshold system: a cycle that passes all ``_A``
    tests is Grade A (tier 0); failing any ``_A`` test but passing all
    ``_B`` tests gives Grade B (tier 1); failing any ``_B`` test gives
    Grade C (tier 2).

    A signal-size guard relaxes the ``nrmse_B`` and ``monotonic_B``
    thresholds proportionally for cycles where the H₂O range is smaller
    than ``signal_mmol_guard`` — preventing mass rejection of valid but
    low-transpiration cycles.

    Parameters
    ----------
    h2o_metrics : dict or None
        Output of :func:`calculate_h2o_flux_for_cycle`.  If ``None``,
        returns tier 2 / Grade C with reason ``'No valid H2O data'``.
    h2o_qc_thresholds : dict or None
        Override the default thresholds.  When ``None``, selects
        :data:`NIGHTTIME_H2O_QC_THRESHOLDS` if ``is_nighttime=True``,
        otherwise :data:`DEFAULT_H2O_QC_THRESHOLDS`.
    is_nighttime : bool
        Switches to the nighttime threshold set when ``True`` and no
        explicit thresholds are supplied.

    Returns
    -------
    tier : int
        0 for Grade A, 1 for Grade B, 2 for Grade C.
    label : str
        ``'A'``, ``'B'``, or ``'C'``.
    reasons : list of str
        Each failing test appends a human-readable string such as
        ``'R2=0.45<0.70'``.  Empty when all tests pass.

    See Also
    --------
    DEFAULT_H2O_QC_THRESHOLDS : Daytime threshold values and key descriptions.
    NIGHTTIME_H2O_QC_THRESHOLDS : Nighttime threshold values.
    calculate_h2o_flux_cycles : Calls this function for every cycle.
    """
    if h2o_qc_thresholds is None:
        h2o_qc_thresholds = (
            NIGHTTIME_H2O_QC_THRESHOLDS if is_nighttime else DEFAULT_H2O_QC_THRESHOLDS
        )

    if h2o_metrics is None:
        return 2, "C", ["No valid H2O data"]

    th = h2o_qc_thresholds
    r2 = h2o_metrics.get("h2o_r2", 0)
    nrmse = h2o_metrics.get("h2o_nrmse", 1)
    snr = h2o_metrics.get("h2o_snr", 0)
    outlier_frac = h2o_metrics.get("h2o_outlier_frac", 1)
    monotonic_frac = h2o_metrics.get("h2o_monotonic_frac", 0)
    h2o_range = h2o_metrics.get("h2o_conc_range", 999)

    reasons = []
    tier = 0

    # Signal-size guard: relax NRMSE and monotonicity for tiny H2O signals
    signal_guard = th.get("signal_mmol_guard", 0.3)
    effective_nrmse_B = th["nrmse_B"]
    effective_mono_B = th["monotonic_B"]
    if signal_guard > 0 and 0 < h2o_range < signal_guard:
        ratio = h2o_range / signal_guard
        effective_nrmse_B = min(0.50, th["nrmse_B"] / max(ratio, 0.3))
        effective_mono_B = max(0.25, th["monotonic_B"] * ratio)

    if r2 < th["r2_A"]:
        reasons.append(f"R2={r2:.2f}<{th['r2_A']}")
        tier = max(tier, 1)
    if nrmse > th["nrmse_A"]:
        reasons.append(f"NRMSE={nrmse:.2f}>{th['nrmse_A']}")
        tier = max(tier, 1)
    if snr < th["snr_A"]:
        reasons.append(f"SNR={snr:.1f}<{th['snr_A']}")
        tier = max(tier, 1)
    if outlier_frac > th["outlier_A"]:
        reasons.append(f"Outliers={outlier_frac:.2f}>{th['outlier_A']}")
        tier = max(tier, 1)
    if not np.isnan(monotonic_frac) and monotonic_frac < th["monotonic_A"]:
        reasons.append(f"Monotonic={monotonic_frac:.2f}<{th['monotonic_A']}")
        tier = max(tier, 1)

    if tier >= 1:  # noqa: SIM102  — verbatim from upstream; explicit two-step gate kept for diff parity
        if (
            r2 < th["r2_B"]
            or nrmse > effective_nrmse_B
            or snr < th["snr_B"]
            or outlier_frac > th["outlier_B"]
            or (not np.isnan(monotonic_frac) and monotonic_frac < effective_mono_B)
        ):
            tier = 2

    label = ["A", "B", "C"][tier]
    return tier, label, reasons


def calculate_h2o_flux_cycles(
    chamber_df,
    chamber_name,
    cycle_gap_sec=300,
    min_points=20,
    min_duration_sec=180,
    h2o_qc_thresholds=None,
    **kwargs,
):
    """Compute H₂O flux for every cycle in *chamber_df*.

    Mirrors :func:`calculate_flux_cycles` for water vapour.  For each cycle,
    calls :func:`calculate_h2o_flux_for_cycle` and then
    :func:`score_h2o_flux_qc`, automatically switching to nighttime thresholds
    when Global_Radiation < 10 W m⁻² (or when the cycle starts before 06:00
    or after 18:00, if radiation is not available).

    Parameters
    ----------
    chamber_df : pd.DataFrame
        Output of :func:`prepare_chamber_data`.  Must contain ``TIMESTAMP``
        and ``H2O``; optionally ``Global_Radiation`` for nighttime detection.
    chamber_name : str
        Chamber label stored in ``Source_Chamber`` (e.g. ``'Chamber 1'``).
    cycle_gap_sec : int
        Gap in seconds that marks cycle boundaries.  Default ``300``.
    min_points : int
        Minimum valid H₂O points required per cycle.  Default ``20``.
    min_duration_sec : float
        Minimum cycle duration in seconds.  Default ``180``.
    h2o_qc_thresholds : dict or None
        Override the daytime H₂O thresholds.  Nighttime thresholds are
        always selected automatically from :data:`NIGHTTIME_H2O_QC_THRESHOLDS`
        regardless of this parameter.  Default: :data:`DEFAULT_H2O_QC_THRESHOLDS`.
    **kwargs
        Absorbed silently so callers can pass ``**DEFAULT_CONFIG`` directly.

    Returns
    -------
    pd.DataFrame
        One row per valid cycle.  Columns:

        - ``cycle_id`` — integer cycle identifier.
        - ``Source_Chamber`` — *chamber_name*.
        - ``h2o_qc`` — QC tier: 0 = A, 1 = B, 2 = C.
        - ``h2o_qc_label`` — ``'A'``, ``'B'``, or ``'C'``.
        - ``h2o_qc_reason`` — semicolon-separated failing-test strings.
        - All keys returned by :func:`calculate_h2o_flux_for_cycle`:
          ``h2o_slope``, ``h2o_intercept``, ``h2o_r2``, ``h2o_nrmse``,
          ``h2o_snr``, ``h2o_outlier_frac``, ``h2o_monotonic_frac``,
          ``h2o_n_points``, ``h2o_duration``, ``h2o_conc_mean``,
          ``h2o_conc_range``.

        Returns an empty DataFrame if *chamber_df* is empty, has no ``H2O``
        column, or all H₂O values are NaN.

    See Also
    --------
    calculate_flux_cycles : CO₂ analogue.
    prepare_chamber_data : Produces the required *chamber_df* input.
    score_h2o_flux_qc : H₂O QC grading function.

    Examples
    --------
    # doctest: +SKIP
    # Requires prepared chamber data from prepare_chamber_data().
    h2o_df = calculate_h2o_flux_cycles(chamber_df, "Chamber 1")
    print(h2o_df[["cycle_id", "h2o_slope", "h2o_qc_label"]].head())
    """
    if h2o_qc_thresholds is None:
        h2o_qc_thresholds = DEFAULT_H2O_QC_THRESHOLDS

    if chamber_df.empty:
        return pd.DataFrame()

    if "H2O" not in chamber_df.columns or chamber_df["H2O"].isna().all():
        print(f"{chamber_name}: No H2O data available")
        return pd.DataFrame()

    df_cycles = identify_cycles(chamber_df, gap_sec=cycle_gap_sec)

    h2o_results = []
    for cycle_id, cycle_data in df_cycles.groupby("cycle_id"):
        metrics = calculate_h2o_flux_for_cycle(
            cycle_data,
            min_points=min_points,
            min_duration_sec=min_duration_sec,
        )
        if metrics is None:
            continue

        # Detect nighttime: use Global_Radiation if available, else hour-based
        nighttime = False
        if "Global_Radiation" in cycle_data.columns:
            nighttime = cycle_data["Global_Radiation"].median() < 10.0
        elif "TIMESTAMP" in cycle_data.columns:
            h = cycle_data["TIMESTAMP"].iloc[0].hour
            nighttime = h < 6 or h >= 18

        # Select thresholds: use nighttime set when appropriate
        effective_th = h2o_qc_thresholds
        if nighttime:
            effective_th = NIGHTTIME_H2O_QC_THRESHOLDS

        tier, label, reasons = score_h2o_flux_qc(metrics, effective_th, is_nighttime=nighttime)

        rec = {
            "cycle_id": cycle_id,
            "Source_Chamber": chamber_name,
            "h2o_qc": tier,
            "h2o_qc_label": label,
            "h2o_qc_reason": ";".join(reasons) if reasons else "",
        }
        rec.update(metrics)
        h2o_results.append(rec)

    if not h2o_results:
        return pd.DataFrame()
    return pd.DataFrame(h2o_results)


# ---------------------------------------------------------------------------
# Tree Biophysical Data
# ---------------------------------------------------------------------------


def load_tree_biophysics(base_dir):
    """Load palm tree biophysical parameters from the PalmStudio spreadsheet.

    Reads ``Vigor_Index_PalmStudio.xlsx`` (expected at ``{base_dir}/``),
    converts Indonesian column names to English, converts measurements from
    centimetres to metres, and extracts the clone identifier from the tree
    ID string.

    The Vigor Index is the estimated above-ground biomass volume (cm³ in the
    spreadsheet, converted to m³ here).  It is computed by PalmStudio from
    measured height and canopy radii.  It is used by
    :func:`get_tree_volume_at_date` to time-interpolate tree volume for
    any given measurement date.

    Parameters
    ----------
    base_dir : str or Path
        Directory that contains ``Vigor_Index_PalmStudio.xlsx``.

    Returns
    -------
    pd.DataFrame or None
        One row per measurement visit per tree.  Columns:

        - ``Tree ID`` — tree identifier string (e.g. ``'EKA1-001'``).
        - ``Date`` — measurement date (datetime).
        - ``Height_m`` — total tree height in metres.
        - ``Max_Radius_m`` — maximum canopy radius in metres.
        - ``Est_Width_m`` — estimated canopy width (2 × mean radius) in
          metres.
        - ``Vigor_Index_m3`` — estimated tree volume in m³ (converted from
          cm³ by dividing by 1 000 000).
        - ``Clone`` — clone name extracted from ``Tree ID``
          (e.g. ``'EKA 1'``).

        Returns ``None`` (with a printed warning) if the file is not found.

    Notes
    -----
    The spreadsheet uses Indonesian column headings (``Tanggal``,
    ``Kode pohon``, ``Tinggi Pohon (cm)``).  This function handles the
    renaming automatically.

    See Also
    --------
    get_tree_volume_at_date : Time-interpolates Vigor Index from the table
        returned by this function.

    Examples
    --------
    # doctest: +SKIP
    # Requires Vigor_Index_PalmStudio.xlsx in the data directory.
    df_vigor = load_tree_biophysics("/path/to/data")
    print(df_vigor[["Tree ID", "Date", "Vigor_Index_m3"]].head())
    """
    vigor_path = Path(base_dir) / "Vigor_Index_PalmStudio.xlsx"

    if not vigor_path.exists():
        print(f"Warning: Vigor data file not found at {vigor_path}")
        return None

    df_vigor = pd.read_excel(vigor_path, header=2)

    rename_map = {
        "Tanggal": "Date",
        "Kode pohon": "Tree ID",
        "Tinggi Pohon (cm)": "Height_cm",
    }
    df_vigor = df_vigor.rename(columns=rename_map)
    df_vigor["Date"] = pd.to_datetime(df_vigor["Date"], errors="coerce")

    if "R1 (cm)" in df_vigor.columns and "R2 (cm)" in df_vigor.columns:
        df_vigor["Mean_Radius_cm"] = df_vigor[["R1 (cm)", "R2 (cm)"]].mean(axis=1)
        df_vigor["Max_Radius_cm"] = df_vigor[["R1 (cm)", "R2 (cm)"]].max(axis=1)
        df_vigor["Est_Width_cm"] = df_vigor["Mean_Radius_cm"] * 2

    df_vigor["Height_m"] = df_vigor["Height_cm"] / 100.0
    df_vigor["Max_Radius_m"] = df_vigor["Max_Radius_cm"] / 100.0
    df_vigor["Est_Width_m"] = df_vigor["Est_Width_cm"] / 100.0

    if "Vigor Index" in df_vigor.columns:
        df_vigor["Vigor_Index_m3"] = df_vigor["Vigor Index"] / 1_000_000.0

    df_vigor["Clone"] = (
        df_vigor["Tree ID"]
        .str.extract(r"(EKA[- ]?\d)", expand=False)
        .str.replace("-", " ", regex=False)
        .str.upper()
    )

    key_cols = [
        "Tree ID",
        "Date",
        "Height_m",
        "Max_Radius_m",
        "Est_Width_m",
        "Vigor_Index_m3",
        "Clone",
    ]
    df_vigor = df_vigor[key_cols].dropna(subset=["Tree ID", "Date"])

    print(f"Loaded biophysical data for {df_vigor['Tree ID'].nunique()} trees")
    print(f"Date range: {df_vigor['Date'].min()} to {df_vigor['Date'].max()}")
    print(f"Measurements: {len(df_vigor)} records")
    return df_vigor


def get_tree_volume_at_date(df_vigor, tree_id, target_date):
    """Time-interpolate the Vigor Index (m³) for a tree at a specific date.

    If an exact measurement exists on *target_date*, that value is returned
    directly.  Otherwise, the Vigor Index time series for the tree is
    linearly interpolated between the two nearest measurements.  No
    extrapolation is performed — dates outside the measurement range return
    ``None`` because the time-based interpolation does not fill beyond the
    index boundaries.

    Parameters
    ----------
    df_vigor : pd.DataFrame or None
        Output of :func:`load_tree_biophysics`.  ``None`` returns ``None``
        immediately.
    tree_id : str
        Tree identifier matching the ``Tree ID`` column in *df_vigor*
        (e.g. ``'EKA1-001'``).
    target_date : str or datetime-like
        The date for which to estimate the tree volume.  String values are
        parsed via :func:`pandas.to_datetime`.

    Returns
    -------
    float or None
        Vigor Index in m³ at *target_date*, or ``None`` if *df_vigor* is
        ``None``, *tree_id* is not found, or the date is outside the
        measured range.

    Notes
    -----
    The interpolation method is pandas ``'time'``, which assumes a constant
    growth rate between measurement visits.  Palm canopy volume grows roughly
    monotonically over the study period, so linear interpolation is
    appropriate for the typical visit interval of a few months.

    See Also
    --------
    load_tree_biophysics : Loads and parses the biophysical spreadsheet.

    Examples
    --------
    # doctest: +SKIP
    # Requires a DataFrame from load_tree_biophysics().
    vol = get_tree_volume_at_date(df_vigor, "EKA1-001", "2023-06-15")
    print(f"Tree volume: {vol:.4f} m3")
    """
    if df_vigor is None or tree_id not in df_vigor["Tree ID"].values:
        return None

    tree_data = df_vigor[df_vigor["Tree ID"] == tree_id].sort_values("Date")
    if len(tree_data) == 0:
        return None

    if isinstance(target_date, str):
        target_date = pd.to_datetime(target_date)

    exact = tree_data[tree_data["Date"] == target_date]
    if len(exact) > 0:
        return exact.iloc[0]["Vigor_Index_m3"]

    series = tree_data.set_index("Date")["Vigor_Index_m3"]
    series = series.reindex(series.index.union([target_date]))
    series = series.interpolate(method="time")

    if target_date in series.index:
        return series.loc[target_date]
    return None


# ---------------------------------------------------------------------------
# WPL QC Overrides
# ---------------------------------------------------------------------------


def apply_wpl_qc_overrides(
    row,
    model_qc,
    flux_qc,
    reason_text,
    wpl_qc_thresholds=None,
    h2o_valid_range=(0.0, 60.0),
):
    """Apply WPL-specific checks and upgrade QC tiers if needed.

    Checks whether the WPL correction was well-conditioned for a given cycle
    (sufficient valid H₂O data, reasonable correction magnitude, plausible
    WPL factor).  If any check fails, the ``model_qc`` and ``flux_qc`` tiers
    are upgraded (never downgraded) and a reason string is appended.

    This function is called after :func:`build_cycle_wpl_metrics` and
    :func:`palmwtc.flux.cycles.score_cycle` in the post-processing pipeline,
    not by :func:`calculate_flux_cycles` directly.

    Parameters
    ----------
    row : pd.Series or dict
        A single cycle row containing WPL metrics produced by
        :func:`build_cycle_wpl_metrics`: ``wpl_valid_fraction``,
        ``wpl_abs_rel_change_p95``, ``wpl_factor_max``, and ``h2o_max``.
    model_qc : int
        Current model QC tier (0 = A, 1 = B, 2 = C) to be potentially
        upgraded.
    flux_qc : int
        Current flux QC tier to be potentially upgraded.
    reason_text : str
        Semicolon-separated QC reasons accumulated so far.  New reasons are
        appended and duplicates are removed.
    wpl_qc_thresholds : dict or None
        Override :data:`DEFAULT_WPL_QC_THRESHOLDS`.
    h2o_valid_range : tuple of float
        ``(lo, hi)`` valid H₂O range in mmol mol⁻¹ (default
        ``(0.0, 60.0)``).  H₂O values above ``hi`` trigger a Grade C
        downgrade.

    Returns
    -------
    tuple of (int, int, int, str)
        ``(model_qc, flux_qc, wpl_qc, reason_text)`` where:

        - ``model_qc``, ``flux_qc`` are the (possibly upgraded) input tiers.
        - ``wpl_qc`` is the WPL-specific tier (0, 1, or 2) that drove the
          upgrade.
        - ``reason_text`` is the updated semicolon-separated reason string.

    See Also
    --------
    DEFAULT_WPL_QC_THRESHOLDS : Threshold values and key descriptions.
    build_cycle_wpl_metrics : Produces the per-cycle WPL metrics consumed here.
    """
    if wpl_qc_thresholds is None:
        wpl_qc_thresholds = DEFAULT_WPL_QC_THRESHOLDS

    reasons = [r for r in str(reason_text).split(";") if r]
    wpl_qc = 0

    valid_frac = row.get("wpl_valid_fraction", np.nan)
    if pd.isna(valid_frac):
        wpl_qc = max(wpl_qc, 2)
        reasons.append("wpl_missing_fraction")
    elif valid_frac < wpl_qc_thresholds["valid_frac_B"]:
        wpl_qc = max(wpl_qc, 2)
        reasons.append("wpl_low_valid_fraction")
    elif valid_frac < wpl_qc_thresholds["valid_frac_A"]:
        wpl_qc = max(wpl_qc, 1)
        reasons.append("wpl_valid_fraction_moderate")

    rel_p95 = row.get("wpl_abs_rel_change_p95", np.nan)
    if pd.notna(rel_p95):
        if rel_p95 > wpl_qc_thresholds["rel_change_p95_B"]:
            wpl_qc = max(wpl_qc, 2)
            reasons.append("wpl_large_adjustment")
        elif rel_p95 > wpl_qc_thresholds["rel_change_p95_A"]:
            wpl_qc = max(wpl_qc, 1)
            reasons.append("wpl_adjustment_moderate")

    factor_max = row.get("wpl_factor_max", np.nan)
    if pd.notna(factor_max) and factor_max > wpl_qc_thresholds["factor_max_B"]:
        wpl_qc = max(wpl_qc, 2)
        reasons.append("wpl_factor_high")

    h2o_max = row.get("h2o_max", np.nan)
    if pd.notna(h2o_max) and h2o_max > h2o_valid_range[1]:
        wpl_qc = max(wpl_qc, 2)
        reasons.append("h2o_out_of_range")

    model_qc = max(model_qc, wpl_qc)
    flux_qc = max(flux_qc, wpl_qc)

    deduped = []
    seen = set()
    for reason in reasons:
        reason = reason.strip()
        if reason and reason not in seen:
            deduped.append(reason)
            seen.add(reason)

    return model_qc, flux_qc, wpl_qc, ";".join(deduped)


# ---------------------------------------------------------------------------
# Closure Confidence
# ---------------------------------------------------------------------------


def compute_closure_confidence(r2, nrmse, global_radiation, rad_max=800.0):
    """Compute a chamber closure confidence score between 0 and 1.

    Combines R², NRMSE, and global radiation into a single scalar that
    expresses how confident we are that the chamber was properly sealed
    during a flux cycle.

    Physical reasoning: poor fit quality (low R², high NRMSE) is more
    likely to indicate a physical leak when photosynthetic demand is high
    (bright conditions).  The same poor fit at night or on a cloudy day
    could simply reflect a small signal close to sensor noise.  The score
    therefore penalizes low R² and high NRMSE more strongly when radiation
    is high.

    Formula
    -------
    .. math::

        r2\\_conf = clip\\left(\\frac{R^2 - 0.25}{0.94 - 0.25}, 0, 1\\right)

        rad\\_norm = clip\\left(\\frac{G}{G_{max}}, 0, 1\\right)

        confidence = clip\\left(r2\\_conf
            - 0.4 \\times rad\\_norm \\times (1 - r2\\_conf)
            - 0.2 \\times rad\\_norm \\times clip(NRMSE / 0.20, 0, 1),
        0, 1\\right)

    Parameters
    ----------
    r2 : float or array-like
        R² of the OLS linear CO₂ vs. time fit (0–1).  NaN is treated as 0.
    nrmse : float or array-like
        Normalized RMSE (RMSE / CO₂ range).  NaN is treated as 0.
    global_radiation : float or array-like
        Incoming solar radiation in W m⁻².  NaN is treated as 0 (worst-case
        penalty removed).
    rad_max : float
        Radiation level at which the radiation penalty is at its maximum.
        Default ``800.0`` W m⁻² (typical clear-sky midday value in the
        tropics).

    Returns
    -------
    float or numpy.ndarray
        Closure confidence score in [0, 1].  A score near 1 indicates a
        well-sealed chamber with a clean linear CO₂ trend.  A score near 0
        indicates likely leakage or strong non-linearity under high light.

    Notes
    -----
    The R² bounds (0.25 to 0.94) and penalty weights (0.4, 0.2) were
    calibrated against manual inspection of gap-width experiment data.

    See Also
    --------
    calculate_flux_cycles : Produces the R², NRMSE, and radiation values
        consumed here.

    Examples
    --------
    >>> from palmwtc.flux.chamber import compute_closure_confidence
    >>> round(float(compute_closure_confidence(0.98, 0.03, 0.0)), 3)
    1.0
    >>> round(float(compute_closure_confidence(0.95, 0.05, 200.0)), 3)
    0.988
    >>> round(float(compute_closure_confidence(0.50, 0.25, 600.0)), 3)
    0.021
    >>> round(float(compute_closure_confidence(0.40, 0.30, 700.0)), 3)
    0.0
    """
    rad_norm = np.clip(global_radiation / rad_max, 0, 1)
    rad_norm = np.where(np.isnan(rad_norm), 0.0, rad_norm)

    r2_safe = np.where(np.isnan(r2), 0.0, r2)
    r2_conf = np.clip((r2_safe - 0.25) / (0.94 - 0.25), 0, 1)

    rad_penalty = rad_norm * (1 - r2_conf) * 0.4

    nrmse_safe = np.where(np.isnan(nrmse), 0.0, nrmse)
    nrmse_penalty = rad_norm * np.clip(nrmse_safe / 0.20, 0, 1) * 0.2

    return np.clip(r2_conf - rad_penalty - nrmse_penalty, 0, 1)
