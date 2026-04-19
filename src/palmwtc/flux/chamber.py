"""
Chamber CO2 & H2O Flux Calculation Pipeline

Reusable functions for:
  - WPL (Webb-Pearman-Leuning) dilution correction on CO2
  - Cycle-level CO2 flux calculation with robust regression and QC scoring
  - Cycle-level H2O flux (transpiration) calculation with QC scoring
  - Chamber data preparation with QC flag filtering
  - Tree biophysical data loading and volume interpolation

Usage from any notebook::

    from palmwtc.flux.chamber import (
        prepare_chamber_data,
        calculate_flux_cycles,
        calculate_h2o_flux_cycles,
        summarize_wpl_correction,
        build_cycle_wpl_metrics,
    )

All functions accept explicit parameters rather than relying on global
constants.  Use :data:`DEFAULT_CONFIG` as a starting point and override
what you need::

    cfg = {**DEFAULT_CONFIG, "min_points": 10, "cycle_gap_sec": 240}
    flux_df = calculate_flux_cycles(chamber_df, "Chamber 1", **cfg)
"""

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

try:
    from palmwtc.flux.absolute import calculate_absolute_flux, calculate_h2o_absolute_flux
except Exception:
    calculate_absolute_flux = None
    calculate_h2o_absolute_flux = None

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

# Relaxed thresholds for nighttime measurements (Global_Radiation < 10 W/m²).
# Respiration signals are smaller; strict daytime criteria cause mass rejection.
NIGHTTIME_CO2_QC_THRESHOLDS = NIGHTTIME_QC_THRESHOLDS

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

DEFAULT_WPL_QC_THRESHOLDS = {
    "valid_frac_A": 0.98,
    "valid_frac_B": 0.95,
    "rel_change_p95_A": 0.04,
    "rel_change_p95_B": 0.07,
    "factor_max_B": 1.08,
}


# ---------------------------------------------------------------------------
# WPL Correction
# ---------------------------------------------------------------------------


def apply_wpl_correction(co2_wet, h2o_mmol_mol):
    """
    Convert wet CO2 (ppm) to dry CO2 using WPL dilution correction.

    CO2_dry = CO2_wet * (1 + chi_w / (1000 - chi_w))

    Parameters
    ----------
    co2_wet : array-like
        Wet CO2 in ppm.
    h2o_mmol_mol : array-like
        Water vapour mole fraction in mmol/mol.

    Returns
    -------
    co2_dry : pd.Series
    factor : pd.Series
    valid : pd.Series of bool
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
    accepted_co2_qc_flags=None,
    accepted_h2o_qc_flags=None,
    prefer_corrected_h2o=True,
    require_h2o_for_wpl=True,
    apply_wpl=True,
    h2o_valid_range=(0.0, 60.0),
    max_abs_wpl_rel_change=0.12,
    **kwargs,
):
    """
    Prepare per-chamber data with WPL correction and QC flag filtering.

    Parameters
    ----------
    data : pd.DataFrame
        Full QC-flagged dataset with columns like CO2_C1, H2O_C1, etc.
    chamber_suffix : str
        ``'C1'`` or ``'C2'``.
    accepted_co2_qc_flags : list of int or None
        Keep only rows whose CO2 QC flag is in this list.  ``None`` = keep all.
    accepted_h2o_qc_flags : list of int or None
        Same for H2O.
    prefer_corrected_h2o : bool
        Prefer ``H2O_{suffix}_corrected`` over raw ``H2O_{suffix}``.
    require_h2o_for_wpl : bool
        Raise if no H2O column found.
    apply_wpl : bool
        Apply WPL correction from CO2/H2O inputs. If ``False``, keep CO2 as
        measured input (``CO2_raw``) and skip WPL-based flag updates.
    h2o_valid_range : tuple (lo, hi)
        Physical bounds for H2O (mmol/mol).
    max_abs_wpl_rel_change : float
        Cap for plausible WPL relative correction.

    Returns
    -------
    pd.DataFrame
        Columns include TIMESTAMP, CO2 (dry or fallback), CO2_raw, H2O,
        Temp, Flag, wpl_factor, wpl_delta_ppm, wpl_rel_change, etc.
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
    """Return summary dict of WPL correction statistics."""
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
    """Aggregate WPL correction metrics per cycle."""
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
    """
    Identify measurement cycles and calculate CO2 flux for each cycle.

    Uses robust window selection, outlier filtering, and QC scoring from
    ``palmwtc.flux.cycles``.

    Parameters
    ----------
    chamber_df : pd.DataFrame
        Output of :func:`prepare_chamber_data`.
    chamber_name : str
        Label such as ``'Chamber 1'``.
    cycle_gap_sec : int
        Time gap (seconds) that marks a new cycle.
    start_cutoff_sec, start_search_sec, min_points, min_duration_sec,
    outlier_z, max_outlier_refit_frac :
        Regression / window-selection parameters.
    use_multiprocessing : bool
        Use ``multiprocessing.Pool`` for large datasets.
    n_jobs : int or None
        Worker count (defaults to min(8, cpu_count)).

    Returns
    -------
    pd.DataFrame
        One row per cycle with flux_slope, r2, flux_absolute, QC fields, etc.
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
    """
    Calculate H2O flux for a single measurement cycle using Theil-Sen
    regression plus OLS metrics.

    Returns
    -------
    dict or None
        Keys: h2o_slope, h2o_intercept, h2o_r2, h2o_nrmse, h2o_snr,
        h2o_outlier_frac, h2o_monotonic_frac, h2o_n_points, h2o_duration,
        h2o_conc_mean, h2o_conc_range.
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
    """
    Assign QC tier for a single H2O cycle.

    Parameters
    ----------
    h2o_metrics : dict or None
    h2o_qc_thresholds : dict, optional
        Override thresholds. If None, selects day/night defaults.
    is_nighttime : bool
        If True and no explicit thresholds, use NIGHTTIME_H2O_QC_THRESHOLDS.

    Returns
    -------
    tier : int
        0 (A), 1 (B), or 2 (C).
    label : str
    reasons : list of str
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
    """
    Calculate H2O flux for every cycle in *chamber_df*.

    Mirrors :func:`calculate_flux_cycles` but uses Theil-Sen + OLS for
    water vapour with relaxed QC thresholds.

    Parameters
    ----------
    chamber_df : pd.DataFrame
        Output of :func:`prepare_chamber_data` (must contain ``H2O``).
    chamber_name : str
        E.g. ``'Chamber 1'``.
    cycle_gap_sec : int
        Gap in seconds to delimit cycles.
    min_points, min_duration_sec :
        Minimum data requirements per cycle.
    h2o_qc_thresholds : dict or None
        Override :data:`DEFAULT_H2O_QC_THRESHOLDS`.

    Returns
    -------
    pd.DataFrame
        One row per valid cycle with h2o_slope, h2o_r2, h2o_qc, etc.
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
    """
    Load tree biophysical parameters from Vigor_Index_PalmStudio.xlsx.

    Returns
    -------
    pd.DataFrame or None
        Columns: Tree ID, Date, Height_m, Max_Radius_m, Est_Width_m,
        Vigor_Index_m3, Clone.
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
    """
    Interpolate Vigor Index (m^3) for *tree_id* at *target_date*.

    Returns
    -------
    float or None
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
    """
    Apply WPL-specific QC checks and upgrade QC tier if needed.

    Parameters
    ----------
    row : pd.Series
        Flux cycle row with WPL metrics.
    model_qc, flux_qc : int
        Current QC tiers (0=A, 1=B, 2=C).
    reason_text : str
        Semicolon-separated QC reasons so far.
    wpl_qc_thresholds : dict or None
        Override :data:`DEFAULT_WPL_QC_THRESHOLDS`.
    h2o_valid_range : tuple
        (lo, hi) valid H2O range in mmol/mol.

    Returns
    -------
    (model_qc, flux_qc, wpl_qc, reason_text) : tuple
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
    """
    Compute chamber closure confidence score (0-1).

    Based on findings from notebook 070: gap-width experiment.
    Higher radiation + lower R2 -> lower confidence (likely closure issue).
    Lower radiation + lower R2 -> moderate confidence (other cause).

    Parameters
    ----------
    r2 : float or array
        R-squared of linear fit.
    nrmse : float or array
        Normalized RMSE.
    global_radiation : float or array
        Solar radiation (W/m2).
    rad_max : float
        Radiation value for full normalization.

    Returns
    -------
    float or array
        Closure confidence score 0-1.
    """
    rad_norm = np.clip(global_radiation / rad_max, 0, 1)
    rad_norm = np.where(np.isnan(rad_norm), 0.0, rad_norm)

    r2_safe = np.where(np.isnan(r2), 0.0, r2)
    r2_conf = np.clip((r2_safe - 0.25) / (0.94 - 0.25), 0, 1)

    rad_penalty = rad_norm * (1 - r2_conf) * 0.4

    nrmse_safe = np.where(np.isnan(nrmse), 0.0, nrmse)
    nrmse_penalty = rad_norm * np.clip(nrmse_safe / 0.20, 0, 1) * 0.2

    return np.clip(r2_conf - rad_penalty - nrmse_penalty, 0, 1)
