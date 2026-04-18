"""Sensor-drift detection and piecewise drift correction.

Ported verbatim from ``flux_chamber/src/qc_functions.py`` (Phase 2).
Behaviour preservation is the prime directive: function signatures and bodies
match the original to 1e-12.
"""

# ruff: noqa: RUF005, RUF013
# Above ignores cover quirks carried verbatim from the original
# ``flux_chamber/src/qc_functions.py`` to honour the Phase 2 "behaviour
# preservation" rule (``[a] + breakpoints + [b]`` list concatenation;
# implicit ``Optional`` on ``qc_flag_col: str = None``). Bug fixes are
# deferred to a later commit.

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_drift_windstats(
    df: pd.DataFrame, var_name: str, qc_flag_col: str = None, window: int = 48
) -> dict:
    """
    Detect sensor drift using rolling window statistics (Z-score of rolling mean).

    Calculates the deviation of the rolling mean from the global mean, normalized by the global standard deviation.
    High absolute scores indicate potential drift.

    Args:
        df: DataFrame containing the variable.
        var_name: Name of the variable to analyze.
        qc_flag_col: Name of the QC flag column. If provided, non-zero flagged data
                     is excluded from the statistics calculation (treated as NaN).
        window: Size of the rolling window (number of timestamps).

    Returns:
        dict: containing 'scores' DataFrame with the drift score.
    """
    if var_name not in df.columns:
        print(f"Variable {var_name} not found in DataFrame.")
        return None

    series = df[var_name].copy()

    # Exclude flagged data if requested
    if qc_flag_col and qc_flag_col in df.columns:
        # Set flagged values to NaN so they don't contaminate the rolling stats
        series[df[qc_flag_col] != 0] = np.nan

    # Calculate global statistics (on valid data)
    global_mean = series.mean()
    global_std = series.std()

    if global_std == 0 or np.isnan(global_std):
        print(f"Identifying drift for {var_name}: Standard deviation is 0 or NaN.")
        return None

    # Calculate rolling mean
    rolling_mean = series.rolling(window=window, min_periods=max(1, window // 2)).mean()

    # Calculate Drift Score (Z-score of the rolling mean)
    # How many standard deviations is the local mean away from the global mean?
    drift_score = (rolling_mean - global_mean) / global_std

    score_df = pd.DataFrame(drift_score, columns=[f"{var_name}_drift_score"])

    return {"scores": score_df, "metric": "rolling_z_score", "window": window}


def apply_drift_correction(df, var_name, breakpoints, reference_baseline=None):
    """
    Apply piecewise drift correction based on detected breakpoints.

    Corrects each segment by shifting its mean to match the reference baseline
    (or the first segment's mean if no baseline provided).

    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with the variable to correct
    var_name : str
        Name of the variable column
    breakpoints : list
        List of breakpoint timestamps (from detect_breakpoints_ruptures)
    reference_baseline : float, optional
        Expected baseline value. If None, uses first segment's mean.

    Returns:
    --------
    pd.Series
        Corrected values
    pd.Series
        Correction offset applied at each point
    """
    if var_name not in df.columns:
        print(f"  Warning: {var_name} not found in DataFrame")
        return df[var_name].copy() if var_name in df.columns else None, None

    corrected = df[var_name].copy()
    offsets = pd.Series(0.0, index=df.index)

    if not breakpoints or len(breakpoints) == 0:
        print(f"  No breakpoints provided for {var_name}, no correction applied")
        return corrected, offsets

    # Sort breakpoints
    breakpoints = sorted([pd.Timestamp(bp) for bp in breakpoints])

    # Create segment boundaries
    boundaries = [df.index.min()] + breakpoints + [df.index.max()]

    # Calculate first segment mean as reference if no baseline provided
    first_segment = df[(df.index >= boundaries[0]) & (df.index < boundaries[1])]
    first_segment_mean = first_segment[var_name].mean()

    if reference_baseline is None:
        reference_baseline = first_segment_mean
        print(f"  Using first segment mean as reference: {reference_baseline:.2f}")

    print(f"  Applying correction to {var_name} using reference baseline: {reference_baseline:.2f}")
    print(f"  Number of segments: {len(boundaries) - 1}")

    # Apply correction to each segment
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]

        # Get segment mask
        if i == len(boundaries) - 2:  # Last segment
            mask = (df.index >= start) & (df.index <= end)
        else:
            mask = (df.index >= start) & (df.index < end)

        segment_data = df.loc[mask, var_name]
        segment_mean = segment_data.mean()

        # Calculate offset to align segment mean with reference
        offset = segment_mean - reference_baseline

        # Apply correction (subtract offset to bring mean to baseline)
        corrected.loc[mask] = df.loc[mask, var_name] - offset
        offsets.loc[mask] = offset

        print(
            f"    Segment {i + 1}: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}, "
            f"mean={segment_mean:.2f}, offset={offset:.2f}"
        )

    return corrected, offsets
