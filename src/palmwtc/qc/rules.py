"""Rule-based QC flag application.

Ported verbatim from ``flux_chamber/src/qc_functions.py`` (Phase 2).
Behaviour preservation is the prime directive: function signatures and bodies
match the original to 1e-12. Internal cross-module references inside the
``palmwtc.qc`` subpackage now resolve via ``palmwtc.qc.*``.

Multi-level flagging system (0-2) using physical bounds, IQR, rate-of-change,
persistence, battery proxy, and date-range exclusion windows.

Example:
    >>> import pandas as pd  # doctest: +SKIP
    >>> from palmwtc.qc import process_variable_qc  # doctest: +SKIP
    >>>
    >>> # Process QC (bounds, IQR, RoC, persistence)
    >>> results = process_variable_qc(df, 'AirTC_Avg', config)  # doctest: +SKIP
"""

# ruff: noqa: B007, E712, F841, I001, RUF010
# Above ignores cover quirks carried verbatim from the original
# ``flux_chamber/src/qc_functions.py`` to honour the Phase 2 "behaviour
# preservation" rule:
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
    """
    Apply physical bounds flagging (hard and soft limits).

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing the variable column
    var_name : str
        Variable column name
    config : dict
        Variable configuration with 'hard' and 'soft' bounds

    Returns:
    --------
    pd.Series
        Quality flags (0, 1, or 2)
        - 0: Within soft bounds (good)
        - 1: Outside soft bounds but within hard bounds (suspect)
        - 2: Outside hard bounds (bad)
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
    """
    Apply IQR-based outlier flagging.

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing the variable column
    var_name : str
        Variable column name
    iqr_factor : float
        Multiplier for IQR to define outliers (default 1.5)

    Returns:
    --------
    pd.Series
        Quality flags for IQR check (0 or 1)
        - 0: Within IQR bounds (good)
        - 1: Outside IQR bounds (suspect outlier)
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
    """
    Combine multiple QC flags into final quality flag.

    Priority order:
    1. Physical bounds (can set flag to 2)
    2. Rate of Change (can elevate flag to 1)
    3. IQR, Persistence (elevate to 1)

    Parameters:
    -----------
    bounds_flags : pd.Series
        Flags from physical bounds check (0, 1, or 2)
    iqr_flags : pd.Series
        Flags from IQR check (0, 1)
    roc_flags : pd.Series, optional
        Flags from Rate of Change check (0, 1)
    persistence_flags : pd.Series, optional
        Flags from Persistence check (0, 1)

    Returns:
    --------
    pd.Series
        Combined quality flags (0, 1, or 2)
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
    """
    Generate summary statistics for quality flags.

    Parameters:
    -----------
    df : pd.DataFrame
        Data with quality flag column
    flag_column : str
        Name of the quality flag column

    Returns:
    --------
    dict
        Summary statistics including counts and percentages for each flag level
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
    """
    Get configuration for a specific variable.

    Handles both direct column names and pattern-based variables (e.g., soil sensors).

    Parameters:
    -----------
    var_name : str
        Variable column name
    var_config_dict : dict
        Variable configuration dictionary

    Returns:
    --------
    dict or None
        Configuration for the variable, or None if not found
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
    """
    Apply Rate of Change (RoC) flagging.

    Checks if the absolute difference between consecutive values exceeds a limit.

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing the variable column
    var_name : str
        Variable column name
    config : dict
        Variable configuration with 'rate_of_change' settings

    Returns:
    --------
    pd.Series
        Quality flags (0 or 1)
        - 0: Within rate of change limit (good)
        - 1: Exceeds rate of change limit (suspect)
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
    """
    Apply Persistence (Flat Line) flagging.

    Checks if values remain within a small epsilon range for a specified duration.

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing the variable column (must have DatetimeIndex)
    var_name : str
        Variable column name
    config : dict
        Variable configuration with 'persistence' settings

    Returns:
    --------
    pd.Series
        Quality flags (0 or 1)
        - 0: Normal variation (good)
        - 1: Persistently flat (suspect)
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
    """
    Propagate battery-low flags to measurement variables.

    For each configured battery sensor: where battery voltage < bad_below,
    elevate target variable rule_flags to 2; where < warn_below, elevate to 1.
    Existing Flag 2 values on targets are never demoted.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with battery columns and {var}_rule_flag / {var}_qc_flag columns (modified in place).
    battery_proxy_config : dict
        The 'battery_proxy' section from variable_config.json.

    Returns
    -------
    dict
        {sensor_col: {'warn_count': int, 'bad_count': int, 'targets_updated': list}}
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
    """Return a flag Series for date-range exclusion windows.

    Reads ``config/sensor_exclusions.yaml`` and flags rows whose index falls
    inside any exclusion window defined for *var_name*.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a DatetimeIndex.
    var_name : str
        Column name to look up (e.g. ``'CO2_C1'``).
    config_path : str or Path, optional
        Override path to the YAML config.

    Returns
    -------
    pd.Series
        Integer flags (0 = no exclusion, 1 or 2 per config).
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
    """Auto-detect exclusion windows from 026 regime audit.

    Reads ``026_regime_audit.csv``, identifies regimes where cross-chamber
    agreement is poor, merges contiguous bad regimes, and returns
    recommendations.  Optionally writes to ``config/sensor_exclusions.yaml``
    (preserving ``source: "manual"`` entries).

    Parameters
    ----------
    audit_path : str or Path, optional
        Path to 026_regime_audit.csv. Auto-resolved if None.
    config_path : str or Path, optional
        Path to sensor_exclusions.yaml for writing. Auto-resolved if None.
    agreement_threshold : float
        Regimes with ``agreement_score < threshold`` OR ``slope_warning=True``
        are flagged.
    write : bool
        If True, write merged recommendations to YAML config.

    Returns
    -------
    dict
        ``{sensor_col: [{"start": str, "end": str, "flag": 2,
          "reason": str, "regimes": list, "source": "026_regime_audit"}, ...]}``
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
    use_sensor_exclusions=False,
    exclusion_config_path=None,
):
    """
    Process all QC checks for a single variable.

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing the variable
    var_name : str
        Variable column name
    var_config_dict : dict
        Variable configuration dictionary
    random_seed : int, optional
        Kept for API compatibility, not used.
    use_sensor_exclusions : bool
        If True, apply sensor exclusion windows from config/sensor_exclusions.yaml
        as the first QC step. Flag=2 exclusions can never be demoted.
    exclusion_config_path : str or Path, optional
        Override path to sensor_exclusions.yaml.

    Returns:
    --------
    dict
        Dictionary containing all QC results and summary statistics
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
    """
    Adds a 'cycle_id' column to the DataFrame based on time gaps.
    A new cycle is computed if the time difference is > gap_threshold_sec.
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
