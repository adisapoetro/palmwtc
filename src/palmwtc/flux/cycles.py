# ruff: noqa: RUF002, RUF005, RUF046, RUF059, SIM102, SIM108, SIM910, F841
"""Cycle-level flux QC primitives ported from ``flux_chamber/src/flux_qc_fast.py``.

Behaviour-preserving single-file port. Only ``import`` statements changed:

- ``from src.flux_analysis import calculate_absolute_flux``
  → ``from palmwtc.flux.absolute import calculate_absolute_flux`` (optional —
    silently degrades when the sibling module isn't on disk yet, exactly like
    the original module did when ``flux_analysis`` was missing)
- ``from src.gpu_utils import get_isolation_forest, DEVICE``
  → ``from palmwtc.hardware.gpu import get_isolation_forest, DEVICE``

Function signatures, bodies, constants, and numerical behaviour are identical
to the source. Joblib parallelism lives in the *callers* (notebooks 030/032
and ``dashboard/core/flux_qc_runner.py``); this module only exposes
``_evaluate_cycle_wrapper`` which is the picklable callable they hand to a
multiprocessing pool. No backend selection happens here — preserved as-is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import linregress, theilslopes

# Optional: absolute-flux conversion. The original used a try/except that
# tolerated the import failing; we keep that exact contract because Batch 2
# may have not landed ``palmwtc.flux.absolute`` yet when this module is first
# imported.
try:
    from palmwtc.flux.absolute import calculate_absolute_flux
except ImportError:
    calculate_absolute_flux = None

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
START_CUTOFF_SEC = 50
START_SEARCH_SEC = 60
MIN_POINTS = 8
MIN_DURATION_SEC = 60
OUTLIER_Z = 3.5
MAX_OUTLIER_REFIT_FRAC = 0.2
NOISE_EPS_PPM = 0.5
USE_MULTIPROCESSING = True

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

HARD_LIMITS = {
    "max_abs_slope": 10.0,
    "max_abs_flux": 100.0,
    "max_co2_range": 2000.0,
}

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


def identify_cycles(data, time_col="TIMESTAMP", gap_sec=CYCLE_GAP_SEC):
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


def detect_bimodal_cycle(values, bin_width=5.0, min_gap_bins=4, min_side_points=3):
    """Detect bimodal CO2/H2O distribution within a single cycle.

    Bimodality here means two clean clusters separated by an empty histogram
    region — the signature of a measurement contamination event (e.g. a stuck
    LI-COR reference cell, mux'd source bleeding into the chamber stream, or
    sensor swap mid-cycle). It is NOT the same as "wide spread"; a noisy but
    unimodal cycle will not trigger.

    Parameters
    ----------
    values : array-like
        Raw concentration values for one cycle (NaNs ignored).
    bin_width : float
        Histogram bin width in the same units as ``values`` (default: 5 ppm).
    min_gap_bins : int
        Minimum run of consecutive empty bins between two non-empty regions
        required to call a cycle bimodal (default: 4 bins → 20 ppm gap).
    min_side_points : int
        Minimum point count on each side of the gap (default: 3).

    Returns
    -------
    dict with keys:
        is_bimodal : bool
        gap_ppm    : float  (0.0 if not bimodal)
        lower_mean : float  (NaN if not bimodal)
        upper_mean : float  (NaN if not bimodal)
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

    if calculate_absolute_flux is not None:
        row["flux_absolute"] = float(calculate_absolute_flux(pd.Series(row)))
    else:
        row["flux_absolute"] = np.nan

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
    row,
    raw_flag,
    thresholds,
    enforce_hard_limits=False,
    snr_field="snr",
    is_nighttime=False,
    nighttime_thresholds=None,
):
    """Score a single flux cycle and return (model_qc, combined_qc, reasons_str).

    Parameters
    ----------
    row : dict-like
        Cycle metrics (flux_slope, r2, nrmse, snr, monotonicity, etc.)
    raw_flag : int
        Raw hardware sensor QC flag (0=good, 1=suspect, 2=bad).
    thresholds : dict
        Daytime QC thresholds (keys: r2_A/B, nrmse_A/B, snr_A/B, etc.)
    enforce_hard_limits : bool
        Apply absolute physical limits (extreme slope/flux/range).
    snr_field : str
        Which SNR column to use ('snr' or 'snr_noise').
    is_nighttime : bool
        When True, use nighttime_thresholds if provided.
    nighttime_thresholds : dict or None
        Relaxed thresholds for nighttime (Global_Radiation < 10 W/m²).
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
    flux_df,
    max_slope_ratio=3.0,
    transition_hours=(6, 7, 8, 17, 18, 19),  # hour 8 added: VPD-delayed stomatal opening
    hourly_cv_threshold=0.50,
):
    """Flag cycles that are implausible given their immediate neighbours.

    Produces two binary flags (0=OK, 1=anomalous):
      - temporal_coherence_flag : individual cycle check (jump or sign-flip)
      - hourly_cv_flag          : within-hour coefficient-of-variation check

    Parameters
    ----------
    flux_df : pd.DataFrame
        Must contain flux_datetime (or flux_date), flux_slope (or co2_slope),
        and flux_qc.  Only already-passed (flux_qc <= 1) cycles are checked.
    max_slope_ratio : float
        Max |slope_i / slope_prev| before flagging a same-sign jump.
    transition_hours : tuple of int
        Dawn/dusk hours where sign flips are physically expected (not flagged).
    hourly_cv_threshold : float
        CV(slopes) threshold within an hour; above = erratic measurements.

    Returns
    -------
    pd.DataFrame with columns temporal_coherence_flag, hourly_cv_flag added.
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


def score_day_quality(day_df, daytime_hours=range(7, 19)):
    """Compute a 0-1 composite quality score for one day of flux data.

    Criteria (weighted sum):
      0.30 × temporal coverage   — fraction of 11-h daytime window with data
      0.30 × R² quality          — median R² of passing cycles
      0.20 × sign consistency    — fraction of daytime cycles with negative slope
      0.10 × diurnal shape       — 1.0 if peak uptake hour falls 9–14 h, else 0.5
      0.10 × NRMSE quality       — 1 - (mean_nrmse / 0.20), floored at 0

    Parameters
    ----------
    day_df : pd.DataFrame
        Subset of flux_df for one date + chamber, pre-filtered to QC <= 1
        and temporal_coherence_flag == 0.
    daytime_hours : range
        Hours considered daytime (default 7-18 inclusive).

    Returns
    -------
    dict with day_score and component scores, or None if eligibility fails.
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


def compute_day_scores(flux_df, day_score_threshold=0.60):
    """Apply score_day_quality() across all days and chambers and merge back.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Must contain flux_qc, temporal_coherence_flag, hourly_cv_flag,
        and flux_datetime (or flux_date).
    day_score_threshold : float
        Informational threshold printed in summary (default 0.60).

    Returns
    -------
    pd.DataFrame with day_score, n_cycles_daytime, n_hours_covered added.
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
    df,
    features=None,
    contamination=0.05,
    n_if_estimators=200,
    max_if_samples=10_000,
    max_mcd_fit_samples=5_000,
    mcd_support_fraction=0.75,
    mcd_threshold_percentile=95.0,
    train_on_passing_only=True,
    passing_qc_col="flux_qc",
    passing_qc_max=1,
    combination_mode="AND",
    random_state=42,
    n_jobs=-1,
):
    """Add ML-based anomaly flags to a cycle-level flux DataFrame.

    Trains two unsupervised anomaly detectors on cycles that passed the
    rule-based QC (``flux_qc <= passing_qc_max``), then scores ALL cycles.
    The ML flag is complementary to the existing A/B/C tier system: it finds
    multivariate anomalies among cycles the rule-based system accepted.

    Models
    ------
    Isolation Forest (sklearn.ensemble.IsolationForest)
        Tree-based outlier detector.  O(n log n) fit and score.
        ``max_samples`` is capped at ``max_if_samples`` so memory is bounded
        even at 1 M rows.

    Robust Covariance / MCD (sklearn.covariance.MinCovDet)
        Fit on a random subsample of at most ``max_mcd_fit_samples`` rows.
        Mahalanobis distances for ALL rows are computed via batched matrix
        multiply — O(n * p^2), NOT O(n^2) — safe at 1 M rows.
        The anomaly threshold is the ``mcd_threshold_percentile``-th percentile
        of training-set distances (empirical calibration, avoiding the
        multivariate-normality assumption of chi-squared thresholding).

    Parameters
    ----------
    df : pd.DataFrame
        Cycle-level DataFrame as produced by notebook 032.
    features : list of str or None
        Feature column names to use.  If None, DEFAULT_ML_FEATURES is used.
        Column aliases are resolved automatically (e.g. ``r2`` → ``co2_r2``).
    contamination : float
        Expected fraction of anomalies for IsolationForest (default 0.05).
    n_if_estimators : int
        Number of trees in the Isolation Forest (default 200).
    max_if_samples : int
        Maximum samples per IF tree (default 10 000).
    max_mcd_fit_samples : int
        Maximum rows used to fit MinCovDet (default 5 000).
    mcd_support_fraction : float
        MCD robust scatter fraction (default 0.75).
    mcd_threshold_percentile : float
        Percentile of training Mahalanobis distances used as MCD threshold
        (default 95.0).
    train_on_passing_only : bool
        If True (default), only A/B cycles train the models.
    passing_qc_col : str
        Rule-based QC column name (default ``'flux_qc'``).
    passing_qc_max : int
        Maximum QC value for training inclusion (default 1 = A and B).
    combination_mode : str
        ``'AND'`` (default) — both detectors must agree (~3% of A/B flagged).
        ``'OR'``            — either detector flags (~7% of A/B flagged).
    random_state : int
        Seed for reproducibility (default 42).
    n_jobs : int
        Parallel workers for IsolationForest (default -1 = all CPUs).

    Returns
    -------
    pd.DataFrame
        Input DataFrame with three new columns:
        ``ml_if_score``     float  Raw IF anomaly score (more negative =
                                   more anomalous).
        ``ml_mcd_dist``     float  Mahalanobis distance from robust centroid
                                   (larger = more anomalous).
        ``ml_anomaly_flag`` int    Combined binary flag (1 = anomalous, 0 = OK).
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
