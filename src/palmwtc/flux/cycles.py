# ruff: noqa: RUF001, RUF002, RUF005, RUF046, RUF059, SIM102, SIM108, SIM910, F841
"""Per-cycle identification and quality scoring for chamber flux measurements.

A **chamber cycle** is a single closed-chamber measurement sequence — typically
~5 minutes of 30-second-cadence readings at near-constant ambient conditions
inside one whole-tree chamber (WTC), producing one CO₂ flux value and one H₂O
flux value per cycle per chamber.

This module covers the full cycle-level QC pipeline:

- **Cycle identification**: assign cycle IDs from raw sensor streams based on
  time-gap thresholds (:func:`identify_cycles`).
- **Best-window selection**: find the most linear sub-segment within each cycle
  (:func:`select_best_window_fast`).
- **Bimodal fault detection**: detect instrument-fault signatures — two
  concentration modes within a single cycle — that point to a real-time-clock
  glitch or interleaved sample streams (:func:`detect_bimodal_cycle`).
- **Per-cycle evaluation**: fit a linear slope, compute diagnostic statistics
  (R², NRMSE, SNR, monotonicity, curvature, Theil-Sen agreement), and convert
  slope → absolute flux (:func:`evaluate_cycle`).
- **Per-cycle scoring**: apply the A/B/C tier rule-based QC system and combine
  with the raw sensor hardware flag (:func:`score_cycle`).
- **Day-level quality scoring**: aggregate cycle scores to a 0–1 composite day
  score based on coverage, linearity, sign consistency, diurnal shape, and NRMSE
  (:func:`score_day_quality`, :func:`compute_day_scores`).
- **Temporal coherence**: flag cycles that are implausible given their immediate
  neighbours (unexpected slope jumps or mid-day sign flips,
  :func:`compute_temporal_coherence`).
- **ML anomaly detection**: Isolation Forest + Robust Covariance (MCD) overlay
  to catch multivariate anomalies among rule-based-passing cycles
  (:func:`compute_ml_anomaly_flags`).

Quality-score thresholds are defined by :data:`QC_THRESHOLDS` (daytime) and
:data:`NIGHTTIME_QC_THRESHOLDS` (nighttime, relaxed).  Hard physical limits that
override scoring are in :data:`HARD_LIMITS`.  The default ML feature set is
:data:`DEFAULT_ML_FEATURES`.

Cycle-level outputs (columns produced by :func:`evaluate_cycle`) are consumed by
:func:`~palmwtc.flux.chamber.calculate_flux_cycles` in the sibling module
``palmwtc.flux.chamber``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import linregress, theilslopes

# Absolute-flux conversion — always present in the installed package.
from palmwtc.flux.absolute import calculate_absolute_flux

# ML anomaly detection (optional dependency)
try:
    from sklearn.covariance import MinCovDet as _MinCovDet

    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

# GPU-aware IsolationForest (falls back to sklearn on CPU/M1).
# DEVICE is re-exported as ``_GPU_DEVICE`` for API parity with ``flux_qc_fast``;
# downstream code (e.g. notebook 030) inspects it for run-time logging.
from palmwtc.hardware.gpu import DEVICE as _GPU_DEVICE  # noqa: F401
from palmwtc.hardware.gpu import get_isolation_forest as _get_isolation_forest

# ------------------------------------------------------------------------------
# Configuration Constants (defaults, can be overridden if needed)
# ------------------------------------------------------------------------------

CYCLE_GAP_SEC = 300
"""Seconds of silence between consecutive measurements that mark a new cycle.

Any timestamp gap longer than this value triggers a new ``cycle_id`` in
:func:`identify_cycles`.  Default 300 s (5 min) matches the automated
opening/closing cadence of the whole-tree chambers.
"""

START_CUTOFF_SEC = 50
"""Seconds from cycle start to skip before searching for the fit window.

The first ~50 s after chamber closure are unstable (headspace flushing and
pressure equilibration).  :func:`select_best_window_fast` ignores all data
before this offset.
"""

START_SEARCH_SEC = 60
"""Width (seconds) of the window-start search zone after ``START_CUTOFF_SEC``.

:func:`select_best_window_fast` tries every candidate start index in the
range ``[START_CUTOFF_SEC, START_CUTOFF_SEC + START_SEARCH_SEC]``.
"""

MIN_POINTS = 8
"""Minimum number of data points required in the fit window.

Cycles with fewer usable points after outlier removal are assigned QC flag 2
(``too_few_points``).
"""

MIN_DURATION_SEC = 60
"""Minimum fit-window duration in seconds.

Windows shorter than this are skipped by :func:`select_best_window_fast` and
cycles that cannot meet it are flagged 2 (``short_duration``).
"""

OUTLIER_Z = 3.5
"""MAD-based Z-score threshold for identifying within-cycle outlier readings.

See :func:`mad_outlier_mask`.  A value of 3.5 corresponds roughly to the
99.9th percentile under a normal distribution.
"""

MAX_OUTLIER_REFIT_FRAC = 0.2
"""Maximum fraction of points that may be removed as outliers before refit.

If outlier fraction exceeds this threshold the original (un-cleaned) fit is
kept, preventing over-removal of valid high-variance cycles.
"""

NOISE_EPS_PPM = 0.5
"""Noise floor (ppm) used by :func:`monotonic_fraction`.

Step changes smaller than this threshold are not counted when computing the
monotonic fraction — they are indistinguishable from sensor quantisation
noise.
"""

USE_MULTIPROCESSING = True
"""Default flag passed to callers (e.g. notebook 032) for pool-based evaluation.

This constant is read by the caller, not used internally in this module.
"""

# QC thresholds (defaults)
QC_THRESHOLDS = {
    "min_points": MIN_POINTS,
    "min_duration_sec": MIN_DURATION_SEC,
    "r2_A": 0.90,
    "r2_B": 0.70,
    "nrmse_A": 0.10,
    "nrmse_B": 0.20,
    "snr_A": 10.0,
    "snr_B": 3.0,  # relaxed from 5.0: SNR<5 at night is OK if R²≥0.70
    "monotonic_A": 0.80,
    "monotonic_B": 0.45,  # relaxed from 0.60: physics-justified for small signals
    "outlier_A": 0.05,
    "outlier_B": 0.15,
    "curvature_aicc": -4.0,
    "slope_diff_A": 0.30,
    "slope_diff_B": 0.60,
    "signal_ppm_guard": 5.0,  # min total CO2 change (ppm) to apply strict monotonicity check
    "b_count_C": 3,  # cycles with >=3 B-tier issues demoted to C
    "curvature_aicc_C": -12.0,  # strong curvature downgrades to C
}
"""Daytime QC thresholds used by :func:`score_cycle`.

Keys (all floats unless noted):

``min_points`` / ``min_duration_sec``
    Hard minimum point count and duration — see :data:`MIN_POINTS` /
    :data:`MIN_DURATION_SEC`.

``r2_A`` / ``r2_B``
    A-tier threshold (0.90) and B-tier lower bound (0.70).  R² below the
    B value triggers QC flag 2 (``low_r2``).

``nrmse_A`` / ``nrmse_B``
    Normalised RMSE thresholds (RMSE / CO₂ range).  Above B → flag 2
    (``high_nrmse``).

``snr_A`` / ``snr_B``
    Signal-to-noise ratio thresholds.  Above A = clean, between A/B = B-tier,
    below B = flag 2 (``low_snr``).

``monotonic_A`` / ``monotonic_B``
    Fraction of point-to-point steps in the same direction as the overall
    slope.  Values below ``signal_ppm_guard`` use a scaled B threshold to
    account for noise-dominated small signals.

``outlier_A`` / ``outlier_B``
    Fraction of points removed as MAD outliers.  Above B → flag 2
    (``many_outliers``).

``curvature_aicc`` / ``curvature_aicc_C``
    AICc difference (quadratic − linear).  Negative means the quadratic fit
    is preferred; very negative (< ``curvature_aicc_C``) indicates strong
    non-linearity → flag 2 (``strong_curvature``).

``slope_diff_A`` / ``slope_diff_B``
    Relative difference between OLS slope and Theil-Sen slope.  Large
    values indicate leverage or asymmetric scatter.

``signal_ppm_guard``
    Minimum total CO₂ change (ppm) to apply the strict monotonicity check.
    Below this value the B threshold is scaled down proportionally.

``b_count_C``
    If a cycle accumulates ≥ ``b_count_C`` B-tier issues it is demoted to C
    (QC flag 2, reason ``many_moderate_issues``).
"""

# Nighttime-specific relaxed thresholds (applied when Global_Radiation < 10 W/m²)
NIGHTTIME_QC_THRESHOLDS = {
    "min_points": MIN_POINTS,
    "min_duration_sec": MIN_DURATION_SEC,
    "r2_A": 0.70,
    "r2_B": 0.40,
    "nrmse_A": 0.25,
    "nrmse_B": 0.40,
    "snr_A": 5.0,
    "snr_B": 2.0,
    "monotonic_A": 0.50,
    "monotonic_B": 0.30,
    "outlier_A": 0.10,
    "outlier_B": 0.20,
    "curvature_aicc": -8.0,
    "curvature_aicc_C": -16.0,
    "slope_diff_A": 0.40,
    "slope_diff_B": 0.80,
    "signal_ppm_guard": 3.0,  # lower guard for smaller respiration signals
    "b_count_C": 4,  # more lenient at night (smaller signals = more B-tier hits)
}
"""Relaxed QC thresholds applied when ``Global_Radiation < 10 W m⁻²``.

At night, respiration signals are smaller and the CO₂ slope is close to zero,
so noise-to-signal ratios are inherently higher.  These thresholds follow the
same key structure as :data:`QC_THRESHOLDS` but with lower R² requirements,
higher NRMSE/SNR tolerances, and a looser monotonicity floor.
:func:`score_cycle` selects this dict automatically when ``is_nighttime=True``.
"""

# Default feature set for ML anomaly detection (compute_ml_anomaly_flags).
# flux_slope is intentionally excluded — extreme but real fluxes must not be flagged.
DEFAULT_ML_FEATURES = [
    "r2",
    "nrmse",
    "snr",
    "monotonicity",
    "outlier_frac",
    "slope_diff_pct",
    "delta_aicc",
    "co2_range",
    "h2o_r2",
    "h2o_snr",
    "h2o_outlier_frac",
]
"""Default feature columns passed to :func:`compute_ml_anomaly_flags`.

``flux_slope`` is intentionally excluded: an extreme but physically real flux
should not be penalised by the anomaly detector.  All features here describe
*how well the cycle was measured*, not *what the measurement value was*.
Column name aliases (e.g. ``r2`` → ``co2_r2``) are resolved automatically.
"""

HARD_LIMITS = {
    "max_abs_slope": 10.0,
    "max_abs_flux": 100.0,
    "max_co2_range": 2000.0,
}
"""Absolute physical limits applied by :func:`score_cycle` when
``enforce_hard_limits=True``.

``max_abs_slope``
    Maximum plausible CO₂ slope in ppm s⁻¹ (default 10.0).
``max_abs_flux``
    Maximum plausible absolute flux in µmol m⁻² s⁻¹ (default 100.0).
``max_co2_range``
    Maximum CO₂ range within a single cycle in ppm (default 2000.0).
"""

# ------------------------------------------------------------------------------
# Core Math Functions (Optimized)
# ------------------------------------------------------------------------------


def calc_aicc(rss, n, k):
    """Calculate AICc (Corrected Akaike Information Criterion)."""
    if n <= k + 1:
        return np.inf
    rss = max(rss, 1e-12)
    aic = n * np.log(rss / n) + 2 * k
    return aic + (2 * k * (k + 1)) / (n - k - 1)


def fit_linear_optimized(t, y, compute_stats=False):
    """
    Fit linear regression y = mx + c.
    optimized using numpy vectorization.

    Returns:
        slope, intercept, r2, p_value, std_err, rmse, rss, aicc, residuals
    """
    n = len(t)
    if n < 2:
        return np.nan, np.nan, 0.0, np.nan, np.nan, 0.0, 0.0, np.inf, np.zeros_like(y)

    # Vectorized least squares
    sum_t = np.sum(t)
    sum_y = np.sum(y)
    sum_t2 = np.sum(t * t)
    sum_ty = np.sum(t * y)

    denominator = n * sum_t2 - sum_t * sum_t
    if denominator == 0:
        return np.nan, np.nan, 0.0, np.nan, np.nan, 0.0, 0.0, np.inf, np.zeros_like(y)

    slope = (n * sum_ty - sum_t * sum_y) / denominator
    intercept = (sum_y - slope * sum_t) / n

    y_pred = slope * t + intercept
    residuals = y - y_pred
    rss = np.sum(residuals**2)
    rmse = np.sqrt(rss / n)

    # R2
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - (rss / ss_tot) if ss_tot > 0 else 0.0

    # AICc (k=2 for linear)
    aicc = calc_aicc(rss, n, 2)

    p_value = np.nan
    std_err = np.nan

    if compute_stats:
        # Use scipy for full stats only when needed
        res = linregress(t, y)
        p_value = res.pvalue
        std_err = res.stderr
        # We can also verify slope/interept match but numpy is usually fine

    return slope, intercept, r2, p_value, std_err, rmse, rss, aicc, residuals


def fit_quadratic_fast(t, y):
    coeffs = np.polyfit(t, y, 2)
    y_hat = np.polyval(coeffs, t)
    residuals = y - y_hat
    rss = np.sum(residuals**2)
    aicc = calc_aicc(rss, len(t), 3)
    return coeffs, rss, aicc, residuals


def mad_outlier_mask(residuals, z_thresh=OUTLIER_Z):
    med = np.median(residuals)
    mad = np.median(np.abs(residuals - med))
    if mad == 0:
        return np.zeros_like(residuals, dtype=bool)
    z = 0.6745 * (residuals - med) / mad
    return np.abs(z) > z_thresh


def monotonic_fraction(y, slope, noise_eps=NOISE_EPS_PPM):
    if len(y) < 3 or slope == 0:
        return np.nan
    dy = np.diff(y)
    valid = np.abs(dy) > noise_eps
    if valid.sum() == 0:
        return np.nan
    return float(np.mean(np.sign(dy[valid]) == np.sign(slope)))


# ------------------------------------------------------------------------------
# Cycle & Window Logic
# ------------------------------------------------------------------------------


def identify_cycles(
    data: pd.DataFrame,
    time_col: str = "TIMESTAMP",
    gap_sec: float = CYCLE_GAP_SEC,
) -> pd.DataFrame:
    """Assign a monotonically increasing cycle ID to each row.

    A new cycle starts whenever the time gap between consecutive rows
    exceeds ``gap_sec`` seconds.  The function sorts by ``time_col`` first,
    so row order in the input does not matter.

    Parameters
    ----------
    data : pd.DataFrame
        Raw sensor DataFrame.  Must contain a datetime-like column named
        ``time_col``.
    time_col : str
        Name of the datetime column (default ``'TIMESTAMP'``).
    gap_sec : float
        Gap threshold in seconds.  Any gap larger than this value starts a
        new cycle (default :data:`CYCLE_GAP_SEC` = 300 s).

    Returns
    -------
    pd.DataFrame
        Copy of ``data`` sorted by ``time_col`` with three new columns:

        ``delta_t_sec`` : float
            Seconds elapsed since the previous row (NaN for the first row).
        ``new_cycle`` : bool
            True where a new cycle begins (gap > ``gap_sec`` or first row).
        ``cycle_id`` : int
            Zero-based cumulative cycle counter.  All rows belonging to the
            same closure event share the same integer ID.

    Examples
    --------
    >>> import pandas as pd
    >>> from palmwtc.flux.cycles import identify_cycles
    >>> ts = pd.to_datetime(["2024-01-01 08:00:00", "2024-01-01 08:00:30",
    ...                      "2024-01-01 08:10:00"])  # 9.5-min gap → new cycle
    >>> df = pd.DataFrame({"TIMESTAMP": ts, "CO2": [400, 401, 402]})
    >>> out = identify_cycles(df)
    >>> list(out["cycle_id"])
    [1, 1, 2]
    """
    data = data.sort_values(time_col).copy()
    delta = data[time_col].diff().dt.total_seconds()
    data["delta_t_sec"] = delta
    data["new_cycle"] = (delta > gap_sec) | delta.isna()
    data["cycle_id"] = data["new_cycle"].cumsum()
    return data


def select_best_window_fast(
    t,
    y,
    start_cutoff_sec,
    start_search_sec,
    min_points,
    min_duration_sec,
    outlier_z=OUTLIER_Z,
    max_outlier_refit_frac=MAX_OUTLIER_REFIT_FRAC,
):
    if len(t) < min_points:
        return None

    # Identify potential start indices
    start_idx = np.searchsorted(t, start_cutoff_sec, side="left")
    if start_idx >= len(t) - min_points:
        return None

    start_limit = start_cutoff_sec + start_search_sec
    start_candidates = np.where((t >= t[start_idx]) & (t <= start_limit))[0]

    if len(start_candidates) == 0:
        start_candidates = np.array([start_idx])

    candidates = []

    # Generate end indices - scan backwards from end
    # Using a stride could be an optimization but relying on fast fit for now
    end_indices = np.unique(
        np.concatenate(
            [np.arange(len(t) - 1, max(start_idx + min_points - 2, 0), -1), [len(t) - 1]]
        )
    )

    for s_idx in start_candidates:
        for e_idx in end_indices:
            if e_idx <= s_idx + min_points - 2:
                break
            duration = t[e_idx] - t[s_idx]
            if duration < min_duration_sec:
                continue

            t_seg = t[s_idx : e_idx + 1]
            y_seg = y[s_idx : e_idx + 1]

            # Fast fit without p/std_err
            slope, intercept, r2, _, _, rmse, rss, aicc, residuals = fit_linear_optimized(
                t_seg, y_seg, compute_stats=False
            )

            if np.isinf(aicc):
                continue

            outlier_mask = mad_outlier_mask(residuals, z_thresh=outlier_z)
            outlier_frac = float(outlier_mask.mean())

            t_use = t_seg
            y_use = y_seg
            slope_use = slope

            # Refit if outliers found
            if (
                0 < outlier_frac <= max_outlier_refit_frac
                and (len(t_seg) - outlier_mask.sum()) >= min_points
            ):
                t_use = t_seg[~outlier_mask]
                y_use = y_seg[~outlier_mask]
                slope_use, intercept, r2, _, _, rmse, rss, aicc, _ = fit_linear_optimized(
                    t_use, y_use, compute_stats=False
                )
                if np.isinf(aicc):
                    continue

            monotonicity = monotonic_fraction(y_use, slope_use, noise_eps=NOISE_EPS_PPM)

            candidates.append(
                {
                    "start_idx": s_idx,
                    "end_idx": e_idx,
                    "t": t_seg,  # Store raw detailed data? Or just indices? Storing arrays takes memory but is safe.
                    "y": y_seg,
                    "t_use": t_use,  # Clean subset
                    "y_use": y_use,
                    "duration_sec": duration,
                    "slope": slope_use,
                    "intercept": intercept,
                    "r2": r2,
                    "p_value": np.nan,  # fill later
                    "std_err": np.nan,  # fill later
                    "rmse": rmse,
                    "rss": rss,
                    "aicc": aicc,
                    "outlier_frac": outlier_frac,
                    "monotonicity": monotonicity,
                }
            )

    if not candidates:
        # Fallback to full range if valid
        e_idx = len(t) - 1
        if e_idx - start_idx + 1 < min_points:
            return None
        t_seg = t[start_idx : e_idx + 1]
        y_seg = y[start_idx : e_idx + 1]
        slope, intercept, r2, _, _, rmse, rss, aicc, _ = fit_linear_optimized(
            t_seg, y_seg, compute_stats=True
        )
        return {
            "start_idx": start_idx,
            "end_idx": e_idx,
            "t": t_seg,
            "y": y_seg,
            "t_use": t_seg,
            "y_use": y_seg,
            "duration_sec": t_seg[-1] - t_seg[0],
            "slope": slope,
            "intercept": intercept,
            "r2": r2,
            "p_value": np.nan,
            "std_err": np.nan,  # fill if needed
            "rmse": rmse,
            "rss": rss,
            "aicc": aicc,
            "outlier_frac": 0.0,
            "monotonicity": monotonic_fraction(y_seg, slope, NOISE_EPS_PPM),
        }

    # Selection Logic
    best_aicc = min(c["aicc"] for c in candidates)
    near_best = [c for c in candidates if c["aicc"] <= best_aicc + 2]

    def mono_score(val):
        m = val["monotonicity"]
        return m if not np.isnan(m) else -1.0

    best = max(near_best, key=lambda c: (mono_score(c), -c["outlier_frac"], c["duration_sec"]))

    # Recalculate full stats for the winner
    # We use t_use/y_use which are the clean points
    res = linregress(best["t_use"], best["y_use"])
    best["p_value"] = res.pvalue
    best["std_err"] = res.stderr

    return best


def detect_bimodal_cycle(
    values: np.ndarray,
    bin_width: float = 5.0,
    min_gap_bins: int = 4,
    min_side_points: int = 3,
) -> dict:
    """Detect bimodal CO₂ or H₂O distribution within a single cycle.

    Bimodality here means two clean clusters separated by a run of empty
    histogram bins — the signature of an instrument fault rather than
    real biological variability.

    The most common fault source is a **real-time-clock (RTC) glitch** in
    the LI-COR multiplexer: when the logger's timestamp loses sync for a few
    seconds, measurements from two different time windows (e.g. one from
    earlier in the cycle and one current) are interleaved into the same
    cycle record.  The two windows have different ambient CO₂ levels, so
    the within-cycle distribution splits into two separate clusters with a
    distinct gap between them.

    This is **not** the same as a wide or noisy distribution.  A cycle with
    large random scatter around a single trend will be unimodal and will
    not be flagged by this function.  The bimodal flag is complementary to
    the R²/NRMSE checks in :func:`score_cycle`: a bimodal cycle often still
    has a plausible R² if both clusters happen to share the same trend.

    The function is called inside :func:`evaluate_cycle` on the full raw
    cycle (before the best-window selection) so that the fault can be
    detected even if the fit window excludes part of the contaminated data.

    Parameters
    ----------
    values : array-like
        Raw concentration values for one cycle (ppm CO₂ or g kg⁻¹ H₂O).
        NaN and Inf values are ignored.
    bin_width : float
        Histogram bin width in the same units as ``values`` (default 5 ppm).
    min_gap_bins : int
        Minimum number of consecutive empty histogram bins between two
        non-empty regions required to call a cycle bimodal (default 4 bins
        = 20 ppm gap at the default ``bin_width``).
    min_side_points : int
        Minimum number of data points required on each side of the gap
        (default 3).  Prevents false positives from single-point outliers.

    Returns
    -------
    dict
        Dictionary with four keys:

        ``is_bimodal`` : bool
            True if a bimodal distribution was detected.
        ``gap_ppm`` : float
            Width of the empty gap in the same units as ``values`` (0.0 if
            not bimodal).
        ``lower_mean`` : float
            Mean of the lower concentration cluster (NaN if not bimodal).
        ``upper_mean`` : float
            Mean of the upper concentration cluster (NaN if not bimodal).

    Notes
    -----
    The algorithm:

    1. Build a histogram of ``values`` with ``bin_width``-wide bins.
    2. Locate the longest run of consecutive zero-count bins between the
       first and last non-empty bin.
    3. If that run spans ≥ ``min_gap_bins`` bins and both sides have
       ≥ ``min_side_points`` points, flag as bimodal.

    The cycle must contain at least 10 finite values and span more than
    ``bin_width × (min_gap_bins + 2)`` ppm; otherwise the function returns
    ``is_bimodal=False`` without computing the histogram.

    Examples
    --------
    Two clusters separated by a 30-ppm gap:

    >>> import numpy as np
    >>> from palmwtc.flux.cycles import detect_bimodal_cycle
    >>> low  = np.linspace(395, 398, 8)
    >>> high = np.linspace(430, 433, 8)
    >>> result = detect_bimodal_cycle(np.concatenate([low, high]))
    >>> result["is_bimodal"]
    True
    >>> result["gap_ppm"] >= 20.0
    True

    A noisy but unimodal cycle is not flagged:

    >>> rng = np.random.default_rng(0)
    >>> unimodal = 400 + rng.normal(0, 2, 20)
    >>> detect_bimodal_cycle(unimodal)["is_bimodal"]
    False
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    null = {"is_bimodal": False, "gap_ppm": 0.0, "lower_mean": np.nan, "upper_mean": np.nan}
    if len(v) < 10:
        return null
    lo, hi = float(v.min()), float(v.max())
    # Need enough span to fit a min-gap and at least one bin on each side.
    if hi - lo < bin_width * (min_gap_bins + 2):
        return null
    edges = np.arange(
        np.floor(lo / bin_width) * bin_width,
        np.ceil(hi / bin_width) * bin_width + bin_width,
        bin_width,
    )
    counts, _ = np.histogram(v, bins=edges)
    nonzero_idx = np.where(counts > 0)[0]
    if len(nonzero_idx) < 2:
        return null

    # Find longest run of empty bins between the first and last non-empty bin.
    best_start, best_len = 0, 0
    cur_start, cur_len = None, 0
    for i in range(nonzero_idx[0], nonzero_idx[-1] + 1):
        if counts[i] == 0:
            if cur_start is None:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_start, cur_len = None, 0

    if best_len < min_gap_bins:
        return null

    split_val = (edges[best_start] + edges[best_start + best_len]) / 2.0
    lower = v[v < split_val]
    upper = v[v >= split_val]
    if len(lower) < min_side_points or len(upper) < min_side_points:
        return null

    return {
        "is_bimodal": True,
        "gap_ppm": float(best_len * bin_width),
        "lower_mean": float(lower.mean()),
        "upper_mean": float(upper.mean()),
    }


def evaluate_cycle(
    group,
    chamber_name,
    time_col="TIMESTAMP",
    co2_col="CO2",
    temp_col="Temp",
    qc_col="Flag",
    options=None,
):
    if options is None:
        options = {}

    # Extract configuration with fallbacks to module constants
    min_points = options.get("min_points", MIN_POINTS)
    min_duration_sec = options.get("min_duration_sec", MIN_DURATION_SEC)
    start_cutoff_sec = options.get("start_cutoff_sec", START_CUTOFF_SEC)
    start_search_sec = options.get("start_search_sec", START_SEARCH_SEC)
    outlier_z = options.get("outlier_z", OUTLIER_Z)
    max_outlier_refit_frac = options.get("max_outlier_refit_frac", MAX_OUTLIER_REFIT_FRAC)
    noise_win_sec = options.get("noise_win_sec", None)
    noise_min_points = options.get("noise_min_points", 5)

    group = group.sort_values(time_col)
    t = (group[time_col] - group[time_col].min()).dt.total_seconds().values
    y = group[co2_col].values.astype(float)

    if len(t) < min_points:
        return None

    # We need to ensure select_best_window_fast uses these params.
    # Current signature: select_best_window_fast(t, y, start_cutoff_sec, start_search_sec, min_points, min_duration_sec)
    # It doesn't accept outlier params yet, those are still global in that function (lines 192, 200).
    # For now we fix the MAIN issue (duration/points).

    window = select_best_window_fast(
        t,
        y,
        start_cutoff_sec,
        start_search_sec,
        min_points,
        min_duration_sec,
        outlier_z=outlier_z,
        max_outlier_refit_frac=max_outlier_refit_frac,
    )
    if window is None:
        return None

    slope = window["slope"]
    intercept = window["intercept"]
    r2 = window["r2"]
    rmse = window["rmse"]

    t_use = window["t_use"]
    y_use = window["y_use"]

    try:
        ts_slope, ts_intercept, ts_low, ts_high = theilslopes(y_use, t_use)
    except Exception:
        ts_slope = slope
        ts_intercept = intercept
        ts_low = np.nan
        ts_high = np.nan

    slope_diff_pct = abs(slope - ts_slope) / max(abs(slope), 1e-9)

    coeffs, _, aicc_quad, _ = fit_quadratic_fast(t_use, y_use)
    delta_aicc = aicc_quad - window["aicc"]

    co2_range = np.ptp(y_use)
    nrmse = rmse / co2_range if co2_range > 0 else np.nan

    duration_sec = t_use[-1] - t_use[0] if len(t_use) > 1 else 0
    snr = (abs(slope) * duration_sec) / (rmse if rmse > 0 else np.nan)

    # Optional noise-based SNR using early-cycle noise estimate
    noise_sigma = np.nan
    if noise_win_sec is not None:
        noise_mask = t <= noise_win_sec
        if noise_mask.sum() >= noise_min_points:
            seg = y[noise_mask]
            med = np.median(seg)
            mad = np.median(np.abs(seg - med))
            if mad > 0:
                noise_sigma = 1.4826 * mad
    snr_noise = (
        (abs(slope) * duration_sec) / noise_sigma
        if pd.notnull(noise_sigma) and noise_sigma > 0
        else np.nan
    )

    monotonicity = window["monotonicity"]
    mean_temp = group[temp_col].mean() if temp_col in group.columns else np.nan
    raw_flag = group[qc_col].max() if qc_col in group.columns else 0

    # Bimodal detection on the full raw cycle (not just the fit window).
    # Per-point physical-bounds QC in 020 cannot catch this; the values are
    # individually plausible but split into two clusters within the cycle.
    bimodal = detect_bimodal_cycle(y)

    cycle_start = group[time_col].min()
    cycle_end = group[time_col].max()

    row = {
        "Source_Chamber": chamber_name,
        "cycle_id": group["cycle_id"].iloc[0],
        "flux_date": cycle_start,
        "cycle_end": cycle_end,
        "cycle_duration_sec": (cycle_end - cycle_start).total_seconds(),
        "window_start_sec": float(window["t"][0]),
        "window_end_sec": float(window["t"][-1]),
        "duration_sec": float(duration_sec),
        "n_points_total": int(len(group)),
        "n_points_used": int(len(t_use)),
        "flux_slope": float(slope),
        "flux_intercept": float(intercept),
        "r2": float(r2),
        "p_value": float(window["p_value"]),
        "std_err": float(window["std_err"]),
        "rmse": float(rmse),
        "nrmse": float(nrmse) if not np.isnan(nrmse) else np.nan,
        "snr": float(snr) if not np.isnan(snr) else np.nan,
        "snr_noise": float(snr_noise) if not np.isnan(snr_noise) else np.nan,
        "noise_sigma": float(noise_sigma) if not np.isnan(noise_sigma) else np.nan,
        "monotonicity": float(monotonicity) if not np.isnan(monotonicity) else np.nan,
        "outlier_frac": float(window.get("outlier_frac", np.nan)),
        "aicc_linear": float(window["aicc"]),
        "aicc_quadratic": float(aicc_quad),
        "delta_aicc": float(delta_aicc),
        "slope_ts": float(ts_slope),
        "slope_ts_low": float(ts_low),
        "slope_ts_high": float(ts_high),
        "slope_diff_pct": float(slope_diff_pct),
        "mean_temp": float(mean_temp) if not np.isnan(mean_temp) else np.nan,
        "qc_flag": int(raw_flag) if pd.notnull(raw_flag) else 0,
        "co2_range": float(co2_range),
        "bimodal_flag": bool(bimodal["is_bimodal"]),
        "bimodal_gap_ppm": bimodal["gap_ppm"],
        "bimodal_lower_mean": bimodal["lower_mean"],
        "bimodal_upper_mean": bimodal["upper_mean"],
    }

    row["flux_absolute"] = float(calculate_absolute_flux(pd.Series(row)))
    return row


def _evaluate_cycle_wrapper(args):
    # Wrapper for multiprocessing
    # Supports unpacking options if present in tuple (cycle_id, group, chamber_name, options)
    if len(args) == 4:
        cycle_id, group, chamber_name, options = args
        return evaluate_cycle(group, chamber_name, options=options)
    else:
        cycle_id, group, chamber_name = args
        return evaluate_cycle(group, chamber_name)


def score_cycle(
    row: dict,
    raw_flag: int,
    thresholds: dict,
    enforce_hard_limits: bool = False,
    snr_field: str = "snr",
    is_nighttime: bool = False,
    nighttime_thresholds: dict | None = None,
) -> tuple[int, int, str]:
    """Score a single flux cycle and return a three-part QC result.

    This function is called row-by-row from
    :func:`~palmwtc.flux.chamber.calculate_flux_cycles` after
    :func:`evaluate_cycle` has computed the cycle statistics.  It applies
    the A/B/C tier rule-based QC system and then combines the model score
    with the raw hardware sensor flag.

    A "good" cycle (QC flag 0, tier A) meets **all** of the following
    physical criteria:

    - **Enough data**: ≥ :data:`MIN_POINTS` usable points and fit window
      ≥ :data:`MIN_DURATION_SEC` seconds.
    - **Linear signal**: R² ≥ ``r2_A`` threshold (default 0.90 daytime) —
      the chamber concentration must rise or fall in a straight line,
      indicating steady-state respiration or photosynthesis flux.
    - **Low residuals**: NRMSE ≤ ``nrmse_A`` — normalised root-mean-square
      error (RMSE / CO₂ range) quantifies scatter around the linear fit.
    - **Detectable signal**: SNR ≥ ``snr_A`` — signal amplitude relative
      to noise floor; small but real respiratory signals at night often
      fall below the daytime SNR threshold, which is why
      :data:`NIGHTTIME_QC_THRESHOLDS` relaxes this to ``snr_A = 5``.
    - **Monotonic slope**: ≥ ``monotonic_A`` fraction of consecutive steps
      point in the same direction as the overall slope.  The threshold is
      scaled down for signals smaller than ``signal_ppm_guard`` ppm because
      instrument noise statistically produces non-monotonic steps for very
      small CO₂ changes.
    - **Few outliers**: outlier fraction ≤ ``outlier_A`` after MAD removal.
    - **Linear curvature**: the AICc improvement from fitting a quadratic
      instead of a linear model must be minimal (``delta_aicc > curvature_aicc``).
    - **OLS/Theil-Sen agreement**: relative slope difference
      ≤ ``slope_diff_A`` — large disagreement indicates leverage points or
      skewed scatter, suggesting the slope estimate is unreliable.

    Cycles that fail one or two of the B-tier thresholds receive flag 1
    (tier B, still usable with reduced confidence).  Cycles with ≥
    ``b_count_C`` B-tier issues or any single hard failure receive flag 2
    (tier C, excluded from flux aggregation by default).

    Parameters
    ----------
    row : dict-like
        Dictionary (or pandas Series) with at minimum the keys produced by
        :func:`evaluate_cycle`:
        ``n_points_used``, ``duration_sec``, ``r2``, ``nrmse``, ``snr``,
        ``monotonicity``, ``outlier_frac``, ``delta_aicc``,
        ``slope_diff_pct``, ``flux_slope``, ``flux_absolute``, ``co2_range``.
    raw_flag : int
        Raw hardware sensor QC flag from the LI-COR or logger (0 = good,
        1 = suspect, 2 = bad).  This is combined with the model score
        via ``max(model_qc, raw_flag)``.
    thresholds : dict
        Daytime QC threshold dict — typically :data:`QC_THRESHOLDS`.
        See the docstring of :data:`QC_THRESHOLDS` for all valid keys.
    enforce_hard_limits : bool
        If True, also apply the absolute physical limits in
        :data:`HARD_LIMITS` (extreme slope, extreme flux, large CO₂ range).
        Default False.
    snr_field : str
        Which SNR column to read from ``row``: ``'snr'`` (regression-based,
        default) or ``'snr_noise'`` (noise-floor-based, requires a
        pre-closure noise window in the raw data).
    is_nighttime : bool
        When True and ``nighttime_thresholds`` is provided, the relaxed
        :data:`NIGHTTIME_QC_THRESHOLDS` are used instead of ``thresholds``.
        Nighttime is defined as ``Global_Radiation < 10 W m⁻²``.
    nighttime_thresholds : dict or None
        Relaxed threshold dict for nighttime — typically
        :data:`NIGHTTIME_QC_THRESHOLDS`.  Ignored when ``is_nighttime=False``.

    Returns
    -------
    model_qc : int
        QC score from the statistical model alone (0, 1, or 2).
    combined_qc : int
        ``max(model_qc, raw_flag)`` — the final QC flag stored as
        ``flux_qc`` in the output DataFrame.
    reasons_str : str
        Semicolon-separated list of failure reasons, e.g.
        ``'r2_moderate;low_snr;sensor_flag_1'``.  Empty string when the
        cycle passes all checks.  Individual reason codes:

        ``too_few_points``         — fewer than ``min_points`` used points.
        ``short_duration``         — fit window < ``min_duration_sec``.
        ``low_r2``                 — R² < B threshold.
        ``r2_moderate``            — R² between A and B thresholds.
        ``high_nrmse``             — NRMSE > B threshold.
        ``nrmse_moderate``         — NRMSE between A and B thresholds.
        ``low_snr``                — SNR < B threshold.
        ``snr_moderate``           — SNR between A and B thresholds.
        ``non_monotonic``          — monotonicity < effective B threshold.
        ``monotonic_moderate``     — monotonicity between A and B thresholds.
        ``many_outliers``          — outlier fraction > B threshold.
        ``some_outliers``          — outlier fraction between A and B thresholds.
        ``curvature``              — AICc improvement for quadratic > B threshold.
        ``strong_curvature``       — AICc improvement > C threshold.
        ``slope_disagreement``     — OLS/Theil-Sen slope difference > threshold.
        ``many_moderate_issues:N`` — N B-tier issues demoted to C.
        ``extreme_slope``          — slope > :data:`HARD_LIMITS` max.
        ``extreme_flux``           — absolute flux > :data:`HARD_LIMITS` max.
        ``large_co2_range``        — CO₂ range > :data:`HARD_LIMITS` max.
        ``sensor_flag_N``          — raw hardware flag = N (1 or 2).

    See Also
    --------
    evaluate_cycle : Produces the per-cycle statistics that ``row`` must contain.
    compute_day_scores : Aggregates cycle scores to a daily composite.

    Examples
    --------
    >>> from palmwtc.flux.cycles import score_cycle, QC_THRESHOLDS
    >>> row = {
    ...     "n_points_used": 12, "duration_sec": 180, "r2": 0.95,
    ...     "nrmse": 0.05, "snr": 15.0, "monotonicity": 0.90,
    ...     "outlier_frac": 0.02, "delta_aicc": 1.0,
    ...     "slope_diff_pct": 0.10, "flux_slope": -0.05,
    ...     "flux_absolute": -2.0, "co2_range": 10.0,
    ... }
    >>> model_qc, combined_qc, reasons = score_cycle(row, raw_flag=0,
    ...                                              thresholds=QC_THRESHOLDS)
    >>> combined_qc  # passes all checks
    0
    >>> reasons
    ''
    """
    # Select effective threshold set
    if is_nighttime and nighttime_thresholds is not None:
        th = nighttime_thresholds
    else:
        th = thresholds

    reasons = []
    model_qc = 0
    b_count = 0

    def bump(level, reason):
        nonlocal model_qc, b_count
        model_qc = max(model_qc, level)
        reasons.append(reason)
        if level == 1:
            b_count += 1

    if row["n_points_used"] < th["min_points"]:
        bump(2, "too_few_points")
    if row["duration_sec"] < th["min_duration_sec"]:
        bump(2, "short_duration")

    r2 = row["r2"]
    if np.isnan(r2) or r2 < th["r2_B"]:
        bump(2, "low_r2")
    elif r2 < th["r2_A"]:
        bump(1, "r2_moderate")

    nrmse = row["nrmse"]
    if np.isnan(nrmse) or nrmse > th["nrmse_B"]:
        bump(2, "high_nrmse")
    elif nrmse > th["nrmse_A"]:
        bump(1, "nrmse_moderate")

    snr = row.get(snr_field, row.get("snr", np.nan))
    if np.isnan(snr) or snr < th["snr_B"]:
        bump(2, "low_snr")
    elif snr < th["snr_A"]:
        bump(1, "snr_moderate")

    # Signal-aware monotonicity check:
    # When total CO2 change is small (< signal_ppm_guard), sensor noise
    # statistically produces non-monotonic steps even for real linear signals.
    # Scale the B-tier threshold down proportionally with signal strength.
    monotonicity = row["monotonicity"]
    if not np.isnan(monotonicity):
        signal_ppm = abs(row.get("flux_slope", 0)) * row.get("duration_sec", 0)
        signal_guard = th.get("signal_ppm_guard", 5.0)
        effective_mono_B = th["monotonic_B"]
        if signal_guard > 0 and 0 < signal_ppm < signal_guard:
            effective_mono_B = max(0.30, th["monotonic_B"] * (signal_ppm / signal_guard))

        if monotonicity < effective_mono_B:
            bump(2, "non_monotonic")
        elif monotonicity < th["monotonic_A"]:
            bump(1, "monotonic_moderate")

    outlier_frac = row["outlier_frac"]
    if outlier_frac > th["outlier_B"]:
        bump(2, "many_outliers")
    elif outlier_frac > th["outlier_A"]:
        bump(1, "some_outliers")

    delta_aicc = row["delta_aicc"]
    if not np.isnan(delta_aicc) and delta_aicc <= th["curvature_aicc"]:
        bump(1, "curvature")
    curv_c = th.get("curvature_aicc_C", None)
    if curv_c is not None and not np.isnan(delta_aicc) and delta_aicc <= curv_c:
        bump(2, "strong_curvature")

    slope_diff = row["slope_diff_pct"]
    if slope_diff > th["slope_diff_B"]:
        bump(2, "slope_disagreement")
    elif slope_diff > th["slope_diff_A"]:
        bump(1, "slope_disagreement")

    b_count_c = th.get("b_count_C", None)
    if b_count_c is not None and b_count >= b_count_c:
        bump(2, f"many_moderate_issues:{b_count}")

    if enforce_hard_limits:
        if abs(row["flux_slope"]) > HARD_LIMITS["max_abs_slope"]:
            bump(2, "extreme_slope")
        if abs(row.get("flux_absolute", np.nan)) > HARD_LIMITS["max_abs_flux"]:
            bump(2, "extreme_flux")
        if row.get("co2_range", 0) > HARD_LIMITS["max_co2_range"]:
            bump(1, "large_co2_range")

    raw_flag = int(raw_flag) if pd.notnull(raw_flag) else 0
    raw_flag = min(raw_flag, 2)
    if raw_flag > 0:
        reasons.append(f"sensor_flag_{raw_flag}")

    combined = max(model_qc, raw_flag)
    return model_qc, combined, ";".join(reasons)


# ------------------------------------------------------------------------------
# Temporal Coherence & Day-Level Quality Scoring
# (shared between notebook 032 and the dashboard)
# ------------------------------------------------------------------------------


def compute_temporal_coherence(
    flux_df: pd.DataFrame,
    max_slope_ratio: float = 3.0,
    transition_hours: tuple = (6, 7, 8, 17, 18, 19),  # hour 8: VPD-delayed stomatal opening
    hourly_cv_threshold: float = 0.50,
) -> pd.DataFrame:
    """Flag cycles that are implausible given their immediate neighbours.

    Two complementary checks are applied:

    1. **Temporal coherence (per-cycle)**: compares each passing cycle's
       slope to the previous passing cycle's slope *on the same day*.
       A cycle is flagged if:

       - It has the **same sign** as its predecessor but the magnitude
         ratio exceeds ``max_slope_ratio`` (sudden unexplained jump).
       - It has the **opposite sign** to its predecessor during mid-day
         hours (08:00–16:00) and the absolute slope is > 0.005 ppm s⁻¹
         (not a genuine zero-crossing — transition hours like dawn/dusk
         are exempt because photosynthesis can genuinely flip sign there).

    2. **Hourly CV flag**: within each (date, hour) group of passing cycles,
       the coefficient of variation CV = std(slopes) / mean(|slopes|) is
       computed.  If CV > ``hourly_cv_threshold``, all cycles in that group
       receive ``hourly_cv_flag = 1`` (erratic within-hour scatter, likely
       indicating unstable ambient conditions or chamber leakage).

    Only cycles with ``flux_qc <= 1`` are checked; QC-2 cycles are skipped
    (they carry ``temporal_coherence_flag = 0`` by default and should be
    excluded before further analysis anyway).

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level DataFrame produced by
        :func:`~palmwtc.flux.chamber.calculate_flux_cycles`.  Must contain:

        - ``flux_datetime`` or ``flux_date`` — datetime of cycle start.
        - ``flux_slope`` or ``co2_slope``    — CO₂ slope in ppm s⁻¹.
        - ``flux_qc``                        — rule-based QC flag (0, 1, 2).

    max_slope_ratio : float
        Maximum |slope_i / slope_prev| ratio within a same-sign pair before
        the cycle is flagged as a temporal jump (default 3.0).
    transition_hours : tuple of int
        Hours of day where sign flips are physically expected (dawn and dusk).
        Cycles at these hours are exempt from the sign-flip check.
        Default ``(6, 7, 8, 17, 18, 19)``; hour 8 is included because
        VPD-delayed stomatal opening can shift the transition past 08:00
        in humid tropical conditions.
    hourly_cv_threshold : float
        CV threshold for the within-hour check (default 0.50 = 50%).
        CV > 0.50 means the within-hour scatter exceeds half the mean
        absolute flux, which is unusual for stable chamber measurements.

    Returns
    -------
    pd.DataFrame
        Copy of ``flux_df`` with two additional columns:

        ``temporal_coherence_flag`` : int (0 or 1)
            1 if the cycle was flagged by the pairwise slope-jump or
            sign-flip check.
        ``hourly_cv_flag`` : int (0 or 1)
            1 if the cycle belongs to a (date, hour) group with CV above
            ``hourly_cv_threshold``.

    Notes
    -----
    The function accepts both ``flux_datetime`` and ``flux_date`` as the
    datetime column name, and both ``flux_slope`` and ``co2_slope`` as the
    slope column name, to be compatible with both the notebook-produced
    DataFrame and the digital-twin CSV format.

    See Also
    --------
    compute_day_scores : Uses the flags produced here to filter clean cycles.

    Examples
    --------
    >>> import pandas as pd  # doctest: +SKIP
    >>> # Full example requires a multi-row flux DataFrame from
    >>> # calculate_flux_cycles(); see tutorial notebook 032.
    """
    df = flux_df.copy()

    dt_col = "flux_datetime" if "flux_datetime" in df.columns else "flux_date"
    df["_dt"] = pd.to_datetime(df[dt_col], errors="coerce")
    df["_date"] = df["_dt"].dt.date
    df["_hour"] = df["_dt"].dt.hour

    slope_col = "flux_slope" if "flux_slope" in df.columns else "co2_slope"

    df = df.sort_values("_dt").reset_index(drop=True)
    df["_prev_slope"] = df[slope_col].shift(1)
    df["_prev_date"] = df["_date"].shift(1)
    df["_prev_hour"] = df["_hour"].shift(1)
    df["_prev_qc"] = df["flux_qc"].shift(1)

    tc_flags = [0] * len(df)
    for i, row in df.iterrows():
        if row["flux_qc"] > 1 or row["_prev_qc"] > 1:
            continue
        if row["_date"] != row["_prev_date"]:
            continue
        prev_slope = row["_prev_slope"]
        cur_slope = row[slope_col]
        if pd.isna(prev_slope) or prev_slope == 0:
            continue

        hour = int(row["_hour"]) if pd.notna(row["_hour"]) else -1
        prev_hour = int(row["_prev_hour"]) if pd.notna(row["_prev_hour"]) else -1

        if hour in transition_hours or prev_hour in transition_hours:
            continue

        same_sign = (cur_slope * prev_slope) > 0
        ratio = abs(cur_slope / prev_slope)

        if same_sign and ratio > max_slope_ratio:
            tc_flags[i] = 1

        if not same_sign and 8 <= hour <= 16:
            if abs(cur_slope) > 0.005:
                tc_flags[i] = 1

    df["temporal_coherence_flag"] = tc_flags

    def _hourly_cv(slopes):
        mean_abs = slopes.abs().mean()
        if mean_abs < 1e-9:
            return pd.Series(0, index=slopes.index)
        cv = slopes.std() / mean_abs
        return pd.Series((1 if cv > hourly_cv_threshold else 0), index=slopes.index)

    df["hourly_cv_flag"] = (
        df.groupby(["_date", "_hour"])[slope_col].transform(_hourly_cv).fillna(0).astype(int)
    )

    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    return df


def score_day_quality(
    day_df: pd.DataFrame,
    daytime_hours: range = range(7, 19),
) -> dict | None:
    """Compute a 0–1 composite quality score for one day of flux data.

    This function is called once per (date, chamber) group by
    :func:`compute_day_scores` after filtering to passing cycles only.
    The score summarises five independent aspects of day quality:

    +----------+-------------------------------------------+--------+
    | Weight   | Criterion                                 | Max    |
    +==========+===========================================+========+
    | 0.30     | Temporal coverage                         | 1.0    |
    +----------+-------------------------------------------+--------+
    | 0.30     | Median R² of passing cycles               | 1.0    |
    +----------+-------------------------------------------+--------+
    | 0.20     | Sign consistency (fraction negative slope)| 1.0    |
    +----------+-------------------------------------------+--------+
    | 0.10     | Diurnal shape (peak uptake hour 09–14 h)  | 1.0    |
    +----------+-------------------------------------------+--------+
    | 0.10     | NRMSE quality (1 − mean_nrmse / 0.20)    | 1.0    |
    +----------+-------------------------------------------+--------+

    **Temporal coverage** is the number of unique hours covered divided by
    11 (the nominal 07:00–17:00 daytime window), capped at 1.0.

    **R² quality** is the median R² over all passing daytime cycles.
    This is more robust than the mean because a few outlier cycles with
    low R² do not dominate the score.

    **Sign consistency** is the fraction of cycles with a negative slope
    (net CO₂ uptake).  A value near 1.0 means the canopy was photosynthesising
    consistently throughout the day; near 0 means net respiration dominated.

    **Diurnal shape** scores 1.0 if the hour with the strongest median
    uptake (most negative slope) falls between 09:00 and 14:00, which is
    the physically expected peak photosynthesis window for oil palm.
    Otherwise 0.5.

    **NRMSE quality** penalises days with noisier cycles:
    ``max(0, 1 − mean_nrmse / 0.20)``.  A mean NRMSE of 0.20 or higher
    gives a zero contribution from this component.

    Parameters
    ----------
    day_df : pd.DataFrame
        Subset of the flux DataFrame for **one date and one chamber**, already
        filtered to passing cycles (``flux_qc <= 1`` and
        ``temporal_coherence_flag == 0``).  Must contain the columns
        ``flux_datetime`` or ``flux_date``, ``flux_slope`` or ``co2_slope``,
        ``r2`` or ``co2_r2``, and ``nrmse`` or ``co2_nrmse``.
    daytime_hours : range
        Hours treated as daytime (default ``range(7, 19)`` = 07:00–18:00
        inclusive).

    Returns
    -------
    dict or None
        Returns ``None`` if the day has fewer than 3 daytime cycles or fewer
        than 4 hours covered (insufficient data to score reliably).

        Otherwise a dict with keys:

        ``n_cycles_daytime`` : int
            Number of passing daytime cycles.
        ``n_hours_covered`` : int
            Number of distinct hours with at least one passing cycle.
        ``coverage_score`` : float [0, 1]
        ``quality_score`` : float [0, 1]   — median R².
        ``frac_negative`` : float [0, 1]   — fraction of cycles with negative slope.
        ``shape_score`` : float {0.5, 1.0} — diurnal shape.
        ``nrmse_score`` : float [0, 1]
        ``day_score`` : float [0, 1]       — weighted composite.

    See Also
    --------
    compute_day_scores : Applies this function across all days and chambers.

    Examples
    --------
    >>> import pandas as pd  # doctest: +SKIP
    >>> # Requires a filtered single-day flux DataFrame from
    >>> # calculate_flux_cycles(); see tutorial notebook 032.
    """
    dt_col = "flux_datetime" if "flux_datetime" in day_df.columns else "flux_date"
    day_df = day_df.copy()
    day_df["_hour"] = pd.to_datetime(day_df[dt_col], errors="coerce").dt.hour
    daytime = day_df[day_df["_hour"].isin(daytime_hours)]

    n_cycles_day = len(daytime)
    n_hours = daytime["_hour"].nunique()
    if n_cycles_day < 3 or n_hours < 4:
        return None

    slope_col = "flux_slope" if "flux_slope" in daytime.columns else "co2_slope"
    r2_col = "r2" if "r2" in daytime.columns else "co2_r2"
    nrmse_col = "nrmse" if "nrmse" in daytime.columns else "co2_nrmse"

    n_target_hours = 11
    coverage_score = min(n_hours / n_target_hours, 1.0)

    r2_vals = pd.to_numeric(daytime[r2_col], errors="coerce").dropna()
    quality_score = float(r2_vals.median()) if len(r2_vals) > 0 else 0.0

    slopes = pd.to_numeric(daytime[slope_col], errors="coerce").dropna()
    frac_negative = float((slopes < 0).mean()) if len(slopes) > 0 else 0.0

    hourly_med = daytime.groupby("_hour")[slope_col].median()
    if len(hourly_med) >= 3:
        peak_uptake_hour = int(hourly_med.idxmin())
        shape_score = 1.0 if 9 <= peak_uptake_hour <= 14 else 0.5
    else:
        shape_score = 0.5

    nrmse_vals = pd.to_numeric(daytime[nrmse_col], errors="coerce").dropna()
    mean_nrmse = float(nrmse_vals.mean()) if len(nrmse_vals) > 0 else 0.20
    nrmse_score = max(0.0, 1.0 - mean_nrmse / 0.20)

    day_score = (
        0.30 * coverage_score
        + 0.30 * quality_score
        + 0.20 * frac_negative
        + 0.10 * shape_score
        + 0.10 * nrmse_score
    )

    return {
        "n_cycles_daytime": n_cycles_day,
        "n_hours_covered": n_hours,
        "coverage_score": round(coverage_score, 4),
        "quality_score": round(quality_score, 4),
        "frac_negative": round(frac_negative, 4),
        "shape_score": round(shape_score, 4),
        "nrmse_score": round(nrmse_score, 4),
        "day_score": round(day_score, 4),
    }


def compute_day_scores(
    flux_df: pd.DataFrame,
    day_score_threshold: float = 0.60,
) -> pd.DataFrame:
    """Apply :func:`score_day_quality` across all days and chambers and merge back.

    This is the top-level aggregation step that runs after per-cycle scoring
    (:func:`score_cycle`) and temporal coherence flagging
    (:func:`compute_temporal_coherence`).  It:

    1. Extracts the date from ``flux_datetime`` or ``flux_date``.
    2. Filters to clean cycles (``flux_qc <= 1``, ``temporal_coherence_flag == 0``,
       ``hourly_cv_flag == 0``).
    3. Groups by (date, chamber) and calls :func:`score_day_quality`.
    4. Left-merges the three summary columns (``day_score``,
       ``n_cycles_daytime``, ``n_hours_covered``) back onto the full
       DataFrame so every row carries its day's score.

    Days that do not meet :func:`score_day_quality`'s eligibility criteria
    (< 3 cycles or < 4 hours) receive ``day_score = 0.0``.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Full cycle-level DataFrame as produced by
        :func:`~palmwtc.flux.chamber.calculate_flux_cycles`.  Must contain:

        - ``flux_qc`` — rule-based QC flag (0, 1, 2).
        - ``temporal_coherence_flag`` — from :func:`compute_temporal_coherence`.
        - ``hourly_cv_flag`` — from :func:`compute_temporal_coherence`.
        - ``flux_datetime`` or ``flux_date`` — cycle timestamp.
        - ``Source_Chamber`` — chamber identifier (optional; if present,
          scores are computed separately per chamber).

    day_score_threshold : float
        Informational threshold for downstream summary statistics (default 0.60).
        Days below this value are considered low-quality in summary reports.
        This parameter does **not** filter any rows.

    Returns
    -------
    pd.DataFrame
        Copy of ``flux_df`` with three new columns merged in:

        ``day_score`` : float
            Composite 0–1 quality score for the cycle's date and chamber.
            0.0 for days with insufficient data.
        ``n_cycles_daytime`` : int
            Number of passing daytime cycles on that date.
        ``n_hours_covered`` : int
            Number of distinct daytime hours with passing cycles.

    See Also
    --------
    score_day_quality : Scoring logic for a single (date, chamber) group.
    compute_temporal_coherence : Must be called before this function.

    Examples
    --------
    >>> import pandas as pd  # doctest: +SKIP
    >>> # Requires a full flux DataFrame from calculate_flux_cycles() and
    >>> # compute_temporal_coherence(); see tutorial notebook 032.
    """
    dt_col = "flux_datetime" if "flux_datetime" in flux_df.columns else "flux_date"
    flux_df = flux_df.copy()
    flux_df["_date_only"] = pd.to_datetime(flux_df[dt_col], errors="coerce").dt.date

    tc_col = "temporal_coherence_flag"
    cv_col = "hourly_cv_flag"
    if tc_col not in flux_df.columns:
        flux_df[tc_col] = 0
    if cv_col not in flux_df.columns:
        flux_df[cv_col] = 0

    clean_df = flux_df[
        (flux_df["flux_qc"] <= 1) & (flux_df[tc_col] == 0) & (flux_df[cv_col] == 0)
    ].copy()

    group_cols = ["_date_only"]
    if "Source_Chamber" in clean_df.columns:
        group_cols.append("Source_Chamber")

    day_scores = []
    for keys, group in clean_df.groupby(group_cols):
        score_dict = score_day_quality(group)
        if score_dict is None:
            continue
        row = {"_date_only": keys[0] if isinstance(keys, tuple) else keys}
        if len(group_cols) > 1:
            row["Source_Chamber"] = keys[1]
        row.update(score_dict)
        day_scores.append(row)

    if day_scores:
        day_score_df = pd.DataFrame(day_scores)
        merge_keys = ["_date_only"]
        if "Source_Chamber" in flux_df.columns:
            merge_keys.append("Source_Chamber")
        flux_df = flux_df.merge(
            day_score_df[merge_keys + ["day_score", "n_cycles_daytime", "n_hours_covered"]],
            on=merge_keys,
            how="left",
        )
        flux_df["day_score"] = flux_df["day_score"].fillna(0.0)
    else:
        flux_df["day_score"] = 0.0
        flux_df["n_cycles_daytime"] = 0
        flux_df["n_hours_covered"] = 0

    flux_df = flux_df.drop(columns=["_date_only"], errors="ignore")
    return flux_df


# ------------------------------------------------------------------------------
# ML Anomaly Detection
# ------------------------------------------------------------------------------

# Column name aliases: in-notebook names → digital twin CSV names
_ML_FEATURE_ALIASES = {
    "r2": "co2_r2",
    "nrmse": "co2_nrmse",
    "snr": "co2_snr",
    "monotonicity": "co2_monotonic_frac",
    "outlier_frac": "co2_outlier_frac",
}


def compute_ml_anomaly_flags(
    df: pd.DataFrame,
    features: list[str] | None = None,
    contamination: float = 0.05,
    n_if_estimators: int = 200,
    max_if_samples: int = 10_000,
    max_mcd_fit_samples: int = 5_000,
    mcd_support_fraction: float = 0.75,
    mcd_threshold_percentile: float = 95.0,
    train_on_passing_only: bool = True,
    passing_qc_col: str = "flux_qc",
    passing_qc_max: int = 1,
    combination_mode: str = "AND",
    random_state: int = 42,
    n_jobs: int = -1,
) -> pd.DataFrame:
    """Add ML-based anomaly flags to a cycle-level flux DataFrame.

    Trains two unsupervised anomaly detectors on cycles that passed the
    rule-based QC (``flux_qc <= passing_qc_max``), then scores **all** cycles.
    The ML flag is complementary to the A/B/C tier system: it detects
    multivariate anomalies — unusual *combinations* of quality metrics —
    that the individual threshold checks in :func:`score_cycle` may miss.

    Because the models train only on passing cycles, the "normal" region of
    feature space is defined by cycles the rule-based system already trusts.
    Cycles flagged by ML but not by the rule-based system represent edge cases
    that are individually plausible on each metric but collectively unusual.

    Models
    ------
    Isolation Forest [1]_ (``sklearn.ensemble.IsolationForest``)
        Random-subspace tree ensemble.  Anomalies are isolated with fewer
        splits than inliers.  O(n log n) fit and score; ``max_samples`` is
        capped at ``max_if_samples`` so memory is bounded even at 1 M rows.
        On machines with a CUDA GPU, :func:`~palmwtc.hardware.gpu.get_isolation_forest`
        substitutes cuML's GPU-accelerated implementation automatically.

    Robust Covariance / MCD (``sklearn.covariance.MinCovDet``)
        Minimum Covariance Determinant estimator [2]_ — a robust alternative
        to the standard covariance matrix that is resistant to outliers in the
        training data.  Fit on a random subsample of at most
        ``max_mcd_fit_samples`` rows.  Mahalanobis distances for **all** rows
        are computed via a batched matrix multiply — O(n × p²), not O(n²) —
        safe at 1 M rows.  The anomaly threshold is the
        ``mcd_threshold_percentile``-th percentile of training-set distances
        (empirical calibration, avoiding the multivariate-normality assumption
        of chi-squared thresholding).

    Parameters
    ----------
    df : pd.DataFrame
        Cycle-level DataFrame as produced by
        :func:`~palmwtc.flux.chamber.calculate_flux_cycles` and scored by
        :func:`score_cycle`.
    features : list of str or None
        Feature column names to use.  If None, :data:`DEFAULT_ML_FEATURES` is
        used.  Column name aliases are resolved automatically (e.g. ``r2`` →
        ``co2_r2``).  At least 3 resolvable features must be present; otherwise
        a ``ValueError`` is raised.
    contamination : float
        Expected fraction of anomalies for Isolation Forest (default 0.05 = 5%).
    n_if_estimators : int
        Number of trees in the Isolation Forest (default 200).
    max_if_samples : int
        Maximum number of training samples per Isolation Forest tree
        (default 10 000).
    max_mcd_fit_samples : int
        Maximum number of rows used to fit the MinCovDet estimator
        (default 5 000).
    mcd_support_fraction : float
        Fraction of observations used to compute the robust MCD scatter
        estimate (default 0.75 — 75% of the fit sample).
    mcd_threshold_percentile : float
        Percentile of training-set Mahalanobis distances used as the MCD
        anomaly threshold (default 95.0).
    train_on_passing_only : bool
        If True (default), only cycles with ``flux_qc <= passing_qc_max``
        are used to train the models.  This ensures the models learn from
        verified good measurements.
    passing_qc_col : str
        Name of the rule-based QC column (default ``'flux_qc'``).
    passing_qc_max : int
        Maximum QC value for training inclusion (default 1 = tier A and B).
    combination_mode : str
        How to combine the two detector outputs:

        ``'AND'`` (default)
            Both detectors must agree.  Flags ~3% of A/B cycles.
        ``'OR'``
            Either detector alone triggers the flag.  Flags ~7% of A/B cycles.
    random_state : int
        Random seed for reproducibility (default 42).
    n_jobs : int
        Number of parallel workers for Isolation Forest fitting (default -1 =
        all available CPUs).

    Returns
    -------
    pd.DataFrame
        Copy of ``df`` with three new columns:

        ``ml_if_score`` : float
            Raw Isolation Forest anomaly score (more negative = more anomalous).
        ``ml_mcd_dist`` : float
            Mahalanobis distance from the robust MCD centroid (larger = more
            anomalous).
        ``ml_anomaly_flag`` : int
            Combined binary flag: 1 = anomalous, 0 = OK.

    Raises
    ------
    ImportError
        If scikit-learn is not installed (it is an optional dependency).
    ValueError
        If fewer than 3 feature columns can be resolved, or if the training
        set has too few rows.

    Notes
    -----
    The ``_completeness_ratio`` feature (``n_points_used / n_points_total``)
    is derived automatically if both columns are present and is added to the
    feature matrix as an extra dimension.  It is removed from the output
    DataFrame before returning.

    References
    ----------
    .. [1] Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation forest.
           *2008 Eighth IEEE International Conference on Data Mining*, 413–422.
           https://doi.org/10.1109/ICDM.2008.17
    .. [2] Rousseeuw, P. J., & Driessen, K. V. (1999). A fast algorithm for
           the minimum covariance determinant estimator. *Technometrics*,
           41(3), 212–223. https://doi.org/10.1080/00401706.1999.10485670

    See Also
    --------
    score_cycle : Rule-based QC that this function complements.
    DEFAULT_ML_FEATURES : Default feature list (``flux_slope`` is excluded).

    Examples
    --------
    >>> import pandas as pd  # doctest: +SKIP
    >>> # Requires a scored flux DataFrame from calculate_flux_cycles() and
    >>> # score_cycle(); see tutorial notebook 032 for a full walkthrough.
    """
    if not _SKLEARN_AVAILABLE:
        raise ImportError(
            "scikit-learn is required for compute_ml_anomaly_flags(). "
            "Install it with: pip install scikit-learn"
        )

    # --- 1. Resolve feature names (handle notebook vs digital-twin CSV aliases) ---
    base_features = list(features) if features is not None else list(DEFAULT_ML_FEATURES)

    resolved = []
    for f in base_features:
        if f in df.columns:
            resolved.append(f)
        elif f in _ML_FEATURE_ALIASES and _ML_FEATURE_ALIASES[f] in df.columns:
            resolved.append(_ML_FEATURE_ALIASES[f])
        # silently skip features not present — graceful degradation

    if len(resolved) < 3:
        raise ValueError(
            f"compute_ml_anomaly_flags: fewer than 3 features resolved from "
            f"{base_features}. Check column names in df."
        )

    # --- 2. Derive completeness ratio as an extra feature ---
    df = df.copy()
    _added_completeness = False
    if "n_points_used" in df.columns and "n_points_total" in df.columns:
        df["_completeness_ratio"] = df["n_points_used"] / df["n_points_total"].replace(0, np.nan)
        resolved.append("_completeness_ratio")
        _added_completeness = True

    # --- 3. Build training mask and fill NaN with training-set medians ---
    if train_on_passing_only and passing_qc_col in df.columns:
        train_mask = (df[passing_qc_col] <= passing_qc_max).values
    else:
        train_mask = np.ones(len(df), dtype=bool)

    n_train = train_mask.sum()
    if n_train < max(50, len(resolved) + 1):
        raise ValueError(
            f"compute_ml_anomaly_flags: only {n_train} training rows — too few. "
            f"Check '{passing_qc_col}' column."
        )

    X_train_raw = df.loc[train_mask, resolved]
    feature_medians = X_train_raw.median()
    X_all = df[resolved].fillna(feature_medians).values.astype(float)
    X_train = X_all[train_mask]

    # --- 4. Isolation Forest (GPU-aware: cuML on CUDA workstation, sklearn on M1/CPU) ---
    max_samples_if = min(max_if_samples, n_train)
    iforest = _get_isolation_forest(
        n_estimators=n_if_estimators,
        max_samples=max_samples_if,
        contamination=contamination,
        max_features=1.0,
        n_jobs=n_jobs,
        random_state=random_state,
    )
    iforest.fit(X_train)

    if_score_all = iforest.score_samples(X_all)  # more negative = more anomalous
    if_flag_all = (iforest.predict(X_all) == -1).astype(int)  # 1 = anomaly

    # --- 5. Robust Covariance (MCD) — fit on subsample, score all in batches ---
    rng = np.random.default_rng(random_state)
    n_mcd_fit = min(max_mcd_fit_samples, n_train)
    sub_idx = rng.choice(n_train, size=n_mcd_fit, replace=False)
    X_mcd_fit = X_train[sub_idx]

    mcd = _MinCovDet(support_fraction=mcd_support_fraction, random_state=random_state)
    mcd.fit(X_mcd_fit)

    # Calibrate threshold empirically from training distances
    diff_train = X_train - mcd.location_
    mcd_dist_train = np.sqrt(np.einsum("ij,jk,ik->i", diff_train, mcd.precision_, diff_train))
    mcd_threshold = np.percentile(mcd_dist_train, mcd_threshold_percentile)

    # Score all rows in 100,000-row batches — O(n * p²), memory-safe at 1 M rows
    BATCH = 100_000
    n_total = X_all.shape[0]
    mcd_dist_all = np.empty(n_total, dtype=np.float64)
    for start in range(0, n_total, BATCH):
        end = min(start + BATCH, n_total)
        diff_b = X_all[start:end] - mcd.location_
        mcd_dist_all[start:end] = np.sqrt(np.einsum("ij,jk,ik->i", diff_b, mcd.precision_, diff_b))

    mcd_flag_all = (mcd_dist_all > mcd_threshold).astype(int)

    # --- 6. Combine flags ---
    mode = combination_mode.upper()
    if mode == "AND":
        ml_anomaly_flag = if_flag_all & mcd_flag_all
    elif mode == "OR":
        ml_anomaly_flag = if_flag_all | mcd_flag_all
    else:
        raise ValueError(f"combination_mode must be 'AND' or 'OR', got '{combination_mode}'")

    # --- 7. Assign output columns ---
    df["ml_if_score"] = if_score_all
    df["ml_mcd_dist"] = mcd_dist_all
    df["ml_anomaly_flag"] = ml_anomaly_flag.astype(int)

    # Remove temporary derived column
    if _added_completeness:
        df = df.drop(columns=["_completeness_ratio"])

    return df
