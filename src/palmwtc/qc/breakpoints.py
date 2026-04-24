"""Breakpoint detection and cross-variable consistency checks.

A *breakpoint* is an instantaneous step change in a sensor stream — for
example, a sensor swap, a re-calibration, or a sudden data-logger offset.
The functions here detect those step changes and filter them so that only
physically meaningful shifts are retained.

Compare with :mod:`palmwtc.qc.drift`, which handles *gradual* offsets that
accumulate over weeks or months rather than appearing as a sudden jump.
"""

# ruff: noqa: F401, I001, RUF005, RUF013, SIM108
# Above ignores cover quirks carried verbatim from the ported source to
# preserve numeric behaviour to 1e-12 (duplicate ``import numpy as np``
# inside function bodies, ``[a] + b`` list concatenation, implicit Optional
# in ``expected_min: float = None``). Bug fixes are deferred to a later commit.

from __future__ import annotations

import pandas as pd


def detect_breakpoints_ruptures(
    df,
    var_name,
    qc_flag_col=None,
    penalty=10,
    n_bkps=None,
    min_confidence=None,
    min_segment_size=100,
    max_samples=10000,
    group_col=None,
    algorithm="Binseg",
    model="l2",
    window_width=100,
):
    """Detect structural breakpoints in a time series using the ruptures library.

    Wraps the ``Binseg``, ``Pelt``, or ``Window`` algorithm from *ruptures*
    [1]_ to locate instantaneous step changes (breakpoints) in a sensor
    variable.  Supports an optional aggregation path — grouping by
    ``group_col`` (e.g. ``'cycle_id'``) before fitting — which is much
    faster when the raw signal has millions of rows.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.  Index should be a ``DatetimeIndex`` for timestamp
        mapping to work correctly.
    var_name : str
        Column name of the variable to analyse.
    qc_flag_col : str or None, optional
        Column whose non-zero values are treated as bad data and excluded
        before fitting.  ``None`` uses all rows.
    penalty : float, optional
        Regularisation penalty for the PELT / Binseg cost function.
        Higher values increase the minimum cost needed to add a breakpoint,
        so the algorithm returns *fewer* breakpoints.  Lower values make the
        detector more sensitive (more breakpoints detected).  Default ``10``.
    n_bkps : int or None, optional
        If given, force exactly this many breakpoints.  Overrides ``penalty``
        for ``Binseg`` and ``Window`` algorithms.
    min_confidence : float or None, optional
        Minimum confidence score in [0, 1] to retain a breakpoint after
        detection.  A score of 1.0 means the inter-segment mean shift
        exceeds three pooled standard deviations.  Breakpoints below this
        threshold are pruned iteratively (least confident first).
    min_segment_size : int, optional
        Minimum number of data points that each segment must contain.
        Ignored for the ``Window`` algorithm.  Default ``100``.
    max_samples : int, optional
        Maximum number of rows used when *not* aggregating.  Rows beyond
        this count are downsampled uniformly.  Default ``10000``.
    group_col : str or None, optional
        Column to aggregate by before detection (e.g. ``'cycle_id'``).
        When given, each group is replaced by its mean value, greatly
        reducing the effective signal length.
    algorithm : {'Binseg', 'Pelt', 'Window'}, optional
        ruptures algorithm to use.  Default ``'Binseg'``.

        - ``'Binseg'`` — binary segmentation; fast, approximate.
        - ``'Pelt'`` — optimal segmentation via dynamic programming; slower
          but exact.  Uses ``penalty`` only (``n_bkps`` ignored).
        - ``'Window'`` — sliding-window approach; good for slowly drifting
          signals.
    model : str, optional
        Cost model for the ruptures algorithm.  ``'l2'`` detects mean-level
        shifts (most common for sensor offsets).  ``'rbf'`` uses a
        kernel-based cost that handles non-Gaussian distributions and
        variance changes — useful when the sensor noise itself changes at
        the breakpoint.  ``'l1'`` is robust to outliers.  Default ``'l2'``.
    window_width : int, optional
        Half-width (in samples) of the sliding window for the ``Window``
        algorithm.  Halved automatically if the signal is too short.
        Default ``100``.

    Returns
    -------
    dict or None
        ``None`` if the variable is missing or no valid data remain.
        Otherwise a dictionary with keys:

        - ``'breakpoints'`` — list of ``pd.Timestamp`` objects, one per
          detected breakpoint.
        - ``'n_breakpoints'`` — integer count.
        - ``'segment_info'`` — list of dicts, each with ``'start'``,
          ``'end'``, ``'mean'``, and ``'std'`` for that segment.
        - ``'confidence_scores'`` — list of floats in [0, 1], one per
          internal boundary (len = n_breakpoints).
        - ``'used_qc_filter'`` — bool, whether ``qc_flag_col`` was applied.

    Notes
    -----
    The confidence score for a boundary is
    ``min(1, |mean2 - mean1| / (3 * pooled_std))``, where ``mean1`` and
    ``mean2`` are the adjacent segment means and ``pooled_std`` is their
    pooled standard deviation.
    A score of 1.0 means the step is at least 3 pooled-SD wide -- the
    standard threshold for a physically significant sensor shift.

    When ``group_col`` is used, the minimum segment size is clamped to
    5 groups regardless of ``min_segment_size``.

    References
    ----------
    .. [1] Truong, C., Oudre, L., & Vayatis, N. (2020). Selective review
           of offline change point detection methods. *Signal
           Processing*, 167, 107299.
           https://doi.org/10.1016/j.sigpro.2019.107299

    Examples
    --------
    >>> import pandas as pd, numpy as np
    >>> from palmwtc.qc import detect_breakpoints_ruptures
    >>> rng = np.random.default_rng(0)
    >>> idx = pd.date_range("2023-01-01", periods=200, freq="30min")
    >>> vals = np.concatenate([rng.normal(400, 5, 100), rng.normal(450, 5, 100)])
    >>> df = pd.DataFrame({"CO2": vals}, index=idx)
    >>> result = detect_breakpoints_ruptures(df, "CO2", penalty=5)  # doctest: +SKIP
    >>> result["n_breakpoints"]  # doctest: +SKIP
    1
    """
    import math
    import numpy as np  # Added for np.nan

    if var_name not in df.columns:
        print(f"  Error: Variable {var_name} not found.")
        return None

    # Lazy import ruptures
    try:
        import ruptures as rpt
    except ImportError:
        print("  Error: 'ruptures' library not installed. pip install ruptures")
        return None

    # 1. Prepare Data
    if qc_flag_col and qc_flag_col in df.columns:
        # Filter for high quality data (Flag 0)
        mask = df[qc_flag_col] == 0
        df_clean = df[mask].copy()
    else:
        df_clean = df.copy()

    # Drop NaNs for the target variable
    df_clean = df_clean.dropna(subset=[var_name])

    if df_clean.empty:
        print(f"  No valid data for {var_name} after filtering.")
        return None

    # --- AGGREGATION PATH (Fastest) ---
    if group_col and group_col in df_clean.columns:
        print(f"  Aggregating by {group_col} for breakpoint detection...")
        # Group by cycle and take mean
        # We also need the start timestamp of each cycle to map back
        aggregated = df_clean.groupby(group_col).agg(
            {
                var_name: "mean",
                # taking the first index relative to the clean df might be tricky if index is not unique
                # assuming index is timestamp is safest, or just use the first timestamp value
            }
        )

        # We need a mapping from aggregate index -> original timestamp
        # Let's get the timestamp corresponding to the *start* of each group in the filtered data
        # Assuming df_clean has a datetime index or we can recoverit
        if isinstance(df_clean.index, pd.DatetimeIndex):
            group_starts = df_clean.groupby(group_col).apply(lambda x: x.index[0])
        elif "TIMESTAMP" in df_clean.columns:
            group_starts = df_clean.groupby(group_col)["TIMESTAMP"].first()
        else:
            # Fallback: just index
            group_starts = df_clean.groupby(group_col).apply(lambda x: x.index[0])

        signal = aggregated[var_name].values
        processing_signal = signal
        original_indices_map = group_starts.values  # This array aligns with 'signal'

        # Adjust min_size for aggregated data (cycles are much fewer than points)
        # e.g. min 5 cycles per regime
        effective_min_size = max(2, 5)

        step = 1  # No downsampling needed usually for aggregated data

    # --- DOWNSAMPLING PATH (Legacy / Fallback) ---
    else:
        signal = df_clean[var_name].values
        step = 1
        original_len = len(signal)
        processing_signal = signal

        if original_len > max_samples:
            step = math.ceil(original_len / max_samples)
            processing_signal = signal[::step]
            effective_min_size = max(2, min_segment_size // step)
            print(
                f"  Downsampling {var_name}: {original_len} -> {len(processing_signal)} points (step={step})"
            )
        else:
            effective_min_size = min_segment_size

        effective_min_size = max(2, effective_min_size)

    # 2. Run Detection
    # model defined in args

    if algorithm == "Binseg":
        algo = rpt.Binseg(model=model, min_size=effective_min_size).fit(processing_signal)
        if n_bkps is not None:
            detected_indices = algo.predict(n_bkps=int(n_bkps))
        else:
            detected_indices = algo.predict(pen=penalty)
    elif algorithm == "Pelt":
        algo = rpt.Pelt(model=model, min_size=effective_min_size).fit(processing_signal)
        detected_indices = algo.predict(pen=penalty)
    elif algorithm == "Window":
        # Adjust window width for aggregated data if needed
        # Window width must be small enough for the signal
        effective_width = window_width
        if len(processing_signal) < effective_width * 2:
            effective_width = len(processing_signal) // 2

        algo = rpt.Window(width=effective_width, model=model, min_size=effective_min_size).fit(
            processing_signal
        )
        if n_bkps is not None:
            detected_indices = algo.predict(n_bkps=int(n_bkps))
        else:
            detected_indices = algo.predict(pen=penalty)
    else:
        print(f"  Warning: Unknown algorithm '{algorithm}', defaulting to Binseg")
        algo = rpt.Binseg(model=model, min_size=effective_min_size).fit(processing_signal)
        if n_bkps is not None:
            detected_indices = algo.predict(n_bkps=int(n_bkps))
        else:
            detected_indices = algo.predict(pen=penalty)

    # --- PRUNING LOGIC (Confidence-Based) ---
    # Iteratively remove the least significant breakpoint until all meet min_confidence

    if min_confidence is not None:
        kept_indices = sorted(detected_indices)

        while len(kept_indices) > 0:
            # Reconstruct boundaries for current set of breakpoints
            curr_boundaries = [0] + kept_indices
            if curr_boundaries[-1] != len(signal):
                curr_boundaries.append(len(signal))
            curr_boundaries = sorted(list(set(curr_boundaries)))

            # compute stats for these segments
            seg_means = []
            seg_stds = []
            for k in range(len(curr_boundaries) - 1):
                s, e = curr_boundaries[k], curr_boundaries[k + 1]
                seg = signal[s:e]
                seg_means.append(seg.mean())
                seg_stds.append(seg.std() if len(seg) > 1 else 0)

            # calculate scores for each internal breakpoint
            # kept_indices[i] corresponds to the boundary between segment i and i+1
            scores = []
            for k in range(len(seg_means) - 1):
                diff = abs(seg_means[k + 1] - seg_means[k])
                pooled_std = (seg_stds[k] + seg_stds[k + 1]) / 2
                if pooled_std > 0:
                    score = min(1.0, diff / (3 * pooled_std))
                else:
                    score = 1.0 if diff > 0 else 0.0
                scores.append(score)

            if not scores:
                break

            min_score = min(scores)
            min_idx = scores.index(min_score)

            if min_score < min_confidence:
                # Remove the breakpoint with the lowest score
                # kept_indices[min_idx] is the one to remove
                # print(f"Pruning breakpoint at index {kept_indices[min_idx]} (score {min_score:.2f} < {min_confidence})")
                kept_indices.pop(min_idx)
            else:
                # All remaining meet criteria
                break

        # Update detected_indices to the filtered set
        detected_indices = kept_indices

    # 3. Map Breakpoints back to Real Timestamps/Indices

    if group_col and group_col in df_clean.columns:
        # Map aggregated indices back to timestamps
        # detected_indices contains indices of the 'signal' array (0 to N_groups)

        breakpoint_timestamps = []
        for idx in detected_indices:
            if idx < len(original_indices_map):
                breakpoint_timestamps.append(original_indices_map[idx])
            elif idx == len(original_indices_map):
                # End of last segment
                pass

    else:
        # Legacy mapping
        if step > 1:
            breakpoint_indices = [idx * step for idx in detected_indices]
        else:
            breakpoint_indices = detected_indices

        if breakpoint_indices and breakpoint_indices[-1] >= len(signal):
            breakpoint_indices[-1] = len(signal)
        if breakpoint_indices and breakpoint_indices[-1] == len(signal):
            breakpoint_indices = breakpoint_indices[:-1]

        breakpoint_timestamps = [
            df_clean.index[i - 1] if i > 0 else df_clean.index[0] for i in breakpoint_indices
        ]

    n_breakpoints = len(breakpoint_timestamps)

    if n_breakpoints == 0:
        print(f"  No breakpoints detected for {var_name}")
        return {
            "breakpoints": [],
            "n_breakpoints": 0,
            "segment_means": [signal.mean()],
            "segment_info": [],
            "confidence_scores": [],
            "used_qc_filter": qc_flag_col is not None,
        }

    # Calculate Segment Info (timestamps + means)
    segment_info = []

    # Retrieve boundaries for segment info
    # We need start_time and end_time for each segment

    # helper to get timestamp
    # (reused logic from above, but cleaner here for final segments)

    boundaries_proc = [0] + detected_indices
    # Ensure end is included
    if boundaries_proc[-1] != len(signal):
        boundaries_proc.append(len(signal))

    # Remove duplicates
    boundaries_proc = sorted(list(set(boundaries_proc)))

    final_confidences = []

    for i in range(len(boundaries_proc) - 1):
        idx_start = boundaries_proc[i]
        idx_end = boundaries_proc[i + 1]  # exclusive

        # Data for this segment
        seg_vals = signal[idx_start:idx_end]
        mean_val = seg_vals.mean()
        std_val = seg_vals.std() if len(seg_vals) > 1 else 0

        # Timestamps
        # For aggregated: idx refers to `original_indices_map`
        # For raw: idx refers to `df_clean.index` (adjusting for step if needed)

        if group_col and group_col in df_clean.columns:
            ts_start = original_indices_map[idx_start]
            ts_end = original_indices_map[idx_end - 1] if idx_end > 0 else ts_start
        else:
            # If using step
            real_idx_start = idx_start * step
            real_idx_end = (idx_end * step) - 1
            if real_idx_start >= len(df_clean):
                real_idx_start = len(df_clean) - 1
            if real_idx_end >= len(df_clean):
                real_idx_end = len(df_clean) - 1

            ts_start = df_clean.index[real_idx_start]
            ts_end = df_clean.index[real_idx_end]

        segment_info.append(
            {
                "start": pd.Timestamp(ts_start),
                "end": pd.Timestamp(ts_end),
                "mean": mean_val,
                "std": std_val,
            }
        )

    # Calculate confidence scores for final set
    for i in range(len(segment_info) - 1):
        prev = segment_info[i]
        curr = segment_info[i + 1]

        diff = abs(curr["mean"] - prev["mean"])
        pooled_std = (prev["std"] + curr["std"]) / 2

        if pooled_std > 0:
            score = min(1.0, diff / (3 * pooled_std))  # >3 sigma shift = 1.0 confidence
        else:
            score = 1.0 if diff > 0 else 0.0
        final_confidences.append(round(score, 2))

    # Ensure breakpoints are pandas Timestamps for consistency (fixes strftime error)
    breakpoint_timestamps = [pd.Timestamp(ts) for ts in breakpoint_timestamps]

    return {
        "breakpoints": breakpoint_timestamps,
        "n_breakpoints": n_breakpoints,
        "segment_info": segment_info,
        "confidence_scores": final_confidences,
        "used_qc_filter": qc_flag_col is not None,
    }


def check_baseline_drift(df: pd.DataFrame, column: str, expected_min: float = None) -> pd.DataFrame:
    """Monitor sensor baseline by inspecting daily minimum values.

    For CO₂ sensors the ambient (open-chamber) minimum should stay near
    400-420 µmol mol⁻¹.  A persistent upward trend in the daily minimum
    indicates that the sensor zero is drifting — a gradual process handled
    separately in :mod:`palmwtc.qc.drift`.  This function flags individual
    *days* where the minimum deviates by more than 50 µmol mol⁻¹ from
    ``expected_min``.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed DataFrame.  The index must support ``resample``.
    column : str
        Name of the sensor column to check.
    expected_min : float or None, optional
        Expected daily minimum value in the same units as ``column``.  When
        given, days outside the ±50-unit tolerance are flagged.
        ``None`` skips the flagging step and returns only the summary
        statistics.

    Returns
    -------
    pd.DataFrame or None
        ``None`` if ``column`` is not found in ``df``.  Otherwise a
        daily-resampled DataFrame with columns:

        - ``{column}_daily_min`` — daily minimum.
        - ``{column}_daily_max`` — daily maximum.
        - ``{column}_daily_mean`` — daily mean.
        - ``{column}_daily_range`` — daily max minus daily min.
        - ``{column}_trend`` — 7-day rolling mean of ``_daily_mean``,
          first-differenced (rate of change, same units day⁻¹).
        - ``{column}_baseline_drift`` — bool, ``True`` on days where
          ``|daily_min - expected_min| > 50`` (only present when
          ``expected_min`` is not ``None``).

    Examples
    --------
    >>> import pandas as pd, numpy as np
    >>> from palmwtc.qc import check_baseline_drift
    >>> idx = pd.date_range("2023-01-01", periods=48, freq="30min")
    >>> df = pd.DataFrame({"CO2": np.full(48, 410.0)}, index=idx)
    >>> result = check_baseline_drift(df, "CO2", expected_min=400)
    CO2: 0 days with baseline drift (>400±50)
    >>> bool(result["CO2_baseline_drift"].any())
    False
    """
    if column not in df.columns:
        return None

    daily_min = df[column].resample("1D").min()
    daily_max = df[column].resample("1D").max()
    daily_mean = df[column].resample("1D").mean()

    result = pd.DataFrame(
        {
            f"{column}_daily_min": daily_min,
            f"{column}_daily_max": daily_max,
            f"{column}_daily_mean": daily_mean,
            f"{column}_daily_range": daily_max - daily_min,
        }
    )

    # Calculate rolling 7-day trend
    result[f"{column}_trend"] = result[f"{column}_daily_mean"].rolling(7).mean().diff()

    if expected_min is not None:
        # Flag days where minimum deviates significantly from expected
        deviation = abs(daily_min - expected_min)
        result[f"{column}_baseline_drift"] = deviation > 50  # >50 ppm deviation
        n_drift_days = result[f"{column}_baseline_drift"].sum()
        print(f"{column}: {n_drift_days} days with baseline drift (>{expected_min}±50)")

    return result


def check_cross_variable_consistency(df: pd.DataFrame) -> pd.DataFrame:
    """Flag physically impossible or mutually inconsistent values across variables.

    Runs four cross-variable checks:

    1. Relative humidity outside [0, 100] % — physically impossible.
    2. Temperature difference > 10 °C between the two chambers — suspicious
       unless one chamber is actively closed.
    3. CO₂ difference > 200 µmol mol⁻¹ between the two chambers during open
       periods.
    4. Soil temperature variability increases with depth — unexpected because
       deeper soil should be more stable than the surface layer.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed DataFrame.  Column names follow the LI-COR / oil-palm
        chamber naming convention (``RH_*``, ``Temp_1_C1``, ``CO2_C1``,
        ``Tsol_15_Avg_Soil``, etc.).

    Returns
    -------
    pd.DataFrame
        Boolean flag DataFrame with the same index as ``df``.  Each column
        corresponds to one consistency check; ``True`` means the row failed
        that check.  Columns present depend on which sensor columns exist in
        ``df``.

    Examples
    --------
    >>> import pandas as pd
    >>> from palmwtc.qc import check_cross_variable_consistency
    >>> df = pd.DataFrame({"RH_1": [50.0, 110.0, 80.0]})
    >>> flags = check_cross_variable_consistency(df)
    RH_1: 1 invalid RH values
    >>> list(flags["RH_1_invalid"])
    [False, True, False]
    """
    flags = pd.DataFrame(index=df.index)

    # Check 1: RH > 100 or < 0
    rh_cols = [c for c in df.columns if "RH" in c and not c.endswith("_source")]
    for col in rh_cols:
        invalid_rh = (df[col] > 100) | (df[col] < 0)
        flags[f"{col}_invalid"] = invalid_rh
        if invalid_rh.sum() > 0:
            print(f"{col}: {invalid_rh.sum():,} invalid RH values")

    # Check 2: Temperature consistency between chambers
    if "Temp_1_C1" in df.columns and "Temp_1_C2" in df.columns:
        temp_diff = abs(df["Temp_1_C1"] - df["Temp_1_C2"])
        flags["temp_chamber_mismatch"] = temp_diff > 10  # >10°C difference is suspicious
        n_mismatch = flags["temp_chamber_mismatch"].sum()
        if n_mismatch > 0:
            print(f"Temperature: {n_mismatch:,} readings with >10°C chamber difference")

    # Check 3: CO2 consistency (both sensors should see similar ambient)
    if "CO2_C1" in df.columns and "CO2_C2" in df.columns:
        # During open periods, CO2 should be similar
        co2_diff = abs(df["CO2_C1"] - df["CO2_C2"])
        flags["co2_chamber_mismatch"] = co2_diff > 200  # >200 ppm difference
        n_mismatch = flags["co2_chamber_mismatch"].sum()
        if n_mismatch > 0:
            print(f"CO2: {n_mismatch:,} readings with >200 ppm chamber difference")

    # Check 4: Soil temperature depth gradient
    soil_temp_cols = ["Tsol_15_Avg_Soil", "Tsol_48_Avg_Soil", "Tsol_80_Avg_Soil"]
    if all(c in df.columns for c in soil_temp_cols):
        # Deep soil should be more stable than shallow
        shallow_var = df["Tsol_15_Avg_Soil"].rolling("1D").std()
        deep_var = df["Tsol_80_Avg_Soil"].rolling("1D").std()
        # Flag if deep soil varies more than shallow (unusual)
        flags["soil_gradient_anomaly"] = deep_var > (shallow_var * 1.5)

    return flags


def filter_major_breakpoints(bp_result, min_confidence=0.3, min_mean_shift=15):
    """Keep only breakpoints that exceed both a confidence and an amplitude threshold.

    After :func:`detect_breakpoints_ruptures` returns a candidate list, this
    function removes breakpoints that are either statistically weak (low
    confidence score) or physically small (mean shift below
    ``min_mean_shift``).  The two thresholds are applied independently —
    a breakpoint must pass *both* to be retained.

    Parameters
    ----------
    bp_result : dict or None
        Return value of :func:`detect_breakpoints_ruptures`.  ``None`` or
        an empty result returns an empty list without error.
    min_confidence : float, optional
        Minimum confidence score (0.0-1.0) required to retain a breakpoint.
        Scores are computed as ``min(1, |delta_mean| / (3 * pooled_std))``; a
        value of 0.3 keeps breakpoints with at least a 0.9 pooled-SD mean
        shift.  Default
        ``0.3``.
    min_mean_shift : float, optional
        Minimum absolute difference between adjacent segment means required
        to retain a breakpoint.  Units match the sensor variable.
        Default ``15`` (appropriate for CO₂ in µmol mol⁻¹).

    Returns
    -------
    list of pd.Timestamp
        Timestamps of breakpoints that passed both thresholds.  Empty list
        if none pass or if ``bp_result`` is ``None``.

    Examples
    --------
    >>> from palmwtc.qc import filter_major_breakpoints
    >>> result = {
    ...     "n_breakpoints": 1,
    ...     "breakpoints": ["2023-06-01"],
    ...     "segment_info": [{"mean": 400.0, "std": 5.0}, {"mean": 450.0, "std": 5.0}],
    ...     "confidence_scores": [0.5],
    ... }
    >>> kept = filter_major_breakpoints(result, min_confidence=0.3, min_mean_shift=15)
    Filtered 1 breakpoints -> 1 major breakpoints
    >>> len(kept)
    1
    """
    if bp_result is None or bp_result["n_breakpoints"] == 0:
        return []

    breakpoints = bp_result["breakpoints"]
    segment_info = bp_result.get("segment_info", [])
    confidence_scores = bp_result.get("confidence_scores", [])

    filtered = []

    for i, bp in enumerate(breakpoints):
        # Check confidence
        if i < len(confidence_scores):
            conf = confidence_scores[i]
            if conf < min_confidence:
                continue

        # Check mean shift
        if segment_info and i < len(segment_info) - 1:
            shift = abs(segment_info[i + 1]["mean"] - segment_info[i]["mean"])
            if shift < min_mean_shift:
                continue

        filtered.append(bp)

    print(f"Filtered {len(breakpoints)} breakpoints -> {len(filtered)} major breakpoints")
    return filtered
