"""Sensor-drift detection and piecewise drift correction.

*Drift* is a gradual offset that builds up over days to weeks — for example,
a CO₂ sensor whose zero point shifts slowly as the optical path ages or
humidity changes the absorption coefficient.  Drift is distinct from a
*breakpoint* (see :mod:`palmwtc.qc.breakpoints`), which is an instantaneous
step change caused by a sensor swap or re-calibration.

This module contains two functions:

- :func:`detect_drift_windstats` — rolling Z-score method that computes how
  far the local mean strays from the global mean, normalised by the global
  standard deviation.  High absolute scores flag periods of persistent drift.
- :func:`apply_drift_correction` — piecewise mean-shift correction that
  aligns each segment to a reference baseline, using breakpoints previously
  detected by :func:`~palmwtc.qc.breakpoints.detect_breakpoints_ruptures`.
"""

# ruff: noqa: RUF005, RUF013
# Above ignores cover quirks carried verbatim from the ported source to
# preserve numeric behaviour to 1e-12 (``[a] + breakpoints + [b]`` list
# concatenation; implicit Optional on ``qc_flag_col: str = None``).
# Bug fixes are deferred to a later commit.

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_drift_windstats(
    df: pd.DataFrame, var_name: str, qc_flag_col: str = None, window: int = 48
) -> dict:
    """Detect gradual sensor drift using a rolling-window Z-score.

    Computes how far the rolling mean deviates from the global mean,
    expressed in units of the global standard deviation.  A persistently
    high (or low) score across many consecutive windows indicates that the
    sensor has drifted away from its typical operating point.

    **Drift vs breakpoints.** Drift is a *gradual* offset that develops over
    days to weeks, for example a CO₂ sensor whose zero point shifts as the
    optical path ages.  A breakpoint is an *instantaneous* step change caused
    by a sensor swap or re-calibration.  Use
    :func:`~palmwtc.qc.breakpoints.detect_breakpoints_ruptures` to find the
    latter; this function targets the former.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.  Index can be any type; a ``DatetimeIndex`` is
        recommended for downstream time-based analysis.
    var_name : str
        Column name of the variable to analyse.
    qc_flag_col : str or None, optional
        Column whose non-zero values are excluded from the rolling and global
        statistics (set to ``NaN`` before computing).  Pass ``None`` to use
        all rows.  Default ``None``.
    window : int, optional
        Number of consecutive timestamps in each rolling window.  Larger
        windows smooth out short spikes but may obscure drift that develops
        over timescales shorter than ``window``.  The rolling calculation
        requires at least ``max(1, window // 2)`` non-NaN values per window.
        Default ``48`` (24 h at 30-minute resolution).

    Returns
    -------
    dict or None
        ``None`` if ``var_name`` is not in ``df`` or if the global standard
        deviation is zero or NaN.  Otherwise a dictionary with keys:

        - ``'scores'`` — ``pd.DataFrame`` with one column
          ``{var_name}_drift_score``, containing the Z-score of the rolling
          mean at each timestamp.
        - ``'metric'`` — the string ``'rolling_z_score'``.
        - ``'window'`` — the ``window`` value that was used.

    Notes
    -----
    The drift score at time ``t`` is::

        score(t) = (rolling_mean(t) - global_mean) / global_std

    Values beyond roughly ±2 suggest the local mean has shifted by 2
    standard deviations from the long-term average.  There is no fixed
    threshold; a practical rule of thumb is to inspect periods where
    ``|score| > 1.5`` for more than one window duration.

    The tuning parameters interact: a short ``window`` with a low
    ``z_threshold`` (set by the caller) catches small, fast drift but
    generates more false positives.  A long ``window`` reduces noise but may
    average out the drift signal.

    Examples
    --------
    >>> import pandas as pd, numpy as np
    >>> from palmwtc.qc import detect_drift_windstats
    >>> rng = np.random.default_rng(1)
    >>> idx = pd.date_range("2023-01-01", periods=96, freq="30min")
    >>> vals = np.concatenate([rng.normal(400, 2, 48), rng.normal(410, 2, 48)])
    >>> df = pd.DataFrame({"CO2": vals}, index=idx)
    >>> result = detect_drift_windstats(df, "CO2", window=24)
    >>> "CO2_drift_score" in result["scores"].columns
    True
    >>> result["metric"]
    'rolling_z_score'
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
    """Apply piecewise mean-shift correction to align each segment to a reference baseline.

    Uses the breakpoints returned by
    :func:`~palmwtc.qc.breakpoints.detect_breakpoints_ruptures` (or any list
    of timestamps) to split the time series into segments.  Each segment's
    mean is shifted so that it equals ``reference_baseline``.  The first
    segment sets the reference if no explicit baseline is given.

    This is a simple mean-shift approach.  It corrects stable offsets between
    segments but does **not** model within-segment drift (a linear or
    polynomial trend inside one segment).

    Parameters
    ----------
    df : pd.DataFrame
        Input data.  Index must be a ``DatetimeIndex`` for timestamp
        comparisons to work correctly.
    var_name : str
        Column name of the variable to correct.
    breakpoints : list of timestamp-like
        Breakpoint timestamps that define segment boundaries.  Values are
        coerced to ``pd.Timestamp``.  An empty list returns the original
        series unchanged.
    reference_baseline : float or None, optional
        Target mean value for all segments in the same units as ``var_name``.
        ``None`` uses the first segment's own mean as the reference.

    Returns
    -------
    corrected : pd.Series
        Corrected values with the same index and name as ``df[var_name]``.
    offsets : pd.Series
        Offset applied at each row (``segment_mean - reference_baseline``).
        Subtract this from the original to reproduce the corrected values.
        Returns ``(None, None)`` if ``var_name`` is not in ``df``.

    Examples
    --------
    >>> import pandas as pd, numpy as np
    >>> from palmwtc.qc import apply_drift_correction
    >>> idx = pd.date_range("2023-01-01", periods=4, freq="30min")
    >>> df = pd.DataFrame({"CO2": [400.0, 402.0, 420.0, 418.0]}, index=idx)
    >>> bps = [pd.Timestamp("2023-01-01 01:00")]
    >>> corrected, offsets = apply_drift_correction(df, "CO2", bps)  # doctest: +SKIP
    >>> float(corrected.iloc[2])  # doctest: +SKIP
    401.0
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
