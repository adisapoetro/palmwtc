"""Rule-based QC flag generators for whole-tree chamber sensor streams.

Each function in this module takes one sensor variable's time series
(plus its variable config) and returns either a flag ``pd.Series`` or
the input frame augmented with per-row QC flag information. Rules cover:

- Physical bounds (hard and soft limits from sensor specifications).
- Statistical outliers (IQR-based, column-wise).
- Rate of change (spike detection between consecutive samples).
- Persistence (stuck / flat-line detection over a rolling time window).
- Battery-voltage proxy (data-logger health propagated to measurements).
- Sensor date-range exclusions (maintenance windows, sensor swapouts).

Flag values carry a three-level severity scale:

- ``0`` — Good: within all bounds, no anomaly detected.
- ``1`` — Suspect: outside soft bounds or flagged by IQR / RoC /
  persistence; use with caution.
- ``2`` — Bad: outside hard bounds or inside an exclusion window;
  exclude from flux calculations.

``combine_qc_flags`` merges per-rule flag series into a single mask per
variable. ``process_variable_qc`` orchestrates all rule checks in order
for one variable and returns a dict of individual plus combined flags.

Tuned for the LI-COR LI-850 gas analyser (CO₂, H₂O) inside a
whole-tree chamber around an individual oil palm, plus soil sensors at
5, 15, 30, 60, and 80 cm depths (Campbell CS616 / CS655 type).
"""

# ruff: noqa: B007, E712, F841, I001, RUF010
# Above ignores cover quirks carried verbatim from the original
# qc_functions implementation to preserve numeric output parity:
# - F841 ``indexer`` assigned-but-never-used (twice) inside
#   ``apply_persistence_flags`` — the original keeps these dead local
#   FixedForwardWindowIndexer constructions next to the real rolling call;
# - B007 unused loop variable ``config_name`` in ``get_variable_config`` and
#   ``hard_max`` / ``soft_max`` style local naming;
# - E712 ``== True`` literal comparison inside the regime-audit mask;
# - I001 lazy ``import yaml; from pathlib import Path`` blocks inside
#   ``_load_sensor_exclusions`` and ``generate_exclusion_recommendations``;
# - RUF010 explicit ``str(e)`` cast inside an f-string.
# Bug fixes are deferred to a later commit.

from __future__ import annotations

import numpy as np
import pandas as pd


def apply_physical_bounds_flags(df, var_name, config):
    """Flag rows where a variable falls outside its physical bounds.

    Compares each value of ``var_name`` in ``df`` against hard and soft
    limits defined in the variable config. Hard bounds represent absolute
    sensor limits (saturation, cable disconnect); soft bounds represent
    expected operating range under normal field conditions.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed sensor data. Must contain at least the column
        ``var_name``. Non-numeric values are coerced to ``NaN`` and
        treated as missing (not flagged).
    var_name : str
        Name of the column in ``df`` to check
        (e.g. ``"CO2_C1"``, ``"SWC_C1_15cm"``).
    config : dict
        Variable config dict. Recognised keys:

        ``"hard"`` : list of [low, high], optional
            Absolute sensor limits in native units. Values outside this
            range receive flag ``2`` (Bad).
        ``"soft"`` : list of [low, high], optional
            Expected operating limits in native units. Values outside
            soft but inside hard receive flag ``1`` (Suspect).

    Returns
    -------
    pd.Series
        Integer flag series aligned to ``df.index``:

        - ``0`` — within soft bounds (or no bounds configured).
        - ``1`` — outside soft bounds but within hard bounds (Suspect).
        - ``2`` — outside hard bounds (Bad).

    Notes
    -----
    Both ``"hard"`` and ``"soft"`` keys are optional. If only ``"hard"``
    is present, there are no Suspect flags — values are either 0 or 2.
    If only ``"soft"`` is present, there are no Bad flags.

    For the LI-850 CO₂ channel (range 0-20 000 ppm), typical hard
    limits are ``[0, 20000]`` and soft limits are ``[350, 2000]`` for
    tropical oil-palm chambers.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({"CO2_C1": [300.0, 1500.0, 25000.0]})
    >>> cfg = {"hard": [0.0, 20000.0], "soft": [350.0, 2000.0]}
    >>> flags = apply_physical_bounds_flags(df, "CO2_C1", cfg)
    >>> flags.tolist()
    [1, 0, 2]
    """
    flags = pd.Series(0, index=df.index)  # Initialize all as good

    # Skip if variable not in dataframe
    if var_name not in df.columns:
        return flags

    # Ensure numeric data
    data_numeric = pd.to_numeric(df[var_name], errors="coerce")

    # Get non-null mask
    valid_mask = data_numeric.notna()

    if "hard" in config:
        hard_min, hard_max = config["hard"]
        # Flag 2: Outside hard bounds
        outside_hard = (data_numeric < hard_min) | (data_numeric > hard_max)
        flags[valid_mask & outside_hard] = 2

    if "soft" in config:
        soft_min, soft_max = config["soft"]
        # Flag 1: Outside soft bounds but inside hard bounds
        outside_soft = (data_numeric < soft_min) | (data_numeric > soft_max)
        flags[valid_mask & outside_soft & (flags == 0)] = 1

    return flags


def apply_iqr_flags(df, var_name, iqr_factor=1.5):
    """Flag statistical outliers using the interquartile range (IQR) method.

    Computes Q1, Q3, and IQR over all valid (non-NaN) rows in the
    column, then flags values outside ``[Q1 - k*IQR, Q3 + k*IQR]``
    where ``k = iqr_factor``.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed sensor data. Must contain at least the column
        ``var_name``. Non-numeric values are coerced to ``NaN``.
    var_name : str
        Name of the column in ``df`` to check
        (e.g. ``"H2O_C1"``, ``"AirTC_Avg"``).
    iqr_factor : float, optional
        Multiplier applied to the IQR to define the outlier fence.
        Default ``1.5`` (the classic Tukey fence). Use a larger value
        (e.g. ``3.0``) for variables with heavy right tails such as
        soil CO₂ efflux.

    Returns
    -------
    pd.Series
        Integer flag series aligned to ``df.index``:

        - ``0`` — within the IQR fence (Good).
        - ``1`` — outside the IQR fence (Suspect).

    Notes
    -----
    IQR-based flagging assumes a roughly symmetric distribution. Tropical
    chamber CO₂ is typically log-normal within a day, so this is a
    coarse filter intended to catch orders-of-magnitude anomalies rather
    than subtle drift. At least 4 valid data points are required;
    fewer returns all zeros. If all values are identical (IQR = 0) the
    function also returns all zeros to avoid flagging constant series
    that may represent a gap period.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({"CO2_C1": [400.0, 410.0, 405.0, 395.0, 9999.0]})
    >>> flags = apply_iqr_flags(df, "CO2_C1", iqr_factor=1.5)
    >>> flags.tolist()
    [0, 0, 0, 0, 1]
    """
    flags = pd.Series(0, index=df.index)

    # Skip if variable not in dataframe
    if var_name not in df.columns:
        return flags

    # Ensure numeric data
    data_numeric = pd.to_numeric(df[var_name], errors="coerce")

    # Get non-null data
    valid_mask = data_numeric.notna()
    valid_data = data_numeric.loc[valid_mask]

    if len(valid_data) < 4:  # Need at least 4 points for meaningful IQR
        return flags

    # Calculate IQR statistics
    Q1 = valid_data.quantile(0.25)
    Q3 = valid_data.quantile(0.75)
    IQR = Q3 - Q1

    if IQR == 0:  # All values are the same
        return flags

    # Define outlier bounds
    lower_bound = Q1 - iqr_factor * IQR
    upper_bound = Q3 + iqr_factor * IQR

    # Flag outliers as suspect (1)
    is_outlier = (valid_data < lower_bound) | (valid_data > upper_bound)
    flags[valid_mask & is_outlier] = 1

    return flags


def combine_qc_flags(bounds_flags, iqr_flags, roc_flags=None, persistence_flags=None):
    """Merge per-rule flag series into a single combined quality flag.

    Applies a worst-case (maximum) merge logic with priority ordering:

    1. Physical bounds flags set the base (can produce flag 2).
    2. IQR, rate-of-change, and persistence flags elevate 0 → 1.
    3. A flag 2 value is never demoted to 1 or 0.

    Parameters
    ----------
    bounds_flags : pd.Series
        Flags from the physical bounds check (values 0, 1, or 2).
        Used as the starting base for the merge.
    iqr_flags : pd.Series
        Flags from the IQR outlier check (values 0 or 1).
        Must share the same index as ``bounds_flags``.
    roc_flags : pd.Series, optional
        Flags from the rate-of-change (spike) check (values 0 or 1).
        If ``None``, treated as all zeros.
    persistence_flags : pd.Series, optional
        Flags from the persistence (flat-line) check (values 0 or 1).
        If ``None``, treated as all zeros.

    Returns
    -------
    pd.Series
        Combined integer flag series (0, 1, or 2) aligned to
        ``bounds_flags.index``.

    Examples
    --------
    >>> import pandas as pd
    >>> bounds = pd.Series([0, 2, 0, 0])
    >>> iqr    = pd.Series([0, 0, 1, 0])
    >>> roc    = pd.Series([0, 0, 0, 1])
    >>> combined = combine_qc_flags(bounds, iqr, roc_flags=roc)
    >>> combined.tolist()
    [0, 2, 1, 1]
    """
    # Start with physical bounds as base
    final_flags = bounds_flags.copy()

    # Handle optional inputs
    if roc_flags is None:
        roc_flags = pd.Series(0, index=bounds_flags.index)
    if persistence_flags is None:
        persistence_flags = pd.Series(0, index=bounds_flags.index)

    # Combine 'Suspect' triggers
    # Flag 1 sources: IQR, RoC, Persistence (and Soft Bounds which are already in final_flags)

    # If final_flags is already 2 (Bad), we don't downgrade it.
    # We only promote 0 to 1.

    suspect_triggers = (iqr_flags == 1) | (roc_flags == 1) | (persistence_flags == 1)

    suspect_mask = (final_flags < 2) & suspect_triggers
    final_flags[suspect_mask] = 1

    return final_flags


def generate_qc_summary(df, flag_column):
    """Count and summarise flag levels for one QC flag column.

    Parameters
    ----------
    df : pd.DataFrame
        Data frame containing at least the column ``flag_column``.
    flag_column : str
        Name of the integer flag column to summarise
        (e.g. ``"CO2_C1_rule_flag"``).

    Returns
    -------
    dict
        Summary statistics with the following keys:

        ``"total_points"`` : int
            Total number of rows.
        ``"flag_0_count"`` : int
            Number of rows with flag 0 (Good).
        ``"flag_1_count"`` : int
            Number of rows with flag 1 (Suspect).
        ``"flag_2_count"`` : int
            Number of rows with flag 2 (Bad).
        ``"flag_0_percent"`` : float
            Percentage of rows with flag 0.
        ``"flag_1_percent"`` : float
            Percentage of rows with flag 1.
        ``"flag_2_percent"`` : float
            Percentage of rows with flag 2.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({"CO2_rule_flag": [0, 0, 1, 2, 0]})
    >>> s = generate_qc_summary(df, "CO2_rule_flag")
    >>> s["total_points"], s["flag_0_count"], s["flag_1_count"], s["flag_2_count"]
    (5, 3, 1, 1)
    """
    total = len(df)
    flag_counts = df[flag_column].value_counts()

    summary = {
        "total_points": total,
        "flag_0_count": int(flag_counts.get(0, 0)),
        "flag_1_count": int(flag_counts.get(1, 0)),
        "flag_2_count": int(flag_counts.get(2, 0)),
        "flag_0_percent": float(flag_counts.get(0, 0) / total * 100),
        "flag_1_percent": float(flag_counts.get(1, 0) / total * 100),
        "flag_2_percent": float(flag_counts.get(2, 0) / total * 100),
    }

    return summary


def get_variable_config(var_name, var_config_dict):
    """Look up the QC configuration for a specific variable column name.

    Handles both direct column-name matches (e.g. ``"CO2_C1"``) and
    prefix-pattern matches used for soil sensor arrays
    (e.g. ``"SWC_C1"`` matching columns like ``"SWC_C1_5cm"``).

    Parameters
    ----------
    var_name : str
        Variable column name to look up (e.g. ``"CO2_C1"``,
        ``"SWC_C1_30cm"``).
    var_config_dict : dict
        Variable configuration dictionary, typically loaded from
        ``variable_config.json``. Each entry is either:

        - A config with ``"columns": [...]`` — list of exact column names
          that share this config.
        - A config with ``"pattern": "<prefix>"`` — all columns whose
          name starts with ``"<prefix>_"`` share this config.

    Returns
    -------
    dict or None
        Configuration dict for the variable if found, otherwise ``None``.

    Notes
    -----
    Direct column matches are checked before pattern matches. If a
    variable matches both, the direct match wins.

    Examples
    --------
    >>> cfg_dict = {
    ...     "co2": {"columns": ["CO2_C1", "CO2_C2"], "hard": [0, 20000]},
    ...     "swc": {"pattern": "SWC_C1", "hard": [0.0, 0.8]},
    ... }
    >>> get_variable_config("CO2_C1", cfg_dict)
    {'columns': ['CO2_C1', 'CO2_C2'], 'hard': [0, 20000]}
    >>> get_variable_config("SWC_C1_30cm", cfg_dict)
    {'pattern': 'SWC_C1', 'hard': [0.0, 0.8]}
    >>> get_variable_config("Temp_air", cfg_dict) is None
    True
    """
    # First, check for direct column match
    for config_name, config in var_config_dict.items():
        if "columns" in config and var_name in config["columns"]:
            return config

    # Check for pattern match (for soil variables)
    for config_name, config in var_config_dict.items():
        if "pattern" in config:
            pattern = config["pattern"]
            if var_name.startswith(pattern + "_"):
                return config

    return None


def apply_rate_of_change_flags(df, var_name, config):
    """Flag rows where consecutive-sample change exceeds a spike limit.

    Computes the absolute first-difference of the column and compares it
    against a configured ``rate_of_change.limit``. Accounts for time
    gaps (e.g. chamber open periods) by skipping the check at transitions
    where the elapsed time exceeds three times the typical sampling
    interval.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed sensor data with a ``pd.DatetimeIndex`` (preferred).
        Must contain at least the column ``var_name``. Non-numeric values
        are coerced to ``NaN``.
    var_name : str
        Name of the column in ``df`` to check
        (e.g. ``"CO2_C1"``, ``"AirTC_Avg"``).
    config : dict
        Variable config dict. Recognised key:

        ``"rate_of_change"`` : dict, optional
            Sub-dict with:

            ``"limit"`` : float
                Maximum allowed absolute change between consecutive
                samples in native units. If missing, the check is
                skipped and all flags return 0.

    Returns
    -------
    pd.Series
        Integer flag series aligned to ``df.index``:

        - ``0`` — change within the allowed limit (Good).
        - ``1`` — change exceeds the limit (Suspect spike).

    Notes
    -----
    The gap-aware logic estimates the typical sampling interval as the
    median of all consecutive time differences. Differences larger than
    3 times that median are treated as legitimate data gaps rather than
    physical spikes and are excluded from flagging. For 4-second chamber
    data this means jumps across gaps longer than 12 seconds are never
    flagged as spikes; for 15-minute soil data the threshold is 45
    minutes.

    Examples
    --------
    >>> import pandas as pd
    >>> idx = pd.date_range("2024-01-01", periods=5, freq="4s")
    >>> df = pd.DataFrame({"CO2_C1": [400.0, 401.0, 500.0, 402.0, 403.0]}, index=idx)
    >>> cfg = {"rate_of_change": {"limit": 20.0}}
    >>> flags = apply_rate_of_change_flags(df, "CO2_C1", cfg)
    >>> flags.tolist()
    [0, 0, 1, 1, 0]
    """
    flags = pd.Series(0, index=df.index)

    # Skip if variable not in dataframe or config not present
    if var_name not in df.columns or "rate_of_change" not in config:
        return flags

    roc_limit = config["rate_of_change"].get("limit")
    if roc_limit is None:
        return flags

    # Ensure numeric data
    data_numeric = pd.to_numeric(df[var_name], errors="coerce")

    # Get non-null mask
    valid_mask = data_numeric.notna()

    # Calculate absolute difference
    # Note: We use .diff().abs() which calculates difference with previous row
    diff = data_numeric.diff().abs()

    # Calculate time difference to handle gaps (e.g. chamber open periods)
    # We shouldn't flag a large change if it happened over 5 minutes
    if isinstance(df.index, pd.DatetimeIndex):
        time_diff = df.index.to_series().diff().dt.total_seconds()

        # Estimate typical sampling interval (median)
        # 4s for chamber, 15m (900s) for soil
        typical_interval = time_diff.median()

        # Allow gaps up to 3x typical interval before ignoring RoC check
        # For 4s data, ignore gaps > 12s. For 900s data, ignore gaps > 2700s.
        # This prevents flagging the return from a 5-min gap as a spike.
        valid_time_mask = time_diff <= (typical_interval * 3)
        valid_time_mask = valid_time_mask.fillna(True)  # First point has NaT diff

        exceeds_limit = (diff > roc_limit) & valid_time_mask
    else:
        # Fallback if no datetime index
        exceeds_limit = diff > roc_limit

    flags[valid_mask & exceeds_limit] = 1

    return flags


def apply_persistence_flags(df, var_name, config):
    """Flag rows where a variable shows no meaningful variation (flat line).

    Computes the rolling max-minus-min range over a backward-looking
    time window and flags rows where that range is at or below an
    epsilon threshold. A persistently flat sensor reading usually
    indicates a stuck analogue output, a disconnected probe, or a
    data-logger averaging artefact.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed sensor data with a ``pd.DatetimeIndex`` (required
        for the time-based rolling window). Must contain at least the
        column ``var_name``. Non-numeric values are coerced to ``NaN``.
    var_name : str
        Name of the column in ``df`` to check
        (e.g. ``"CO2_C1"``, ``"SWC_C1_5cm"``).
    config : dict
        Variable config dict. Recognised key:

        ``"persistence"`` : dict, optional
            Sub-dict with:

            ``"window_hours"`` : float
                Rolling window length in hours. If missing the check is
                skipped and all flags return 0.
            ``"epsilon"`` : float, optional
                Maximum range (max - min) that is still considered flat.
                Default ``0.0`` (exact equality required). Set higher
                for noisy sensors, e.g. ``0.01`` for SWC.

    Returns
    -------
    pd.Series
        Integer flag series aligned to ``df.index``:

        - ``0`` — normal variation within the window (Good).
        - ``1`` — range within the window is <= epsilon (Suspect flat).

    Notes
    -----
    A row is flagged when the *entire backward-looking window ending at
    that row* had suspiciously low variation. This means the flag
    appears at the end of a flat sequence, not at its start.
    Short sequences at the beginning of a file that are shorter than
    ``window_hours`` use ``min_periods=1`` and may receive false positives
    if the variable genuinely does not change during the initial window.

    Examples
    --------
    >>> import pandas as pd
    >>> idx = pd.date_range("2024-01-01", periods=6, freq="30min")
    >>> vals = [400.0, 400.0, 400.0, 400.0, 400.0, 500.0]
    >>> df = pd.DataFrame({"CO2_C1": vals}, index=idx)
    >>> cfg = {"persistence": {"window_hours": 1.5, "epsilon": 0.01}}
    >>> flags = apply_persistence_flags(df, "CO2_C1", cfg)
    >>> flags.tolist()
    [1, 1, 1, 1, 1, 0]
    """
    flags = pd.Series(0, index=df.index)

    # Skip if variable not in dataframe or config not present
    if var_name not in df.columns or "persistence" not in config:
        return flags

    persist_config = config["persistence"]
    window_hours = persist_config.get("window_hours")
    epsilon = persist_config.get("epsilon", 0.0)

    if window_hours is None:
        return flags

    # Ensure numeric data
    data_numeric = pd.to_numeric(df[var_name], errors="coerce")

    # Get non-null data
    valid_mask = data_numeric.notna()

    # We'll use rolling standard deviation or range to detect flatness
    # Since data is likely 4-second (or monthly integrated?), we need to know the frequency.
    # We are working with the dataframe passed in.

    # Convert window_hours to number of periods if possible, or use time-based rolling
    # Pandas rolling support time offsets string 'H'

    try:
        # Calculate rolling min and max
        # If max - min <= epsilon over the window, it's a flat line.

        # Use simple 'min_periods' to avoid flagging start of file if less than window
        indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=0)
        # Wait, we want backward looking? "Has been flat for X hours"

        window_str = f"{window_hours}h"

        # Calculate rolling min and max
        # If max - min <= epsilon over the window, it's a flat line.

        # Use simple 'min_periods' to avoid flagging start of file if less than window
        indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=0)
        # Wait, we want backward looking? "Has been flat for X hours"

        window_str = f"{window_hours}h"

        rolling_max = data_numeric.rolling(window_str, min_periods=1).max()
        rolling_min = data_numeric.rolling(window_str, min_periods=1).min()

        range_val = rolling_max - rolling_min

        # Current logic: If range of *past* window is small, flag the *current* point?
        # Usually we flag the whole window. But flagging current point if "it is part of a flat line ending now"
        # checks if *past* X hours were flat.

        is_flat = range_val <= epsilon

        # However, we only settle for "flagging the points that are part of the flat sequence"
        # The rolling check above flags the end of a flat sequence.
        # But if the window is 2 hours, and it's flat, `is_flat` will be True at the end.

        # Let's perform a vectorized apply? Or just stick to this simple definition:
        # "This data point is suspect because the variance over the last X hours (including it) was suspiciously low."

        flags[valid_mask & is_flat] = 1

    except Exception as e:
        print(f"  Warning: Persistence check failed for {var_name}: {str(e)}")

    return flags


def apply_battery_proxy_flags(df, battery_proxy_config):
    """Propagate data-logger battery health flags to dependent measurements.

    For each configured battery sensor column: when the battery voltage
    falls below a warning threshold, dependent measurement variables are
    elevated to Suspect (flag 1); below a bad threshold they are elevated
    to Bad (flag 2). Existing flag 2 values are never demoted.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing battery voltage columns and, for each
        target variable, both a ``{var}_rule_flag`` column and
        optionally a ``{var}_qc_flag`` column. Modified in place.
    battery_proxy_config : dict
        The ``"battery_proxy"`` section from the variable config JSON.
        Expected structure::

            {
              "sensors": {
                "<batt_col>": {
                  "warn_below": <float>,
                  "bad_below": <float>,
                  "targets": ["<var1>", "<var2>", ...]
                },
                ...
              }
            }

        Where:

        ``"<batt_col>"`` : str
            Column name of the battery voltage sensor
            (e.g. ``"BattV_Min"``).
        ``"warn_below"`` : float
            Voltage threshold in volts below which target flags are
            elevated to 1 (Suspect).
        ``"bad_below"`` : float
            Voltage threshold in volts below which target flags are
            elevated to 2 (Bad).
        ``"targets"`` : list of str
            Variable names whose ``{var}_rule_flag`` columns are updated
            when the battery voltage is low.

    Returns
    -------
    dict
        ``{batt_col: {"warn_count": int, "bad_count": int,
        "targets_updated": list}}`` — one entry per configured battery
        sensor, reporting how many rows were affected at each severity
        level and which target variables were updated.

    Notes
    -----
    Battery-voltage proxy flagging matters in the whole-tree chamber
    setup because the data-logger (CR1000X) runs from a 12 V sealed
    lead-acid battery charged by a small solar panel. During cloudy
    multi-day periods the battery can drop enough to cause the LI-850
    to produce noisy or clipped readings before the logger shuts down.
    Flagging those measurements proactively prevents erroneous
    flux estimates.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "BattV_Min": [12.5, 11.5, 10.8],
    ...     "CO2_C1_rule_flag": [0, 0, 0],
    ...     "CO2_C1_qc_flag":   [0, 0, 0],
    ... })
    >>> batt_cfg = {
    ...     "sensors": {
    ...         "BattV_Min": {
    ...             "warn_below": 11.8,
    ...             "bad_below": 11.0,
    ...             "targets": ["CO2_C1"],
    ...         }
    ...     }
    ... }
    >>> result = apply_battery_proxy_flags(df, batt_cfg)
    >>> df["CO2_C1_rule_flag"].tolist()
    [0, 1, 2]
    >>> result["BattV_Min"]["warn_count"]
    2
    """
    summary = {}
    sensors = battery_proxy_config.get("sensors", {})

    for batt_col, cfg in sensors.items():
        if batt_col not in df.columns:
            continue

        warn_below = cfg["warn_below"]
        bad_below = cfg["bad_below"]
        targets = cfg.get("targets", [])

        batt = pd.to_numeric(df[batt_col], errors="coerce")
        warn_mask = batt < warn_below
        bad_mask = batt < bad_below

        warn_count = int(warn_mask.sum())
        bad_count = int(bad_mask.sum())
        updated_targets = []

        for tgt in targets:
            flag_col = f"{tgt}_rule_flag"
            if flag_col not in df.columns:
                continue
            # Elevate: warn → 1, bad → 2; never demote existing flags
            df.loc[warn_mask & (df[flag_col] < 1), flag_col] = 1
            df.loc[bad_mask & (df[flag_col] < 2), flag_col] = 2
            # Keep qc_flag in sync
            qc_col = f"{tgt}_qc_flag"
            if qc_col in df.columns:
                df[qc_col] = df[[flag_col, qc_col]].max(axis=1)
            updated_targets.append(tgt)

        summary[batt_col] = {
            "warn_count": warn_count,
            "bad_count": bad_count,
            "targets_updated": updated_targets,
        }

    return summary


# ── Sensor exclusion windows ─────────────────────────────────────────────────


def _load_sensor_exclusions(config_path=None):
    """Load sensor exclusion windows from YAML config.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to sensor_exclusions.yaml. Defaults to config/sensor_exclusions.yaml
        relative to the project root.

    Returns
    -------
    dict
        ``{column_name: [{"start": str, "end": str, "flag": int, "reason": str, "source": str}, ...]}``
        Empty dict if file not found.
    """
    import yaml
    from pathlib import Path

    if config_path is None:
        # Resolve project root: walk up from this file's directory
        here = Path(__file__).resolve().parent.parent
        config_path = here / "config" / "sensor_exclusions.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        return {}

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return raw.get("sensor_exclusions", {}) if raw else {}


def apply_sensor_exclusion_flags(df, var_name, config_path=None):
    """Flag rows that fall inside a sensor maintenance or swap-out window.

    Reads exclusion windows from ``config/sensor_exclusions.yaml`` and
    flags every row whose timestamp is inside any window defined for
    ``var_name``. This step is applied before other QC rules so that
    hardware-verified bad periods are always marked Bad (flag 2)
    regardless of what the IQR or physical-bounds checks produce.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a ``pd.DatetimeIndex``. Row timestamps are
        compared directly against window boundaries.
    var_name : str
        Column name to look up in the exclusion config
        (e.g. ``"CO2_C1"``).
    config_path : str or Path, optional
        Override path to ``sensor_exclusions.yaml``. If ``None``, the
        file is resolved relative to the package ``config/`` directory.

    Returns
    -------
    pd.Series
        Integer flag series aligned to ``df.index``:

        - ``0`` — no exclusion window applies.
        - ``1`` or ``2`` — per the ``flag`` field in the YAML config
          (most windows use ``2`` for Bad).

    Notes
    -----
    Exclusion windows are inclusive on both start and end dates (end date
    extended to 23:59:59 to cover sub-daily data). Within each window,
    flags are only ever elevated — existing higher flags are preserved.

    The YAML config structure for one variable::

        sensor_exclusions:
          CO2_C1:
            - start: "2024-03-10"
              end:   "2024-03-14"
              flag:  2
              reason: "Sensor removed for cleaning"
              source: "manual"

    Examples
    --------
    >>> import pandas as pd
    >>> import tempfile, os, textwrap
    >>> yaml_txt = textwrap.dedent('''
    ...     sensor_exclusions:
    ...       CO2_C1:
    ...         - start: "2024-01-02"
    ...           end:   "2024-01-02"
    ...           flag:  2
    ...           reason: "test"
    ...           source: "manual"
    ... ''')
    >>> with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
    ...     _ = f.write(yaml_txt)
    ...     tmp = f.name
    >>> idx = pd.date_range("2024-01-01", periods=3, freq="1D")
    >>> df = pd.DataFrame({"CO2_C1": [400.0, 500.0, 410.0]}, index=idx)
    >>> flags = apply_sensor_exclusion_flags(df, "CO2_C1", config_path=tmp)
        Exclusion: CO2_C1 2024-01-02 → 2024-01-02 (flag=2, 1 rows) — test
    >>> flags.tolist()
    [0, 2, 0]
    >>> os.unlink(tmp)
    """
    exclusions = _load_sensor_exclusions(config_path)
    flags = pd.Series(0, index=df.index)
    windows = exclusions.get(var_name, [])
    if not windows:
        return flags

    for win in windows:
        start = pd.to_datetime(win["start"])
        end = pd.to_datetime(win["end"]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        flag_val = int(win.get("flag", 2))
        mask = (df.index >= start) & (df.index <= end)
        n_hit = int(mask.sum())
        if n_hit > 0:
            # Only elevate within the mask window, never demote
            flags.loc[mask] = np.maximum(flags.loc[mask], flag_val)
            reason = win.get("reason", "")
            print(
                f"    Exclusion: {var_name} {win['start']} → {win['end']} "
                f"(flag={flag_val}, {n_hit:,} rows) — {reason}"
            )

    return flags


def generate_exclusion_recommendations(
    audit_path=None, config_path=None, agreement_threshold=0.3, write=False
):
    """Auto-detect exclusion windows from a cross-chamber agreement audit.

    Reads a regime-audit CSV that records per-regime cross-chamber
    agreement scores and drift-slope warnings. Identifies regimes where
    agreement is poor, merges contiguous bad regimes into date windows,
    and returns per-sensor exclusion recommendations. Optionally writes
    the merged recommendations to ``config/sensor_exclusions.yaml``
    while preserving any ``source: "manual"`` entries already there.

    Parameters
    ----------
    audit_path : str or Path, optional
        Path to the regime audit CSV
        (e.g. ``Data/Integrated_QC_Data/026_regime_audit.csv``).
        Auto-resolved relative to the package root if ``None``.
    config_path : str or Path, optional
        Path to ``sensor_exclusions.yaml`` for writing. Auto-resolved
        relative to the package root if ``None``.
    agreement_threshold : float, optional
        Regimes with ``agreement_score < threshold`` OR
        ``slope_warning=True`` are considered bad. Default ``0.3``.
    write : bool, optional
        If ``True``, write merged recommendations to the YAML config
        file (preserving ``source: "manual"`` entries). Default
        ``False`` (dry-run, returns dict only).

    Returns
    -------
    dict
        ``{sensor_col: [{"start": str, "end": str, "flag": 2,
        "reason": str, "regimes": list, "source": "026_regime_audit"},
        ...]}``

        Where ``sensor_col`` is the chamber column to exclude
        (e.g. ``"CO2_C2"``), ``"start"`` and ``"end"`` are
        ``"YYYY-MM-DD"`` strings covering the merged bad window, and
        ``"regimes"`` is a list of per-regime metadata dicts.

    Notes
    -----
    The regime audit CSV is expected to have at least these columns:
    ``agreement_score``, ``slope_warning``, ``start``, ``end``,
    ``variable``, ``reference``, ``regime``, ``slope``.

    The ``reference`` column indicates which chamber had the more
    reliable reading during that regime. The *other* chamber's column is
    the one recommended for exclusion.

    Contiguous regimes (gap <= 1 day) are merged into a single window to
    avoid fragmented exclusion entries.

    Examples
    --------
    >>> generate_exclusion_recommendations(
    ...     audit_path="/path/to/026_regime_audit.csv",
    ...     agreement_threshold=0.3,
    ...     write=False,
    ... )  # doctest: +SKIP
    {}
    """
    import yaml
    from pathlib import Path

    here = Path(__file__).resolve().parent.parent
    if audit_path is None:
        audit_path = here / "Data" / "Integrated_QC_Data" / "026_regime_audit.csv"
    else:
        audit_path = Path(audit_path)

    if not audit_path.exists():
        print(f"  026 regime audit not found: {audit_path}")
        return {}

    audit = pd.read_csv(audit_path)

    # Identify bad regimes
    bad_mask = (audit["agreement_score"] < agreement_threshold) | (audit["slope_warning"] == True)
    bad = audit[bad_mask].copy()

    if bad.empty:
        print("  No bad regimes detected.")
        return {}

    # Map variable + reference → sensor column to exclude
    # reference = the good chamber → exclude the other one
    def _non_ref_col(row):
        ref = row.get("reference", "C1")
        other = "C2" if ref == "C1" else "C1"
        return f"{row['variable']}_{other}"

    bad["sensor_col"] = bad.apply(_non_ref_col, axis=1)
    bad["start"] = pd.to_datetime(bad["start"])
    bad["end"] = pd.to_datetime(bad["end"])

    recommendations = {}

    for sensor_col, group in bad.groupby("sensor_col"):
        group = group.sort_values("start")

        # Merge contiguous/overlapping regimes into windows
        windows = []
        for _, row in group.iterrows():
            regime_info = {
                "regime": int(row["regime"]),
                "slope": float(row["slope"]),
                "agreement_score": float(row["agreement_score"]),
                "slope_warning": bool(row["slope_warning"]),
            }
            if windows and row["start"] <= windows[-1]["end"] + pd.Timedelta(days=1):
                # Extend current window
                windows[-1]["end"] = max(windows[-1]["end"], row["end"])
                windows[-1]["regimes"].append(regime_info)
            else:
                windows.append(
                    {
                        "start": row["start"],
                        "end": row["end"],
                        "regimes": [regime_info],
                    }
                )

        sensor_recs = []
        for win in windows:
            regime_ids = [r["regime"] for r in win["regimes"]]
            avg_score = np.mean([r["agreement_score"] for r in win["regimes"]])
            has_warning = any(r["slope_warning"] for r in win["regimes"])
            reason_parts = [f"026 regimes {','.join(map(str, regime_ids))}"]
            reason_parts.append(f"avg agreement={avg_score:.2f}")
            if has_warning:
                reason_parts.append("slope_warning=True")
            sensor_recs.append(
                {
                    "start": win["start"].strftime("%Y-%m-%d"),
                    "end": win["end"].strftime("%Y-%m-%d"),
                    "flag": 2,
                    "reason": "; ".join(reason_parts),
                    "regimes": win["regimes"],
                    "source": "026_regime_audit",
                }
            )
        recommendations[sensor_col] = sensor_recs

    # Print summary
    for sensor, recs in recommendations.items():
        for r in recs:
            n_regimes = len(r["regimes"])
            print(
                f"  Recommend exclude {sensor}: {r['start']} → {r['end']} "
                f"({n_regimes} regime{'s' if n_regimes > 1 else ''}) — {r['reason']}"
            )

    if write:
        if config_path is None:
            config_path = here / "config" / "sensor_exclusions.yaml"
        else:
            config_path = Path(config_path)

        # Preserve manual entries from existing config
        existing = _load_sensor_exclusions(config_path)
        manual_entries = {}
        for col, entries in existing.items():
            manual = [e for e in entries if e.get("source") == "manual"]
            if manual:
                manual_entries[col] = manual

        # Build new config: auto-detected + manual
        merged = {}
        for col, recs in recommendations.items():
            merged[col] = [{k: v for k, v in r.items() if k != "regimes"} for r in recs]
        for col, entries in manual_entries.items():
            merged.setdefault(col, []).extend(entries)

        # Write with header comment
        from datetime import date

        header = (
            "# Sensor-level date exclusion windows.\n"
            "# Data in these windows is flagged in notebook 020 and excluded from downstream.\n"
            "#\n"
            "# " + "=" * 75 + "\n"
            "# HOW TO ADD A MANUAL EXCLUSION:\n"
            "#   1. Add an entry under the sensor name (e.g. CO2_C1, H2O_C2, Temp_1_C1)\n"
            '#   2. Required fields: start, end, flag (1=suspect, 2=bad), reason, source: "manual"\n'
            "#   3. Run notebook 025 Section 2c to verify the exclusion with evidence plots\n"
            "#   4. Re-run notebook 020 to apply flags to downstream pipeline\n"
            "#\n"
            "# HOW TO ADD AN AUTO-DETECTED EXCLUSION:\n"
            "#   1. Run notebook 026 (generates 026_regime_audit.csv)\n"
            "#   2. Run notebook 025 Section 2c (auto-recommends windows from audit)\n"
            '#   3. Review evidence plots, then run the "Write config" cell to commit\n'
            "#\n"
            "# HOW TO REMOVE AN EXCLUSION:\n"
            "#   1. Delete or comment out the entry below\n"
            "#   2. Re-run notebook 020 to re-flag data\n"
            "#\n"
            "# " + "=" * 75 + "\n"
            "# FIELDS:\n"
            "#   start  : First date to exclude (inclusive), format YYYY-MM-DD\n"
            "#   end    : Last date to exclude (inclusive), format YYYY-MM-DD\n"
            "#   flag   : QC flag: 2 = bad (excluded from all), 1 = suspect\n"
            "#   reason : Human-readable justification\n"
            '#   source : "026_regime_audit" (auto) or "manual" (hand-added)\n'
            "# " + "=" * 75 + "\n"
            f"#\n# Last updated: {date.today().isoformat()}\n\n"
        )

        yaml_body = yaml.dump(
            {"sensor_exclusions": merged},
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        with open(config_path, "w") as f:
            f.write(header)
            f.write(yaml_body)

        print(f"\n  Written to {config_path}")

    return recommendations


def process_variable_qc(
    df,
    var_name,
    var_config_dict,
    random_seed=None,
    skip_persistence_for=None,
    skip_rate_of_change_for=None,
    use_sensor_exclusions=True,
    exclusion_config_path=None,
):
    """Run all QC rule checks for one variable and return combined flags.

    Orchestrates the full QC pipeline in order:

    1. Sensor exclusion windows (optional; flag 2 never demoted).
    2. Physical bounds (hard and soft limits).
    3. IQR-based outlier detection.
    4. Rate-of-change (spike) detection.
    5. Persistence (flat-line) detection.
    6. Combine all flags into a single worst-case flag per row.

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed sensor data. Must contain at least the column
        ``var_name``. Non-numeric values in ``var_name`` are coerced to
        ``NaN``.
    var_name : str
        Name of the column in ``df`` to process
        (e.g. ``"CO2_C1"``, ``"SWC_C1_15cm"``).
    var_config_dict : dict
        Variable configuration dictionary (typically from
        ``variable_config.json``). Passed to ``get_variable_config``
        to look up the per-variable config block.
    random_seed : int, optional
        Accepted for API compatibility but not used. Has no effect.
    skip_persistence_for : list of str, optional
        If ``var_name`` is in this list, the persistence check is
        skipped and its flags default to 0. Useful for variables with
        naturally flat periods (e.g. soil temperature at depth).
    skip_rate_of_change_for : list of str, optional
        If ``var_name`` is in this list, the rate-of-change check is
        skipped and its flags default to 0. Useful for variables where
        fast step-changes are physically expected (e.g. chamber CO₂
        at cycle transitions).
    use_sensor_exclusions : bool, optional
        If ``True``, load and apply date-range exclusion windows from
        ``config/sensor_exclusions.yaml`` before other QC checks.
        Default ``False``.
    exclusion_config_path : str or Path, optional
        Override path to ``sensor_exclusions.yaml``. Only used when
        ``use_sensor_exclusions=True``.

    Returns
    -------
    dict
        Dictionary with the following keys:

        ``"final_flags"`` : pd.Series
            Combined worst-case flag (0, 1, or 2) for each row.
        ``"exclusion_flags"`` : pd.Series
            Flags from sensor exclusion windows (0, 1, or 2).
        ``"bounds_flags"`` : pd.Series
            Flags from physical bounds check (0, 1, or 2).
        ``"iqr_flags"`` : pd.Series
            Flags from IQR outlier check (0 or 1).
        ``"roc_flags"`` : pd.Series
            Flags from rate-of-change check (0 or 1).
        ``"persistence_flags"`` : pd.Series
            Flags from persistence check (0 or 1).
        ``"summary"`` : dict
            Counts and percentages per flag level from
            ``generate_qc_summary``.
        ``"config"`` : dict
            The variable config block that was used (absent when no
            config was found for ``var_name``).

    Notes
    -----
    When no config is found for ``var_name`` in ``var_config_dict``, a
    warning is printed and all flag series are returned as zeros (no
    filtering applied). This allows the pipeline to proceed even for
    variables without explicit configuration.

    Examples
    --------
    >>> import pandas as pd
    >>> idx = pd.date_range("2024-01-01", periods=5, freq="4s")
    >>> df = pd.DataFrame({"CO2_C1": [400.0, 405.0, 402.0, 410.0, 50000.0]}, index=idx)
    >>> cfg = {
    ...     "co2": {
    ...         "columns": ["CO2_C1"],
    ...         "hard": [0.0, 20000.0],
    ...         "soft": [350.0, 2000.0],
    ...     }
    ... }
    >>> result = process_variable_qc(df, "CO2_C1", cfg)
    >>> result["final_flags"].tolist()
    [0, 0, 0, 0, 2]
    """
    # Get configuration
    config = get_variable_config(var_name, var_config_dict)

    if config is None:
        print(f"  Warning: No configuration found for {var_name}")
        # Return default flags (all zeros)
        flags = pd.Series(0, index=df.index)
        return {
            "final_flags": flags,
            "exclusion_flags": flags.copy(),
            "bounds_flags": flags.copy(),
            "iqr_flags": flags.copy(),
            "roc_flags": flags.copy(),
            "persistence_flags": flags.copy(),
            "summary": generate_qc_summary(
                pd.DataFrame({f"{var_name}_rule_flag": flags}), f"{var_name}_rule_flag"
            ),
        }

    # Step 0: Apply sensor exclusion windows (before other checks)
    if use_sensor_exclusions:
        exclusion_flags = apply_sensor_exclusion_flags(df, var_name, exclusion_config_path)
    else:
        exclusion_flags = pd.Series(0, index=df.index)

    # Apply physical bounds flagging
    bounds_flags = apply_physical_bounds_flags(df, var_name, config)

    # Apply IQR flagging
    iqr_factor = config.get("iqr_factor", 1.5)
    iqr_flags = apply_iqr_flags(df, var_name, iqr_factor)

    # Apply Rate of Change flagging
    if skip_rate_of_change_for is not None and var_name in skip_rate_of_change_for:
        print(f"  Skipping Rate of Change check for {var_name}")
        roc_flags = pd.Series(0, index=df.index)
    else:
        roc_flags = apply_rate_of_change_flags(df, var_name, config)

    # Apply Persistence flagging
    if skip_persistence_for is not None and var_name in skip_persistence_for:
        print(f"  Skipping Persistence check for {var_name}")
        persistence_flags = pd.Series(0, index=df.index)
    else:
        persistence_flags = apply_persistence_flags(df, var_name, config)

    # Combine flags (exclusion_flags take priority — flag=2 never demoted)
    final_flags = combine_qc_flags(bounds_flags, iqr_flags, roc_flags, persistence_flags)
    final_flags = np.maximum(final_flags, exclusion_flags)

    # Generate summary
    summary_df = pd.DataFrame({f"{var_name}_rule_flag": final_flags})
    summary = generate_qc_summary(summary_df, f"{var_name}_rule_flag")

    return {
        "final_flags": final_flags,
        "exclusion_flags": exclusion_flags,
        "bounds_flags": bounds_flags,
        "iqr_flags": iqr_flags,
        "roc_flags": roc_flags,
        "persistence_flags": persistence_flags,
        "summary": summary,
        "config": config,
    }


def add_cycle_id(df, time_col="TIMESTAMP", gap_threshold_sec=300):
    """Assign a sequential cycle ID to rows based on time gaps.

    A new measurement cycle begins whenever the time difference between
    consecutive rows exceeds ``gap_threshold_sec`` seconds. In the
    whole-tree chamber setup, each automated flux measurement cycle is
    separated from the next by a ventilation period during which the
    chamber is open; those open periods create gaps in the logged data.

    Parameters
    ----------
    df : pd.DataFrame
        Sensor data. The function works with either a ``TIMESTAMP``
        column (or another column given by ``time_col``) or a
        ``pd.DatetimeIndex``. If neither is present a warning is printed
        and ``df`` is returned unchanged.
    time_col : str, optional
        Name of the timestamp column. Default ``"TIMESTAMP"``.
    gap_threshold_sec : float, optional
        Minimum gap duration in seconds that triggers a new cycle ID.
        Default ``300`` (5 minutes). Set lower for higher-frequency data
        or shorter ventilation periods.

    Returns
    -------
    pd.DataFrame
        Copy of ``df`` with an added integer column ``"cycle_id"``
        starting at 1 and incrementing at each detected gap.

    Notes
    -----
    The first row always starts cycle 1 (its time-diff is ``NaT``/NaN).
    Cycle IDs are contiguous integers; they do not encode absolute time
    or date.

    Examples
    --------
    >>> import pandas as pd
    >>> idx = pd.date_range("2024-01-01", periods=6, freq="4s")
    >>> df = pd.DataFrame({"CO2_C1": [400.0] * 6}, index=idx)
    >>> df_with_gap = pd.concat([df.iloc[:3], df.iloc[3:].shift(freq="10min")])
    >>> result = add_cycle_id(df_with_gap)
    >>> result["cycle_id"].tolist()
    [1, 1, 1, 2, 2, 2]
    """
    if df.empty:
        return df

    df = df.copy()
    if time_col not in df.columns:
        # Try finding a datetime index
        if isinstance(df.index, pd.DatetimeIndex):
            timestamps = pd.Series(df.index, index=df.index)
        else:
            print(f"Warning: {time_col} not found and index is not DatetimeIndex.")
            return df
    else:
        timestamps = df[time_col]

    # Calculate time gaps
    # Ensure timestamps are datetime objects
    if not pd.api.types.is_datetime64_any_dtype(timestamps):
        timestamps = pd.to_datetime(timestamps)

    delta_t = timestamps.diff().dt.total_seconds()

    # Identify new cycles
    new_cycle = (delta_t > gap_threshold_sec) | (delta_t.isna())
    df["cycle_id"] = new_cycle.cumsum()

    return df
