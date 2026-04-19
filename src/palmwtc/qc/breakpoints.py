"""Breakpoint detection and cross-variable consistency checks.

Ported verbatim from ``flux_chamber/src/qc_functions.py`` (Phase 2).
Behaviour preservation is the prime directive: function signatures and bodies
match the original to 1e-12. Internal cross-module references inside the
``palmwtc.qc`` subpackage now resolve via ``palmwtc.qc.*``.
"""

# ruff: noqa: F401, I001, RUF005, RUF013, SIM108
# Above ignores cover quirks carried verbatim from the original
# ``flux_chamber/src/qc_functions.py`` to honour the Phase 2 "behaviour
# preservation" rule (e.g. duplicate ``import numpy as np`` inside the
# function body, two-statements-per-line ``if`` clauses, ``[a] + b`` list
# concatenation, lazy imports inside function bodies, implicit Optional in
# ``expected_min: float = None``). Bug fixes are deferred to a later commit.

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
    """
    Detect structural breakpoints in a time series using the Ruptures library.

    Now supports aggregation by `group_col` (e.g. 'cycle_id') for much faster processing.
    If `group_col` is provided, data is aggregated (mean) by group before detection.

    Args:
        df: DataFrame containing the data.
        var_name: Name of the variable to analyze.
        qc_flag_col: Name of column containing QC flags (0=Good).
        penalty: Penalty parameter for PELT/Binseg algorithm (higher = fewer breakpoints).
        n_bkps: Number of breakpoints to detect (if known/fixed). Overrides penalty for Binseg/Window.
        min_confidence: Minimum confidence score (0.0-1.0) to keep a breakpoint. Filters out minor shifts.
        min_segment_size: Minimum number of points per segment (not used for Window).
        max_samples: Maximum number of samples to use for detection (if not aggregating).
        group_col: Column to group by before detection (e.g., 'cycle_id').
        algorithm: 'Binseg', 'Pelt', or 'Window'.
        model: Cost model ('l2' for mean shift, 'l1', 'normal').
        window_width: Window size for 'Window' algorithm.

    Returns:
        dict: Breakpoint detection results.
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
    """
    Check for sensor drift by monitoring daily minimum values.
    For CO2 sensors, baseline should be around 400-420 ppm.
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
    """
    Check for inconsistencies between related variables.

    Examples:
    - Temperature and vapor pressure should be correlated
    - RH > 100% is physically impossible
    - Soil temp at different depths should show gradient
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
    """
    Filter breakpoints to keep only major ones based on confidence and mean shift.

    Returns:
    --------
    list: Filtered list of breakpoint timestamps
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
