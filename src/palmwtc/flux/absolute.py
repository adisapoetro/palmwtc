# ruff: noqa: RUF002, RUF059, SIM108
"""Absolute flux primitives — CO2 and H2O.

Behaviour-preserving port of the absolute-flux helpers from
``flux_chamber/src/flux_analysis.py``. Function bodies are byte-equivalent;
only ``import`` statements and module location have changed.

Public API:
    - ``calculate_absolute_flux(row)`` — CO2 flux (umol m-2 s-1)
    - ``calculate_h2o_absolute_flux(row)`` — H2O flux (mmol m-2 s-1)
    - ``calculate_flux_for_chamber(...)`` — cycle-level slope + flux convenience
      (legacy; not used by the active 030/033/080 pipeline but retained for
      parity with the original module's public surface)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import linregress
from tqdm.notebook import tqdm


def calculate_absolute_flux(row):
    """
    Calculates absolute CO2 flux (umol m-2 s-1) from slope (ppm/s).
    Adjusts for chamber dimensions based on date.
    """
    # Constants
    R = 8.314  # J/(mol K)
    P_std = 101325  # Pa

    # Temperature (Kelvin)
    # Use 'mean_temp' if available, else default to 25C
    if "mean_temp" in row and pd.notnull(row["mean_temp"]):
        T_c = row["mean_temp"]
    else:
        T_c = 25.0
    T_k = T_c + 273.15

    # Chamber Dimensions
    if "flux_date" not in row:
        # Fallback if flux_date is missing, though it should be there
        return np.nan

    date = row["flux_date"]
    cutoff_date = pd.Timestamp("2025-07-01")

    # V/A Ratio (Effective Height)
    if date < cutoff_date:
        # Before July 2025: 2x2x2 m -> Vol=8, Area=4 -> h=2
        base_vol = 8.0
        area = 4.0
    else:
        # After July 2025: 6x4x4 m -> Vol=96, Area=16 -> h=6
        base_vol = 96.0
        area = 16.0

    # Tree Volume Correction
    tree_vol = row.get("tree_volume", 0.0)
    if pd.isna(tree_vol):
        tree_vol = 0.0

    net_vol = base_vol - tree_vol
    # Defensive check: volume cannot be too small
    net_vol = max(net_vol, 0.1)

    h_eff = net_vol / area

    # Air Density (mol/m3) = P / (RT)
    rho_air = P_std / (R * T_k)

    flux = row["flux_slope"] * rho_air * h_eff
    return flux


def calculate_h2o_absolute_flux(row):
    """
    Calculate absolute H2O flux (mmol m-2 s-1) from h2o_slope (mmol/mol/s).

    Uses the same chamber geometry and ideal gas law as calculate_absolute_flux.
    h2o_slope is d[H2O]/dt in mmol/mol/s (mixing ratio rate of change).
    Absolute flux = h2o_slope × rho_air × h_eff, giving mmol/(m2·s).
    """
    R = 8.314  # J/(mol K)
    P_std = 101325  # Pa

    if "mean_temp" in row and pd.notnull(row["mean_temp"]):
        T_c = row["mean_temp"]
    else:
        T_c = 25.0
    T_k = T_c + 273.15

    if "flux_date" not in row:
        return np.nan

    date = row["flux_date"]
    cutoff_date = pd.Timestamp("2025-07-01")

    if date < cutoff_date:
        base_vol = 8.0
        area = 4.0
    else:
        base_vol = 96.0
        area = 16.0

    tree_vol = row.get("tree_volume", 0.0)
    if pd.isna(tree_vol):
        tree_vol = 0.0

    net_vol = max(base_vol - tree_vol, 0.1)
    h_eff = net_vol / area

    rho_air = P_std / (R * T_k)  # mol/m³

    h2o_slope = row.get("h2o_slope", np.nan)
    if pd.isna(h2o_slope):
        return np.nan

    return h2o_slope * rho_air * h_eff


def calculate_flux_for_chamber(
    chamber_df, chamber_name, temp_col="Temp", min_points=5, min_r2=0.0, start_cutoff=50
):
    """
    Identifies cycles and calculates flux slope for a given chamber dataframe.
    Expects columns: 'TIMESTAMP', 'CO2', [temp_col], and optionally 'Flag'.

    Args:
        chamber_df (pd.DataFrame): Data for the chamber.
        chamber_name (str): Name of the chamber (for labeling).
        temp_col (str): Column name for temperature.
        min_points (int): Minimum measurements required to fit a slope.
        min_r2 (float): Minimum R-squared value to accept the flux calculation.
        start_cutoff (int): Number of seconds to ignore from the start of each cycle.
    """
    print(f"Calculating flux for {chamber_name}...")

    if chamber_df.empty:
        print(f"  -> Warning: Dataframe for {chamber_name} is empty.")
        return pd.DataFrame()

    results = []

    # Ensure sorted by time
    chamber_df = chamber_df.sort_values("TIMESTAMP").copy()

    # Calculate time gaps to identify cycles
    # A gap > 300 seconds (5 mins) indicates a new cycle
    chamber_df["delta_t_sec"] = chamber_df["TIMESTAMP"].diff().dt.total_seconds()
    chamber_df["new_cycle"] = (chamber_df["delta_t_sec"] > 300) | (chamber_df["delta_t_sec"].isna())
    chamber_df["cycle_id"] = chamber_df["new_cycle"].cumsum()

    total_cycles = chamber_df["cycle_id"].max()
    print(f"  -> Found {total_cycles} potential cycles")

    # Iterate through cycles
    for cycle_id, group in tqdm(chamber_df.groupby("cycle_id"), desc=f"Processing {chamber_name}"):
        start_time = group["TIMESTAMP"].min()
        seconds_from_start = (group["TIMESTAMP"] - start_time).dt.total_seconds().values
        co2_values = group["CO2"].values

        # Filter: ignore first `start_cutoff` seconds
        mask = seconds_from_start >= start_cutoff

        # Apply filter
        seconds_from_start = seconds_from_start[mask]
        co2_values = co2_values[mask]

        # Filter: minimum points required for regression (after cutoff)
        if len(seconds_from_start) < min_points:
            continue

        # Check for zero variance in time (shouldn't happen if diff > 0)
        if len(np.unique(seconds_from_start)) <= 1:
            continue

        # Linear Regression
        slope, intercept, r_value, p_value, std_err = linregress(seconds_from_start, co2_values)

        # Robustness check: R-squared
        r_squared = r_value**2
        if r_squared < min_r2:
            continue

        # Mean Temp for this cycle
        # Temp should probably be averaged over the valid period too, but using cycle mean is okay for now
        # Ideally we filter temp too, but usually temp is stable. Let's filter it for consistency if easy.
        # But we extracted values. Let's stick to group mean for now unless requested.
        # Actually, let's look at the original code:
        # mean_temp = group[temp_col].mean() if temp_col in group.columns else np.nan
        # It's safer to use the filtered group mean, but group is a dataframe.
        # To avoid complexity, we'll stick to full cycle mean for temp/QC or filter if critical.
        # Given flux slope is the main thing, and temp/QC usually cycle-level properties, full group mean is acceptable.

        mean_temp = group[temp_col].mean() if temp_col in group.columns else np.nan

        # Max QC Flag (worst quality in the cycle)
        max_flag = group["Flag"].max() if "Flag" in group.columns else 0

        results.append(
            {
                "Source_Chamber": chamber_name,
                "cycle_id": cycle_id,
                "flux_date": start_time,
                "flux_slope": slope,
                "r_squared": r_squared,
                "mean_temp": mean_temp,
                "qc_flag": max_flag,
                "n_points": len(seconds_from_start),
                # Update duration to reflect the max time used - min time used?
                # Or just the cycle duration?
                # Original: duration_sec = seconds_from_start.max()
                # We should probably keep original duration concept (how long the cycle was ON)
                # or effective duration. Let's keep the filtered max to avoid confusion on what data was used.
                "duration_sec": seconds_from_start.max() if len(seconds_from_start) > 0 else 0,
            }
        )

    if not results:
        print(f"  -> Warning: No valid flux cycles found for {chamber_name}.")
        return pd.DataFrame()

    flux_df = pd.DataFrame(results)

    # Calculate Absolute Flux
    flux_df["flux_absolute"] = flux_df.apply(calculate_absolute_flux, axis=1)

    return flux_df
